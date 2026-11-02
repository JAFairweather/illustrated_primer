import copy
from fractions import Fraction
import math
import unittest

from notebook_right_triangle import right_triangle
from notebook_semantic import compile_semantic, SemanticError
from notebook_stroke_asset import storyboard_assets


def lesson(legs=(3,4)):
    total=sum(Fraction(str(n))**2 for n in legs)
    return {'v':1,'mode':'lesson','intent':'Relate side squares in a right triangle',
        'scene':{'family':'quantitative','objects':[
            {'id':'t','component':'right_triangle','legs':list(legs)}]},
        'steps':[
            {'caption':f'The horizontal leg is {legs[0]} and the vertical leg is {legs[1]}.',
             'reveal':['t.triangle']},
            {'caption':'Build a square on each leg.', 'reveal':['t.a_square','t.b_square']},
            {'caption':'Build the third square on the hypotenuse.', 'reveal':['t.c_square']},
            {'caption':'Pythagoras relates these three square areas.', 'reveal':['t.areas']}],
        'claims':[{'object':'t','predicate':'hypotenuse_squared',
                   'value':{'numerator':total.numerator,'denominator':total.denominator}}],
        'takeaway':'This is a numerical application of Pythagoras, not a general proof.'}


def cross(a,b):return a[0]*b[1]-a[1]*b[0]
def sub(a,b):return [a[i]-b[i] for i in (0,1)]


class RightTriangleTest(unittest.TestCase):
    def test_scaled_squares_equal_edges_right_angles_and_outward(self):
        for legs in ((3,4),(4,3),(5,12),(1,1),(.1,.5),(.5,.1),(10000,2000),(2.5,3.5)):
            with self.subTest(legs=legs):
                spec=lesson(legs);original=copy.deepcopy(spec)
                plan=compile_semantic(spec);m=plan['semantic']['metrics']['t']
                self.assertEqual(spec,original)
                triangle=m['triangle']
                v,w=sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0])
                self.assertAlmostEqual(sum(a*b for a,b in zip(v,w)),0)
                self.assertAlmostEqual(math.dist(*triangle[:2])/math.dist(triangle[0],triangle[2]),legs[0]/legs[1])
                for square,area in zip(m['squares'],m['area_values']):
                    lengths=[math.dist(square[i],square[(i+1)%4]) for i in range(4)]
                    for length in lengths:self.assertAlmostEqual(length,lengths[0])
                    vectors=[sub(square[(i+1)%4],square[i]) for i in range(4)]
                    for i in range(4):self.assertAlmostEqual(sum(a*b for a,b in zip(vectors[i],vectors[(i+1)%4])),0)
                    self.assertAlmostEqual(lengths[0]**2/m['uniform_scale']**2,float(Fraction(area)))
                    other=next(p for p in triangle if p not in square[:2])
                    self.assertLess(cross(sub(square[1],square[0]),sub(other,square[0]))*
                                    cross(sub(square[1],square[0]),sub(square[2],square[0])),0)
                    for x,y in square:self.assertTrue(0<=x<=600 and 0<=y<=360)
                assets=storyboard_assets(plan)
                for asset,stage in zip(assets,plan['stages']):
                    self.assertLessEqual(asset['stroke_count'],64)
                    self.assertLessEqual(asset['point_count'],3000)
                    self.assertLessEqual(stage['estimated_pen_seconds'],30)
                self.assertFalse(m['general_proof_verified'])

    def test_no_shared_edge_is_redrawn(self):
        c=right_triangle(lesson()['scene']['objects'][0]);edges=[]
        for name in ('triangle','a_square','b_square','c_square'):
            for command in c['parts'][name]:
                points=command['points']
                edges += [tuple(sorted((tuple(a),tuple(b)))) for a,b in zip(points,points[1:])]
        self.assertEqual(len(edges),len(set(edges)))
        self.assertEqual(len(edges),14)  # 3 triangle + 2 right-angle marker + 9 square edges

    def test_exact_roots_and_non_square_roots(self):
        for legs,result in (((3,4),'c=5'),((5,12),'c=13'),((1,1),r'c=\sqrt{2}'),((.3,.4),r'c=\frac{1}{2}')):
            self.assertTrue(compile_semantic(lesson(legs))['equation'].endswith(result))

    def test_claims_dependencies_and_untrusted_fields(self):
        bad=lesson();bad['claims'][0]['value']['numerator']=24
        with self.assertRaises(SemanticError):compile_semantic(bad)
        bad=lesson();bad['steps'][1],bad['steps'][3]=bad['steps'][3],bad['steps'][1]
        with self.assertRaises(SemanticError):compile_semantic(bad)
        for value in (None, [3], [0,4], [True,4], [3,float('inf')], [1,6], ['3',4]):
            bad=lesson();bad['scene']['objects'][0]['legs']=value
            with self.assertRaises(SemanticError):compile_semantic(bad)
        bad=lesson();bad['scene']['objects'][0]['corners']=[[0,0]]
        with self.assertRaises(SemanticError):compile_semantic(bad)

    def test_contract_advertises_high_level_component(self):
        from notebook_semantic_prompt import semantic_reply_instructions
        text=semantic_reply_instructions()
        self.assertIn('"component":"right_triangle","legs":[a,b]',text)
        self.assertIn('NOT square corners',text)


if __name__=='__main__':unittest.main()
