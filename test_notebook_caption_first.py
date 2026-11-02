import copy
import json
import unittest
from notebook_semantic import compile_semantic, SemanticError
from notebook_semantic_examples import examples
from notebook_lesson_native import native_semantic_bundle


class CaptionFirstTests(unittest.TestCase):
    def test_upper_and_lower_dividers_have_separate_cues(self):
        spec=examples()['fractions-variant']
        bundle=native_semantic_bundle(json.dumps(spec),playback=True,pen_equations=True)
        self.assertEqual(bundle['blocks'][0]['text'],'')
        for index,step in enumerate(spec['steps']):
            caption,ink=bundle['blocks'][1+index*2:3+index*2]
            self.assertEqual(caption['kind'],'text')
            self.assertEqual(caption['text'],step['caption'])
            self.assertEqual(ink['kind'],'ink')
        upper=bundle['blocks'][4]; lower=bundle['blocks'][6]
        self.assertEqual(upper['stroke_count'],2)
        self.assertEqual(lower['stroke_count'],4)
        self.assertLess(upper['bounds'][3],lower['bounds'][1])
        self.assertEqual(len({b['scene'] for b in bundle['blocks'] if b['kind']=='ink' and b.get('role')!='equation'}),1)

    def test_invalid_split_and_reordering_hold(self):
        for value in (None,1,'true',[]):
            spec=examples()['fractions-variant']
            spec['scene']['objects'][0]['split_partitions']=value
            with self.assertRaises(SemanticError): compile_semantic(spec)
        spec=examples()['fractions-variant']
        spec['steps'][1],spec['steps'][2]=spec['steps'][2],spec['steps'][1]
        with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_legacy_combined_partitions_unchanged(self):
        plan=compile_semantic(examples()['fractions'])
        self.assertEqual(len(plan['stages']),4)

    def test_clean_handwritten_prompt_wraps_and_stays_bounded(self):
        from tablet_acceptance import hand_letter_paths
        text='What is greater, 2/3 or 3/5? Explain visually.'
        paths,height=hand_letter_paths(text,960)
        self.assertGreater(len(paths),40)
        self.assertLessEqual(height,100)
        self.assertTrue(all(0<=x<=960 and 0<=y<=height for path in paths for x,y in path))
