import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ink import append, strokes, line_block
from notebook_ink_catalog import InkCatalog
from notebook_ink_runs import InkRuns, MAX_PLAN_BYTES, match_translated, saved_stroke_records
from notebook_stroke_asset import storyboard_assets, _block
from notebook_storyboard import integral_storyboard
from test_notebook_ink_catalog import manifest


REQUEST = 'notebook-'+'7'*32
DOC = '905df7ae-ff54-46b9-a71e-45bb02bef638'
PAGE = '3ad12986-0467-48fe-986d-d1bd480c4777'
AUTHOR = '4b4acc76-62ce-428b-8602-a7ad7ac9e330'
HEADER = b'reMarkable .lines file, version=6'.ljust(43,b' ')


class InkRunsTest(unittest.TestCase):
    def test_animated_fraction_plan_over_64k_is_readable_after_registration(self):
        from notebook_semantic_examples import examples
        from notebook_lesson_native import native_semantic_bundle
        spec = copy.deepcopy(examples()['fractions'])
        spec['scene']['objects'][0]['fractions'] = [
            dict(numerator=2, denominator=3), dict(numerator=4, denominator=6)]
        bundle = native_semantic_bundle(json.dumps(spec), playback=True)
        context = dict(fresh=True, active=True, doc=DOC, page=PAGE, surface='test',
                       ink_revision=4, content_revision=8, text_bounds=[-468,500,936,100])
        with tempfile.TemporaryDirectory() as directory:
            store = InkRuns(directory)
            store.register(REQUEST, DOC+'/'+PAGE+'.rm', context, bundle['blocks'], HEADER)
            size = (Path(directory)/(REQUEST+'.plan.json')).stat().st_size
            self.assertGreater(size,65536)
            self.assertLess(size,MAX_PLAN_BYTES)
            # Restart does not make the newly written plan unreadable.
            store = InkRuns(directory)
            plan = store._plan(REQUEST)
            for block in plan['blocks']:
                query = dict(request=REQUEST,page=plan['path'],scene=block['scene'],stage=block['stage'],
                             surface='test',ink_revision=4,revision=8,origin=[-468,630],ui_locked=True)
                self.assertTrue(store.claim(query,lambda:context,lambda *args:None)['claimed'])
                store.complete({k:query[k] for k in ('request','scene','stage')})
            with self.assertRaises(FileExistsError):
                store.claim(query,lambda:context,lambda *args:None)

    def test_plan_byte_cap_rejects_before_any_journal_write_and_bounds_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            store,context,_,blocks = self.setup_run(directory)
            other = 'notebook-'+'8'*32
            blocks[0]['oversized'] = 'x'*MAX_PLAN_BYTES
            with self.assertRaisesRegex(ValueError,'plan exceeds its budget'):
                store.register(other,DOC+'/'+PAGE+'.rm',context,blocks,HEADER)
            self.assertEqual(list(Path(directory).glob(other+'*')),[])
            # Corrupt/oversized on-disk plans still fail before claims/preflight.
            store._write_once(other+'.plan.json',{'oversized':'x'*MAX_PLAN_BYTES})
            with self.assertRaisesRegex(ValueError,'journal exceeds its budget'):
                store._plan(other)
            store._write_once(other+'.done.json',{'oversized':'x'*65536})
            with self.assertRaisesRegex(ValueError,'journal exceeds its budget'):
                store._read(other+'.done.json')

    def test_reply_revision_checks_existing_journal_without_clearing_anything(self):
        for suffix in ('.plan.json', '.before-ids.json', '-stage.claim.json', '-stage.done.json'):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                store = InkRuns(directory)
                store.require_unprepared(REQUEST)
                other = 'notebook-'+'8'*32
                store._write_once(other+suffix, {'unrelated': True})
                store.require_unprepared(REQUEST)
                store._write_once(REQUEST+suffix, {'existing': True})
                with self.assertRaisesRegex(ValueError, 'journal already prepared'):
                    store.require_unprepared(REQUEST)
                self.assertEqual(store._read(REQUEST+suffix), {'existing': True})
                self.assertEqual(store._read(other+suffix), {'unrelated': True})
        with tempfile.TemporaryDirectory() as directory:
            store = InkRuns(directory)
            with self.assertRaises(ValueError): store.require_unprepared('../notebook')
            with patch('notebook_ink_runs.os.scandir', side_effect=PermissionError('unreadable')):
                with self.assertRaises(PermissionError): store.require_unprepared(REQUEST)
            for target in (store.captures, store.measurements):
                target[(REQUEST, 'key')] = 'untouched'
                with self.assertRaisesRegex(ValueError, 'capture already prepared'):
                    store.require_unprepared(REQUEST)
                self.assertEqual(target[(REQUEST, 'key')], 'untouched')
                target.clear()

    def setup_run(self, directory, before=HEADER):
        catalog = InkCatalog(manifest(AUTHOR))
        blocks = [dict(kind='ink', **catalog.get('unit-square-integral', stage)) for stage in ('see','measure','notice')]
        context = dict(fresh=True, active=True, doc=DOC, page=PAGE, surface='1793064000000-123',
                       ink_revision=4, content_revision=8, text_bounds=[-468,500,936,100])
        store = InkRuns(directory)
        store.register(REQUEST,DOC+'/'+PAGE+'.rm',context,blocks,before)
        query = dict(request=REQUEST,page=DOC+'/'+PAGE+'.rm',scene='unit-square-integral',stage='see',
                     surface=context['surface'],ink_revision=4,revision=8,origin=[-468,630],ui_locked=True)
        return store,context,query,blocks

    def test_durable_claims_order_common_origin_and_idempotent_commit_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            store,context,query,blocks = self.setup_run(directory)
            self.assertTrue(store.claim(query,lambda:context,lambda *args:None)['claimed'])
            with self.assertRaises(FileExistsError):
                InkRuns(directory).claim(query,lambda:context,lambda *args:None)
            second = dict(query,stage='measure')
            with self.assertRaises(FileNotFoundError):
                store.claim(second,lambda:context,lambda *args:None)
            done = {k:query[k] for k in ('request','scene','stage')}
            self.assertFalse(store.complete(done)['persisted'])
            self.assertTrue(store.complete(done)['accepted'])
            with self.assertRaises(ValueError):
                store.claim(dict(second,origin=[-468,680]),lambda:context,lambda *args:None)
            self.assertTrue(store.claim(second,lambda:context,lambda *args:None)['claimed'])

    def test_a_later_picture_may_sit_below_earlier_pictures_not_only_below_text(self):
        # Handwritten captions add no text, so the next region is placed below the last one written (1d7a684f).
        with tempfile.TemporaryDirectory() as directory:
            store,context,query,blocks = self.setup_run(directory)
            later = dict(blocks[0],scene='lesson-'+'1'*24)
            store = InkRuns(directory+'/b')
            store.register(REQUEST,DOC+'/'+PAGE+'.rm',context,blocks+[later],HEADER)
            for stage in ('see','measure','notice'):
                store.claim(dict(query,stage=stage),lambda:context,lambda *args:None)
                store.complete(dict(request=REQUEST,scene=query['scene'],stage=stage))
            below = dict(query,scene=later['scene'],origin=[-468,630+300+30+250])
            with self.assertRaisesRegex(ValueError,'reserved below'):
                store.claim(dict(below,origin=[-468,630+300+30+301]),lambda:context,lambda *args:None)
            self.assertTrue(store.claim(below,lambda:context,lambda *args:None)['claimed'])

    def test_a_reply_that_types_no_words_writes_just_below_the_question_across_the_column(self):
        # A handwritten reply's only typed text is its blank label lines; its ink may start above them.
        import uuid
        from notebook_lesson_native import _hand_blocks
        hand = _hand_blocks('Hello, James.','primer',str(uuid.uuid4()),0)[0][0]
        picture = dict(kind='ink', **InkCatalog(manifest(AUTHOR)).get('unit-square-integral','see'))
        before = dict(fresh=True, active=True, doc=DOC, page=PAGE, surface='test',
                      ink_revision=4, content_revision=8, text_bounds=[0,0,0,0])
        after = dict(before, text_bounds=[-468,500,936,100])
        query = dict(request=REQUEST,page=DOC+'/'+PAGE+'.rm',scene=hand['scene'],stage='hand',surface='test',
                     ink_revision=4,revision=8,origin=[-570,300],ui_locked=True)
        with tempfile.TemporaryDirectory() as directory:
            InkRuns(directory).register(REQUEST,DOC+'/'+PAGE+'.rm',before,[hand,picture],HEADER)
            with self.assertRaisesRegex(ValueError,'reserved below'):
                InkRuns(directory).claim(query,lambda:after,lambda *args:None)
        with tempfile.TemporaryDirectory() as directory:
            store = InkRuns(directory)
            store.register(REQUEST,DOC+'/'+PAGE+'.rm',before,[hand,picture],HEADER,blank_prose=True)
            with self.assertRaisesRegex(ValueError,'reserved below'):
                store.claim(dict(query,origin=[-400,300]),lambda:after,lambda *args:None)  # must span the column
            self.assertTrue(store.claim(query,lambda:after,lambda *args:None)['claimed'])
        with tempfile.TemporaryDirectory() as directory:
            store = InkRuns(directory)
            store.register(REQUEST,DOC+'/'+PAGE+'.rm',dict(before,text_bounds=[-468,100,936,250]),[hand,picture],HEADER,
                           blank_prose=True)
            with self.assertRaisesRegex(ValueError,'reserved below'):  # still below typed text already on the page
                store.claim(query,lambda:after,lambda *args:None)
            self.assertTrue(store.claim(dict(query,origin=[-570,370]),lambda:after,lambda *args:None)['claimed'])

    def test_changed_page_ink_or_revision_and_changed_during_io_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            store,context,query,blocks = self.setup_run(directory)
            for change,named in (({'fresh':False},'fresh'),({'page':DOC},'page'),({'ink_revision':5},'ink_revision'),
                                 ({'content_revision':9},'content_revision')):
                with self.assertRaisesRegex(ValueError,'changed: '+named+'$'):
                    store.claim(query,lambda:dict(context,**change),lambda *args:self.fail('preflight should not run'))
            changed = copy.deepcopy(context)
            def preflight(*args):
                changed['ink_revision'] += 1
            with self.assertRaises(ValueError):
                store.claim(query,lambda:changed,preflight)
            with self.assertRaises(ValueError):
                store.claim(dict(query,ui_locked=False),lambda:context,lambda *args:None)
            with self.assertRaises(ValueError):
                store.claim(dict(query,origin=[-468,590]),lambda:context,lambda *args:None)

    def test_saved_proof_requires_every_stage_and_all_native_shapes(self):
        assets = {a['stage']:a['data'] for a in storyboard_assets(integral_storyboard(),AUTHOR,ink_labels=True)}
        header = b'reMarkable .lines file, version=6'.ljust(43,b' ')
        paths = [points for raw in assets.values() for _,points,_ in strokes(raw)]
        saved = append(header,[[(x-400,y+700,w) for x,y,w in path] for path in paths],start=((0,11),(1,14)))
        with tempfile.TemporaryDirectory() as directory:
            store,context,query,blocks = self.setup_run(directory)
            read_source = lambda block: assets[block['stage']]
            self.assertEqual(store.saved_proof(REQUEST,lambda path:saved,read_source)['state'],'waiting')
            for stage in assets:
                query['stage'] = stage
                store.claim(query,lambda:context,lambda *args:None)
                store.complete({k:query[k] for k in ('request','scene','stage')})
            self.assertEqual(store.saved_proof(REQUEST,lambda path:b'',read_source)['state'],'waiting')
            partial = append(header,paths[:1],start=((0,11),(1,14)))
            self.assertEqual(store.saved_proof(REQUEST,lambda path:partial,read_source)['state'],'waiting')
            proof = InkRuns(directory).saved_proof(REQUEST,lambda path:saved,read_source)
            self.assertEqual(proof['state'],'persisted')
            self.assertEqual(proof['strokes'],len(paths))
            with self.assertRaises(ValueError):
                store.saved_proof(REQUEST,lambda path:saved,lambda block:assets[block['stage']]+b'changed')

    def test_shape_match_needs_shared_translation_and_unique_target_lines(self):
        source = [[(0,0,2),(1,0,2)],[(1,1,2),(1,2,2)]]
        target = [[(10,10,2),(11,10,2)],[(11,11,2),(11,12,2)]]
        self.assertEqual(match_translated(source,target,set()),{0,1})
        self.assertIsNone(match_translated(source,target,{0}))
        target[1] = [(20,20,2),(20,21,2)]
        self.assertIsNone(match_translated(source,target,set()))

    def test_old_identical_diagram_cannot_prove_a_new_insertion(self):
        assets = {a['stage']:a['data'] for a in storyboard_assets(integral_storyboard(),AUTHOR,ink_labels=True)}
        paths = [points for raw in assets.values() for _,points,_ in strokes(raw)]
        before = append(HEADER,paths,start=((0,11),(1,14)))
        with tempfile.TemporaryDirectory() as directory:
            store,context,query,blocks = self.setup_run(directory,before)
            for stage in assets:
                query['stage'] = stage
                store.claim(query,lambda:context,lambda *args:None)
                store.complete({k:query[k] for k in ('request','scene','stage')})
            proof = lambda raw: store.saved_proof(REQUEST,lambda _:raw,lambda block:assets[block['stage']])
            self.assertEqual(proof(before)['state'],'waiting', 'same old geometry is insufficient')
            partial = append(before,paths[:1])
            self.assertEqual(proof(partial)['state'],'waiting')
            after = append(before,[[(x+20,y+500,w) for x,y,w in path] for path in paths])
            self.assertEqual(proof(after)['state'],'persisted')
            self.assertEqual(proof(after)['strokes'],len(paths))

    def test_identity_reader_rejects_truncation_and_duplicate_item_revisions(self):
        raw = append(HEADER,[[(0,0,2),(1,1,2)]],start=((0,11),(1,14)))
        records,authors = saved_stroke_records(raw)
        self.assertEqual(len(records),1)
        self.assertEqual(authors,[])
        for invalid in (raw[:-1],raw+b'bad',raw+raw[43:]):
            with self.assertRaises(ValueError):
                saved_stroke_records(invalid)

    def test_new_diagram_cannot_hide_deleted_or_changed_preexisting_ink(self):
        assets = {a['stage']:a['data'] for a in storyboard_assets(integral_storyboard(),AUTHOR,ink_labels=True)}
        paths = [points for raw in assets.values() for _,points,_ in strokes(raw)]
        old = [(0,0,2),(80,40,2)]
        before = append(HEADER,[old],start=((0,11),(1,14)))
        # New diagram identities are distinct even when the old stroke is absent.
        new_only = append(HEADER,paths,start=((0,11),(1,15)))
        with tempfile.TemporaryDirectory() as directory:
            store,context,query,_ = self.setup_run(directory,before)
            for stage in assets:
                query['stage'] = stage
                store.claim(query,lambda:context,lambda *args:None)
                store.complete({k:query[k] for k in ('request','scene','stage')})
            proof = lambda raw: store.saved_proof(REQUEST,lambda _:raw,lambda block:assets[block['stage']])
            self.assertEqual(proof(before+new_only[43:])['state'],'persisted')
            for old_block in (b'',
                    line_block((0,11),(1,15),(0,0),[(0,0,2),(80,45,2)]),
                    line_block((0,11),(1,15),(0,0),old,color=1)):
                with self.subTest(old_block=bool(old_block)):
                    result = proof(HEADER+old_block+new_only[43:])
                    self.assertEqual(result['state'],'waiting')
                    self.assertIn('pre-existing ink',result['reason'])

    def test_changed_author_map_cannot_reinterpret_old_numeric_ids_as_new_strokes(self):
        assets = {a['stage']:a['data'] for a in storyboard_assets(integral_storyboard(),AUTHOR,ink_labels=True)}
        paths = [points for raw in assets.values() for _,points,_ in strokes(raw)]
        with tempfile.TemporaryDirectory() as directory:
            store,context,query,blocks = self.setup_run(directory)
            for stage in assets:
                query['stage'] = stage
                store.claim(query,lambda:context,lambda *args:None)
                store.complete({k:query[k] for k in ('request','scene','stage')})
            saved = append(HEADER,paths,start=((0,11),(1,14)))+_block(9,b'changed author map')
            result = store.saved_proof(REQUEST,lambda _:saved,lambda block:assets[block['stage']])
            self.assertEqual(result['state'],'waiting')
            self.assertIn('author map',result['reason'])


if __name__ == '__main__':
    unittest.main()
