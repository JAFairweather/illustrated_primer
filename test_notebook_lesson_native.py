import hashlib
import copy
import json
import tempfile
import unittest
import uuid
import io
import zipfile
from unittest.mock import patch, Mock

from ink import strokes
from notebook_lesson_examples import EXAMPLES
from notebook_lesson import format_lesson
from notebook_lesson_native import (native_lesson_bundle, prepare_native_lesson,
                                    source_document_files, provision_lesson_sources, lesson_source_archive,
                                    inspect_source_archive, remap_imported_lesson)
from notebook_media import AssetStore, notebook_blocks, notebook_content


class NativeLessonTest(unittest.TestCase):
    def test_import_remaps_every_page_only_after_full_byte_validation(self):
        bundle = native_lesson_bundle(EXAMPLES['integral']())
        original = copy.deepcopy(bundle)
        doc, parent, destination = [str(uuid.uuid4()) for _ in range(3)]
        pages = [str(uuid.uuid4()) for _ in bundle['sources']]
        metadata = dict(type='DocumentType', parent=parent,
                        visibleName='Agent lesson source '+bundle['sources'][0]['source_doc'])
        content = {'cPages':{'pages':[{'id':p} for p in pages]}}
        replies = [json.dumps(metadata).encode(), json.dumps(content).encode()]
        replies += [s['data'] for s in bundle['sources']]
        remote = Mock(side_effect=replies)
        result = remap_imported_lesson(bundle,doc,parent,destination,remote)
        self.assertEqual(bundle,original)
        for item,page in zip(result['sources'],pages):
            self.assertEqual((item['source_doc'],item['source_page']),(doc,page))
        for item,page in zip([b for b in result['blocks'] if b['kind']=='ink'],pages):
            self.assertEqual((item['source_doc'],item['source_page']),(doc,page))
        self.assertTrue(all(len(c.args)==1 and c.args[0].startswith('dd if=') for c in remote.call_args_list))
        for invalid in (replies[:-1]+[b'bad final page'],
                        replies[:2]+list(reversed(replies[2:])),
                        [b'{}']+replies[1:]):
            with self.assertRaises(ValueError):
                remap_imported_lesson(bundle,doc,parent,destination,Mock(side_effect=invalid))
            self.assertEqual(bundle,original)
        for invalid_doc in (destination, '../path', None):
            remote = Mock()
            with self.assertRaises(ValueError):
                remap_imported_lesson(bundle,invalid_doc,parent,destination,remote)
            remote.assert_not_called()
        duplicate = {'cPages':{'pages':[{'id':pages[0]} for p in pages]}}
        with self.assertRaises(ValueError):
            remap_imported_lesson(bundle,doc,parent,destination,
                Mock(side_effect=[replies[0],json.dumps(duplicate).encode()]))

    def test_import_validates_actual_bytes_once_before_returning_any_bundle(self):
        bundle = native_lesson_bundle(EXAMPLES['integral']())
        original = copy.deepcopy(bundle)
        doc, parent, destination = [str(uuid.uuid4()) for _ in range(3)]
        pages = [str(uuid.uuid4()) for _ in bundle['sources']]
        replies = [json.dumps(dict(type='DocumentType',parent=parent,
                    visibleName='Agent lesson source '+bundle['sources'][0]['source_doc'])).encode(),
                   json.dumps({'cPages':{'pages':[{'id':p} for p in pages]}}).encode()]
        replies += [s['data'] for s in bundle['sources']]
        check = Mock()
        remote = Mock(side_effect=replies)
        result = remap_imported_lesson(bundle,doc,parent,destination,remote,validate_source=check)
        self.assertEqual(remote.call_count,2+len(pages))
        self.assertEqual(check.call_count,len(pages))
        for call, block, data in zip(check.call_args_list,
                [b for b in result['blocks'] if b['kind']=='ink'],replies[2:]):
            self.assertEqual(call.args,(block,data))
            self.assertIs(call.args[1],data)  # actual device result, not prepared bytes
        check = Mock(side_effect=[None]*(len(pages)-1)+[ValueError('bad final playback')])
        with self.assertRaisesRegex(ValueError,'bad final playback'):
            remap_imported_lesson(bundle,doc,parent,destination,Mock(side_effect=replies),validate_source=check)
        self.assertEqual(bundle,original)
        check = Mock()
        with self.assertRaisesRegex(ValueError,'page bytes'):
            remap_imported_lesson(bundle,doc,parent,destination,
                Mock(side_effect=replies[:-1]+[b'changed']),validate_source=check)
        self.assertEqual(check.call_count,len(pages)-1)
        self.assertEqual(bundle,original)
        for change in ('missing','reordered'):
            bad=copy.deepcopy(bundle)
            inks=[i for i,b in enumerate(bad['blocks']) if b['kind']=='ink']
            if change=='missing':bad['blocks'].pop(inks[-1])
            else:bad['blocks'][inks[0]],bad['blocks'][inks[1]]=bad['blocks'][inks[1]],bad['blocks'][inks[0]]
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'source/block'):
                remap_imported_lesson(bad,doc,parent,destination,Mock(side_effect=replies),validate_source=Mock())

    def test_import_archive_contains_only_fresh_validated_sources(self):
        bundle = native_lesson_bundle(EXAMPLES['integral']())
        parent = str(uuid.uuid4())
        template = {'cPages':{}, 'fileType':'notebook'}
        doc, data = lesson_source_archive(bundle, template, parent)
        page = bundle['sources'][0]['source_page']
        count = bundle['blocks'][0]['stroke_count']
        self.assertEqual(inspect_source_archive(data, doc, parent, page, count),
                         hashlib.sha256(bundle['sources'][0]['data']).hexdigest())
        for args in ((doc, parent, page, count+1), (doc, str(uuid.uuid4()), page, count),
                     (doc, parent, str(uuid.uuid4()), count)):
            with self.assertRaises(ValueError):
                inspect_source_archive(data, *args)
        unsafe = io.BytesIO(data)
        with zipfile.ZipFile(unsafe, 'a') as archive:
            archive.writestr('../foreign.metadata', '{}')
        with self.assertRaises(ValueError):
            inspect_source_archive(unsafe.getvalue(), doc, parent, page, count)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            expected = {doc+'.metadata', doc+'.content', doc+'.pagedata'}
            for source in bundle['sources']:
                name = doc+'/'+source['source_page']+'.rm'
                expected.add(name)
                self.assertEqual(archive.read(name), source['data'])
            self.assertEqual(set(archive.namelist()), expected)
            self.assertTrue(all(not n.startswith('/') and '..' not in n for n in archive.namelist()))
            meta = json.loads(archive.read(doc+'.metadata'))
            self.assertEqual(meta['visibleName'], 'Agent lesson source '+doc)
            self.assertEqual(meta['parent'], parent)
            self.assertEqual(archive.read(doc+'.pagedata'), b'Blank\n'*len(bundle['sources']))
        bad = copy.deepcopy(bundle)
        bad['sources'][0]['data'] = b'x'*262144
        with self.assertRaisesRegex(ValueError, 'transfer budget'):
            lesson_source_archive(bad, template, parent)

    def test_source_provisioning_checks_every_byte_and_publishes_metadata_last(self):
        bundle = native_lesson_bundle(EXAMPLES['odd-squares']())
        template = {'cPages':{}, 'fileType':'notebook'}
        parent = 'a7a7e181-7b6b-4a84-a169-3bc7e5fe35da'
        uploaded, events = {}, []
        def remote(command, data=None):
            events.append(command)
            if 'printf source-created' in command:
                return b'source-created'
            if data is not None:
                target = command.split('test ! -e ')[1].split(' ')[0]
                self.assertNotIn(target,uploaded)
                uploaded[target] = data
                self.assertIn('set -C',command)
                return b'source-published'
            target = command.split('dd if=')[1].split(' ')[0]
            return uploaded[target]
        guard = Mock()
        doc = provision_lesson_sources(bundle,template,parent,remote,guard)
        self.assertTrue(events[-1].startswith('dd if='))
        self.assertIn(doc+'.metadata',events[-1])
        self.assertEqual(len(uploaded),6)
        self.assertEqual(guard.call_count,8)
        self.assertTrue(all(doc in path for path in uploaded))

    def test_failed_reservation_readback_or_page_change_never_publishes_metadata(self):
        bundle = native_lesson_bundle(EXAMPLES['odd-squares']())
        template = {'cPages':{}}
        parent = 'a7a7e181-7b6b-4a84-a169-3bc7e5fe35da'
        for responses in ([b''],[b'source-created',b''],
                          [b'source-created',b'source-published',b'corrupt']):
            remote = Mock(side_effect=responses)
            with self.subTest(responses=responses), self.assertRaises(ValueError):
                provision_lesson_sources(bundle,template,parent,remote,Mock())
            self.assertFalse(any('.metadata' in c.args[0] and len(c.args)>1 for c in remote.call_args_list))
        remote = Mock(return_value=b'source-created')
        guard = Mock(side_effect=[None,ValueError('page changed')])
        with self.assertRaisesRegex(ValueError,'page changed'):
            provision_lesson_sources(bundle,template,parent,remote,guard)
        self.assertEqual(remote.call_count,1)

    def test_equation_is_resolved_to_registered_media_before_any_device_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            bundle = prepare_native_lesson(EXAMPLES['integral'](),store)
            self.assertEqual({b['kind'] for b in bundle['blocks']},{'text','ink','media'})
            equations = [b for b in bundle['blocks'] if b['kind'] == 'media']
            self.assertEqual(len(equations),1)
            self.assertTrue(store.get(equations[0]['asset']).startswith(b'\x89PNG'))
        store = Mock()
        with self.assertRaises(ValueError):
            prepare_native_lesson(EXAMPLES['integral']().replace('Takeaway:','Bad ending:'),store)
        store.equation.assert_not_called()

    def test_source_payloads_are_separate_fresh_pages_and_metadata_is_last(self):
        bundle = native_lesson_bundle(EXAMPLES['odd-squares']())
        template = {'fileType':'notebook','formatVersion':2,'orientation':'portrait',
                    'cPages':{'pages':[{'id':'old-page-id'}], 'lastOpened':{'value':'old-page-id'}},
                    'pages':['old-page-id'],'redirectionPageMap':['old-page-id'],
                    'pageTags':[{'pageId':'old-page-id'}],'tags':[{'name':'private tag'}],
                    'pageMetadatas':{'old-page-id':{'scrollPosition':9000}}}
        original = copy.deepcopy(template)
        parent = 'a7a7e181-7b6b-4a84-a169-3bc7e5fe35da'
        doc, files = source_document_files(bundle,template,parent)
        self.assertEqual(template,original)
        self.assertEqual([name for name,_ in files[-2:]],[doc+'.content',doc+'.metadata'])
        self.assertEqual(len(files),6)
        content = json.loads(files[-2][1])
        metadata = json.loads(files[-1][1])
        self.assertNotIn('old-page-id',json.dumps(content))
        self.assertNotIn('private tag',json.dumps(content))
        self.assertEqual(content['pageCount'],4)
        self.assertEqual(metadata['parent'],parent)
        for (name,data),source in zip(files,bundle['sources']):
            self.assertEqual(name,doc+'/'+source['source_page']+'.rm')
            self.assertEqual(data,source['data'])
        with self.assertRaises(ValueError):
            source_document_files(bundle,{},parent)
        with self.assertRaises(ValueError):
            source_document_files(bundle,template,'../foreground')
        duplicate = copy.deepcopy(bundle)
        duplicate['sources'][1]['source_page'] = duplicate['sources'][0]['source_page']
        with self.assertRaises(ValueError):
            source_document_files(duplicate,template,parent)

    def test_legacy_reply_path_cannot_dump_drawing_json_as_prose(self):
        for function in (notebook_blocks,notebook_content):
            for raw in (EXAMPLES['integral'](),'```board-step\ninvalid JSON\n```'):
                store = Mock()
                with self.subTest(function=function.__name__), self.assertRaisesRegex(ValueError,'native lesson adapter'):
                    function(raw,store)
                store.equation.assert_not_called()

    def test_ink_then_caption_shared_picture_and_fresh_immutable_sources(self):
        for name, example in EXAMPLES.items():
            with self.subTest(name=name):
                bundle = native_lesson_bundle(example())
                plan, blocks, sources = (bundle[k] for k in ('plan','blocks','sources'))
                count = len(plan['stages'])
                self.assertEqual(len(sources),count)
                for index, (stage, source) in enumerate(zip(plan['stages'], sources)):
                    ink, caption = blocks[index*2:index*2+2]
                    self.assertEqual(ink['kind'],'ink')
                    self.assertEqual(caption['kind'],'text')
                    self.assertEqual(caption['text'],stage['text'])
                    self.assertEqual(ink['scene'],plan['scene'])
                    self.assertEqual(ink['stage_index'],index)
                    self.assertEqual(ink['stage_count'],count)
                    self.assertEqual(ink['sha256'],hashlib.sha256(source['data']).hexdigest())
                    self.assertEqual(ink['stroke_count'],len(strokes(source['data'])))
                    for field in ('source_doc','source_page'):
                        self.assertEqual(ink[field],str(uuid.UUID(source[field])))
                    self.assertNotIn('data',ink)  # no binary payload in client JSON
                self.assertEqual(len({s['source_doc'] for s in sources}),1)
                self.assertEqual(len({s['source_page'] for s in sources}),count)
                self.assertEqual(blocks[-2],dict(kind='equation',source=plan['equation']))
                self.assertEqual(blocks[-1]['text'],'Takeaway: '+plan['takeaway'])
                second = native_lesson_bundle(example())
                self.assertNotEqual(sources[0]['source_doc'],second['sources'][0]['source_doc'])

    def test_last_step_or_equation_failure_allocates_no_source_identity(self):
        valid = EXAMPLES['integral']()
        for invalid in (valid.replace('Takeaway:','Missing takeaway:'), valid+'\n```python\n1\n```'):
            with patch('notebook_lesson_native.uuid.uuid4',side_effect=AssertionError('source allocated too early')):
                with self.assertRaises(ValueError):
                    native_lesson_bundle(invalid)

    def test_later_label_collision_is_held_before_assets_or_source_ids(self):
        response = format_lesson([
            {'caption':'First, draw the arrow.',
             'draw':[{'op':'arrow','from':[100,100],'to':[300,100]}]},
            {'caption':'Add a separate shape.',
             'draw':[{'op':'circle','center':[400,200],'radius':20}]},
            {'caption':'This label mistakenly covers earlier ink.',
             'draw':[{'op':'label','at':[200,110],'text':'bad','size':20}]},
        ], 'Conclusion.')
        with patch('notebook_lesson_native.storyboard_assets',
                   side_effect=AssertionError('assets built before final layout validation')), \
             patch('notebook_lesson_native.uuid.uuid4',
                   side_effect=AssertionError('source allocated before final layout validation')):
            with self.assertRaisesRegex(ValueError,'label collision'):
                native_lesson_bundle(response)


if __name__ == '__main__':
    unittest.main()
