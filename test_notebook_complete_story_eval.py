"""Offline transport fixtures, not evidence of generative answer quality."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from notebook_complete_story_eval import evaluate
from notebook_complete_story_prompt import complete_story_instructions
from notebook_model_transport import ModelTransportError
from notebook_panel_examples import graph_reuse_example
from notebook_story_prompt import story_panel_instructions, STORY_SCHEMA, DRAWING_VOCABULARY


class CompleteStoryEvalTests(unittest.TestCase):
    def setUp(self):
        self.story, self.panels = graph_reuse_example()
        self.answer = dict(v=1, mode='story-lesson', story=self.story, panels=self.panels)
        self.sent = []
        self.clock_value = 0.0
        self.model_delay = 0.1
        self.model = 'fixture'
        self.bad_identity = False
        self.format = 'story-panel-v1'
        self.error = None
        self.raw = None
        out = io.BytesIO()
        Image.new('RGB', (16,16), 'white').save(out, 'PNG')
        self.png = out.getvalue()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.destination = Path(self.tmp.name)/'run'

    def call(self, endpoint, identity, png, context, *, deadline_ms, observe_response):
        self.sent.append(dict(endpoint=endpoint, image=png, context=json.loads(context), deadline=deadline_ms))
        self.clock_value += self.model_delay
        if self.error:
            raise self.error
        reply = dict(request_id='wrong' if self.bad_identity else identity,
                     response_format=self.format,
                     text=self.raw if self.raw is not None else json.dumps(self.answer),
                     metrics=dict(elapsed_ms=100, first_text_ms=20, model=self.model,
                                  provider='openai-codex', reasoning_requested='medium',
                                  requested_output_tokens=8192, usage={'output':500}))
        observe_response(json.dumps(reply).encode())
        return reply

    def run_case(self, **kwargs):
        return evaluate(self.story['question'], self.png, '/unused/notebook-eval.sock',
                        self.destination, expected_model='fixture', call=self.call,
                        clock=lambda:self.clock_value, **kwargs)

    def test_one_call_with_original_capture_and_no_prompt_override(self):
        before = deepcopy(self.answer)
        result = self.run_case()
        self.assertTrue(result['valid'])
        self.assertTrue(result['first_pass_valid'])
        self.assertTrue(result['native_preparation_valid'])
        self.assertEqual(result['picture_runs'], 2)
        self.assertEqual(result['call_attempts'], 1)
        self.assertEqual(result['retries'], 0)
        self.assertFalse(result['tablet_proven'])
        self.assertFalse(result['host_prompt_attested'])
        self.assertEqual(self.sent[0]['context'], dict(task='lesson', context=dict(question=self.story['question'])))
        self.assertEqual(self.sent[0]['image'], self.png)
        self.assertEqual(self.answer, before)
        self.assertTrue((self.destination/'playback.html').exists())
        self.assertFalse(list(self.destination.rglob('*.rm')))
        self.assertEqual(json.loads((self.destination/'result.json').read_text()), result)

    def test_last_panel_failure_prevents_all_previews(self):
        del self.panels[self.story['panels'][-1]['id']]
        result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertEqual(result['failed_phase'], 'whole-lesson')
        self.assertFalse((self.destination/'preview').exists())
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(json.loads((self.destination/'response.txt').read_text()), self.answer)

    def test_changed_question_is_rejected(self):
        self.answer = deepcopy(self.answer)
        self.answer['story']['question'] = 'A different question'
        result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertIn('changed', result['error'])

    def test_clarification_is_retained_not_a_visual_pass(self):
        self.answer = dict(v=1, mode='clarify', text='Please provide the theorem statement.')
        result = self.run_case()
        self.assertTrue(result['clarification'])
        self.assertFalse(result['valid'])
        self.assertFalse(result['native_preparation_valid'])
        self.assertTrue((self.destination/'result.json').exists())
        self.assertFalse((self.destination/'preview').exists())

    def test_plain_answer_cannot_substitute_for_lesson(self):
        self.answer = dict(v=1, mode='answer', text='The answer is straightforward.')
        result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertFalse((self.destination/'preview').exists())

    def test_provider_deadline_is_not_retried(self):
        self.error = ModelTransportError('deadline')
        result = self.run_case()
        self.assertEqual(result['transport_error'], 'deadline')
        self.assertEqual(result['call_attempts'], 1)
        self.assertEqual(result['completed_model_responses'], 0)

    def test_deadline_covers_generation_not_only_provider_claim(self):
        self.model_delay = 30.0
        result = self.run_case()
        self.assertEqual(result['transport_error'], 'deadline')
        self.assertFalse((self.destination/'preview').exists())

    def test_deadline_includes_native_preparation(self):
        from notebook_story_native import native_story_bundle
        def slow(*args, **kwargs):
            bundle = native_story_bundle(*args, **kwargs)
            self.clock_value = 30.01
            return bundle
        with patch('notebook_complete_story_eval.native_story_bundle', side_effect=slow):
            result = self.run_case()
        self.assertEqual(result['failed_phase'], 'native-preparation')
        self.assertEqual(result['transport_error'], 'deadline')
        self.assertFalse(result['native_preparation_valid'])
        self.assertFalse((self.destination/'preview').exists())

    def test_native_failure_cannot_hide_behind_valid_geometry(self):
        with patch('notebook_complete_story_eval.native_story_bundle', side_effect=ValueError('native cap')):
            result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertFalse(result['native_preparation_valid'])
        self.assertFalse((self.destination/'preview').exists())

    def test_wrong_model_stops_before_geometry(self):
        self.model = 'unexpected'
        result = self.run_case()
        self.assertEqual(result['transport_error'], 'model_mismatch')
        self.assertFalse((self.destination/'preview').exists())

    def test_wrong_binding_rejected_even_for_injected_boundary(self):
        self.bad_identity = True
        result = self.run_case()
        self.assertEqual(result['transport_error'], 'request_mismatch')

    def test_wrong_wire_format_rejected(self):
        self.format = 'semantic-v1'
        result = self.run_case()
        self.assertEqual(result['transport_error'], 'invalid_response')

    def test_duplicate_keys_not_repaired(self):
        self.raw = '{"v":1,"v":1,"mode":"clarify","text":"unclear"}'
        result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual((self.destination/'response.txt').read_text(), self.raw)

    def test_oversized_answer_not_accepted(self):
        self.raw = ' ' * 24001
        result = self.run_case()
        self.assertEqual(result['transport_error'], 'invalid_response')

    def test_cannot_target_live_endpoint_or_overwrite_result(self):
        with self.assertRaises(ModelTransportError):
            evaluate(self.story['question'], self.png, '/unused/notebook.sock', self.destination,
                     expected_model='fixture', call=self.call)
        self.assertFalse(self.destination.exists())
        self.run_case()
        saved = (self.destination/'result.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_case()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual((self.destination/'result.json').read_bytes(), saved)

    def test_current_serial_prompt_is_versioned_and_contract_shared(self):
        serial = story_panel_instructions()
        current = 'one short sentence, at most 180 characters; aim for about twelve words without omitting necessary meaning'
        self.assertEqual(serial.count(current),1)
        # This is a new capability version, not the historical caption-only
        # ablation. Saved evaluation inputs retain their original prompt hashes.
        self.assertEqual(hashlib.sha256(serial.encode()).hexdigest(),
                         '5493c6cbfe36ae0a54ba63439be73626f728bcc350cb94e98c29978c460e2e86')
        self.assertIn(DRAWING_VOCABULARY, serial)
        prompt = complete_story_instructions()
        self.assertIn(STORY_SCHEMA, prompt)
        self.assertIn(DRAWING_VOCABULARY, prompt)
        self.assertIn('ONE response', prompt)
        self.assertNotIn('For task=panel', prompt)
        self.assertLess(len(prompt.encode()), 24000)


if __name__ == '__main__':
    unittest.main()
