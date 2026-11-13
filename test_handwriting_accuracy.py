"""Synthetic B3 scoring controls; no tablet text or images live here."""
import unittest

from handwriting_accuracy import distance, normalize, score


HASH = 'a' * 64


def ref(page, text):
    return {'page': page, 'image_sha256': HASH, 'text': text}


def out(page, model, text=None, error=None):
    row = {'page': page, 'image_sha256': HASH, 'model': model}
    row['text' if error is None else 'error'] = text if error is None else error
    return row


class HandwritingAccuracyTests(unittest.TestCase):
    def test_edit_controls_and_normalization(self):
        self.assertEqual(distance('cat', 'cut'), 1)  # substitution
        self.assertEqual(distance('cat', 'cart'), 1)  # insertion
        self.assertEqual(distance('cart', 'cat'), 1)  # deletion
        self.assertEqual(distance('', 'cat'), 3)
        self.assertEqual(normalize('Cafe\u0301\n  now'), 'Café now')

    def test_micro_average_and_missing_are_explicit(self):
        result = score([ref('p1', 'red cat'), ref('p2', 'blue bird')], [
            out('p1', 'gemini-3.5-flash-lite', 'red bat'),
            out('p2', 'gemini-3.5-flash-lite', 'blue bird'),
            out('p1', 'gpt-5.6-luna', error='timeout'),
        ], ('gemini-3.5-flash-lite', 'gpt-5.6-luna'))
        gemini = result['models']['gemini-3.5-flash-lite']
        self.assertEqual((gemini['char_edits'], gemini['ref_chars']), (1, 16))
        self.assertEqual((gemini['word_edits'], gemini['ref_words']), (1, 4))
        self.assertAlmostEqual(gemini['cer'], 1/16)
        self.assertAlmostEqual(gemini['wer'], 1/4)
        luna = result['models']['gpt-5.6-luna']
        self.assertEqual((luna['scored'], luna['errors'], luna['missing']), (0, 1, 1))
        self.assertIsNone(luna['cer'])

    def test_refuses_mismatched_image_and_duplicate(self):
        wrong = out('p1', 'gpt-5.6-luna', 'hello')
        wrong['image_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'mismatched input'):
            score([ref('p1', 'hello')], [wrong], ('gpt-5.6-luna',))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            score([ref('p1', 'hello')], [out('p1', 'gpt-5.6-luna', 'hello')] * 2,
                  ('gpt-5.6-luna',))

    def test_complete_gate_and_empty_reference(self):
        with self.assertRaisesRegex(ValueError, '100 reference'):
            score([ref('p1', 'hello')], [], ('gpt-5.6-luna',), True)
        with self.assertRaisesRegex(ValueError, 'blank reference'):
            score([ref('p1', '  ')], [], ('gpt-5.6-luna',))
        with self.assertRaisesRegex(ValueError, 'uncertain reference'):
            score([ref('p1', 'one [unclear] two')], [], ('gpt-5.6-luna',))

    def test_complete_gate_requires_baseline_and_pi_comparator(self):
        references = [ref(f'p{i}', 'hello') for i in range(100)]
        gemini_outputs = [out(f'p{i}', 'gemini-3.5-flash-lite', 'hello')
                          for i in range(100)]
        with self.assertRaisesRegex(ValueError, 'baseline and Pi comparator'):
            score(references, gemini_outputs, ('gemini-3.5-flash-lite',), True)
        with self.assertRaisesRegex(ValueError, 'baseline and Pi comparator'):
            score(references, [out(f'p{i}', 'gpt-5.6-luna', 'hello')
                               for i in range(100)], ('gpt-5.6-luna',), True)

        complete = score(references, gemini_outputs + [
            out(f'p{i}', 'gpt-5.6-luna', 'hello') for i in range(100)
        ], ('gemini-3.5-flash-lite', 'gpt-5.6-luna'), True)
        self.assertEqual(complete['models']['gpt-5.6-luna']['missing'], 0)


if __name__ == '__main__':
    unittest.main()
