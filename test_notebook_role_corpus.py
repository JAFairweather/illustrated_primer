"""Input preparation tests only: no model quality or device claims."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from notebook_lesson_eval import QUESTIONS
from notebook_role_corpus import load_corpus, planner_input, prepare, question_png


class RoleCorpusTests(unittest.TestCase):
    def test_keeps_ten_original_questions_and_adds_hard_case(self):
        _, corpus = load_corpus()
        self.assertEqual([(q['id'], q['question']) for q in corpus['questions'][:-1]], QUESTIONS)
        self.assertEqual(corpus['questions'][-1]['id'], 'riemann-seven-eighths')
        self.assertEqual(len(corpus['questions']), 11)

    def test_model_inputs_do_not_leak_reviewer_checks(self):
        _, corpus = load_corpus()
        for row in corpus['questions']:
            row['review_checks'].append('REVIEW_ONLY_SENTINEL')
            row['expected_score'] = 'REVIEW_ONLY_SENTINEL'
            value = planner_input(corpus, row)
            self.assertNotIn('REVIEW_ONLY_SENTINEL', json.dumps(value))
            self.assertEqual(set(value['context']), {'question', 'audience', 'sources', 'source_policy'})
            self.assertEqual(value['context']['question'], row['question'])
        self.assertEqual(len(planner_input(corpus, corpus['questions'][-1])['context']['sources']), 4)

    def test_packet_hashes_identical_inputs_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as root:
            a, b = Path(root)/'a', Path(root)/'b'
            first, second = prepare(a), prepare(b)
            self.assertEqual(first, second)
            for row in first['questions']:
                for field in ('context', 'image'):
                    data = (a/row[field]).read_bytes()
                    self.assertEqual(data, (b/row[field]).read_bytes())
                    self.assertEqual(hashlib.sha256(data).hexdigest(), row[field+'_sha256'])
            with self.assertRaises(FileExistsError):
                prepare(a)
            self.assertEqual(first['model_calls'], 0)
            self.assertEqual(first['tablet_operations'], 0)

    def test_unknown_sources_fail_before_any_output(self):
        _, corpus = load_corpus()
        corpus['questions'][-1]['source_ids'].append('missing')
        with tempfile.TemporaryDirectory() as root:
            source, destination = Path(root)/'bad.json', Path(root)/'output'
            source.write_text(json.dumps(corpus))
            with self.assertRaisesRegex(ValueError, 'unknown source'):
                prepare(destination, corpus_path=source)
            self.assertFalse(destination.exists())

    def test_all_images_are_uncropped_native_resolution_typeset_inputs(self):
        from PIL import Image
        _, corpus = load_corpus()
        for row in corpus['questions']:
            image = Image.open(BytesIO(question_png(row['question'])))
            self.assertEqual(image.size, (960, 720))
        with self.assertRaisesRegex(ValueError, 'never silently clip'):
            question_png('x' * 2000)

    def test_rubric_does_not_count_missing_picture_evidence_as_success(self):
        _, corpus = load_corpus()
        self.assertEqual(len(corpus['rubric']['story']), 4)
        self.assertEqual(len(corpus['rubric']['picture']), 4)
        self.assertIn('unreviewed', corpus['rubric']['gate'])
        self.assertIn('actual stage previews', corpus['rubric']['evidence'])


if __name__ == '__main__':
    unittest.main()
