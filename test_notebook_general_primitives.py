from copy import deepcopy
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from notebook_lesson import _primitive, compile_lesson
from notebook_hatching import hatch_paths
from notebook_panel_shapes import _lower, _frame, _point, compile_panel_shapes, _hatch_polygon
from notebook_panel_examples import primitive_capabilities_example
from notebook_panel_eval import review_panels
from notebook_contract_feedback import item_fields, ContractError
from notebook_pen_budget import NativePenBudgetError
from notebook_stroke_asset import storyboard_assets
from notebook_story_native import native_story_bundle


def inside(point, polygon):
    """Independent ray-casting oracle including the boundary."""
    x,y=point; contained=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        cross=dx*(y-a[1])-dy*(x-a[0])
        if abs(cross)<1e-7 and min(a[0],b[0])-1e-7<=x<=max(a[0],b[0])+1e-7 and min(a[1],b[1])-1e-7<=y<=max(a[1],b[1])+1e-7:
            return True
        if (a[1]>y)!=(b[1]>y) and x<a[0]+(y-a[1])*dx/dy:
            contained=not contained
    return contained


class GeneralPrimitivesTests(unittest.TestCase):
    def test_shade_stays_inside_concave_region_in_both_windings(self):
        polygon=[[50,50],[350,50],[350,100],[100,100],[100,300],[50,300]]
        for vertices in (polygon,list(reversed(polygon)),polygon+[polygon[0]]):
            paths=_primitive(dict(op='shade',points=vertices))
            self.assertTrue(paths)
            self.assertTrue(all(len(path)==2 for path in paths))
            for a,b in paths:
                self.assertGreater(b[0],a[0]);self.assertLess(b[1],a[1])
                for i in range(101):
                    t=i/100
                    self.assertTrue(inside([a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t],polygon))
        self.assertEqual(_primitive(dict(op='shade',points=polygon)),
                         _primitive(dict(op='shade',points=polygon+[polygon[0]])))

    def test_random_simple_polygons_keep_every_hatch_sample_inside(self):
        rng=random.Random(530)
        for n in range(3,24):
            polygon=[]
            for i in range(n):
                angle=math.tau*i/n;radius=rng.uniform(20,100)
                polygon.append([250+radius*math.cos(angle),180+radius*math.sin(angle)])
            for a,b in _primitive(dict(op='shade',points=polygon)):
                for i in range(31):
                    t=i/30
                    self.assertTrue(inside([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t],polygon))

    def test_small_region_has_clipped_cue_but_subpixel_region_is_not_enlarged(self):
        vertices=[[10,10],[14,10],[14,14],[10,14]]
        self.assertEqual(hatch_paths(vertices),[])
        paths=_primitive(dict(op='shade',points=vertices))
        self.assertEqual(len(paths),1)
        self.assertTrue(all(inside(point,vertices) for point in paths[0]))
        with self.assertRaisesRegex(ValueError,'too thin'):
            _primitive(dict(op='shade',points=[[10,10],[10.01,10],[10.01,10.01],[10,10.01]]))

    def test_shade_rejects_degeneracy_crossing_touching_and_untrusted_fields(self):
        bad=[[],[[1,1],[2,2]],[[1,1],[2,2],[3,3]],
             [[10,10],[100,100],[10,100],[100,10]],
             [[10,10],[100,10],[50,10],[50,100],[10,100]],
             [[10,10],[100,10],[50,50],[10,10],[10,100]],
             [[10,10],[100,10],[100,100],[50,10],[10,100]],
             [[True,10],[100,10],[100,100]],[[0,0],[601,0],[100,100]],
             [[0,0],[100,0],[100,float('nan')]],[[1,1]]*161]
        for points in bad:
            with self.subTest(points=points),self.assertRaises(ValueError):
                _primitive(dict(op='shade',points=points))
        for extra in ({'url':'https://example.org'},{'path':'/tmp/ink'},{'density':1}):
            with self.assertRaises(ValueError):
                _primitive(dict(op='shade',points=[[10,10],[100,10],[100,100]],**extra))

    def test_dashed_edge_ends_on_both_points_within_a_dozen_dashes(self):
        for end in ([60,60],[590,350],[30,70]):
            paths=_primitive(dict(op='dashed',**{'from':[20,40],'to':end}))
            self.assertTrue(2<=len(paths)<=12)
            self.assertEqual(paths[0][0],(20,40)); self.assertAlmostEqual(math.dist(paths[-1][1],end),0,places=6)
            self.assertTrue(all(len(path)==2 for path in paths))
        with self.assertRaises(ValueError):
            _primitive(dict(op='dashed',**{'from':[20,40],'to':[25,40]}))

    def test_ellipse_turns_and_stays_in_the_region(self):
        flat=_primitive(dict(op='ellipse',center=[300,180],radii=[100,30]))[0]
        tilted=_primitive(dict(op='ellipse',center=[300,180],radii=[100,30],angle=90))[0]
        self.assertAlmostEqual(max(x for x,_ in flat)-min(x for x,_ in flat),200,places=6)
        self.assertAlmostEqual(max(y for _,y in tilted)-min(y for _,y in tilted),200,places=6)
        self.assertEqual(flat[0],flat[-1])
        for bad in (dict(center=[50,180],radii=[100,30]),dict(center=[300,180],radii=[100]),
                    dict(center=[300,180],radii=[100,30],angle=400),dict(center=[300,180],radii=[100,30],tilt=5)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _primitive(dict(op='ellipse',**bad))

    def test_dot_trace_and_dimension_are_bounded_marks(self):
        dot=_primitive(dict(op='dot',center=[100,100]))
        self.assertEqual(len(dot),1); self.assertTrue(all(math.dist(p,(100,100))<=4.5+1e-9 for p in dot[0]))
        trace=_primitive(dict(op='trace',points=[[40,40],[90,40],[110,60],[110,120]]))
        self.assertEqual(trace[0],[(40,40),(90,40),(110,60),(110,120)]); self.assertEqual(len(trace),3)
        self.assertTrue(all(abs(math.dist(p,(40,40))-3)<1e-9 for p in trace[1]))
        self.assertEqual({p for p in trace[2]},{(107,117),(113,117),(113,123),(107,123)})
        dimension=_primitive(dict(op='dimension',**{'from':[60,270],'to':[160,270]}))
        self.assertEqual(dimension[0],[(60,270),(160,270)]); self.assertEqual(len(dimension),5)
        for bad in (dict(op='dot',center=[2,100]),dict(op='trace',points=[[40,40]]),
                    dict(op='trace',points=[[40,40]]*13),dict(op='trace',points=[[1,40],[90,40]]),
                    dict(op='dimension',**{'from':[60,270],'to':[65,270]})):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _primitive(bad)

    def test_sampled_plot_preserves_exact_input_order_and_never_evaluates_code(self):
        frame=_frame(dict(id='ax',type='axes',x=[0,1],y=[0,1],aspect='independent'))
        item=dict(id='curve',type='plot',**{'in':'ax'},points=[[.9,.1],[.2,.7],[.8,.4]])
        self.assertEqual(_lower(item,{'ax':frame}),
                         [dict(op='polyline',points=[_point(frame,p) for p in item['points']])])
        for bad in ({'coefficients':[1],'domain':[0,1]}, {'expression':'lambda x:x'}, {'points':'sin(x)'}):
            with self.assertRaises(ValueError):_lower(dict(item,**bad),{'ax':frame})
        with self.assertRaises(ContractError):item_fields(dict(item,coefficients=[1]))

    def test_brace_orientation_uses_data_space_left_normal(self):
        frame=_frame(dict(id='ax',type='axes',x=[0,1],y=[0,1],aspect='independent'))
        for side in (-1,1):
            item=dict(id='brace',type='brace',**{'in':'ax','from':[.2,.5],'to':[.8,.5]},side=side)
            command=_lower(item,{'ax':frame})[0];points=_primitive(command)[0]
            self.assertEqual(points[0],tuple(_point(frame,item['from'])))
            self.assertEqual(points[-1],tuple(_point(frame,item['to'])))
            self.assertEqual(command['side'],-side)
            self.assertLess((points[5][1]-points[0][1])*side,0)
        for side in (True,0,2,'left'):
            with self.assertRaises(ValueError):_lower(dict(item,side=side),{'ax':frame})

    def test_existing_sampled_area_hatching_keeps_identical_geometry(self):
        # Independent copy of the prior even-odd algorithm protects polynomial
        # area/zero-crossing behavior when sharing the hatch implementation.
        for polygon in ([[[80,280],[300,60],[520,280],[520,290],[80,290]]],
                        [[[80,180],[190,80],[300,180],[410,280],[520,180]]]):
            points=polygon[0];spacing=32*math.sqrt(2);offsets=[x+y for x,y in points];expected=[]
            for i in range(math.ceil(min(offsets)/spacing),math.floor(max(offsets)/spacing)+1):
                offset=i*spacing;xs=[]
                for (x1,y1),(x2,y2) in zip(points,points[1:]+points[:1]):
                    t1,t2=x1+y1,x2+y2
                    if t1<=offset<t2 or t2<=offset<t1:
                        xs.append(x1+(x2-x1)*(offset-t1)/(t2-t1))
                xs.sort()
                for left,right in zip(xs[::2],xs[1::2]):
                    if (right-left)*math.sqrt(2)>=1:
                        expected.append([[left,offset-left],[right,offset-right]])
            actual=[list((c['from'],c['to'])) for c in _hatch_polygon(points)]
            for a,b in zip(actual,expected):
                for p,q in zip(a,b):
                    for x,y in zip(p,q):self.assertAlmostEqual(x,y)
            self.assertEqual(len(actual),len(expected))

    def test_complete_native_story_preserves_old_ink_and_all_caps(self):
        story,drafts=primitive_capabilities_example();original=deepcopy(drafts)
        result=compile_panel_shapes(story,drafts)
        self.assertEqual(original,drafts)
        previous=[]
        for panel in story['panels']:
            plan=result['panels'][panel['id']]['plan']
            self.assertEqual(plan['stages'][:-1],previous)
            previous=deepcopy(plan['stages'])
            for stage,asset in zip(plan['stages'],storyboard_assets(plan)):
                self.assertLessEqual(asset['point_count'],3000)
                self.assertLessEqual(asset['stroke_count'],64)
                self.assertLessEqual(stage['estimated_pen_seconds'],30)
        bundle=native_story_bundle(story,drafts)
        self.assertFalse(bundle['tablet_proven'])
        self.assertEqual(len(bundle['sources']),4)

    def test_shading_cannot_bypass_native_budgets(self):
        command=dict(op='shade',points=[[10,10],[590,10],[590,350],[10,350]])
        with self.assertRaises(NativePenBudgetError):
            compile_lesson([dict(caption='Shade the region.',draw=[command]*5)],'Bounded ink.',allow_short=True)

    def test_bad_last_polygon_prevents_all_asset_encoding(self):
        story,drafts=primitive_capabilities_example()
        drafts['measure']['items']=[dict(id='bad',type='shade',**{'in':'ax'},points=[[0,0],[1,1],[0,1],[1,0]])]
        with patch('notebook_story_native.storyboard_assets') as assets,patch('notebook_ink_playback.playback_assets') as playback:
            with self.assertRaises(ValueError):native_story_bundle(story,drafts)
            assets.assert_not_called();playback.assert_not_called()
        with tempfile.TemporaryDirectory() as root:
            result=review_panels(json.dumps(story).encode(),json.dumps(drafts).encode(),Path(root)/'invalid')
            self.assertFalse(result['valid']);self.assertEqual(list(Path(root).rglob('*.png')),[])


if __name__=='__main__':unittest.main()
