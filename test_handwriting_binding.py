"""Stand-in controls for manifest, byte, replacement and receipt binding."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from handwriting_binding import verify
from handwriting_sample import select


MODELS = ('gemini-3.5-flash-lite', 'gpt-5.6-luna')


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        candidates = []
        self.bytes = {}
        for i in range(120):
            page = f'p{i:03}'
            payload = b'\x89PNG\r\n\x1a\n' + page.encode()
            self.bytes[page] = payload
            candidates.append({'page': page, 'image_sha256': hashlib.sha256(payload).hexdigest(),
                               'notebook': 'synthetic', 'eligible': True})
        self.manifest = select(candidates, 'stand-in-seed')
        self.selected = [row['page'] for row in self.manifest['sample']]
        self.images = {}
        for page in self.selected:
            path = self.root / f'{page}.png'
            path.write_bytes(self.bytes[page])
            self.images[page] = path
        frozen = {row['page']: row['image_sha256'] for row in candidates}
        self.refs = [{'page': page, 'image_sha256': frozen[page], 'text': 'a question'}
                     for page in self.selected]
        self.outs = [{'page': page, 'image_sha256': frozen[page], 'model': model,
                      'text': 'a question'} for page in self.selected for model in MODELS]
        self.config = {'prompt_sha256': 'a' * 64,
                       'models': {model: hashlib.sha256(model.encode()).hexdigest()
                                  for model in MODELS}}
        self.receipts = self.make_receipts(self.outs)

    def make_receipts(self, outputs):
        return [{'page': row['page'], 'image_sha256': row['image_sha256'],
                 'model': row['model'], 'prompt_sha256': self.config['prompt_sha256'],
                 'config_sha256': self.config['models'][row['model']],
                 'output_sha256': hashlib.sha256(json.dumps(
                     row, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False).encode()).hexdigest()} for row in outputs]

    def check(self, replacements=()):
        return verify(self.manifest, self.images, self.refs, self.outs, MODELS,
                      self.config, self.receipts, replacements)

    def test_complete_stand_in_run_and_mutated_png(self):
        self.assertEqual(self.check()['pages'], 100)
        page = self.selected[0]
        self.images[page].write_bytes(self.bytes[page] + b'changed')
        with self.assertRaisesRegex(ValueError, 'PNG bytes differ'):
            self.check()

    def test_private_cli_one_run_and_mutated_byte(self):
        manifest_path = self.root / 'sample.json'
        refs_path = self.root / 'references.jsonl'
        outs_path = self.root / 'outputs.jsonl'
        config_path = self.root / 'config.json'
        receipts_path = self.root / 'receipts.jsonl'
        images_dir = self.root / 'images'
        images_dir.mkdir()
        for page, path in self.images.items():
            path.replace(images_dir / f'{page}.png')
        manifest_path.write_text(json.dumps(self.manifest))
        config_path.write_text(json.dumps(self.config))
        for path, rows in ((refs_path, self.refs), (outs_path, self.outs),
                           (receipts_path, self.receipts)):
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        command = [sys.executable, str(Path(__file__).with_name('handwriting_binding.py')),
                   '--manifest', str(manifest_path), '--images', str(images_dir),
                   '--references', str(refs_path), '--outputs', str(outs_path),
                   '--run-config', str(config_path), '--receipts', str(receipts_path)]
        for model in MODELS:
            command.extend(['--model', model])
        good = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)['pages'], 100)
        first = images_dir / f'{self.selected[0]}.png'
        first.write_bytes(first.read_bytes() + b'changed')
        bad = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(bad.stdout, '')
        self.assertIn('private input rejected', bad.stderr)
        self.assertNotIn(self.selected[0], bad.stderr)

    def test_declared_hash_and_receipt_mutations(self):
        self.refs[0]['image_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'scored row differs'):
            self.check()
        self.refs[0]['image_sha256'] = self.outs[0]['image_sha256']
        self.receipts[0]['prompt_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'adapter receipt differs'):
            self.check()

    def test_replacement_requires_next_ranked_reserve(self):
        excluded = self.selected[0]
        reserve = self.manifest['reserves'][0]['page']
        with self.assertRaisesRegex(ValueError, 'rank order'):
            self.check([{'excluded_page': excluded, 'reserve_page':
                         self.manifest['reserves'][1]['page'], 'reason': 'unclear'}])
        self.images.pop(excluded).unlink()
        path = self.root / f'{reserve}.png'
        path.write_bytes(self.bytes[reserve])
        self.images[reserve] = path
        self.refs = [row for row in self.refs if row['page'] != excluded]
        self.refs.append({'page': reserve, 'image_sha256': self.manifest['reserves'][0]['image_sha256'],
                          'text': 'a question'})
        self.outs = [row for row in self.outs if row['page'] != excluded]
        self.outs.extend({'page': reserve,
                          'image_sha256': self.manifest['reserves'][0]['image_sha256'],
                          'model': model, 'text': 'a question'} for model in MODELS)
        self.receipts = self.make_receipts(self.outs)
        self.assertEqual(self.check([{'excluded_page': excluded, 'reserve_page': reserve,
                                      'reason': 'unclear'}])['pages'], 100)

    def test_frozen_sample_order_cannot_be_rewritten(self):
        self.manifest['reserves'][0], self.manifest['reserves'][1] = (
            self.manifest['reserves'][1], self.manifest['reserves'][0])
        with self.assertRaisesRegex(ValueError, 'sample/reserve order'):
            self.check()


if __name__ == '__main__':
    unittest.main()
