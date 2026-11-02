"""Invalid reveal plans fail before spatial search, independent of subject."""
import copy
import unittest
from unittest.mock import patch

import notebook_procedural as board
from notebook_semantic import compile_semantic, SemanticError


def example():
    return dict(kind='network',objects=[
        dict(id='a',shape='box',label='Input'),
        dict(id='b',shape='box',label='Output')],
        links=[dict(id='edge',**{'from':'a','to':'b'},label='Transforms')],
        steps=[dict(add=['a'],caption='Introduce an input.'),
               dict(add=['b'],caption='Introduce its output.'),
               dict(add=['edge'],caption='Connect the two objects.')],
        takeaway='The relationship connects the given objects.')


class NetworkPreflightTest(unittest.TestCase):
    def assert_early_failure(self,spec,message):
        original=copy.deepcopy(spec)
        with patch.object(board,'_object') as objects, \
                patch.object(board,'_route') as route, \
                patch.object(board,'_place_labels') as labels:
            with self.assertRaisesRegex(ValueError,message):board.compile_board(spec)
            objects.assert_not_called();route.assert_not_called();labels.assert_not_called()
        self.assertEqual(spec,original)

    def test_missing_relationship_does_not_enter_layout_search(self):
        spec=example()
        spec['objects'].append(dict(id='c',shape='box',label='Extra'))
        spec['steps'][2]['add']=['c']
        self.assert_early_failure(spec,'every declared object/connection')

    def test_duplicates_unknown_and_empty_reveals_fail_before_geometry(self):
        for ids in (['a'],['edge','edge'],['unknown'],[]):
            with self.subTest(ids=ids):
                spec=example();spec['steps'][2]['add']=ids
                self.assert_early_failure(spec,'exactly once|bounded object/connection IDs')

    def test_connection_cannot_appear_before_its_endpoints(self):
        spec=example();spec['steps'][0]['add']=['a','edge'];spec['steps'][2]['add']=['b']
        self.assert_early_failure(spec,'endpoints before or with')

    def test_all_graph_ids_are_unique_before_routing(self):
        for identity in ('a','edge'):
            spec=example();spec['links'].append(dict(spec['links'][0],id=identity))
            self.assert_early_failure(spec,'unique ID')

    def test_caption_and_label_markup_is_rejected_before_geometry(self):
        spec=example();spec['steps'][0]['caption']='**Input**'
        self.assert_early_failure(spec,'plain text')
        spec=example();spec['objects'][0]['label']='x'*25
        self.assert_early_failure(spec,'text')

    def test_same_step_endpoints_are_allowed_without_reordering(self):
        spec=example()
        spec['objects'].append(dict(id='c',shape='circle',label='Third'))
        spec['steps']=[dict(add=['a'],caption='First object.'),
                       dict(add=['b','edge'],caption='Second object and relationship.'),
                       dict(add=['c'],caption='Independent third object.')]
        original=copy.deepcopy(spec)
        self.assertEqual(set(board._network_preflight(spec)),{'a','b','c'})
        self.assertEqual(spec,original)

    def test_semantic_wrapper_reports_schema_not_layout_failure(self):
        source=example()
        source['objects'].append(dict(id='c',shape='box',label='Third'))
        source['steps'][2]['add']=['c']
        spec=dict(v=1,mode='lesson',intent='Explain a relationship',
            scene=dict(family='causal',
                objects=[dict(id=o['id'],component=o['shape'],label=o['label']) for o in source['objects']],
                relations=[dict(r,type='process') for r in source['links']]),
            steps=[dict(reveal=s['add'],caption=s['caption']) for s in source['steps']],
            claims=[],takeaway=source['takeaway'])
        with patch.object(board,'_place_labels') as labels:
            with self.assertRaises(SemanticError) as caught:compile_semantic(spec)
            self.assertEqual(caught.exception.code,'invalid_schema')
            labels.assert_not_called()


if __name__=='__main__':unittest.main()
