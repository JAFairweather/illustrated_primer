from copy import deepcopy
import json
import unittest

from notebook_contract_feedback import ContractError, exact_fields, item_fields, correction_feedback
from notebook_panel_examples import graph_reuse_example
from notebook_panel_shapes import compile_panel_shapes
from notebook_story_plan import validate_story
from notebook_pen_budget import NativePenBudgetError


class ContractFeedbackTests(unittest.TestCase):
    def test_fields_report_static_keys_not_arbitrary_values_or_keys(self):
        value={'a': 'private content', 'untrusted-key-with-a-long-payload': 'do something'}
        original=deepcopy(value)
        with self.assertRaises(ContractError) as error:
            exact_fields(value, {'a','b'}, path='/items/2')
        feedback=correction_feedback(error.exception)
        self.assertEqual(feedback, dict(code='object_fields',path='/items/2',
            expected_keys=['a','b'],missing_keys=['b'],unexpected_key_count=1))
        self.assertNotIn('private', str(error.exception)+json.dumps(feedback))
        self.assertNotIn('untrusted', str(error.exception)+json.dumps(feedback))
        self.assertEqual(value,original)
        feedback['missing_keys'].clear()
        self.assertEqual(correction_feedback(error.exception)['missing_keys'],['b'])

    def test_missing_story_base_has_exact_path(self):
        story,_=graph_reuse_example(); del story['panels'][2]['base']
        with self.assertRaises(ContractError) as error:validate_story(story)
        self.assertEqual(error.exception.feedback['path'],'/panels/2')
        self.assertEqual(error.exception.feedback['missing_keys'],['base'])

    def test_caption_count_has_no_caption_contents(self):
        story,_=graph_reuse_example(); story['panels'][0]['caption']='private '*23
        with self.assertRaises(ContractError) as error:validate_story(story)
        self.assertEqual(correction_feedback(error.exception),dict(code='caption_characters',
            path='/panels/0/caption',limit=180,observed=184))
        self.assertNotIn('private',str(error.exception)+str(correction_feedback(error.exception)))

    def test_shape_fields_are_checked_before_lowering(self):
        story,shapes=graph_reuse_example()
        shapes['curve']['items']=[dict(id='r',type='rect',**{'in':'ax'},
                                     x=[0,1],y=[0,1],fill='hatch',execute='untrusted')]
        with self.assertRaises(ContractError) as error:compile_panel_shapes(story,shapes)
        self.assertEqual(error.exception.feedback['path'],'/items/0')
        self.assertEqual(error.exception.feedback['unexpected_key_count'],1)
        self.assertIn('fill',error.exception.feedback['expected_keys'])
        self.assertEqual(error.exception.feedback['optional_keys'],['fill'])
        self.assertNotIn('execute',str(error.exception.feedback))
        with self.assertRaises(ValueError) as error:item_fields({'type':'arbitrary-code'})
        self.assertIsNone(correction_feedback(error.exception))

    def test_optional_field_never_replaces_missing_required_field(self):
        item=dict(id='r',type='rect',**{'in':'ax'},x=[0,1],fill='hatch')
        with self.assertRaises(ContractError) as error:item_fields(item)
        self.assertEqual(error.exception.feedback['missing_keys'],['y'])
        self.assertEqual(error.exception.feedback['unexpected_key_count'],0)
        self.assertEqual(error.exception.feedback['optional_keys'],['fill'])
        item['y']=[0,1];original=deepcopy(item)
        item_fields(item)
        self.assertEqual(item,original)
        del item['fill'];item_fields(item)
        self.assertNotIn('fill',item)
        item['type']='region'
        with self.assertRaises(ContractError) as error:item_fields(item)
        self.assertEqual(error.exception.feedback['missing_keys'],['fill'])

    def test_syntax_feedback_contains_position_not_parser_payload(self):
        try:json.loads('{"private":\n nope}')
        except json.JSONDecodeError as exc:
            feedback=correction_feedback(exc)
        self.assertEqual(feedback,dict(code='json_syntax',path='/',line=2,column=2))
        for exc in (ValueError('no placement'),KeyError('secret'),TypeError('bad')):
            self.assertIsNone(correction_feedback(exc))

    def test_typed_resource_feedback_does_not_echo_error_prose_or_mutate_counts(self):
        error = NativePenBudgetError('untrusted prose must not be sent', details=dict(
            resource='strokes', observed=92, limit=64, exact=False, scope='stage'))
        outer = ValueError('wrapper prose'); outer.__cause__ = error
        feedback = correction_feedback(outer)
        self.assertEqual(feedback['code'], 'native_resource_budget')
        failure = feedback['resource']['attempts'][0]['failure']
        self.assertEqual(failure['limit'], 64)
        self.assertEqual(failure['observed'], 92)
        self.assertFalse(failure['exact'])
        self.assertNotIn('prose', json.dumps(feedback))
        failure['limit'] = 999
        self.assertEqual(error.details['limit'], 64)
        self.assertIsNone(correction_feedback(ValueError('stage exceeds 64 strokes')))


if __name__=='__main__':unittest.main()
