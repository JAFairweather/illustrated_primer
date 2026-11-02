"""Quantity-driven fraction diagrams; no provider or device calls."""
import copy
from fractions import Fraction
import json
import unittest
from unittest.mock import patch

from notebook_semantic import compile_semantic,SemanticError
from notebook_semantic_examples import examples
from notebook_lesson_native import native_semantic_bundle
from notebook_motion_program import compile_motion_program


def spec(a,b,c,d):
    value=examples()['fractions']
    value['scene']['objects'][0]['fractions']=[{'numerator':a,'denominator':b},{'numerator':c,'denominator':d}]
    left,right=Fraction(a,b),Fraction(c,d)
    value['claims'][0]['predicate']='equal' if left==right else 'first_greater' if left>right else 'second_greater'
    return value


class FractionComponentTests(unittest.TestCase):
    def test_combined_fraction_shading_uses_procedural_not_agent_command_budget(self):
        # Separate image-first model probe: two reveal IDs expand to 38
        # primitives, but only 42 native strokes; no response rewriting.
        value=spec(3,4,2,3)
        value['scene']['objects'][0]['split_partitions']=True
        value['steps']=[
            {'reveal':['bars.wholes'],'caption':'Start with equal-sized wholes.'},
            {'reveal':['bars.upper_partitions','bars.lower_partitions'],
             'caption':'Divide the upper whole into fourths and the lower into thirds.'},
            {'reveal':['bars.first','bars.second'],
             'caption':'Three fourths selects more than two thirds.'}]
        value['takeaway']='Three fourths is greater than two thirds.'
        before=copy.deepcopy(value)
        plan=compile_semantic(value)
        self.assertEqual(value,before)
        self.assertEqual(plan['equation'],r'\frac{3}{4}>\frac{2}{3}')
        self.assertEqual([len(s['paths']) for s in plan['stages']],[11,5,42])  # Continuous glyphs save four lifts.
        motion=compile_motion_program(plan)
        for budget in motion['stage_budgets'].values():
            self.assertLessEqual(budget['points'],3000)
            self.assertLessEqual(budget['contacts'],64)
            self.assertLessEqual(budget['estimated_pen_seconds'],30)
        bundle=native_semantic_bundle(json.dumps(value),reveal=True)
        self.assertEqual([b['kind'] for b in bundle['blocks']],['ink','text']*3+['equation','text'])

    def test_combined_fraction_shading_does_not_bypass_native_limits(self):
        value=spec(11,12,10,11)
        value['steps'][2]['reveal']=['bars.first','bars.second']
        value['steps'].pop()
        # Short semantic input is not permission to exceed expanded motion.
        with self.assertRaisesRegex(ValueError,'budget|strokes|pen time|primitives'):
            compile_motion_program(compile_semantic(value))

    def test_equal_wholes_and_shading_are_driven_by_numbers_not_captions(self):
        for a,b,c,d in ((1,2,2,4),(2,3,4,6),(2,3,3,5),(1,12,11,12),(11,12,1,2),(1,7,2,3)):
            value=spec(a,b,c,d);before=copy.deepcopy(value)
            plan=compile_semantic(value);metric=plan['semantic']['metrics']['bars']
            with self.subTest(fractions=(a,b,c,d)):
                self.assertEqual(metric['comparison'],'=' if a*d==c*b else '>' if a*d>c*b else '<')
                for row,n,denom in zip(metric['fractions'],(a,c),(b,d)):
                    x,y,right,bottom=row['whole_bounds']
                    self.assertEqual((right-x,bottom-y),(360,58))
                    self.assertAlmostEqual((row['selected_bounds'][2]-x)/(right-x),n/denom)
                    self.assertEqual(row['selected_cells'],n);self.assertTrue(row['hatches'])
                    for line in row['hatches']:
                        self.assertAlmostEqual(line[1][0]-line[0][0],line[0][1]-line[1][1])
                        for px,py in line:
                            self.assertLess(x,px);self.assertLess(px,row['selected_bounds'][2])
                            self.assertLess(y,py);self.assertLess(py,bottom)
                self.assertEqual(value,before)
                self.assertFalse(plan['semantic']['prose_verified'])
                self.assertEqual(len(compile_motion_program(plan)['stage_budgets']),4)
                bundle=native_semantic_bundle(json.dumps(value),reveal=True)
                self.assertEqual([b['kind'] for b in bundle['blocks']],['ink','text']*4+['equation','text'])

    def test_same_amount_has_same_selected_width_for_every_supported_denominator(self):
        for denominator in range(2,13):
            for numerator in range(1,denominator):
                f=Fraction(numerator,denominator)
                metric=compile_semantic(spec(numerator,denominator,f.numerator,f.denominator))['semantic']['metrics']['bars']
                self.assertEqual(metric['comparison'],'=')
                self.assertEqual(metric['fractions'][0]['selected_bounds'][2],metric['fractions'][1]['selected_bounds'][2])
                normalized=[[[[x,y-row['whole_bounds'][1]] for x,y in line] for line in row['hatches']]
                            for row in metric['fractions']]
                self.assertEqual(len(normalized[0]),len(normalized[1]))
                for first,second in zip(normalized[0],normalized[1]):
                    for p,q in zip(first,second):
                        for a,b in zip(p,q):self.assertAlmostEqual(a,b,places=9)

    def test_false_missing_claim_invalid_quantities_and_coordinate_overrides_fail(self):
        good=spec(1,2,2,4)
        mutations=[lambda v:v.update(claims=[]),
                   lambda v:v['claims'][0].update(predicate='first_greater'),
                   lambda v:v['scene']['objects'][0].update(origin=[0,0]),
                   lambda v:v['steps'][2].update(reveal=['bars.second'])]
        for n,d in ((0,2),(2,2),(-1,3),(1,13),(True,3),(1,2.0),(1,'2')):
            mutations.append(lambda v,n=n,d=d:v['scene']['objects'][0]['fractions'][0].update(numerator=n,denominator=d))
        for mutate in mutations:
            value=copy.deepcopy(good);mutate(value)
            with patch('notebook_lesson_native.storyboard_assets') as encoder:
                with self.assertRaises(SemanticError):native_semantic_bundle(json.dumps(value))
                encoder.assert_not_called()

    def test_partitions_added_once_and_whole_equation_exact(self):
        plan=compile_semantic(spec(1,2,2,4))
        self.assertEqual(plan['equation'],r'\frac{1}{2}=\frac{2}{4}')
        paths=plan['stages'][1]['paths']
        self.assertEqual(len(paths),4)  # 1 half-divider and 3 quarter-dividers
        # Dividers are drawn by hand, within a couple of pixels of the true line.
        for path,(x,y) in zip(paths,[(280,75),(190,205),(280,205),(370,205)]):
            self.assertAlmostEqual(path[0][0],x,delta=2)
            self.assertAlmostEqual(path[0][1],y,delta=2)
        self.assertTrue(all(s['estimated_pen_seconds']<=30 and len(s['paths'])<=64 and s['points']<=3000 for s in plan['stages']))


if __name__=='__main__':unittest.main()
