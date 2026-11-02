from copy import deepcopy
import unittest
from unittest.mock import patch

from notebook_label_attachment import contour_attachment
from notebook_lesson import _primitive
from notebook_panel_examples import relationship_example
from notebook_panel_shapes import compile_panel_shapes
from notebook_pen_budget import NativePenBudgetError
from notebook_procedural import _object, _bounds, _segment_distance
from notebook_stroke_asset import storyboard_assets


class ContourAttachmentTests(unittest.TestCase):
    def assert_on_contour(self, point, owner):
        self.assertTrue(any(_segment_distance(point,point,a,b)<1e-8
                            for command in owner for path in _primitive(command)
                            for a,b in zip(path,path[1:])))

    def test_symbolic_contours_have_real_attachment_points_on_all_sides(self):
        for shape in ('circle','person','sun','cloud','water'):
            owner=_object(shape,300,180);original=deepcopy(owner)
            left,top,right,bottom=_bounds(owner)
            boxes=((right+20,165,right+80,195),(left-80,165,left-20,195),
                   (270,top-55,330,top-20),(270,bottom+20,330,bottom+55))
            attach=contour_attachment(owner,owner)
            for box in boxes:
                with self.subTest(shape=shape,box=box):
                    pointer=attach(box)
                    self.assertIsNotNone(pointer)
                    self.assertEqual(len(pointer),1)
                    self.assert_on_contour(pointer[0]['to'],owner)
                    self.assertEqual(pointer,attach(box))
            self.assertEqual(owner,original)

    def test_diagonal_circle_label_does_not_attach_to_empty_bounding_corner(self):
        owner=[dict(op='circle',center=[150,150],radius=40)]
        pointer=contour_attachment(owner,owner)([220,60,280,100])
        self.assertEqual(len(pointer),1)
        self.assert_on_contour(pointer[0]['to'],owner)
        self.assertNotEqual(pointer[0]['to'],[190,110])

    def test_only_labels_inside_actual_closed_contour_are_pointer_free(self):
        owner=[dict(op='circle',center=[150,150],radius=40)]
        attach=contour_attachment(owner,owner)
        self.assertEqual(attach([140,140,160,160]),[])
        self.assertNotEqual(attach([112,112,124,124]),[])
        with self.assertRaises(ValueError):contour_attachment([],[])

    def test_pointer_cannot_cross_an_obstacle_or_enclosing_other_contour(self):
        owner=[dict(op='circle',center=[150,150],radius=40)]
        wall=dict(op='line',**{'from':[210,20],'to':[210,300]})
        self.assertIsNone(contour_attachment(owner,owner+[wall])([230,135,280,165]))
        outside=dict(op='circle',center=[150,150],radius=48)
        self.assertIsNone(contour_attachment(owner,owner+[outside])([230,135,280,165]))

    def test_compiler_preserves_annotation_on_inherited_circle(self):
        story,drafts=relationship_example()
        drafts['objects']['items'][0]['shape']='circle'
        original=deepcopy(drafts)
        panels=compile_panel_shapes(story,drafts)['panels']
        group=panels['objects']['groups']['input-name']
        self.assertEqual(group[0]['op'],'line')
        self.assert_on_contour(group[0]['to'],panels['objects']['groups']['input'])
        self.assertEqual(group,panels['observer']['groups']['input-name'])
        self.assertEqual(drafts,original)
        self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000
                            for a in storyboard_assets(panels['observer']['plan'])))

    def test_contour_pointers_remain_inside_native_stroke_budget(self):
        story,drafts=relationship_example()
        story['panels']=story['panels'][:1]
        drafts={'objects':drafts['objects']}
        drafts['objects']['items']=[drafts['objects']['items'][i] for i in (0,2)]
        drafts['objects']['items'][0]['shape']='circle'
        excessive=[dict(op='line',**{'from':[10,10],'to':[11,10]}) for _ in range(62)]
        with patch('notebook_panel_shapes.contour_attachment',return_value=lambda box:excessive):
            with self.assertRaises(NativePenBudgetError) as error:
                compile_panel_shapes(story,drafts)
        self.assertEqual(error.exception.details['limit'],64)
        self.assertEqual(error.exception.details['resource'],'strokes')


if __name__=='__main__':unittest.main()
