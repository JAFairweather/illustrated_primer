import copy
import json
import unittest
from unittest.mock import patch

from notebook_anchored_labels import resolve_labels
from notebook_lesson import compile_lesson, LessonLayoutError
from notebook_lesson_native import native_semantic_bundle
from notebook_procedural import LabelPlacementError
from notebook_semantic import SemanticError


def steps():
    return [
        {'caption':'Name a bounded region.','draw':[
            {'op':'rect','id':'region','origin':[210,100],'size':[180,120]},
            {'op':'label','target':'region','text':'Area'}]},
        {'caption':'Divide it without crossing the label.','draw':[
            {'op':'line','from':[210,160],'to':[390,160]}]},
        {'caption':'Name a separate point.','draw':[
            {'op':'circle','id':'point','center':[500,100],'radius':25},
            {'op':'label','target':'point','text':'P'}]}]


def spec(source):
    return dict(v=1,mode='lesson',intent='A growing labelled drawing',scene={'family':'drawing'},
                steps=source,claims=[],takeaway='Names stay associated with their objects.')


class AnchoredLabelTests(unittest.TestCase):
    def test_short_arrow_label_clears_neighbouring_geometry(self):
        source=[{'caption':'A short connection beside a region.','draw':[
            {'op':'rect','origin':[205,145],'size':[90,70]},
            {'op':'arrow','id':'edge','from':[300,180],'to':[350,180]},
            {'op':'label','target':'edge','text':'motion'},
            {'op':'line','from':[170,250],'to':[350,250]}]}]
        saved=copy.deepcopy(source)
        plan=compile_lesson(source,'The connection remains unchanged.',allow_short=True)
        self.assertEqual(source,saved)
        self.assertEqual(plan['anchored_labels'][0]['target'],'edge')
        self.assertTrue(all(s['points']<=3000 and len(s['paths'])<=64 for s in plan['stages']))

    def test_winding_open_path_label_can_clear_the_whole_contour(self):
        for flip_x in (False,True):
            for flip_y in (False,True):
                def point(x,y):return [600-x if flip_x else x,360-y if flip_y else y]
                source=[{'caption':'Name the winding path.','draw':[
                    {'op':'polyline','id':'path','points':[point(x,y) for x,y in
                        [(80,180),(110,180),(125,155),(145,205),(165,155),(185,205),(205,180)]]},
                    {'op':'label','target':'path','text':'Contour'},
                    {'op':'line','from':point(80,90),'to':point(80,270)},
                    {'op':'polyline','points':[point(x,y) for x,y in
                        [(205,145),(295,145),(295,215),(205,215),(205,145)]]}]}]
                saved=copy.deepcopy(source)
                with self.subTest(flip_x=flip_x,flip_y=flip_y):
                    plan=compile_lesson(source,'The name belongs to the entire contour.',allow_short=True)
                    self.assertEqual(source,saved)
                    self.assertEqual(plan,compile_lesson(source,plan['takeaway'],allow_short=True))
                    box=plan['anchored_labels'][0]['label_box']
                    self.assertTrue(box[3]<155 or box[1]>205)
                    self.assertTrue(all(s['points']<=3000 and len(s['paths'])<=64 for s in plan['stages']))

    def test_edge_labels_slide_without_moving_objects_or_later_obstacles(self):
        # Reflect the same geometry into every corner. No topic vocabulary or
        # per-question coordinates belong to the placement policy.
        for flip_x in (False,True):
            for flip_y in (False,True):
                def point(x,y):return [600-x if flip_x else x,360-y if flip_y else y]
                source=[{'caption':'Identify the endpoint.','draw':[
                    {'op':'circle','id':'node','center':point(550,300),'radius':15},
                    {'op':'label','target':'node','text':'Receiver'}]},
                    {'caption':'Add an incoming path.','draw':[
                        {'op':'arrow','from':point(475,285),'to':point(540,300)}]},
                    {'caption':'Add the second path.','draw':[
                        {'op':'arrow','from':point(430,85),'to':point(540,285)}]}]
                saved=copy.deepcopy(source)
                with self.subTest(flip_x=flip_x,flip_y=flip_y):
                    plan=compile_lesson(source,'The label remains attached to its endpoint.')
                    resolved,layout=resolve_labels(source)
                    self.assertEqual(source,saved)
                    self.assertEqual((resolved,layout),resolve_labels(source))
                    box=layout[0]['label_box']
                    self.assertTrue(4<=box[0]<box[2]<=596 and 4<=box[1]<box[3]<=356)
                    self.assertEqual(layout[0]['text'],'Receiver')
                    self.assertEqual(layout[0]['size'],18)
                    for before,after in zip(source,resolved):
                        self.assertEqual([{k:v for k,v in c.items() if k!='id'} for c in before['draw'] if c['op']!='label'],
                                         [c for c in after['draw'] if c['op']!='label'])
                    self.assertEqual(len(native_semantic_bundle(json.dumps(spec(source)))['sources']),3)
                    self.assertTrue(all(s['points']<=3000 and len(s['paths'])<=64 for s in plan['stages']))

    def test_final_geometry_placement_preserves_original_shapes_and_captions(self):
        original=steps();saved=copy.deepcopy(original)
        resolved,layout=resolve_labels(original)
        self.assertEqual(original,saved)
        self.assertEqual((resolved,layout),resolve_labels(original))
        for before,after in zip(original,resolved):
            self.assertEqual(before['caption'],after['caption'])
            geometry=[{k:v for k,v in c.items() if k!='id'} for c in before['draw'] if c['op']!='label']
            self.assertEqual(geometry,[c for c in after['draw'] if c['op']!='label'])
        area=next(r for r in layout if r['target']=='region')
        # Future dividing stroke prevents a centre label: whole-plan placement.
        self.assertFalse(area['label_box'][1]<=160<=area['label_box'][3])
        plan=compile_lesson(original,'Names stay associated with their objects.')
        self.assertEqual(plan['stages'],compile_lesson(resolved,plan['takeaway'])['stages'])
        self.assertEqual(plan['anchored_labels'],layout)
        bundle=native_semantic_bundle(json.dumps(spec(original)))
        self.assertEqual(len(bundle['sources']),3)

    def test_explicit_labels_are_never_moved_or_repaired(self):
        source=steps()
        source[0]['draw'][1]={'op':'label','at':[270,170],'text':'Area','size':18}
        resolved,_=resolve_labels(source)
        self.assertEqual(resolved[0]['draw'][1],source[0]['draw'][1])
        with self.assertRaises(LessonLayoutError):compile_lesson(source,'Keep the explicit coordinates.')

    def test_fixed_label_boxes_are_reserved_not_only_individual_glyph_strokes(self):
        source=steps()
        source[2]['draw'].insert(1,{'op':'label','at':[492,108],'text':'A','size':18})
        plan=compile_lesson(source,'Keep existing labels clear.')
        resolved,_=resolve_labels(source)
        self.assertEqual(resolved[2]['draw'][1],source[2]['draw'][1])
        self.assertEqual(len(plan['anchored_labels']),2)

    def test_invalid_reference_order_schema_and_limits_allocate_nothing(self):
        changes=[
            lambda s:s[0]['draw'][1].update(target='missing'),
            lambda s:s[0]['draw'][1].update(target='point'),
            lambda s:s[0]['draw'].reverse(),
            lambda s:s[2]['draw'][0].update(id='region'),
            lambda s:s[0]['draw'][0].update(id='/tmp/file'),
            lambda s:s[0]['draw'][1].update(at=[50,50]),
            lambda s:s[0]['draw'][1].update(size=12),
            lambda s:s[0]['draw'][1].update(text=''),
            lambda s:s[0]['draw'][1].update(url='https://example.org'),
            lambda s:s[0]['draw'][0].update(origin=[601,100])]
        for change in changes:
            source=steps();change(source)
            with self.subTest(source=source):
                with patch('notebook_lesson_native.storyboard_assets') as encode,patch('notebook_lesson_native.uuid.uuid4') as allocate:
                    with self.assertRaises(SemanticError):native_semantic_bundle(json.dumps(spec(source)))
                    encode.assert_not_called();allocate.assert_not_called()

    def test_no_clear_final_space_is_held_without_partial_native_allocation(self):
        source=[{'caption':'An object.','draw':[{'op':'circle','id':'c','center':[300,180],'radius':20}]},
                {'caption':'Name the object.','draw':[{'op':'label','target':'c','text':'Cloud'}]},
                {'caption':'Future geometry occupies all nearby label positions.','draw':[
                    {'op':'line','from':[50,y],'to':[550,y]} for y in range(90,271,30)]}]
        with patch('notebook_lesson_native.storyboard_assets') as encode:
            with self.assertRaisesRegex(SemanticError,'label location'):native_semantic_bundle(json.dumps(spec(source)))
            encode.assert_not_called()

    def test_a_label_with_no_clear_space_is_left_out_when_asked(self):
        source=[{'caption':'An object.','draw':[{'op':'circle','id':'c','center':[300,180],'radius':20},
                                                 {'op':'label','target':'c','text':'Cloud'}]},
                {'caption':'Future geometry occupies all nearby label positions.','draw':[
                    {'op':'line','from':[50,y],'to':[550,y]} for y in range(90,271,30)]}]
        with self.assertRaisesRegex(LabelPlacementError,'label location'):resolve_labels(copy.deepcopy(source))
        dropped=[]
        resolved,layout=resolve_labels(copy.deepcopy(source),dropped)
        self.assertEqual(dropped,[('step 1 command 2','Cloud')])
        self.assertEqual(layout,[])
        self.assertEqual([c['op'] for c in resolved[0]['draw']],['circle'])
        plan=compile_lesson(copy.deepcopy(source),'Clouds.',allow_short=True,drop_colliding_labels=True)
        self.assertIn(('step 1 command 2','Cloud'),plan['dropped_labels'])

    def test_a_label_too_long_to_anchor_is_left_out_when_asked(self):
        source=[{'caption':'A region.','draw':[{'op':'rect','id':'r','origin':[100,100],'size':[300,120]},
                                               {'op':'label','target':'r','text':'critical strip 0 < Re(s) < 1'},
                                               {'op':'label','target':'r','text':'strip'}]}]
        with self.assertRaisesRegex(ValueError,'excessive lesson text'):resolve_labels(copy.deepcopy(source))
        dropped=[]
        resolved,layout=resolve_labels(copy.deepcopy(source),dropped)
        self.assertEqual(dropped,[('step 1 command 2','critical strip 0 < Re(s) < 1')])
        self.assertEqual([p['text'] for p in layout],['strip'])

    def test_excessive_geometry_is_rejected_before_label_search(self):
        source=steps()
        source[0]['draw']=[{'op':'circle','id':'large','center':[300,180],'radius':170}]
        source[0]['draw'] += [{'op':'circle','center':[300,180],'radius':170} for _ in range(30)]
        source[0]['draw'].append({'op':'label','target':'large','text':'A'})
        with patch('notebook_procedural._place_labels') as search:
            with self.assertRaises(ValueError):compile_lesson(source,'Do not search an over-budget picture.')
            search.assert_not_called()

    def test_segment_labels_follow_the_segment_not_page_axes(self):
        for end in ([430,100],[130,300],[430,300]):
            source=[{'caption':'A directed line.','draw':[
                        {'op':'arrow','id':'edge','from':[130,100],'to':end},
                        {'op':'label','target':'edge','text':'Flow'}]},
                    {'caption':'Add a point.','draw':[{'op':'circle','center':[520,300],'radius':12}]},
                    {'caption':'Add another point.','draw':[{'op':'circle','center':[50,300],'radius':12}]}]
            plan=compile_lesson(source,'The label belongs to the directed segment.')
            self.assertEqual(plan['anchored_labels'][0]['target'],'edge')
            self.assertEqual(plan['anchored_labels'][0]['text'],'Flow')
            self.assertTrue(all(len(stage['paths'])<=64 and stage['points']<=3000 for stage in plan['stages']))

    def test_different_diagram_fixtures_preserve_geometry_and_fit_paced_motion(self):
        from notebook_anchored_label_examples import examples
        from notebook_semantic import compile_semantic
        from notebook_motion_program import compile_motion_program
        for name,raw in examples().items():
            with self.subTest(name=name):
                original=copy.deepcopy(raw)
                plan=compile_semantic(raw)
                self.assertEqual(original,raw)
                self.assertEqual(len(native_semantic_bundle(json.dumps(raw))['sources']),len(raw['steps']))
                motion=compile_motion_program(plan)
                self.assertTrue(all(stage['estimated_pen_seconds']<=30 and stage['points']<=3000
                                    and stage['contacts']<=64 for stage in motion['stage_budgets'].values()))
                resolved,_=resolve_labels(raw['steps'])
                for before,after in zip(raw['steps'],resolved):
                    self.assertEqual([{k:v for k,v in c.items() if k!='id'} for c in before['draw'] if c['op']!='label'],
                                     [c for c in after['draw'] if c['op']!='label'])


class LabelCountTests(unittest.TestCase):
    def test_past_twelve_labels_the_rest_are_left_out_rather_than_refused(self):
        dots=[{'op':'circle','id':f'dot-{i}','center':[60+(i%7)*80,90+(i//7)*150],'radius':12} for i in range(13)]
        many=[{'caption':'Thirteen dots.','draw':dots},
              {'caption':'Each named.','draw':[{'op':'label','target':f'dot-{i}','text':f'D{i}'} for i in range(13)]}]
        with self.assertRaisesRegex(ValueError,'twelve'):
            resolve_labels(copy.deepcopy(many))
        dropped=[]
        resolve_labels(copy.deepcopy(many),dropped)
        self.assertIn(('step 2 command 13','D12'),dropped)


class CaptionLengthTests(unittest.TestCase):
    def test_a_long_story_episode_is_a_caption_and_the_writer_clips_to_the_same_limit(self):
        # The 07:01 raven on 2026-11-01 was held: Opus's first episode was 300 characters, the schema allowed 280.
        import notebook_image_model as gm
        episode=('In a snowy forest lived a raven named Hugo, who pulled a string up with his beak and held each loop '
                 'under his foot until the bread tied to its end reached him, because a raven can picture a plan '
                 'before he tries it, and very few animals in the whole world can work out a puzzle in their heads.')
        self.assertGreater(len(episode),280)
        source=steps(); source[0]=dict(source[0],caption=episode)
        self.assertEqual(compile_lesson(source,'Ravens plan ahead.')['stages'][0]['text'],episode)
        tale=gm._tale({'steps':[{'caption':'x '*250,'see':''}]*3,'takeaway':'t'},'Once upon a time')
        self.assertLessEqual(len(tale['steps'][0]['caption']),gm.CAPTION)
        self.assertTrue(tale['steps'][0]['caption'].endswith('x\u2026'))
        # A long takeaway keeps its closing question whole, or ends on its last whole sentence, never mid-word.
        ending=('The rioters were mostly driven by the false belief that the election was stolen. '*5+
                'Why do you think one person was given a power that no court can undo?')
        tale=gm._tale({'steps':[{'caption':'x','see':''}]*3,'takeaway':ending},'Once upon a time')
        self.assertLessEqual(len(tale['takeaway']),500)
        self.assertTrue(tale['takeaway'].endswith('?'))
        tale=gm._tale({'steps':[{'caption':'x','see':''}]*3,'takeaway':'One sentence. '*40},'Once upon a time')
        self.assertTrue(tale['takeaway'].endswith('sentence.'))


if __name__=='__main__':unittest.main()
