import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from notebook_semantic_prompt import semantic_reply_instructions
from notebook_teaching_prompt import CONTRACT_MARKER, TEACHING_PREAMBLE, teaching_variant, main


class TeachingPromptTests(unittest.TestCase):
    def test_preserves_entire_rendering_contract_and_worked_examples(self):
        original=semantic_reply_instructions()
        candidate=teaching_variant(original)
        self.assertEqual(original.split(CONTRACT_MARKER)[1],candidate.split(CONTRACT_MARKER)[1])
        self.assertNotEqual(original,candidate)
        self.assertEqual(candidate,teaching_variant(original))
        self.assertEqual(candidate.count(CONTRACT_MARKER),1)

    def test_retains_single_response_and_existing_modes(self):
        self.assertIn('NO additional planning or review fields',TEACHING_PREAMBLE)
        for mode in ('lesson','answer','clarify'):
            self.assertIn('"mode":"'+mode+'"',TEACHING_PREAMBLE)
        self.assertIn('caption is read BEFORE',TEACHING_PREAMBLE)
        self.assertIn('exactly\nonce',TEACHING_PREAMBLE)
        self.assertIn('simple request to draw',TEACHING_PREAMBLE)

    def test_focuses_on_evidence_not_topic_templates(self):
        for phrase in ('shared scale','actual dependencies','finite example',
                       'short captions','supplied\n  sources','not instructions'):
            self.assertIn(phrase,TEACHING_PREAMBLE)
        for topic in ('Kakeya','Langlands','hat tile','Bayes','transistor'):
            self.assertNotIn(topic,TEACHING_PREAMBLE)

    def test_invalid_base_is_rejected(self):
        valid='Preamble\n'+CONTRACT_MARKER+'Contract'
        for value in (None,b'bytes','',valid+'\0',valid+CONTRACT_MARKER,
                      CONTRACT_MARKER+'Contract','Preamble'+CONTRACT_MARKER,
                      valid+'x'*64000,'\ud800'+valid):
            with self.subTest(value=repr(value)[:60]),self.assertRaises(ValueError):
                teaching_variant(value)

    def test_candidate_bound_is_checked_after_replacement(self):
        oversized_candidate='x'+CONTRACT_MARKER+'y'*62000
        self.assertLess(len(oversized_candidate.encode()),64000)
        with self.assertRaisesRegex(ValueError,'candidate prompt exceeds'):
            teaching_variant(oversized_candidate)

    def test_cli_preserves_base_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'base.txt';dest=Path(tmp)/'candidate.txt'
            before=semantic_reply_instructions().encode()
            base.write_bytes(before)
            with patch('sys.argv',['prompt',str(base),str(dest)]):main()
            self.assertEqual(base.read_bytes(),before)
            saved=dest.read_bytes()
            self.assertEqual(saved,teaching_variant(before.decode()).encode())
            self.assertEqual(dest.stat().st_mode & 0o777,0o600)
            for target in (base,dest):
                with patch('sys.argv',['prompt',str(base),str(target)]),self.assertRaises(FileExistsError):main()
            self.assertEqual(base.read_bytes(),before)
            self.assertEqual(dest.read_bytes(),saved)

    def test_cli_checks_input_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'base.txt';dest=Path(tmp)/'candidate.txt'
            for raw in (b'wrong contract',b'\xff',b'x'*64001):
                base.write_bytes(raw)
                with patch('sys.argv',['prompt',str(base),str(dest)]),self.assertRaises(ValueError):main()
                self.assertFalse(dest.exists())


if __name__=='__main__':unittest.main()
