"""Role separation tests with fake answers, never model-quality evidence."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from notebook_model_transport import ModelTransportError
from notebook_panel_examples import graph_reuse_example
from notebook_role_eval import generate, critique, parse_review, invoke
from notebook_role_prompts import role_prompt, STORY_DIMENSIONS, PICTURE_DIMENSIONS


class RoleEvalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.story, self.shapes = graph_reuse_example()
        self.packet = {'task': 'story', 'context': {'question': self.story['question'], 'sources': []}}
        self.configs = {role: {'endpoint': f'/unused/{role}/notebook-eval.sock', 'expected': {
            'role': role, 'harness': 'pi', 'provider': 'openai-codex', 'model': f'fixture-{role}',
            'reasoning_requested': 'high' if role == 'planner' else 'medium',
            'requested_output_tokens': 4096, 'prompt_sha256': hashlib.sha256(role_prompt(role).encode()).hexdigest()}}
            for role in ('planner', 'drawer', 'critic')}
        output = BytesIO()
        Image.new('RGB', (16,16), 'white').save(output, 'PNG')
        self.png = output.getvalue()
        self.sent = []
        self.review = {'v': 1, 'mode': 'lesson-review', 'critical_issues': []}
        for category, dims in [('story', STORY_DIMENSIONS), ('picture', PICTURE_DIMENSIONS)]:
            self.review[category] = {key: {'score': 3, 'panel': 'axes',
                                          'evidence': 'Authored fake review for contract testing.'} for key in dims}
        self.outputs = {'planner': self.story,
                        'drawer': {'v': 1, 'mode': 'story-shapes', 'panels': self.shapes},
                        'critic': self.review}
        self.time = 0

    def call(self, endpoint, identity, png, context, *, expected, deadline_ms, observe_response):
        role = expected['role']
        self.sent.append({'role': role, 'packet': json.loads(context), 'image': png,
                          'expected': expected, 'deadline_ms': deadline_ms})
        self.time += .1
        reply = {'request_id': identity, 'response_format': 'role-eval-v1',
                 'evaluation': {k: expected[k] for k in ('role', 'harness', 'prompt_sha256')},
                 'text': json.dumps(self.outputs[role]),
                 'metrics': {k: expected[k] for k in ('provider', 'model', 'reasoning_requested', 'requested_output_tokens')}}
        reply['metrics'].update(elapsed_ms=100, first_text_ms=10, usage={'input': 100, 'output': 100})
        observe_response(json.dumps(reply).encode())
        return reply

    def run_case(self, **kwargs):
        return generate(self.packet, self.png, {k: self.configs[k] for k in ('planner', 'drawer')},
                        self.root/'run', call=kwargs.pop('call', self.call),
                        clock=lambda: self.time, **kwargs)

    def test_two_calls_independent_models_no_story_rewrite_and_real_previews(self):
        result = self.run_case()
        self.assertTrue(result['valid'], result)
        self.assertTrue(result['native_preparation_valid'])
        self.assertEqual(result['attempts'], 2)
        self.assertEqual([c['role'] for c in self.sent], ['planner', 'drawer'])
        self.assertEqual(self.sent[1]['packet'], {'task': 'draw', 'context': {'story': self.story}})
        self.assertEqual(result['quality_status'], 'unreviewed')
        self.assertFalse(result['tablet_proven'])
        self.assertEqual(len(list((self.root/'run/preview').glob('*.png'))), 4)
        self.assertFalse(list(self.root.rglob('*.rm')))
        self.assertEqual(result['preparation_ms'], 200)
        self.assertEqual(result['deadline_per_call_ms'], 30000)

    def test_invalid_second_config_prevents_first_call(self):
        self.configs['drawer']['expected']['prompt_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'fixed prompt'):
            self.run_case()
        self.assertEqual(self.sent, [])
        self.assertFalse((self.root/'run').exists())

    def test_unavailable_plan_is_retained_without_drawing(self):
        self.outputs['planner'] = {'v':1, 'mode':'unavailable', 'reason':'Please supply the theorem statement.'}
        result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertEqual(result['attempts'], 1)
        self.assertIn('theorem', result['unavailable'])
        self.assertTrue((self.root/'run/planner/response.txt').exists())

    def test_changed_question_prevents_drawing(self):
        self.story['question'] = 'Different question'
        result = self.run_case()
        self.assertEqual(result['failed_phase'], 'planner')
        self.assertEqual(result['attempts'], 1)

    def test_drawer_cannot_replace_story_or_omit_last_panel(self):
        self.outputs['drawer']['story'] = self.story
        result = self.run_case()
        self.assertEqual(result['failed_phase'], 'drawer')
        self.assertFalse((self.root/'run/preview').exists())

    def test_late_geometry_failure_prevents_any_preview(self):
        del self.shapes['branch']
        result = self.run_case()
        self.assertEqual(result['failed_phase'], 'native-preparation')
        self.assertFalse(result['native_preparation_valid'])
        self.assertFalse((self.root/'run/preview').exists())
        self.assertTrue((self.root/'run/drawer/response.txt').exists())

    def test_transport_timeout_stops_without_retry(self):
        def timeout(*args, **kwargs):
            raise ModelTransportError('deadline')
        result = self.run_case(call=timeout)
        self.assertEqual(result['transport_error'], 'deadline')
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(result['retries'], 0)
        self.assertFalse((self.root/'run/drawer').exists())

    def test_wrong_reported_model_rejected_even_with_injected_call(self):
        def wrong(*args, **kwargs):
            result = self.call(*args, **kwargs)
            result['metrics']['model'] = 'unexpected'
            return result
        result = self.run_case(call=wrong)
        self.assertEqual(result['transport_error'], 'candidate_mismatch')
        self.assertEqual(result['attempts'], 1)

    def test_critic_sees_actual_previews_not_model_identity_or_timing(self):
        self.assertTrue(self.run_case()['valid'])
        reviewed = critique(self.story, [], self.root/'run/preview', self.configs['critic'],
                            self.root/'critique', call=self.call, clock=lambda: self.time)
        self.assertEqual(reviewed, self.review)
        sent = self.sent[-1]
        self.assertEqual(sent['role'], 'critic')
        self.assertEqual(sent['packet']['context']['preview_panel_ids'], ['axes','curve','mark','branch'])
        self.assertNotEqual(sent['image'], self.png)
        self.assertNotIn('fixture-planner', json.dumps(sent['packet']))
        self.assertNotIn('metrics', json.dumps(sent['packet']))
        record = json.loads((self.root/'critique/review.json').read_text())
        self.assertFalse(record['critic_calibrated'])
        self.assertFalse(record['human_reviewed'])

    def test_review_scores_require_evidence_exact_dimensions_and_valid_panels(self):
        for key, bad in [('score',True),('score',5),('score',2.5),('panel','missing'),('evidence','')]:
            value = deepcopy(self.review)
            value['picture']['visible_argument'][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                parse_review(json.dumps(value), self.story)
        value = deepcopy(self.review)
        value['picture']['visible_argument']['score'] = None
        self.assertIsNone(parse_review(json.dumps(value), self.story)['picture']['visible_argument']['score'])

    def test_duplicate_json_keys_rejected(self):
        raw = json.dumps(self.review).replace('"v": 1', '"v": 1, "v": 1')
        with self.assertRaises(ValueError):
            parse_review(raw, self.story)

    def test_invalid_critic_output_is_retained_not_repaired(self):
        self.assertTrue(self.run_case()['valid'])
        self.review['picture']['visible_argument']['score'] = 99
        with self.assertRaises(ValueError):
            critique(self.story, [], self.root/'run/preview', self.configs['critic'],
                     self.root/'critique', call=self.call, clock=lambda: self.time)
        record = json.loads((self.root/'critique/review.json').read_text())
        self.assertFalse(record['valid'])
        self.assertTrue((self.root/'critique/response.txt').exists())
        self.assertEqual(len(self.sent), 3)

    def test_fixed_prompts_keep_roles_separate(self):
        planner = role_prompt('planner')
        self.assertNotIn('coefficients:', planner)
        self.assertNotIn('PANEL_MAP', planner)
        self.assertIn('3-8', planner)
        self.assertIn('Do not return or rewrite the story', role_prompt('drawer'))
        self.assertIn('null, not zero or a pass', role_prompt('critic'))


if __name__ == '__main__':
    unittest.main()
