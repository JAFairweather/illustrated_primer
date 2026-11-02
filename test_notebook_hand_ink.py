import math
import unittest
import copy
import json
import uuid
from unittest.mock import Mock
from notebook_hand_ink import hand_lines, hand_plans, end_plan, WIDTH, MARGIN, SIZE, VELOCITY
from notebook_handwriting import handwriting_paths
from notebook_ink_playback import validate_playback, playback_assets
from notebook_drawing import HAND_STROKES
from notebook_lesson_native import (prepare_semantic_reply, _bundle_from_compiled_lesson, prepare_head_reply,
                                    lesson_source_archive, inspect_source_archive)
from notebook_semantic_examples import examples
from notebook_stroke_asset import validate_native_ink_budget

LONG = ('Each square adds the next odd number of dots: one, then three, then five, so the running total of the odd '
        'numbers is always a perfect square, and the picture shows why without any algebra at all.')


class HandInkTests(unittest.TestCase):
    def test_lines_wrap_inside_the_margins_and_keep_every_word(self):
        lines=hand_lines(LONG)
        self.assertGreater(len(lines),1)
        self.assertEqual(' '.join(lines).split(),LONG.split())
        for line in lines:
            self.assertLessEqual(handwriting_paths(line,SIZE,hand='primer')[1],WIDTH-2*MARGIN)

    def test_typographic_punctuation_is_written_plain(self):
        self.assertEqual(hand_lines('It’s “done”…'),['It\'s "done"...'])

    def test_regions_fit_the_native_stage_budget_and_differ(self):
        plans=hand_plans(LONG*3)
        self.assertGreater(len(plans),1)
        self.assertEqual(len({p['scene'] for p in plans}),len(plans))
        self.assertNotEqual(hand_plans('A short note.')[0]['scene'],hand_plans('A short note.','reader')[0]['scene'])
        for plan in plans:
            paths=plan['stages'][0]['paths']
            self.assertLessEqual(len(paths),HAND_STROKES)
            self.assertLessEqual(sum(map(len,paths)),3000)
            self.assertTrue(200<=plan['height']<=500)
            self.assertTrue(all(MARGIN-5<=x<=WIDTH-MARGIN+5 for p in paths for x,_ in p))

    def test_print_regions_hold_more_strokes_than_a_drawing_stage_within_the_timed_playback(self):
        plans=hand_plans(LONG,'letter')
        self.assertGreater(max(len(p['stages'][0]['paths']) for p in plans),64,'print lifts the pen at every letter')
        for plan in plans:
            asset=playback_assets(plan,velocity=VELOCITY)[0]
            self.assertLessEqual(asset['stroke_count'],HAND_STROKES)
            self.assertLessEqual(asset['playback']['duration_ms'],30000)
        self.assertLessEqual(len(plans),len(hand_plans(LONG))+1,'print takes about as many regions as the script')

    def test_a_region_holds_two_wide_lines_at_a_close_pitch_with_curves_kept(self):
        two=' '.join(hand_lines(LONG)[:2])
        plans=hand_plans(two)
        self.assertEqual(len(plans),1,'two wide lines share one region, so no region gap opens between them')
        self.assertLessEqual(plans[0]['height'],260)
        paths=plans[0]['stages'][0]['paths']
        self.assertTrue(all(math.dist(a,b)<=8.01 for p in paths for a,b in zip(p,p[1:])))
        self.assertGreater(sum(map(len,paths)),len(paths)*20,'curves keep their close points')

    def test_unwritable_words_are_refused(self):
        for text in ('', 'x'*80, 'unknown hand', LONG*20):
            with self.subTest(text=text),self.assertRaises(ValueError):
                hand_plans(text, hand='scribe' if text=='unknown hand' else 'primer')

    def lesson(self, takeaway, hand='primer'):
        spec=copy.deepcopy(examples()['fractions-variant'])
        spec['takeaway']=takeaway
        return prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand=hand)

    def test_takeaway_is_written_last_after_the_equation(self):
        bundle=self.lesson('Two thirds is more than three fifths.')
        blocks=bundle['blocks']
        self.assertEqual([b.get('role') for b in blocks[-2:]],['equation','hand'])
        self.assertFalse(any(b['kind']=='text' and b['text'].startswith('Takeaway') for b in blocks))
        written=blocks[-1]
        self.assertTrue(written['scene'].startswith('hand-'))
        validate_playback(written,bundle['sources'][-1]['data'])
        parent=str(uuid.uuid4())
        doc,data=lesson_source_archive(bundle,{'cPages':{},'fileType':'notebook'},parent)
        self.assertEqual(inspect_source_archive(data,doc,parent,written['source_page'],written['stroke_count']),
                         written['sha256'])

    def test_takeaway_stays_typed_without_a_hand_or_with_an_unwritable_glyph(self):
        for takeaway,hand in (('Two thirds is more.',None),('Water boils at 100° at sea level.','primer')):
            with self.subTest(hand=hand):
                blocks=self.lesson(takeaway,hand)['blocks']
                self.assertEqual(blocks[-1]['text'],'Takeaway: '+takeaway)
                self.assertEqual(any(b.get('role')=='hand' for b in blocks),hand is not None)  # captions still by hand

    def test_every_caption_is_written_where_its_typed_caption_stood(self):
        bundle=self.lesson('Two thirds is more than three fifths.')
        blocks=bundle['blocks']
        self.assertEqual(blocks[0],dict(kind='text',text='',styles=[]))
        self.assertFalse(any(b['kind']=='text' and b['text'] for b in blocks))
        steps=[i for i,b in enumerate(blocks) if b['kind']=='ink' and b.get('role') is None]
        self.assertTrue(all(blocks[i-1].get('role')=='hand' for i in steps),'each step is narrated before it is drawn')
        written=[b for b in blocks if b.get('role')=='hand']
        self.assertEqual(len({b['scene'] for b in written}),len(written))
        self.assertTrue(all(b['playback']['velocity']==VELOCITY for b in written))
        self.assertEqual([b['source_page'] for b in blocks if b['kind']=='ink'],[s['source_page'] for s in bundle['sources']])
        parent=str(uuid.uuid4())
        doc,data=lesson_source_archive(bundle,{'cPages':{},'fileType':'notebook'},parent)
        self.assertEqual(inspect_source_archive(data,doc,parent,written[0]['source_page'],written[0]['stroke_count']),
                         written[0]['sha256'])

    def test_identical_captions_get_separate_regions(self):
        spec=copy.deepcopy(examples()['fractions-variant'])
        for step in spec['steps']:step['caption']='Look again.'
        blocks=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand='primer')['blocks']
        written=[b['scene'] for b in blocks if b.get('role')=='hand']
        self.assertEqual(len(set(written)),len(written))

    def test_captions_fall_back_to_typed_before_the_takeaway_does(self):
        from test_notebook_equation_ink import EquationInkTests
        plan=EquationInkTests.six_step_plan(None)
        for stage in plan['stages']:stage['text']=LONG*3  # far past the handwriting budget
        blocks=_bundle_from_compiled_lesson(plan,playback=True,pen_equations=True,hand='primer')['blocks']
        typed=[b['text'] for b in blocks if b['kind']=='text'][1:]  # the later captions, the earlier stay written
        self.assertTrue(0 < len(typed) < 6 and typed == [LONG*3]*len(typed), len(typed))
        self.assertEqual(blocks[-1]['role'],'hand')
        plan['stages'][0]['text']='Water boils at 100°.'  # an unwritable caption is typed by itself
        plan['stages'][1:]=plan['stages'][1:2]
        plan['stages'][1]['text']=LONG
        blocks=_bundle_from_compiled_lesson(plan,playback=True,pen_equations=True,hand='primer')['blocks']
        self.assertEqual([b['text'] for b in blocks if b['kind']=='text'][1:],['Water boils at 100°.'])
        self.assertEqual(blocks[-1]['role'],'hand')

    def test_the_reply_opens_with_the_readers_name_by_hand(self):
        spec=copy.deepcopy(examples()['fractions-variant'])
        opening='James, once upon a time...'
        bundle=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand='primer',
                                      opening=opening)
        blocks=bundle['blocks']
        self.assertEqual(blocks[0],dict(kind='text',text='',styles=[]))
        self.assertEqual(blocks[1]['scene'],hand_plans(opening,'primer',place=len(spec['steps'])+1)[0]['scene'])
        self.assertEqual(blocks[2]['role'],'hand')
        self.assertEqual([b['source_page'] for b in blocks if b['kind']=='ink'],[s['source_page'] for s in bundle['sources']])
        for hand in (None,):  # no hand: no opening, the label carries the name instead
            plain=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand=hand,opening=opening)
            self.assertFalse(any(b.get('role')=='hand' for b in plain['blocks']))

    def test_a_story_ends_with_the_end_centred_over_a_scroll(self):
        spec=copy.deepcopy(examples()['fractions-variant'])
        bundle=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand='letter',
                                      opening='James, once upon a time...')
        end=end_plan('letter')
        self.assertEqual(bundle['blocks'][-1]['scene'],end['scene'])
        self.assertEqual(bundle['sources'][-1]['source_page'],bundle['blocks'][-1]['source_page'])
        xs=[x for path in end['stages'][0]['paths'] for x,_ in path]
        self.assertAlmostEqual((min(xs)+max(xs))/2,WIDTH/2,delta=40)
        self.assertNotIn(end['scene'],bundle['passages'])  # the narrator says "The end." on its own
        validate_native_ink_budget(bundle['blocks'])
        plain=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand='letter')
        self.assertNotEqual(plain['blocks'][-1].get('scene'),end['scene'])  # no opening, no ending

    def test_the_ending_is_left_out_before_any_passage_is_typed(self):
        from test_notebook_equation_ink import EquationInkTests
        plan=EquationInkTests.six_step_plan(None)
        for stage in plan['stages']:stage['text']=LONG*3
        blocks=_bundle_from_compiled_lesson(plan,playback=True,pen_equations=True,hand='primer',
                                            opening='James, once upon a time...')['blocks']
        self.assertNotEqual(blocks[-1]['scene'],end_plan('primer')['scene'])

    def test_the_bundle_names_each_written_passage_by_its_first_block(self):
        spec=copy.deepcopy(examples()['fractions-variant'])
        opening='James, once upon a time...'
        bundle=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand='primer',
                                      opening=opening)
        written=[b['scene'] for b in bundle['blocks'] if b.get('role')=='hand']
        passages=bundle['passages']
        self.assertEqual(passages[written[0]],opening)
        self.assertEqual(list(passages.values())[1:],[s['caption'] for s in spec['steps']]+[spec['takeaway']])
        self.assertTrue(set(passages)<=set(written))
        typed=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand=None,opening=opening)
        self.assertFalse(any(key.startswith('hand-') for key in typed['passages']))
        self.assertEqual(list(typed['passages'].values()),[s['caption'] for s in spec['steps']])

    def test_a_storys_head_and_rest_write_the_whole_reply_once(self):
        spec=copy.deepcopy(examples()['fractions-variant'])
        opening,first='James, once upon a time...',spec['steps'][0]['caption']
        head=prepare_head_reply(opening,first,'primer')
        written=[b for b in head['blocks'] if b.get('role')=='hand']
        self.assertEqual(head['blocks'][0],dict(kind='text',text='',styles=[]))
        self.assertEqual(len(written),len(head['blocks'])-1,'no picture, takeaway or ending in the head')
        self.assertEqual(list(head['passages'].values()),[opening,first])
        self.assertTrue(set(head['passages'])<={b['scene'] for b in written})
        self.assertEqual([b['source_page'] for b in written],[s['source_page'] for s in head['sources']])
        validate_native_ink_budget(head['blocks'])
        whole=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand='primer',opening=opening)
        rest=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand='primer',told=first)
        self.assertEqual(list(rest['passages'].values()),[s['caption'] for s in spec['steps'][1:]]+[spec['takeaway']])
        self.assertEqual(rest['blocks'][-1]['scene'],end_plan('primer')['scene'])  # "The End"
        drawings=lambda bundle:[b['scene'] for b in bundle['blocks'] if b['kind']=='ink' and b.get('role')!='hand']
        self.assertEqual(drawings(rest),drawings(whole),'the first caption\'s picture comes with the rest')
        self.assertFalse(any(b['kind']=='text' and first in b.get('text','') for b in rest['blocks']))
        validate_native_ink_budget(rest['blocks'])
        parent='00000000-0000-4000-8000-000000000000'
        for bundle in (head,rest):  # 11-02 (ab29bbaa): the head had no plan, and staging its archive raised
            doc,data=lesson_source_archive(bundle,{'cPages':{},'fileType':'notebook'},parent)
            self.assertEqual(doc,bundle['sources'][0]['source_doc'])
        with self.assertRaises(ValueError):
            prepare_head_reply(opening,first,None)

    def test_the_opening_stays_when_the_captions_fall_back_to_typed(self):
        from test_notebook_equation_ink import EquationInkTests
        plan=EquationInkTests.six_step_plan(None)
        for stage in plan['stages']:stage['text']=LONG*3
        blocks=_bundle_from_compiled_lesson(plan,playback=True,pen_equations=True,hand='primer',
                                            opening='James, once upon a time...')['blocks']
        self.assertEqual(blocks[1]['role'],'hand')
        self.assertEqual(blocks[-1]['role'],'hand')
        typed=[b['text'] for b in blocks if b['kind']=='text'][1:]
        self.assertTrue(0 < len(typed) < 6 and typed == [LONG*3]*len(typed), len(typed))

    def test_a_missing_letter_is_written_plain_and_only_an_unwritable_passage_is_typed(self):
        # 2026-11-01 11:27: "Erdős" in three passages typed every caption and the takeaway.
        spec=copy.deepcopy(examples()['fractions-variant'])
        spec['steps'][0]['caption']='Paul Erdős asked it first.'
        spec['steps'][1]['caption']='A dot \u2603 waited.'  # a snowman: no plain letter to fall back on
        bundle=prepare_semantic_reply(json.dumps(spec),Mock(),playback=True,pen_equations=True,hand='letter',
                                      opening='James, once upon a time...')
        self.assertIn('Paul Erdős asked it first.',bundle['passages'].values())
        typed=[key for key,text in bundle['passages'].items() if text=='A dot \u2603 waited.']
        self.assertEqual([key.startswith('hand-') for key in typed],[False])  # said as its drawing starts
        self.assertIn('A dot \u2603 waited.',[b.get('text') for b in bundle['blocks'] if b['kind']=='text'])
        self.assertIn(spec['takeaway'],bundle['passages'].values())

    def test_a_lesson_past_the_tablets_pages_keeps_its_earliest_passages_written(self):
        # 2026-11-01 11:58: six long captions and a long takeaway in the letter hand made 21 pages; the tablet takes 19.
        from test_notebook_equation_ink import EquationInkTests
        from notebook_lesson_native import LESSON_PAGES
        plan=EquationInkTests.six_step_plan(None)
        for stage in plan['stages']:stage['text']=LONG+' '+LONG[:60]
        plan['takeaway']=LONG*2
        bundle=_bundle_from_compiled_lesson(plan,playback=True,pen_equations=True,hand='letter',
                                            opening='James, once upon a time...')
        self.assertLessEqual(len(bundle['sources']),LESSON_PAGES)
        written=[text for key,text in bundle['passages'].items() if key.startswith('hand-')]
        self.assertEqual(written[:2],['James, once upon a time...',plan['stages'][0]['text']])
        self.assertEqual(written[-1],plan['takeaway'])
        typed=[b['text'] for b in bundle['blocks'] if b['kind']=='text' and b['text']]
        self.assertIn(plan['stages'][-1]['text'],typed)

    def test_handwriting_regions_are_renderer_owned_and_separate(self):
        blocks=self.lesson(LONG)['blocks']
        self.assertEqual(blocks[-1]['role'],'hand')
        validate_native_ink_budget(blocks)
        for mutation in ('shared','stage','width','scene'):
            bad=copy.deepcopy(blocks)
            written=[b for b in bad if b.get('role')=='hand'][0]
            if mutation=='shared':written['scene']=[b for b in bad if b.get('role')=='hand'][1]['scene']
            if mutation=='stage':written['stage_count']=2
            if mutation=='width':written['width']=700
            if mutation=='scene':written['scene']='lesson-'+'0'*24
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_native_ink_budget(bad)


if __name__=='__main__':unittest.main()
