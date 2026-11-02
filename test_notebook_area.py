"""Curved fills are procedural geometry, not model-enumerated hatch strokes."""
from copy import deepcopy
import math
import random
import unittest
from unittest.mock import patch

from notebook_panel_shapes import (_frame, _point, _lower, _hatch_region,
                                   _hatch_polygon, _sample_curve, compile_panel_shapes)
from notebook_panel_examples import graph_reuse_example
from notebook_story_native import native_story_bundle
from notebook_lesson import _primitive


def area(**changes):
    return dict(dict(id='shaded', type='area', **{'in':'ax'},
        coefficients=[0,0,1], domain=[0,1], baseline=0, fill='hatch'), **changes)


def frame(x=None, y=None):
    return _frame(dict(id='ax', type='axes', x=x or [0,1], y=y or [0,1],
                       aspect='independent'))


class AreaTests(unittest.TestCase):
    def test_rectangle_hatching_matches_existing_page_aligned_lattice(self):
        box=[80,50,520,290];left,top,right,bottom=box
        polygon=[[left,top],[right,top],[right,bottom],[left,bottom]]
        self.assertEqual(_hatch_polygon(polygon), _hatch_region(*box))
        forward,reverse=_hatch_polygon(polygon),_hatch_polygon(list(reversed(polygon)))
        self.assertEqual(len(forward),len(reverse))
        for a,b in zip(forward,reverse):
            for key in ('from','to'):
                for x,y in zip(a[key],b[key]):self.assertAlmostEqual(x,y)

    def test_outline_reuses_exact_plot_samples_and_preserves_input(self):
        f=frame();source=area();before=deepcopy(source)
        commands=_lower(source,{'ax':f})
        plot=_lower(dict(id='curve',type='plot',**{'in':'ax'},
                         coefficients=[0,0,1],domain=[0,1]),{'ax':f})
        self.assertEqual(commands[0]['points'][:65],plot[0]['points'])
        self.assertEqual(commands[0]['points'][-1],commands[0]['points'][0])
        self.assertEqual(source,before)
        self.assertGreater(len(commands),1)
        for command in commands:_primitive(command)

    def test_every_hatch_segment_stays_between_sampled_curve_and_baseline(self):
        for coefficients,baseline in (([0,0,1],0),([0,0,-1],0),([0,1],0),
                                      ([-.2,0,1],.1),([0,0,-1,0,1],0)):
            with self.subTest(coefficients=coefficients,baseline=baseline):
                f=frame([-1,1],[-1.2,1.2])
                source=area(coefficients=coefficients,domain=[-1,1],baseline=baseline)
                values=_sample_curve(source)
                commands=_lower(source,{'ax':f})
                self.assertGreater(len(commands),1)
                left,top,right,bottom=f['box']
                for command in commands[1:]:
                    a,b=command['from'],command['to']
                    self.assertAlmostEqual(a[0]+a[1],b[0]+b[1])
                    self.assertGreaterEqual(math.dist(a,b),1-1e-9)
                    for sample in range(17):
                        px=a[0]+(b[0]-a[0])*sample/16
                        py=a[1]+(b[1]-a[1])*sample/16
                        x=-1+2*(px-left)/(right-left)
                        y=-1.2+2.4*(bottom-py)/(bottom-top)
                        intervals=len(values)-1
                        interval=max(0,min(intervals-1,int((x+1)*intervals/2)))
                        x0,y0=values[interval];x1,y1=values[interval+1]
                        curve_y=y0+(y1-y0)*(x-x0)/(x1-x0)
                        self.assertGreaterEqual(y,min(baseline,curve_y)-1e-8)
                        self.assertLessEqual(y,max(baseline,curve_y)+1e-8)

    def test_zero_area_has_no_fabricated_fill_and_outline_only_has_no_hatches(self):
        self.assertEqual(len(_lower(area(coefficients=[0]),{'ax':frame()})),1)
        self.assertEqual(len(_lower(area(fill='none'),{'ax':frame()})),1)

    def test_deterministic_polynomial_sweep_keeps_hatches_in_sampled_region(self):
        randomizer=random.Random(384)
        for case in range(60):
            coefficients=[randomizer.uniform(-2,2) for _ in range(1+case%5)]
            baseline=randomizer.uniform(-1,1)
            source=area(coefficients=coefficients,domain=[-2,2],baseline=baseline)
            values=_sample_curve(source)
            ymin=min([y for x,y in values]+[baseline])-1
            ymax=max([y for x,y in values]+[baseline])+1
            f=frame([-2,2],[ymin,ymax]);left,top,right,bottom=f['box']
            commands=_lower(source,{'ax':f})
            self.assertEqual(commands,_lower(source,{'ax':f}))
            for command in commands[1:]:
                a,b=command['from'],command['to']
                for t in (0,.25,.5,.75,1):
                    px=a[0]+(b[0]-a[0])*t;py=a[1]+(b[1]-a[1])*t
                    x=-2+4*(px-left)/(right-left)
                    y=ymin+(ymax-ymin)*(bottom-py)/(bottom-top)
                    intervals=len(values)-1
                    interval=max(0,min(intervals-1,int((x+2)*intervals/4)))
                    x0,y0=values[interval];x1,y1=values[interval+1]
                    value=y0+(y1-y0)*(x-x0)/(x1-x0)
                    self.assertGreaterEqual(y,min(baseline,value)-1e-8)
                    self.assertLessEqual(y,max(baseline,value)+1e-8)

    def test_invalid_geometry_rejected_before_hatching(self):
        for changes in ({'coefficients':[2]}, {'baseline':2}, {'domain':[-1,1]},
                        {'domain':[0,0]}, {'coefficients':[float('nan')]},
                        {'coefficients':['x']}, {'coefficients':[0]*6},
                        {'fill':'solid'}, {'path':'/tmp/x'}, {'samples':10000}):
            with self.subTest(changes=changes),patch('notebook_panel_shapes._hatch_polygon') as hatch:
                with self.assertRaises(ValueError):_lower(area(**changes),{'ax':frame()})
                hatch.assert_not_called()

    def test_native_bundle_inherits_without_mutating_source_and_enforces_budget(self):
        story,drafts=graph_reuse_example()
        drafts['curve']['items']=[area(id='square')]
        drafts['mark']['items']=drafts['mark']['items'][:1]
        before=deepcopy(drafts)
        bundle=native_story_bundle(story,drafts)
        self.assertEqual(bundle['mode'],'story')
        self.assertLessEqual(bundle['delivery_points'],12000)
        self.assertEqual(drafts,before)
        drafts['curve']['items']=[area(id='fill-'+str(i)) for i in range(12)]
        with self.assertRaises(ValueError):native_story_bundle(story,drafts)

    def test_sampled_decimal_domain_ends_exactly_at_declared_bounds(self):
        source=area(domain=[-.7,.1],coefficients=[.25])
        values=_sample_curve(source)
        self.assertEqual(values[0][0],-.7);self.assertEqual(values[-1][0],.1)
        _lower(source,{'ax':frame([-.7,.1],[0,1])})

    def test_full_span_reference_line_label_uses_clear_route_positions(self):
        story,drafts=graph_reuse_example()
        story['panels']=story['panels'][:1];story['acts']=story['acts'][:1]
        drawings=[dict(id='ax',type='axes',x=[-1,1],y=[-1,1],aspect='independent'),
                  area(coefficients=[0,1],domain=[-1,1]),
                  dict(id='zero',type='hline',**{'in':'ax'},value=0),
                  dict(id='name',type='label',to='zero',text='baseline 0',side='left')]
        drafts={'axes':dict(v=1,mode='panel-shapes',panel='axes',items=drawings)}
        result=compile_panel_shapes(story,drafts)['panels']['axes']
        label=next(row for row in result['label_layout'] if row['id']=='name')
        self.assertEqual(' '.join(label['lines']),'baseline 0')
        self.assertEqual(result['items']['name']['to'],'zero')


if __name__=='__main__':unittest.main()
