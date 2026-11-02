from copy import deepcopy
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
import uuid
from unittest.mock import Mock, patch

from notebook_panel_examples import graph_reuse_example
from notebook_story_native import native_story_bundle
from notebook_stroke_asset import validate_native_ink_budget
from notebook_ink_playback import validate_playback
from notebook_lesson_native import (lesson_source_archive, inspect_source_archive,
                                    source_document_files, remap_imported_lesson)


def inks(bundle):
    return [b for b in bundle['blocks'] if b['kind']=='ink']


class NativeStoryTests(unittest.TestCase):
    def test_reused_sources_need_distinct_saved_ink_and_preserve_existing_content(self):
        from ink import append, strokes
        from notebook_ink_runs import InkRuns
        from test_notebook_ink_runs import REQUEST,DOC,PAGE,HEADER
        bundle=native_story_bundle(*graph_reuse_example())
        sources={s['source_page']:s['data'] for s in bundle['sources']}
        before=append(HEADER,[[(1,2,2),(3,4,2)]],start=((0,11),(1,14)))
        context=dict(fresh=True,active=True,doc=DOC,page=PAGE,surface='story',
                     ink_revision=4,content_revision=8,text_bounds=[-468,500,936,100])
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory)
            store.register(REQUEST,DOC+'/'+PAGE+'.rm',context,bundle['blocks'],before)
            paths=[];only_unique=[];seen=set()
            for b in inks(bundle):
                offset=800 if b['scene'].endswith('-0') else 1600
                context['text_bounds']=[-468,offset-130,936,100]
                query=dict(request=REQUEST,page=DOC+'/'+PAGE+'.rm',scene=b['scene'],stage=b['stage'],
                    surface='story',ink_revision=4,revision=8,origin=[-468,offset],ui_locked=True)
                store.claim(query,lambda:context,lambda *a:None)
                store.complete({k:query[k] for k in ('request','scene','stage')})
                translated=[[(x-468,y+offset,w) for x,y,w in points]
                    for _,points,_ in strokes(sources[b['source_page']])]
                paths.extend(translated)
                if b['source_page'] not in seen:only_unique.extend(translated)
                seen.add(b['source_page'])
            proof=lambda raw:InkRuns(directory).saved_proof(REQUEST,lambda _:raw,
                lambda b:sources[b['source_page']])
            self.assertEqual(proof(append(before,only_unique))['state'],'waiting')
            self.assertEqual(proof(append(before,paths))['state'],'persisted')
            self.assertEqual(proof(append(HEADER,paths,start=((0,11),(1,15))))['state'],'waiting')

    def test_service_assembled_reply_uses_story_bridge_and_preserves_byte_bound(self):
        from notebook_semantic_reply import parse_semantic_reply
        from notebook_semantic import MAX_BYTES
        from notebook_lesson_native import native_semantic_bundle
        story,drafts=graph_reuse_example()
        value=dict(v=1,mode='story-lesson',story=story,panels=drafts)
        raw=json.dumps(value)
        parsed=parse_semantic_reply(raw)
        self.assertEqual(parsed,dict(mode='lesson',story=story,drafts=drafts))
        for playback in (False,True):
            bundle=native_semantic_bundle(raw,playback=playback)
            self.assertEqual(bundle['mode'],'story')
            self.assertEqual(len(inks(bundle)),5)
            self.assertTrue(all(('playback' in b)==playback for b in inks(bundle)))
        for bad in (raw+' '*MAX_BYTES,json.dumps(dict(value,source_doc=str(uuid.uuid4())))):
            with self.assertRaises(ValueError):parse_semantic_reply(bad)
        value['panels']['branch']['items'][0]['to']=[1000,1000]
        with patch('notebook_story_native.storyboard_assets') as assets:
            with self.assertRaises(ValueError):native_semantic_bundle(json.dumps(value))
            assets.assert_not_called()

    def test_extension_adds_only_new_ink_branch_copies_exact_historical_snapshot(self):
        story,drafts=graph_reuse_example();original=deepcopy((story,drafts))
        bundle=native_story_bundle(story,drafts)
        self.assertEqual((story,drafts),original)
        blocks=inks(bundle)
        self.assertEqual([b['stage'] for b in blocks],['axes','curve','mark','axes','branch'])
        self.assertEqual([b['stage_index'] for b in blocks],[0,1,2,0,1])
        self.assertEqual([b['stage_count'] for b in blocks],[3,3,3,2,2])
        self.assertEqual(len({b['scene'] for b in blocks[:3]}),1)
        self.assertNotEqual(blocks[2]['scene'],blocks[3]['scene'])
        for field in ('source_doc','source_page','sha256','stroke_count','point_count','playback'):
            self.assertEqual(blocks[0][field],blocks[3][field])
        self.assertEqual(len(bundle['sources']),4)
        self.assertEqual(bundle['delivery_points'],sum(b['point_count'] for b in blocks))
        self.assertLess(bundle['delivery_points'],bundle['snapshot_points'])
        self.assertFalse(bundle['tablet_proven'])

    def test_short_sentence_beyond_twelve_words_is_preserved_before_unchanged_ink(self):
        story,drafts=graph_reuse_example()
        before=native_story_bundle(story,drafts)
        caption='The inverse would send y to two inputs, so it is not a function.'
        story['panels'][0]['caption']=caption
        after=native_story_bundle(story,drafts)
        from ink import strokes
        def geometry(bundle):
            return [[points for _,points,_ in strokes(source['data'])]
                    for source in bundle['sources']]
        # Content-derived source IDs legitimately change with the caption;
        # the generated stroke geometry and delivery budgets must not.
        self.assertEqual(geometry(before),geometry(after))
        self.assertEqual(before['delivery_points'],after['delivery_points'])
        self.assertEqual(before['snapshot_points'],after['snapshot_points'])
        texts=[b['text'] for b in after['blocks'] if b['kind']=='text']
        self.assertEqual(texts.count(caption),1)

    def test_caption_once_before_each_panel_and_one_final_takeaway(self):
        story,drafts=graph_reuse_example();bundle=native_story_bundle(story,drafts)
        texts=[b['text'] for b in bundle['blocks'] if b['kind']=='text']
        self.assertEqual(texts,['']+[p['caption'] for p in story['panels']]+['Takeaway: '+story['takeaway']])
        last_text=None
        for b in bundle['blocks']:
            if b['kind']=='text':last_text=b['text']
            else:self.assertEqual(last_text,story['panels'][b['story']['panel']]['caption'])

    def test_whole_story_checked_before_any_source_is_encoded(self):
        story,drafts=graph_reuse_example()
        drafts['branch']['items'][0]['to']=[1000,1000]
        with patch('notebook_story_native.storyboard_assets') as assets:
            with self.assertRaises(ValueError):native_story_bundle(story,drafts,playback=False)
            assets.assert_not_called()
        for value in (None,1,'yes'):
            with self.assertRaises(ValueError):native_story_bundle(*graph_reuse_example(),playback=value)

    def test_panel_and_picture_order_cannot_be_dropped_mixed_or_repeated(self):
        good=inks(native_story_bundle(*graph_reuse_example()))
        cases=[good[:-1],good[1:],good+[deepcopy(good[-1])],list(reversed(good))]
        mutations=[('story','version',True),('story','panel',0),('story','part',1),
                   ('story','parts',2),('story','panels',3),('story','id','f'*64),
                   (None,'stage_index',True),(None,'stage_count',2),(None,'role','equation'),
                   (None,'scene','lesson-foreign'),(None,'stage','axes')]
        for parent,key,value in mutations:
            bad=deepcopy(good)
            (bad[1][parent] if parent else bad[1])[key]=value
            cases.append(bad)
        bad=deepcopy(good);del bad[1]['story'];cases.append(bad)
        for index,case in enumerate(cases):
            with self.subTest(case=index),self.assertRaises(ValueError):
                validate_native_ink_budget(case)

    def test_repeated_source_import_read_once_but_every_use_is_validated(self):
        bundle=native_story_bundle(*graph_reuse_example());original=deepcopy(bundle)
        doc,parent,destination=[str(uuid.uuid4()) for _ in range(3)]
        pages=[str(uuid.uuid4()) for _ in bundle['sources']]
        replies=[json.dumps(dict(type='DocumentType',parent=parent,
                    visibleName='Agent lesson source '+bundle['sources'][0]['source_doc'])).encode(),
                 json.dumps({'cPages':{'pages':[{'id':p} for p in pages]}}).encode()]
        replies += [s['data'] for s in bundle['sources']]
        check=Mock(side_effect=validate_playback);remote=Mock(side_effect=replies)
        remapped=remap_imported_lesson(bundle,doc,parent,destination,remote,validate_source=check)
        self.assertEqual(remote.call_count,2+len(pages))
        self.assertEqual(check.call_count,len(inks(bundle)))
        self.assertEqual(inks(remapped)[0]['source_page'],inks(remapped)[3]['source_page'])
        self.assertEqual(bundle,original)
        with self.assertRaisesRegex(ValueError,'page bytes'):
            remap_imported_lesson(bundle,doc,parent,destination,
                Mock(side_effect=replies[:-1]+[b'bad last source']),validate_source=validate_playback)
        self.assertEqual(bundle,original)

    def test_twelve_panels_use_twelve_sources_without_relaxing_stage_limits(self):
        story,drafts=graph_reuse_example();story['acts']=story['acts'][:1]
        template=deepcopy(story['panels'][0]);story['panels']=[];drafts={}
        for n in range(12):
            name='p'+str(n)
            panel=deepcopy(template);panel.update(id=name,base=None);story['panels'].append(panel)
            drafts[name]=dict(v=1,mode='panel-shapes',panel=name,items=[
                dict(id='ax',type='axes',x=[0,1],y=[0,1],aspect='equal'),
                dict(id='dot',type='dot',**{'in':'ax'},at=[.5,.5])])
        b=native_story_bundle(story,drafts);self.assertEqual(len(b['sources']),12)
        parent=str(uuid.uuid4());template=dict(cPages={},fileType='notebook')
        doc,archive=lesson_source_archive(b,template,parent)
        source=b['sources'][-1];block=inks(b)[-1]
        # A lesson with handwritten captions may carry more pages (7 + HAND_REGIONS) than a story's twelve.
        for story in (False,True):
            self.assertEqual(inspect_source_archive(archive,doc,parent,source['source_page'],
                block['stroke_count'],story=story),hashlib.sha256(source['data']).hexdigest())
        # Old six-step wire format keeps its old limit; story opts in explicitly.
        old=deepcopy(inks(b))
        for block in old:del block['story']
        with self.assertRaises(ValueError):validate_native_ink_budget(old)
        for field,value in (('stroke_count',65),('point_count',3001)):
            bad=deepcopy(inks(b));bad[0][field]=value
            with self.assertRaises(ValueError):validate_native_ink_budget(bad)
        bad=deepcopy(inks(b))
        for block in bad:block['point_count']=2000
        with self.assertRaisesRegex(ValueError,'whole-lesson point'):
            validate_native_ink_budget(bad)

    def test_source_reuse_cannot_hide_foreign_or_unused_pages(self):
        b=native_story_bundle(*graph_reuse_example());template=dict(cPages={},fileType='notebook')
        parent=str(uuid.uuid4())
        for action in ('extra','swap','foreign','legacy'):
            bad=deepcopy(b)
            if action=='extra':
                source=deepcopy(bad['sources'][0]);source['source_page']=str(uuid.uuid4());bad['sources'].append(source)
            elif action=='swap':bad['sources'][0],bad['sources'][1]=bad['sources'][1],bad['sources'][0]
            elif action=='foreign':inks(bad)[-1]['source_doc']=str(uuid.uuid4())
            else:bad['mode']='lesson'
            with self.subTest(action=action),self.assertRaises(ValueError):
                source_document_files(bad,template,parent)

    def test_nine_saved_model_lessons_use_native_assets_without_changing_answers(self):
        root=Path(__file__).parent/'evaluations/label-attachment-20261029/inputs'
        for case in sorted(root.iterdir()):
            with self.subTest(case=case.name):
                story=json.loads((case/'story.txt').read_text())
                drafts=json.loads((case/'shapes.txt').read_text())
                b=native_story_bundle(story,drafts)
                pages={s['source_page']:s['data'] for s in b['sources']}
                self.assertLessEqual(b['delivery_points'],b['snapshot_points'])
                self.assertLessEqual(b['snapshot_points'],12000)
                for block in inks(b):validate_playback(block,pages[block['source_page']])
                self.assertEqual(b['story'],story)


if __name__=='__main__':unittest.main()
