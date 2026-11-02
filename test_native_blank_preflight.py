import importlib.machinery
import importlib.util
import json
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from notebook_storyboard import integral_storyboard
from notebook_stroke_asset import storyboard_assets
from notebook_native_probe import NativeProbe


class NativeBlankPreflightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader('native_blank_preflight_server',
                    str(Path(__file__).with_name('herd-board-serve')))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.server = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.server)

    def sample(self):
        body = dict(doc='4ffe884f-a4d6-437d-8091-75bf63252c16',
                    page='9d8b4913-ac90-4f8f-b20d-abc165d779e5', surface='1793062625450-526481929',
                    source_doc='4a48e85d-40e3-437a-92c5-c411a8bff83e',
                    source_page='ef846d65-f19a-4870-af4e-f13435f7b5c1', expected_strokes=2)
        parent = '76ba516f-7dd9-4bf9-a109-0bf31b3c69d6'
        source = storyboard_assets(integral_storyboard())[0]['data']
        replies = [json.dumps(dict(parent=parent, visibleName='To pidog')).encode(),
                   json.dumps(dict(visibleName='Native clone tests (Codex)')).encode(),
                   json.dumps(dict(parent=parent, visibleName='Procedural stroke sources')).encode(),
                   source, b'']
        context = dict(body, fresh=True, active=True, ink_revision=0,
                       view=[1,0,0,1,-702,0], text_bounds=[-468,0,936,0])
        return body, context, replies

    def test_blank_fixture_accepts_generated_source_not_user_templates(self):
        body, context, replies = self.sample()
        with patch.object(self.server.device_context, 'snapshot', return_value=context), \
             patch.object(self.server, 'tablet', side_effect=replies), \
             patch.object(self.server, 'live_capture', return_value=Image.new('L',(1404,1872),255)):
            self.assertEqual(len(self.server.native_blank_preflight(body)), 64)

    def test_existing_visible_or_saved_content_is_rejected(self):
        for saved in (False, True):
            body, context, replies = self.sample()
            image = Image.new('L',(1404,1872),255)
            if saved:
                replies[-1] = replies[-2]  # actual native strokes in destination
            else:
                image.putpixel((300,400),0)
            with patch.object(self.server.device_context, 'snapshot', return_value=context), \
                 patch.object(self.server, 'tablet', side_effect=replies), \
                 patch.object(self.server, 'live_capture', return_value=image):
                with self.assertRaisesRegex(ValueError, 'content'):
                    self.server.native_blank_preflight(body)

    def test_wrong_folder_or_changed_view_fails_before_capture(self):
        body, context, replies = self.sample()
        replies[1] = json.dumps(dict(visibleName='Correspondence')).encode()
        with patch.object(self.server.device_context, 'snapshot', return_value=context), \
             patch.object(self.server, 'tablet', side_effect=replies), \
             patch.object(self.server, 'live_capture') as capture:
            with self.assertRaisesRegex(ValueError, 'isolated'):
                self.server.native_blank_preflight(body)
            capture.assert_not_called()
        with patch.object(self.server.device_context, 'snapshot', return_value=dict(context, ink_revision=1)), \
             patch.object(self.server, 'tablet') as tablet:
            with self.assertRaises(ValueError):
                self.server.native_blank_preflight(body)
            tablet.assert_not_called()

    def test_anchor_diagnostic_checks_private_source_and_unchanged_bytes(self):
        body, context, replies = self.sample()
        body.update(operation='text-anchor', expected_strokes=0)
        parent = '76ba516f-7dd9-4bf9-a109-0bf31b3c69d6'
        source = replies[3]
        reads = [json.dumps(dict(parent=parent)).encode(),
                 json.dumps(dict(visibleName='Storyboard tests (Codex)', type='CollectionType')).encode(), source]
        with patch.object(self.server, 'tablet', side_effect=reads) as remote:
            self.assertEqual(self.server.native_anchor_source_hash(body), hashlib.sha256(source).hexdigest())
            self.assertTrue(all(call.args[0].startswith(('cat ', 'dd if=')) for call in remote.call_args_list))
        for change in ({'source_page': '../page'}, {'source_doc': body['doc'], 'source_page': body['page']}):
            with patch.object(self.server, 'tablet') as remote:
                with self.assertRaises(ValueError):
                    self.server.native_anchor_source_hash(dict(body, **change))
                remote.assert_not_called()
        for invalid in (b'{}', json.dumps(dict(visibleName='James notes',type='CollectionType')).encode()):
            with patch.object(self.server, 'tablet', side_effect=[reads[0], invalid]):
                with self.assertRaises(ValueError):
                    self.server.native_anchor_source_hash(body)
        probe = NativeProbe()
        identity = probe.arm(body, context, hashlib.sha256(source).hexdigest())['id']
        report = dict(id=identity, state='text-anchor', view_active=True, page_ready=True,
                      controller=True, working=False, clone_selected=True, clone_value=False,
                      select_rect=True, select_area=False, select_all=False, selected=0, cloned=0,
                      text_anchor=[-464, 267.59375, 69.55, 23])
        with patch.object(self.server, 'native_probe', probe), \
             patch.object(self.server.device_context, 'snapshot', return_value=context):
            with patch.object(self.server, 'tablet', side_effect=reads[:2]+[source+b'changed']):
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    self.server.complete_native_probe(report)
            self.assertEqual(probe.snapshot()['state'], 'waiting')
            with patch.object(self.server, 'tablet', side_effect=reads):
                self.assertTrue(self.server.complete_native_probe(report)['accepted'])


if __name__ == '__main__':
    unittest.main()
