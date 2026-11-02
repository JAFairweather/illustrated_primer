"""Exact affine lowering, not approximate simplification of curved data."""
from copy import deepcopy
import unittest

from notebook_panel_shapes import _sample_curve, _lower, _frame, _point, _hatch_polygon
from notebook_lesson import _primitive


class AffineSamplingTests(unittest.TestCase):
    def test_constant_linear_and_zero_padded_coefficients_use_exact_endpoints(self):
        for coefficients in ([2], [2,0], [2,3], [2,-3,0,0,0], [0,0,-0.0]):
            item=dict(coefficients=coefficients,domain=[-.7,.1])
            original=deepcopy(item)
            values=_sample_curve(item)
            self.assertEqual(values,[[x,sum(c*x**i for i,c in enumerate(coefficients))]
                                      for x in item['domain']])
            self.assertEqual(item,original)

    def test_nonzero_curvature_is_never_flattened_even_when_tiny(self):
        for coefficients in ([0,0,1e-20], [0,1,0,1e-20], [0,1,0,0,-1e-20]):
            values=_sample_curve(dict(coefficients=coefficients,domain=[-2,3]))
            self.assertEqual(len(values),65)
            self.assertEqual(values[0][0],-2);self.assertEqual(values[-1][0],3)
            for x,y in values:
                self.assertEqual(y,sum(c*x**i for i,c in enumerate(coefficients)))

    def test_affine_plot_equals_direct_line_in_display_space(self):
        for coefficients in ([0,.6], [.2,0], [.6,-.3], [.1,.5,0,0]):
            frame=_frame(dict(id='ax',type='axes',x=[-1,2],y=[-1,2],aspect='independent'))
            plot=dict(id='curve',type='plot',**{'in':'ax'},
                      coefficients=coefficients,domain=[-.5,1.5])
            values=_sample_curve(plot)
            direct=dict(id='line',type='line',**{'in':'ax','from':values[0],'to':values[1]})
            result=_lower(plot,{'ax':frame})
            self.assertEqual(_primitive(result[0]),_primitive(_lower(direct,{'ax':frame})[0]))

    def test_affine_area_keeps_boundary_baseline_closure_and_hatches(self):
        frame=_frame(dict(id='ax',type='axes',x=[0,2],y=[-1,2],aspect='independent'))
        for coefficients in ([0,.5], [.5,0], [.7,-.5]):
            source=dict(id='fill',type='area',**{'in':'ax'},coefficients=coefficients,
                        domain=[0,2],baseline=0,fill='hatch')
            original=deepcopy(source)
            commands=_lower(source,{'ax':frame})
            values=_sample_curve(source)
            expected=[_point(frame,p) for p in values+[[2,0],[0,0],values[0]]]
            self.assertEqual(commands[0]['points'],expected)
            self.assertGreater(len(commands),1)
            self.assertEqual(source,original)
            for command in commands:_primitive(command)

    def test_model_supplied_polyline_vertices_are_not_simplified(self):
        frame=_frame(dict(id='ax',type='axes',x=[0,2],y=[0,2],aspect='independent'))
        values=[[0,0],[.5,.5],[1,1],[2,2]]
        result=_lower(dict(id='line',type='polyline',**{'in':'ax'},points=values),{'ax':frame})
        self.assertEqual(result[0]['points'],[_point(frame,p) for p in values])

    def test_affine_hatching_matches_the_previous_dense_boundary(self):
        frame=_frame(dict(id='ax',type='axes',x=[-1,2],y=[-2,3],aspect='independent'))
        for intercept,slope,baseline in ((0,1,0),(.25,-.7,.1),(1,0,-.2),(-1,0,0)):
            source=dict(id='fill',type='area',**{'in':'ax'},coefficients=[intercept,slope],
                        domain=[-1,2],baseline=baseline,fill='hatch')
            old_values=[[-1+3*i/64,intercept+slope*(-1+3*i/64)] for i in range(65)]
            old_boundary=[_point(frame,p) for p in old_values+[[2,baseline],[-1,baseline]]]
            expected=_hatch_polygon(old_boundary)
            actual=_lower(source,{'ax':frame})[1:]
            self.assertEqual(len(actual),len(expected))
            for a,b in zip(actual,expected):
                for key in ('from','to'):
                    for x,y in zip(a[key],b[key]):self.assertAlmostEqual(x,y,places=8)

    def test_invalid_affine_input_still_fails(self):
        for changes in (dict(coefficients=[float('nan')]),dict(domain=[1,1]),
                        dict(coefficients=[1,0,0,0,0,0]),dict(domain=[0,1e7])):
            item=dict(coefficients=[0,1],domain=[0,1]);item.update(changes)
            with self.assertRaises(ValueError):_sample_curve(item)
        frame=_frame(dict(id='ax',type='axes',x=[0,1],y=[0,1],aspect='independent'))
        with self.assertRaises(ValueError):
            _lower(dict(id='line',type='plot',**{'in':'ax'},
                        coefficients=[0,2],domain=[0,1]),{'ax':frame})


if __name__=='__main__':unittest.main()
