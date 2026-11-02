import math
import unittest
import copy
import json
import uuid
from unittest.mock import Mock
from notebook_hand_ink import hand_lines, hand_plans, WIDTH, MARGIN, SIZE, VELOCITY
from notebook_handwriting import handwriting_paths
from notebook_ink_playback import validate_playback, playback_assets
from notebook_drawing import HAND_STROKES
from notebook_lesson_native import (prepare_semantic_reply, _bundle_from_compiled_lesson,
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
                self.assertFalse(any(b.get('role')=='hand' for b in blocks))

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
        self.assertEqual([b['text'] for b in blocks if b['kind']=='text'][1:],[LONG*3]*6)
        self.assertEqual(blocks[-1]['role'],'hand')
        plan['stages'][0]['text']='Water boils at 100°.'  # one unwritable caption keeps every caption typed
        plan['stages'][1:]=plan['stages'][1:2]
        blocks=_bundle_from_compiled_lesson(plan,playback=True,pen_equations=True,hand='primer')['blocks']
        self.assertEqual([b['text'] for b in blocks if b['kind']=='text'][1:],['Water boils at 100°.',LONG*3])
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

    def test_the_opening_stays_when_the_captions_fall_back_to_typed(self):
        from test_notebook_equation_ink import EquationInkTests
        plan=EquationInkTests.six_step_plan(None)
        for stage in plan['stages']:stage['text']=LONG*3
        blocks=_bundle_from_compiled_lesson(plan,playback=True,pen_equations=True,hand='primer',
                                            opening='James, once upon a time...')['blocks']
        self.assertEqual(blocks[1]['role'],'hand')
        self.assertEqual(blocks[-1]['role'],'hand')
        self.assertEqual([b['text'] for b in blocks if b['kind']=='text'][1:],[LONG*3]*6)

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
