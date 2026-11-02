"""The fast JSON route must reuse the complete native drawing validator."""
import copy
import json
import unittest
from unittest.mock import patch

from ink import strokes
from notebook_lesson import compile_lesson, STEP, parse_lesson
from notebook_lesson_examples import EXAMPLES
from notebook_lesson_native import native_semantic_bundle
from notebook_semantic import compile_semantic, SemanticError, CAPABILITIES
from notebook_semantic_reply import parse_semantic_reply
from notebook_semantic_prompt import semantic_reply_instructions
from notebook_stroke_asset import storyboard_assets


def drawing_spec():
    return dict(v=1,mode='lesson',intent='A sparse growing drawing',scene={'family':'drawing'},claims=[],
        steps=[{'caption':'Add one visible relationship.',
                'draw':[{'op':'line','from':[30,30+i*50],'to':[100,30+i*50]}]}
               for i in range(3)],takeaway='One picture builds up without redrawing earlier marks.')


class DrawingSceneTests(unittest.TestCase):
    def test_existing_worked_examples_keep_exact_geometry_and_native_order(self):
        for name,make in EXAMPLES.items():
            raw=make();old=parse_lesson(raw)
            spec=drawing_spec()
            spec.update(steps=[json.loads(m[1]) for m in STEP.finditer(raw)],
                        takeaway=old['takeaway'],equation=old['equation'])
            before=copy.deepcopy(spec)
            plan=compile_semantic(spec)
            self.assertEqual(spec,before)
            self.assertEqual(plan['stages'],old['stages'])
            self.assertEqual(plan['equation'],old['equation'])
            self.assertEqual(plan['semantic']['verified_claims'],[])
            self.assertFalse(plan['semantic']['metrics']['mathematics_verified'])
            bundle=native_semantic_bundle(json.dumps(spec))
            self.assertEqual([strokes(s['data']) for s in bundle['sources']],
                             [strokes(a['data']) for a in storyboard_assets(old)])
            for index,stage in enumerate(plan['stages']):
                self.assertEqual(bundle['blocks'][index*2]['kind'],'ink')
                self.assertEqual(bundle['blocks'][index*2+1]['text'],stage['text'])

    def test_every_primitive_uses_the_same_compiler(self):
        spec=drawing_spec()
        spec['steps'][0]['draw']=[
            {'op':'line','from':[30,30],'to':[70,30]},
            {'op':'arrow','from':[30,60],'to':[70,60]},
            {'op':'circle','center':[130,70],'radius':20},
            {'op':'rect','origin':[180,40],'size':[50,40]},
            {'op':'polyline','points':[[260,40],[270,70],[290,55]]},
            {'op':'plot','points':[[320,70],[340,60],[360,40]]},
            {'op':'brace','from':[390,40],'to':[450,40],'side':1},
            {'op':'label','at':[460,70],'text':'x²','size':20},
            {'op':'shade','points':[[200,100],[230,100],[230,130],[200,130]]},
            {'op':'dashed','from':[30,200],'to':[130,200]},
            {'op':'dimension','from':[30,250],'to':[130,250]},
            {'op':'ellipse','center':[300,240],'radii':[60,20],'angle':30},
            {'op':'dot','center':[420,240]},
            {'op':'trace','points':[[470,200],[520,200],[540,220],[540,300]]}]
        compiled=parse_semantic_reply(json.dumps(spec))['plan']
        self.assertEqual(compiled['stages'],compile_lesson(spec['steps'],spec['takeaway'])['stages'])
        self.assertEqual(set(CAPABILITIES['drawing']['commands']),
                         {c['op'] for c in spec['steps'][0]['draw']} | {'connect'})
        # connect is a high-level relation lowered to these same primitives;
        # its reference/routing/native integration is covered separately.
        self.assertIn('drawing: {"family":"drawing"}',semantic_reply_instructions())

    def test_bad_late_geometry_claims_or_equation_allocate_nothing(self):
        mutations=[
            lambda s:s['steps'][-1]['draw'][0].update(to=[601,5]),
            lambda s:s['steps'][-1]['draw'][0].update(op='exec'),
            lambda s:s['steps'][-1]['draw'][0].update(file='/tmp/ink'),
            lambda s:s['scene'].update(objects=[]),
            lambda s:s.update(claims=[{'object':'x','predicate':'proven'}]),
            lambda s:s.update(equation=r'\input{private}'),
            lambda s:s.update(equation='https://example.org'),
            lambda s:s['steps'][-1].update(reveal=['scene.secret']),
            lambda s:s.update(steps=[]),
            lambda s:s.update(steps=s['steps']*3)]
        for mutate in mutations:
            spec=drawing_spec();mutate(spec)
            with patch('notebook_lesson_native.storyboard_assets') as encode, \
                    patch('notebook_lesson_native.uuid.uuid4') as identity:
                with self.assertRaises(SemanticError):native_semantic_bundle(json.dumps(spec))
                encode.assert_not_called();identity.assert_not_called()

    def test_whole_lesson_label_clearance_and_native_caps_still_apply(self):
        spec=drawing_spec()
        spec['steps'][0]['draw']=[{'op':'label','at':[100,100],'text':'A'}]
        spec['steps'][-1]['draw']=[{'op':'line','from':[90,90],'to':[140,90]}]
        with self.assertRaisesRegex(SemanticError,'collision'):compile_semantic(spec)
        spec=drawing_spec()
        spec['steps'][-1]['draw']=[{'op':'circle','center':[300,180],'radius':170}]*32
        with self.assertRaises(SemanticError):compile_semantic(spec)
        spec=drawing_spec()
        spec['steps'][-1]['draw']*=33
        with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_component_equations_and_geometry_cannot_be_overridden(self):
        from notebook_semantic_examples import examples
        for extra in ({'equation':'1=2'}, {'steps':drawing_spec()['steps']}):
            spec=examples()['integral'];spec.update(extra)
            with self.assertRaises(SemanticError):compile_semantic(spec)


if __name__=='__main__':unittest.main()
