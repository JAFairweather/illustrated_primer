from copy import deepcopy
import unittest
from unittest.mock import patch

from notebook_label_attachment import region_attachment, contour_attachment
from notebook_label_candidates import corner_callouts
from notebook_panel_examples import graph_reuse_example, relationship_example
from notebook_panel_shapes import compile_panel_shapes, _axis_title_candidates, _candidates
from notebook_procedural import (_place_labels, LabelPlacementError,
                                 _route_label_candidates, _label_group, _group_label_bounds)
from notebook_stroke_asset import storyboard_assets
from notebook_pen_budget import NativePenBudgetError


class LabelAttachmentTests(unittest.TestCase):
    def test_dot_pointer_cannot_cross_an_axis_to_reach_its_label(self):
        dot=dict(op='circle',center=[200,190],radius=3)
        axis=dict(op='line',**{'from':[100,200],'to':[300,200]})
        attach=contour_attachment([dot],[dot,axis])
        self.assertIsNone(attach([180,220,220,240]))
        pointer=attach([180,150,220,170])
        self.assertEqual(len(pointer),1)
        self.assertLess(pointer[0]['to'][1],200)

    def test_point_labels_have_checked_pointers_for_every_side_preference(self):
        import math
        for side in ('auto','top','bottom','left','right'):
            with self.subTest(side=side):
                story,drafts=graph_reuse_example()
                drafts['mark']['items'][1]['side']=side
                original=deepcopy(drafts)
                result=compile_panel_shapes(story,drafts)
                panel=result['panels']['mark']
                label=next(row for row in panel['label_layout'] if row['id']=='note')
                self.assertEqual(' '.join(label['lines']),'one quarter')
                self.assertEqual(label['size'],18)
                self.assertEqual(len(label['leaders']),1)
                dot=panel['groups']['half'][0]
                # The endpoint lies on the tiny dot's actual polygonal ink,
                # rather than on an axis or at an empty bounding-box corner.
                radius=math.dist(dot['center'],label['leaders'][0]['to'])
                self.assertAlmostEqual(radius,3,delta=.1)
                self.assertEqual(panel['groups']['note'][0],label['leaders'][0])
                self.assertEqual(panel['groups']['square'],result['panels']['curve']['groups']['square'])
                self.assertEqual(drafts,original)
                self.assertEqual(result,compile_panel_shapes(story,drafts))

    def test_point_attachment_is_inherited_and_consumes_native_budget(self):
        story,drafts=graph_reuse_example()
        story['panels'][-1]['base']='mark'
        panels=compile_panel_shapes(story,drafts)['panels']
        self.assertEqual(panels['mark']['groups']['note'],panels['branch']['groups']['note'])
        self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000
                            for a in storyboard_assets(panels['branch']['plan'])))
        excessive=[dict(op='line',**{'from':[10,10],'to':[11,10]}) for _ in range(61)]
        with patch('notebook_panel_shapes.contour_attachment',return_value=lambda box:excessive):
            with self.assertRaises(NativePenBudgetError):
                compile_panel_shapes(story,drafts)

    def test_near_axis_point_uses_clear_diagonal_callout_without_shrinking(self):
        dot=dict(op='circle',center=[124,284],radius=3)
        geometry=[dot,
            dict(op='line',**{'from':[80,50],'to':[80,290]}),
            dict(op='line',**{'from':[80,290],'to':[520,290]}),
            dict(op='polyline',points=[[80,286],[124,284],[168,281],[212,277],
                                      [256,270],[300,260],[344,244],[388,223],
                                      [432,190],[476,141],[520,72]])]
        bounds=[121,281,127,287]
        candidates=_candidates(bounds,'right')
        attach=contour_attachment([dot],geometry)
        # The ordinary candidates strand this long annotation between a
        # frame edge and a shallow curve. Do not drop the ownership rule.
        with self.assertRaises(LabelPlacementError):
            _place_labels([('note','point annotation',candidates)],geometry,
                          attachments={'note':attach})
        candidates.fallback=lambda box:corner_callouts(bounds,box,diagonal=True)
        groups,layout=_place_labels([('note','point annotation',candidates)],geometry,
                                   attachments={'note':attach})
        self.assertEqual(layout[0]['size'],18)
        self.assertEqual(' '.join(layout[0]['lines']),'point annotation')
        self.assertEqual(len(layout[0]['leaders']),1)
        self.assertEqual(groups['note'][0],layout[0]['leaders'][0])

    def setUp(self):
        self.bounds = [100,100,200,200]
        self.geometry = [dict(op='rect', origin=[100,100], size=[100,100])]

    def test_pointer_ends_at_middle_of_facing_target_edge(self):
        attach = region_attachment(self.bounds,self.geometry)
        for box,end in [([220,135,260,165],[200,150]),
                        ([40,135,80,165],[100,150]),
                        ([130,60,170,80],[150,100]),
                        ([130,220,170,240],[150,200]),
                        ([210,20,250,40],[150,100])]:
            with self.subTest(box=box):
                leader = attach(box)
                self.assertEqual(len(leader),1)
                self.assertEqual(leader[0]['op'],'line')
                self.assertEqual(leader[0]['to'],end)
                self.assertEqual(leader,attach(box))

    def test_inside_label_needs_no_pointer_and_boundary_straddle_rejected(self):
        attach = region_attachment(self.bounds,self.geometry)
        self.assertEqual(attach([120,120,180,160]),[])
        self.assertIsNone(attach([90,140,130,170]))
        self.assertIsNone(attach([201,130,230,170]))

    def test_later_empty_sibling_region_cannot_acquire_an_earlier_label(self):
        strip = dict(op='rect',origin=[100,50],size=[100,50])
        box = [120,60,180,80]
        self.assertTrue(region_attachment(self.bounds,self.geometry)(box))
        for attach in (region_attachment(self.bounds,self.geometry+[strip]),
                       contour_attachment(self.geometry,self.geometry+[strip])):
            self.assertIsNone(attach(box))
            self.assertEqual(attach([120,120,180,160]),[])

    def test_child_and_overlapping_regions_are_competitors_but_parent_is_not(self):
        parent = dict(op='rect',origin=[50,50],size=[200,200])
        child = dict(op='rect',origin=[110,110],size=[80,60])
        overlapping = dict(op='rect',origin=[150,110],size=[100,60])
        box = [160,130,180,150]
        self.assertEqual(region_attachment(self.bounds,self.geometry+[parent])(box),[])
        for other in (child,overlapping):
            self.assertIsNone(region_attachment(self.bounds,self.geometry+[other])(box))
        # An external label may still use space inside a containing parent,
        # provided its pointer makes the smaller target unambiguous.
        self.assertTrue(region_attachment(self.bounds,self.geometry+[parent])([120,65,180,85]))

    def test_complete_picture_reserves_future_regions_without_moving_inherited_text(self):
        story,drafts=graph_reuse_example()
        story['panels']=story['panels'][:3];story['acts']=story['acts'][:1]
        drafts={key:drafts[key] for key in ('axes','curve','mark')}
        drafts['curve']['items']=[
            dict(id='inner',type='rect',**{'in':'ax'},x=[.1,.7],y=[.1,.6]),
            dict(id='name',type='label',to='inner',text='Inner',side='top')]
        drafts['mark']['items']=[
            dict(id='strip',type='rect',**{'in':'ax'},x=[.1,.7],y=[.6,.95]),
            dict(id='outer',type='rect',**{'in':'ax'},x=[.1,.7],y=[.1,.95])]
        original=deepcopy(drafts)
        panels=compile_panel_shapes(story,drafts)['panels']
        label=next(row for row in panels['curve']['label_layout'] if row['id']=='name')
        l,t,r,b=panels['mark']['item_bounds']['strip']; box=label['label_box']
        self.assertFalse(box[0]<r and box[2]>l and box[1]<b and box[3]>t)
        self.assertEqual(panels['curve']['groups']['name'],panels['mark']['groups']['name'])
        self.assertEqual(drafts,original)
        self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000
                            for a in storyboard_assets(panels['mark']['plan'])))

    def test_pointer_cannot_cross_other_ink_or_run_along_target_border(self):
        obstacles = self.geometry + [dict(op='line', **{'from':[210,110],'to':[210,190]})]
        self.assertIsNone(region_attachment(self.bounds,obstacles)([220,135,260,165]))
        near_endpoint = self.geometry + [dict(op='line', **{'from':[201,110],'to':[201,190]})]
        self.assertIsNone(region_attachment(self.bounds,near_endpoint)([220,135,260,165]))
        # A coincident parent border is allowed only at the attachment endpoint.
        parent = dict(op='rect', origin=[100,100], size=[200,100])
        attach = region_attachment(self.bounds,self.geometry+[parent])
        self.assertIsNotNone(attach([130,60,170,80]))
        # A shallow diagonal hugs the top border: retain the clearance rule.
        self.assertIsNone(attach([230,60,280,80]))

    def test_pointer_tip_may_approach_hatching_without_crossing_it(self):
        hatch = dict(op='line', **{'from':[149,200],'to':[160,189]})
        attach = region_attachment(self.bounds,self.geometry+[hatch])
        self.assertIsNotNone(attach([130,220,170,240]))

    def test_divider_at_midpoint_uses_clear_interior_edge_anchor(self):
        # Works on every side; no fraction/question-specific placement rule.
        for box,divider,axis,edge in (
                ([120,50,180,80], [[150,20],[150,200]], 1,100),
                ([120,220,180,250], [[150,100],[150,280]], 1,200),
                ([40,120,80,180], [[20,150],[200,150]], 0,100),
                ([220,120,260,180], [[100,150],[280,150]], 0,200)):
            with self.subTest(box=box):
                geometry=self.geometry+[dict(op='line',**{'from':divider[0],'to':divider[1]})]
                before=deepcopy(geometry)
                attach=region_attachment(self.bounds,geometry)
                pointer=attach(box)
                self.assertEqual(len(pointer),1)
                self.assertEqual(pointer[0]['to'][axis],edge)
                self.assertEqual(pointer[0]['to'][1-axis],125)
                self.assertEqual(pointer,attach(box))
                self.assertEqual(geometry,before)

    def test_divided_region_joint_labels_slide_without_changing_words_or_geometry(self):
        bounds=[124,110,300,158]
        geometry=[dict(op='rect',origin=[124,110],size=[176,48]),
                  dict(op='line',**{'from':[212,50],'to':[212,290]}),
                  dict(op='line',**{'from':[300,50],'to':[300,290]})]
        original=deepcopy(geometry)
        items=[('first','Selected area',_candidates(bounds,'top')),
               ('second','Same region',_candidates(bounds,'bottom'))]
        attach=region_attachment(bounds,geometry)
        groups,layout=_place_labels(items,geometry,attachments={'first':attach,'second':attach})
        self.assertEqual(geometry,original)
        self.assertEqual([row['size'] for row in layout],[18,18])
        self.assertEqual([' '.join(row['lines']) for row in layout],['Selected area','Same region'])
        self.assertTrue(all(row['leaders'] for row in layout))
        for group in groups.values():
            end=group[0]['to']
            self.assertTrue((end[1] in (110,158) and 124<end[0]<300) or
                            (end[0] in (124,300) and 110<end[1]<158))
        self.assertEqual((groups,layout),_place_labels(items,geometry,
                         attachments={'first':attach,'second':attach}))

    def test_joint_search_rejects_pointer_through_another_label(self):
        items=[('a','A',[(100,100)]),('b','B',[(250,100)])]
        def pointer(box):
            return [dict(op='line', **{'from':[140,90],'to':[300,90]})]
        with self.assertRaises(LabelPlacementError):
            _place_labels(items,[],attachments={'a':pointer})
        # Without pointers, the established two-label layout still succeeds.
        placed,_=_place_labels(items,[])
        self.assertEqual(set(placed),{'a','b'})

    def test_joint_search_rejects_crossing_pointers(self):
        items=[('a','A',[(100,60)]),('b','B',[(400,60)])]
        attachments={
            'a':lambda box:[dict(op='line', **{'from':[150,150],'to':[350,250]})],
            'b':lambda box:[dict(op='line', **{'from':[150,250],'to':[350,150]})]}
        with self.assertRaises(LabelPlacementError):
            _place_labels(items,[],attachments=attachments)

    def test_pointer_cannot_cross_a_reserved_label_box(self):
        pointer=lambda box:[dict(op='line', **{'from':[140,90],'to':[300,90]})]
        with self.assertRaises(LabelPlacementError):
            _place_labels([('a','A',[(100,100)])],[],[(200,80,220,100)],
                          attachments={'a':pointer})

    def test_pointer_geometry_is_not_exempt_from_native_stroke_cap(self):
        story,drafts=graph_reuse_example()
        story['panels']=story['panels'][:2];story['acts']=story['acts'][:1]
        drafts={key:drafts[key] for key in ('axes','curve')}
        drafts['curve']['items']=[
            dict(id='area',type='rect',**{'in':'ax'},x=[.2,.7],y=[.2,.6]),
            dict(id='caption',type='label',to='area',text='Area',side='top')]
        # 62 pointers + rectangle + one label = 64 commands, but the glyph's
        # multiple strokes must still exceed the separate native stroke cap.
        excessive=[dict(op='line',**{'from':[10,10],'to':[11,10]}) for _ in range(62)]
        with patch('notebook_panel_shapes.region_attachment',return_value=lambda box:excessive):
            with self.assertRaises(NativePenBudgetError) as error:
                compile_panel_shapes(story,drafts)
        self.assertEqual(error.exception.details['resource'],'strokes')
        self.assertEqual(error.exception.details['limit'],64)

    def test_later_panels_inherit_exact_annotation_ink_and_native_counts(self):
        story,drafts=graph_reuse_example()
        story['panels']=story['panels'][:3];story['acts']=story['acts'][:1]
        drafts={key:drafts[key] for key in ('axes','curve','mark')}
        drafts['curve']['items']=[
            dict(id='area',type='region',**{'in':'ax'},x=[.2,.7],y=[.2,.6],fill='hatch'),
            dict(id='area-label',type='label',to='area',text='Selected area',side='top')]
        drafts['mark']['items']=[dict(id='new-dot',type='dot',**{'in':'ax'},at=[.9,.9])]
        original=deepcopy(drafts)
        panels=compile_panel_shapes(story,drafts)['panels']
        self.assertEqual(drafts,original)
        group=panels['curve']['groups']['area-label']
        self.assertEqual(group[0]['op'],'line')
        self.assertEqual(' '.join(c['text'] for c in group if c['op']=='label'),'Selected area')
        self.assertEqual(group,panels['mark']['groups']['area-label'])
        self.assertEqual(panels['curve']['plan']['stages'],panels['mark']['plan']['stages'][:-1])
        placement=next(p for p in panels['curve']['label_layout'] if p['id']=='area-label')
        self.assertEqual(placement['leaders'],group[:1])
        assets=storyboard_assets(panels['mark']['plan'])
        self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000 for a in assets))
        self.assertEqual(assets[1]['stroke_count'],len(panels['curve']['plan']['stages'][-1]['paths']))

    def test_axis_title_candidates_never_move_to_a_different_edge(self):
        bounds=[80,50,520,290]
        local=[-30,-18,30,0]
        for side in ('top','bottom','left','right','auto'):
            choices=_axis_title_candidates(bounds,side)(local)
            self.assertTrue(choices)
            for x,y in choices:
                if side in ('top','auto'):self.assertLessEqual(y+local[3],bounds[1])
                elif side=='bottom':self.assertGreaterEqual(y+local[1],bounds[3])
                elif side=='left':self.assertLessEqual(x+local[2],bounds[0])
                else:self.assertGreaterEqual(x+local[0],bounds[2])

    def test_curve_label_uses_actual_path_before_empty_bounding_box_corners(self):
        story,drafts=graph_reuse_example()
        story['panels']=story['panels'][:2];story['acts']=story['acts'][:1]
        drafts={key:drafts[key] for key in ('axes','curve')}
        drafts['curve']['items'].append(
            dict(id='name',type='label',to='square',text='Curve',side='top'))
        panel=compile_panel_shapes(story,drafts)['panels']['curve']
        label=next(x for x in panel['label_layout'] if x['id']=='name')
        paths=panel['groups']['square'][0]['points']
        local=_group_label_bounds(_label_group(('Curve',),0,0))
        expected=_route_label_candidates(paths,local)
        actual=panel['groups']['name'][-1]
        box=label['label_box']
        center=((box[0]+box[2])/2,actual['at'][1])
        self.assertTrue(any(abs(center[0]-x)<1e-8 and abs(center[1]-y)<1e-8 for x,y in expected))

    def test_connector_side_preferences_never_select_remote_box_candidates(self):
        for side in ('auto','top','bottom','left','right'):
            story,drafts=relationship_example()
            story['panels']=story['panels'][:2]
            drafts={key:drafts[key] for key in ('objects','forward')}
            drafts['forward']['items'][1]['side']=side
            result=compile_panel_shapes(story,drafts)['panels']['forward']
            label=next(row for row in result['label_layout'] if row['id']=='flow-name')
            local=_group_label_bounds(_label_group(tuple(label['lines']),0,0))
            expected=_route_label_candidates(result['groups']['flow'][0]['points'],local,
                                             gaps=(12,24,36,48))
            actual=result['groups']['flow-name'][-1]
            box=label['label_box'];center=((box[0]+box[2])/2,actual['at'][1])
            self.assertTrue(any(abs(center[0]-x)<1e-8 and abs(center[1]-y)<1e-8 for x,y in expected))

    def test_symbolic_box_label_has_visible_pointer_to_its_own_box(self):
        story,drafts=relationship_example()
        result=compile_panel_shapes(story,drafts)['panels']['objects']
        for identity,target in (('input-name','input'),('output-name','output')):
            label=next(row for row in result['label_layout'] if row['id']==identity)
            self.assertTrue(label['leaders'])
            left,top,right,bottom=result['item_bounds'][target]
            x,y=label['leaders'][0]['to']
            self.assertTrue((x in (left,right) and top<=y<=bottom) or
                            (y in (top,bottom) and left<=x<=right))

    def test_wide_connector_label_clears_endpoint_shapes_without_changing_owner(self):
        story,drafts=relationship_example()
        story['panels']=story['panels'][:2]
        drafts={key:drafts[key] for key in ('objects','forward')}
        drafts['objects']['items']=[
            dict(id='source',type='object',shape='box',position='top-left'),
            dict(id='relay',type='object',shape='box',position='top-center'),
            dict(id='receiver',type='object',shape='person',position='top-right')]
        drafts['forward']['items']=[
            dict(id='incoming',type='connect',**{'from':'source','to':'relay'}),
            dict(id='outgoing',type='connect',**{'from':'relay','to':'receiver'}),
            dict(id='name',type='label',to='outgoing',text='delivered information',side='bottom')]
        original=deepcopy(drafts)
        panel=compile_panel_shapes(story,drafts)['panels']['forward']
        label=next(row for row in panel['label_layout'] if row['id']=='name')
        self.assertEqual(' '.join(label['lines']),'delivered information')
        self.assertEqual(label['size'],18)
        center=(label['label_box'][0]+label['label_box'][2])/2
        path=panel['groups']['outgoing'][0]['points']
        self.assertGreaterEqual(center,min(p[0] for p in path))
        self.assertLessEqual(center,max(p[0] for p in path))
        local=_group_label_bounds(_label_group(tuple(label['lines']),0,0))
        # Short offsets collide with the flanking shapes. More clearance is
        # allowed only along this same connector, never near the incoming one.
        baseline=panel['groups']['name'][-1]['at'][1]
        self.assertFalse(any(abs(center-x)<1e-8 and abs(baseline-y)<1e-8
                             for x,y in _route_label_candidates(path,local)))
        self.assertEqual(drafts,original)
        self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000
                            for a in storyboard_assets(panel['plan'])))


if __name__=='__main__': unittest.main()
