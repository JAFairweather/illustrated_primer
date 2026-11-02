"""Generic ownership and safety tests for fallback mathematical annotations."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from notebook_label_attachment import contour_attachment
from notebook_label_candidates import corner_callouts
from notebook_lesson import _primitive
from notebook_panel_examples import graph_reuse_example
from notebook_panel_shapes import compile_panel_shapes, _candidates
from notebook_pen_budget import NativePenBudgetError
from notebook_procedural import _place_labels, _bounds, _segment_distance, LabelPlacementError
from notebook_story_native import native_story_bundle


class MathematicalCalloutTests(unittest.TestCase):
    def assert_on_owner(self, endpoint, owner):
        self.assertTrue(any(_segment_distance(endpoint,endpoint,a,b)<1e-8
            for command in owner for path in _primitive(command)
            for a,b in zip(path,path[1:])))

    def test_point_circle_and_open_curve_fallbacks_attach_to_actual_ink(self):
        owners=[
            [dict(op='circle',center=[300,180],radius=3)],
            [dict(op='circle',center=[300,180],radius=35)],
            [dict(op='line',**{'from':[250,180],'to':[350,180]})],
            [dict(op='polyline',points=[[240,210],[280,160],[340,180]])]]
        for owner in owners:
            with self.subTest(owner=owner):
                def candidates(box):return []
                candidates.fallback=lambda box:corner_callouts(_bounds(owner),box)
                source=deepcopy(owner)
                placed,layout=_place_labels([('note','Value',candidates)],owner,
                    fallback_attachments={'note':contour_attachment(owner,owner)})
                self.assertTrue(layout[0]['leaders'])
                self.assert_on_owner(layout[0]['leaders'][0]['to'],owner)
                self.assertEqual(placed['note'][0],layout[0]['leaders'][0])
                self.assertEqual(source,owner)

    def test_clear_primary_label_does_not_acquire_a_pointer_or_extra_padding(self):
        def candidates(box):return [(300,100)]
        candidates.fallback=lambda box:[(150,100)]
        before=_place_labels([('note','Value',candidates)],[])
        with patch('notebook_label_attachment._pointer_clear',return_value=False):
            after=_place_labels([('note','Value',candidates)],[],
                fallback_attachments={'note':lambda box:None})
        self.assertEqual(before,after)
        self.assertNotIn('leaders',after[1][0])

    def test_rejected_or_obstructed_fallback_never_returns_unowned_text(self):
        owner=[dict(op='circle',center=[300,180],radius=3)]
        wall=dict(op='line',**{'from':[380,10],'to':[380,350]})
        def candidates(box):return []
        candidates.fallback=lambda box:[(470,180)]
        with self.assertRaises(LabelPlacementError):
            _place_labels([('note','Value',candidates)],owner+[wall],
                fallback_attachments={'note':contour_attachment(owner,owner+[wall])})

    def force_point_fallback(self,bounds,side,**kwargs):
        # Isolate the fallback path without depending on a particular question
        # or solver preference: dots always have a six-unit diameter.
        if abs(bounds[2]-bounds[0]-6)<1e-8 and abs(bounds[3]-bounds[1]-6)<1e-8:
            return lambda box:[]
        return _candidates(bounds,side,**kwargs)

    def test_compiler_fallback_preserves_math_and_charges_native_ink(self):
        story,drafts=graph_reuse_example()
        original=deepcopy((story,drafts))
        with patch('notebook_panel_shapes._candidates',side_effect=self.force_point_fallback):
            compiled=compile_panel_shapes(story,drafts)
            bundle=native_story_bundle(story,drafts)
        panel=compiled['panels']['mark']
        self.assertEqual((story,drafts),original)
        self.assert_on_owner(panel['groups']['note'][0]['to'],panel['groups']['half'])
        for key,commands in compiled['panels']['curve']['groups'].items():
            self.assertEqual(panel['groups'][key],commands)
        inks=[block for block in bundle['blocks'] if block['kind']=='ink']
        self.assertTrue(all(block['stroke_count']<=64 and block['point_count']<=3000
                            for block in inks))
        self.assertLessEqual(bundle['snapshot_points'],12000)

    def test_fallback_pointers_cannot_bypass_native_stroke_limit(self):
        story,drafts=graph_reuse_example()
        excessive=[dict(op='line',**{'from':[10,10],'to':[11,10]}) for _ in range(60)]
        with patch('notebook_panel_shapes._candidates',side_effect=self.force_point_fallback), \
             patch('notebook_panel_shapes.contour_attachment',return_value=lambda box:excessive):
            with self.assertRaises(NativePenBudgetError):compile_panel_shapes(story,drafts)

    def test_remote_callout_reserves_more_space_than_local_annotation(self):
        def primary(box):return [(300,100)]
        def fallback(box):return []
        fallback.fallback=lambda box:[(300,100)]
        _,local=_place_labels([('note','Value',primary)],[])
        _,remote=_place_labels([('note','Value',fallback)],[])
        a,b=local[0]['label_box'],remote[0]['label_box']
        self.assertEqual(b,[a[0]-6,a[1]-6,a[2]+6,a[3]+6])


if __name__=='__main__':unittest.main()
