from copy import deepcopy
import math
import unittest

from notebook_function_plot import function_points
from notebook_contract_feedback import item_fields
from notebook_panel_examples import graph_reuse_example
from notebook_panel_shapes import compile_panel_shapes
from notebook_story_native import native_story_bundle


def fn(name='cos'):
    return dict(name=name,amplitude=1,rate=1,phase=0,offset=0)


class FunctionPlotTests(unittest.TestCase):
    def test_known_period_and_half_life_values_not_model_supplied_samples(self):
        points=function_points(dict(name='cos',amplitude=2,rate=2*math.pi,phase=0,offset=3),[0,2])
        for x,y in ((0,5),(.25,3),(.5,1),(.75,3),(1,5),(1.5,1),(2,5)):
            actual=min(points,key=lambda p:abs(p[0]-x))
            self.assertAlmostEqual(actual[0],x);self.assertAlmostEqual(actual[1],y)
        points=function_points(dict(name='exp',amplitude=8,rate=-math.log(2),phase=0,offset=0),[0,2])
        for x,y in ((0,8),(1,4),(2,2)):
            self.assertAlmostEqual(next(p[1] for p in points if p[0]==x),y)

    def test_different_function_examples_fit_existing_native_budgets(self):
        from notebook_function_examples import function_examples
        for name,(story,drafts) in function_examples().items():
            with self.subTest(name=name):
                original=deepcopy(drafts)
                compiled=compile_panel_shapes(story,drafts)
                self.assertEqual(drafts,original)
                native_story_bundle(story,drafts)
                for panel in compiled['panels'].values():
                    for stage in panel['plan']['stages']:
                        self.assertLessEqual(stage['points'],3000)
                        self.assertLessEqual(len(stage['paths']),64)

    def test_values_are_computed_from_parameters_in_data_units(self):
        for name in ('sin','cos','exp'):
            for rate in (-.8,0,.4):
                parameters=dict(name=name,amplitude=-2,rate=rate,phase=.3,offset=4)
                original=deepcopy(parameters)
                points=function_points(parameters,[-1,2])
                self.assertEqual(parameters,original)
                self.assertEqual(points[0][0],-1);self.assertEqual(points[-1][0],2)
                self.assertEqual(points,function_points(parameters,[-1,2]))
                self.assertTrue(all(a[0]<b[0] for a,b in zip(points,points[1:])))
                for x,y in points:
                    self.assertAlmostEqual(y,4-2*getattr(math,name)(rate*x+.3))

    def test_every_peak_is_sampled_with_positive_or_negative_rate(self):
        for name in ('sin','cos'):
            for rate in (-7,7):
                p=dict(name=name,amplitude=2,rate=rate,phase=.37,offset=3)
                points=function_points(p,[0,3])
                self.assertLessEqual(len(points),160)
                self.assertAlmostEqual(min(y for _,y in points),1)
                self.assertAlmostEqual(max(y for _,y in points),5)
                lo,hi=sorted((p['phase'],p['phase']+rate*3))
                shift=math.pi/2 if name=='sin' else 0
                peaks=[(shift+k*math.pi-p['phase'])/rate
                    for k in range(math.ceil((lo-shift)/math.pi),math.floor((hi-shift)/math.pi)+1)]
                self.assertTrue(all(x in [p[0] for p in points] for x in peaks))

    def test_constant_function_is_one_segment_without_false_curve(self):
        for change in ({'rate':0},{'amplitude':0}):
            p=fn();p.update(change)
            self.assertEqual(len(function_points(p,[0,1])),2)

    def test_invalid_or_executable_inputs_are_not_interpreted(self):
        for change in ({'name':'__import__("os")'},{'name':[]},{'name':'tan'},
                       {'url':'https://example.org'},{'rate':True},{'rate':math.inf},
                       {'phase':math.nan},{'amplitude':'1/2'}):
            p=fn();p.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):function_points(p,[0,1])
        for domain in ([1,0],[1,1],['0',1],[0,True],None):
            with self.subTest(domain=domain),self.assertRaises(ValueError):function_points(fn(),domain)
        p=fn();del p['phase']
        with self.assertRaises(ValueError):function_points(p,[0,1])

    def test_dense_periods_and_exp_overflow_are_rejected_not_aliased(self):
        with self.assertRaisesRegex(ValueError,'four cycles'):
            function_points(fn(),[0,8*math.pi+.001])
        self.assertLessEqual(len(function_points(fn(),[0,8*math.pi])),160)
        for domain in ([-31,0],[0,31]):
            with self.assertRaisesRegex(ValueError,'exponential arguments'):
                function_points(fn('exp'),domain)

    def test_exactly_one_plot_representation_and_no_function_area_backdoor(self):
        item=dict(id='curve',type='plot',**{'in':'ax'},function=fn(),domain=[0,1])
        item_fields(item)
        for extra in ({'coefficients':[0,1]},{'points':[[0,0],[1,1]]},{'code':'sin(x)'}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):item_fields(dict(item,**extra))
        with self.assertRaises(ValueError):item_fields(dict(item,type='area',baseline=0,fill='none'))

    def test_native_story_and_peak_outside_frame_fail_closed(self):
        story,drafts=graph_reuse_example()
        story['acts']=story['acts'][:1];story['panels']=story['panels'][:2]
        drafts={k:drafts[k] for k in ('axes','curve')}
        drafts['axes']['items'][0].update(x=[0,6],y=[-1,1])
        drafts['curve']['items']=[dict(id='wave',type='plot',**{'in':'ax'},function=fn(),domain=[0,6])]
        result=compile_panel_shapes(story,drafts)
        self.assertTrue(result['geometry_validated'])
        native_story_bundle(story,drafts)
        # The peak is deliberately between the uniform samples.
        drafts['curve']['items'][0]['function']['phase']=.371
        drafts['axes']['items'][0]['y']=[-.99999,.99999]
        with self.assertRaises(ValueError):compile_panel_shapes(story,drafts)


if __name__=='__main__':unittest.main()
