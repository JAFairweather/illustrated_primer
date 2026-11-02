from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from notebook_panel_shapes import compile_panel_shapes, _frame, _point, _hatch_region
from notebook_pen_budget import NativePenBudgetError
from notebook_drawing import preview_svg
from notebook_panel_examples import graph_reuse_example as fixture
from notebook_panel_eval import review_panels


class PanelShapesTests(unittest.TestCase):
    def test_hatching_is_diagonal_bounded_and_not_a_partition_line(self):
        for box in ([80,50,520,290], [100,90,100.1,90.1], [120,80,121,250], [90,140,500,141]):
            left,top,right,bottom=box
            lines=_hatch_region(*box)
            self.assertTrue(lines)
            self.assertEqual(lines,_hatch_region(*box))
            self.assertLessEqual(len(lines),17)
            for line in lines:
                a,b=line['from'],line['to']
                self.assertGreater(b[0],a[0])
                self.assertLess(b[1],a[1])
                self.assertAlmostEqual(b[0]-a[0],a[1]-b[1])
                for x,y in (a,b):
                    self.assertGreaterEqual(x,left-1e-9)
                    self.assertLessEqual(x,right+1e-9)
                    self.assertGreaterEqual(y,top-1e-9)
                    self.assertLessEqual(y,bottom+1e-9)

    def test_hatch_grid_is_shared_across_adjacent_regions(self):
        whole=_hatch_region(80,50,520,290)
        pieces=_hatch_region(80,50,300,290)+_hatch_region(300,50,520,290)
        def lengths(lines):
            result={}
            for line in lines:
                x,y=line['from'];end=line['to']
                key=round(x+y,7)
                result[key]=result.get(key,0)+(end[0]-x)
            return result
        self.assertEqual(set(lengths(whole)),set(lengths(pieces)))
        for key,length in lengths(whole).items():
            self.assertAlmostEqual(length,lengths(pieces)[key])

    def test_data_mapping_is_renderer_owned(self):
        frame = _frame(dict(id='ax',type='axes',x=[-2,2],y=[-1,1],aspect='independent'))
        self.assertEqual(_point(frame,[-2,-1]),[80,290])
        self.assertEqual(_point(frame,[2,1]),[520,50])
        self.assertEqual(_point(frame,[0,0]),[300,170])
        equal = _frame(dict(id='ax',type='axes',x=[0,2],y=[0,2],aspect='equal'))
        self.assertEqual(equal['box'],[180,50,420,290])

    def test_complete_story_and_exact_historical_branch(self):
        story, drafts = fixture(); original = deepcopy(drafts)
        result = compile_panel_shapes(story,drafts); panels = result['panels']
        self.assertTrue(result['geometry_validated'])
        self.assertFalse(result['native_delivery_supported'])
        self.assertEqual(drafts,original)
        self.assertEqual(panels['axes']['plan']['stages'], panels['mark']['plan']['stages'][:1])
        self.assertEqual(panels['curve']['plan']['stages'], panels['mark']['plan']['stages'][:2])
        self.assertEqual(panels['axes']['item_bounds']['ax'],panels['mark']['item_bounds']['ax'])
        self.assertEqual(list(panels['branch']['items']),['ax','linear'])
        self.assertNotIn('square',panels['branch']['items'])
        self.assertEqual([s['id'] for s in panels['branch']['plan']['stages']],['axes','branch'])
        self.assertIn('<polyline',preview_svg(panels['mark']['plan']))
        self.assertEqual(result['snapshot_points'],sum(p['snapshot_points'] for p in panels.values()))
        panels['branch']['plan']['stages'][0]['paths'][0][0]=(0,0)
        self.assertNotEqual(panels['axes']['plan']['stages'][0]['paths'][0][0],(0,0))

    def test_axis_titles_are_measured_before_mapping_and_stay_frozen(self):
        for title in ('Distance (m)', 'Downward speed (m/s)', 'Population count'):
            story, drafts = fixture()
            drafts['axes']['items'].append(dict(id='axis-title', type='label',
                to='ax', text=title, side='left'))
            result = compile_panel_shapes(story, drafts)
            panels = result['panels']
            frame = panels['axes']['frames']['ax']
            self.assertGreater(frame['box'][0], 80)
            label = next(x for x in panels['axes']['label_layout'] if x['id']=='axis-title')
            self.assertLess(label['label_box'][2], frame['box'][0])
            self.assertEqual(panels['axes']['frames'], panels['mark']['frames'])
            self.assertEqual(panels['axes']['groups']['axis-title'],
                             panels['mark']['groups']['axis-title'])
            # Data endpoints still coincide exactly with their measured frame.
            self.assertEqual(_point(frame, [0,0]), [frame['box'][0],frame['box'][3]])

    def test_future_title_is_measured_before_final_frames_are_frozen(self):
        story, drafts = fixture()
        original = compile_panel_shapes(story, drafts)['panels']['axes']['frames']
        drafts['curve']['items'].append(dict(id='late-title', type='label',
            to='ax', text='Downward speed (m/s)', side='left'))
        result = compile_panel_shapes(story, drafts)
        final = result['panels']['axes']['frames']
        self.assertGreater(final['ax']['box'][0], original['ax']['box'][0])
        self.assertEqual(result['panels']['mark']['frames'], final)
        self.assertEqual(result['panels']['axes']['plan']['stages'],
                         result['panels']['mark']['plan']['stages'][:1])

    def test_label_side_is_preferred_not_permission_to_clip_or_move_geometry(self):
        story, drafts = fixture()
        story['panels']=story['panels'][:2]; story['acts']=story['acts'][:1]
        drafts={key:drafts[key] for key in ('axes','curve')}
        drafts['curve']['items']=[
            dict(id='edge-dot',type='dot',**{'in':'ax'},at=[1,.5]),
            dict(id='name',type='label',to='edge-dot',text='Boundary point',side='right')]
        panel=compile_panel_shapes(story,drafts)['panels']['curve']
        self.assertEqual(panel['groups']['edge-dot'][0]['center'],[520,170])
        label=panel['label_layout'][0]['label_box']
        self.assertGreaterEqual(label[0],4);self.assertLessEqual(label[2],596)

    def test_late_invalid_panel_returns_no_partial_story(self):
        story,drafts = fixture()
        drafts['branch']['items'][0]['to']=[2,2]
        with self.assertRaises(ValueError):compile_panel_shapes(story,drafts)
        for missing in ('axes','mark'):
            story,drafts=fixture(); del drafts[missing]
            with self.assertRaises(ValueError):compile_panel_shapes(story,drafts)

    def test_changing_narrative_intent_does_not_change_any_ink(self):
        story, drafts = fixture()
        before = compile_panel_shapes(story, drafts)
        story['panels'][1]['visual_kind'] = 'relationship'
        story['panels'][2]['visual_kind'] = 'comparison'
        after = compile_panel_shapes(story, drafts)
        self.assertEqual(before, after)
        # Metadata cannot authorize changes to a previously drawn object.
        drafts['curve']['items'][0]['id'] = 'ax'
        with self.assertRaisesRegex(ValueError, 'redefine'):
            compile_panel_shapes(story, drafts)

    def test_unknown_paths_code_pixels_and_redefinitions_rejected(self):
        for key,value in (('path','/tmp/x'),('url','https://example.org'),('x',100),('width',440),('fn','x*x')):
            story,drafts=fixture();drafts['curve']['items'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):compile_panel_shapes(story,drafts)
        story,drafts=fixture();drafts['curve']['items'][0]['id']='ax'
        with self.assertRaisesRegex(ValueError,'redefine'):compile_panel_shapes(story,drafts)
        story,drafts=fixture();drafts['curve']['items'][0]['in']='missing'
        with self.assertRaisesRegex(ValueError,'axes ID'):compile_panel_shapes(story,drafts)

    def test_circles_need_equal_mathematical_scale(self):
        story,drafts=fixture()
        drafts['curve']['items']=[dict(id='c',type='circle',**{'in':'ax'},center=[.5,.5],radius=.2)]
        with self.assertRaisesRegex(ValueError,'equal axis'):compile_panel_shapes(story,drafts)
        drafts['axes']['items'][0]['aspect']='equal'
        # Keep this fixture focused on the circle, without an unrelated caption/label.
        story['panels']=story['panels'][:2];story['acts']=story['acts'][:1]
        drafts={k:drafts[k] for k in ('axes','curve')}
        result=compile_panel_shapes(story,drafts)
        self.assertAlmostEqual(result['panels']['curve']['groups']['c'][0]['radius'],48)

    def test_whole_picture_layout_avoids_later_marks_before_freezing_labels(self):
        story,drafts=fixture()
        accepted=compile_panel_shapes(story,drafts)
        box=accepted['panels']['mark']['label_layout'][0]['label_box']
        frame=accepted['panels']['mark']['frames']['ax']
        left,top,right,bottom=frame['box']
        y=(bottom-(box[1]+box[3])/2)/(bottom-top)
        story['panels'][-1]['base']='mark'
        drafts['branch']['items']=[dict(id='cross',type='hline',**{'in':'ax'},value=y)]
        original = deepcopy(accepted)
        result = compile_panel_shapes(story,drafts)
        self.assertNotEqual(result['panels']['mark']['groups']['note'],
                            accepted['panels']['mark']['groups']['note'])
        self.assertEqual(result['panels']['mark']['groups']['note'],
                         result['panels']['branch']['groups']['note'])
        self.assertEqual(result['panels']['mark']['plan']['stages'],
                         result['panels']['branch']['plan']['stages'][:-1])
        self.assertEqual(accepted, original)  # No previously returned plan mutated.

    def test_sibling_label_ids_are_scoped_but_ancestor_ink_is_shared(self):
        story,drafts=fixture()
        drafts['branch']['items'].append(dict(id='note',type='label',
            to='linear',text='Other slope',side='auto'))
        result=compile_panel_shapes(story,drafts)['panels']
        self.assertNotEqual(result['mark']['groups']['note'],result['branch']['groups']['note'])
        self.assertEqual(result['mark']['groups']['ax'],result['branch']['groups']['ax'])

    def test_independent_picture_does_not_relayout_another_picture(self):
        story,drafts=fixture()
        story['panels'][-1]['base']=None
        drafts['branch']['items']=[
            dict(id='ax',type='axes',x=[0,1],y=[0,1],aspect='independent')]
        before=compile_panel_shapes(story,drafts)['panels']['mark']
        drafts['branch']['items'].append(
            dict(id='note',type='label',to='ax',text='Separate title',side='left'))
        result=compile_panel_shapes(story,drafts)['panels']
        self.assertEqual(before,result['mark'])
        self.assertNotEqual(result['mark']['frames'],result['branch']['frames'])
        self.assertEqual([s['id'] for s in result['branch']['plan']['stages']],['branch'])

    def test_invalid_future_title_cannot_produce_any_encoded_ink(self):
        story,drafts=fixture()
        drafts['branch']['items'].append(dict(id='late-title',type='label',
            to='ax',text='Future title',side='left',url='https://example.org'))
        with tempfile.TemporaryDirectory() as tmp, patch('notebook_panel_eval.storyboard_assets') as encode:
            result=review_panels(json.dumps(story).encode(),json.dumps(drafts).encode(),
                                 Path(tmp)/'review')
        self.assertFalse(result['valid'])
        encode.assert_not_called()

    def test_polynomial_sample_endpoints_and_no_clipping(self):
        story,drafts=fixture();result=compile_panel_shapes(story,drafts)
        points=result['panels']['curve']['groups']['square'][0]['points']
        self.assertEqual(len(points),65)
        self.assertEqual(points[0],[80,290]);self.assertEqual(points[-1],[520,50])
        self.assertEqual(points[32],[300,230])
        drafts['curve']['items'][0]['coefficients']=[0,0,2]
        with self.assertRaises(ValueError):compile_panel_shapes(story,drafts)

    def test_native_stage_and_whole_story_limits_are_not_relaxed(self):
        story,drafts=fixture()
        drafts['curve']['items']=[dict(id='label-'+str(i),type='label',to='ax',text='long label',side='auto')
                                  for i in range(25)]
        with self.assertRaisesRegex(ValueError,'1..24'):compile_panel_shapes(story,drafts)
        # Twenty-four arrows expand to 72 strokes, beyond the existing 64 cap.
        drafts['curve']['items']=[dict(id='line-'+str(i),type='arrow',
                                      **{'in':'ax','from':[i/24,0],'to':[i/24,1]})
                                  for i in range(24)]
        # Isolate the resource bound from unrelated later label collisions.
        story['panels']=story['panels'][:2];story['acts']=story['acts'][:1]
        drafts={key:drafts[key] for key in ('axes','curve')}
        with self.assertRaises(NativePenBudgetError):compile_panel_shapes(story,drafts)

    def test_materialized_snapshot_cost_cannot_hide_behind_reuse(self):
        story,drafts=fixture()
        story['acts']=story['acts'][:1];story['panels']=story['panels'][:1]
        drafts={'axes':drafts['axes']}
        for i in range(1,12):
            identity='panel-'+str(i)
            panel=deepcopy(story['panels'][0]);panel.update(id=identity,base=story['panels'][-1]['id'])
            story['panels'].append(panel)
            drafts[identity]=dict(v=1,mode='panel-shapes',panel=identity,
                items=[dict(id='line-'+str(i),type='hline',**{'in':'ax'},value=i/12)])
        with self.assertRaises(NativePenBudgetError) as caught:compile_panel_shapes(story,drafts)
        self.assertEqual(caught.exception.details['scope'],'story-snapshots')
        self.assertEqual(caught.exception.details['limit'],12000)

    def test_other_primitives_use_data_coordinates_and_engine_hatching(self):
        shapes=[dict(id='shape',type='rect',x=[.2,.8],y=[.2,.8]),
                dict(id='shape',type='region',x=[.2,.8],y=[.2,.8],fill='hatch'),
                dict(id='shape',type='vline',value=.5),
                dict(id='shape',type='hline',value=.5),
                dict(id='shape',type='arrow',**{'from':[.2,.2],'to':[.8,.8]}),
                dict(id='shape',type='polyline',points=[[0,.5],[.5,1],[1,.5]])]
        for shape in shapes:
            story,drafts=fixture();story['panels']=story['panels'][:2];story['acts']=story['acts'][:1]
            drafts={key:drafts[key] for key in ('axes','curve')}
            drafts['curve']['items']=[dict(shape,**{'in':'ax'})]
            with self.subTest(kind=shape['type']):
                panel=compile_panel_shapes(story,drafts)['panels']['curve']
                box=panel['item_bounds']['shape']
                self.assertTrue(all(0<=v<=600 for v in box))
                self.assertGreater(panel['added_points'],0)
                if shape['type']=='region':
                    # One rectangle plus nine clipped diagonal fill strokes.
                    self.assertEqual(len(panel['groups']['shape']),10)

    def test_exact_axis_numbers_and_invalid_data_ranges(self):
        for ranges in ([0,0],[1,0],[False,1],[0,float('nan')],[0,float('inf')],[-1e9,1]):
            with self.subTest(ranges=ranges),self.assertRaises(ValueError):
                _frame(dict(id='ax',type='axes',x=ranges,y=[0,1],aspect='equal'))
        story,drafts=fixture();story['panels']=story['panels'][:1];story['acts']=story['acts'][:1]
        drafts={'axes':drafts['axes']};drafts['axes']['items'][0]['x']=[0,.123456789]
        panel=compile_panel_shapes(story,drafts)['panels']['axes']
        self.assertEqual(panel['label_layout'][1]['lines'],['0.123456789'])

    def test_offline_encoder_and_preview_with_failure_before_assets(self):
        story,drafts=fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=review_panels(json.dumps(story).encode(),json.dumps(drafts).encode(),root/'ok')
            self.assertTrue(result['valid'])
            self.assertTrue(result['ink_encoding_validated'])
            self.assertTrue(result['preview_complete'])
            self.assertFalse(result['tablet_proven'])
            self.assertFalse(result['native_delivery_supported'])
            self.assertEqual(list((root/'ok').glob('*.rm')),[])
            self.assertEqual(len(list((root/'ok').glob('*.svg'))),4)
            drafts['branch']['items'][0]['to']=[2,2]
            with patch('notebook_panel_eval.storyboard_assets') as encoder:
                failed=review_panels(json.dumps(story).encode(),json.dumps(drafts).encode(),root/'failed')
                encoder.assert_not_called()
            self.assertFalse(failed['valid'])
            self.assertEqual(list((root/'failed').glob('*.png')),[])
            self.assertTrue((root/'failed'/'result.json').exists())
            with self.assertRaises(FileExistsError):
                review_panels(json.dumps(story).encode(),json.dumps(drafts).encode(),root/'ok')


if __name__=='__main__':unittest.main()
