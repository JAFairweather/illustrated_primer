"""Complete generated-story delivery contracts; all tablet I/O is mocked."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from notebook_panel_examples import graph_reuse_example
import test_notebook_lesson_server as legacy_server

PATH,REQUEST,PAGE=(getattr(legacy_server,k) for k in ('PATH','REQUEST','PAGE'))


def response():
    story,drafts=graph_reuse_example()
    return json.dumps(dict(v=1,mode='story-lesson',story=story,panels=drafts))


class StoryDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        legacy_server.LessonServerTest.setUpClass()
        cls.s=legacy_server.LessonServerTest.s

    server_job=legacy_server.LessonServerTest.server_job

    def test_archive_staging_marks_explicit_story_import_without_foreground_writes(self):
        from notebook_story_native import native_story_bundle
        s=self.s;bundle=native_story_bundle(*graph_reuse_example());staged=[]
        context=('surface',(1,0,0,1,-702,0),10)
        def remote(command,data=None):
            if command.endswith(s.LESSON_SOURCE_TEMPLATE+'.metadata'):
                return json.dumps({'parent':PAGE}).encode()
            if command.endswith(PAGE+'.metadata'):
                return json.dumps({'visibleName':'Storyboard tests (Codex)'}).encode()
            if command.endswith(s.LESSON_SOURCE_TEMPLATE+'.content'):
                return json.dumps({'cPages':{},'fileType':'notebook'}).encode()
            if command.startswith('mkdir -p /home/root/.cache/herd-board/imports &&'):
                staged.append(data);return b'archive-staged'
            if command.startswith('dd if=/home/root/.cache/herd-board/imports/'):
                return staged[-1]
            self.fail('unexpected tablet command: '+command)
        with patch.object(s,'native_ack_context',return_value=context), \
             patch.object(s.device_context,'snapshot',return_value={'content_revision':7}), \
             patch.object(s,'tablet',side_effect=remote):
            result=s.prepare_notebook_lesson_import(PATH,bundle)
        self.assertEqual(result['command'],dict(doc=bundle['sources'][0]['source_doc'],
            parent=PAGE,pages=4,story_version=1))
        self.assertEqual(len(staged),1)
        self.assertEqual(result['content_revision'],7)

    def test_story_capability_required_before_import_and_again_on_callback(self):
        s=self.s
        with self.server_job(response(),response_format='semantic-v1') as (provision,register,remote):
            for capability in (False,1,'1',None):
                with self.assertRaisesRegex(ValueError,'story client'):
                    s.native_text(PATH,ink_supported=True,story_supported=capability)
            provision.assert_not_called();register.assert_not_called();remote.assert_not_called()
            s.native_text(PATH,ink_supported=True,story_supported=True)
            provision.assert_called_once()
            with self.assertRaisesRegex(ValueError,'story client'):
                s.native_text(PATH,ink_supported=True,imported={'request':REQUEST,'doc':PAGE})
            register.assert_not_called();remote.assert_not_called()
            self.assertFalse(Path(s.live_baseline(PATH)+'.native-attempt').exists())

    def test_branching_story_uses_existing_import_registration_and_saved_proof(self):
        s=self.s
        with self.server_job(response(),response_format='semantic-v1') as (provision,register,remote), \
             patch.object(s,'prepare_native_lesson',side_effect=AssertionError('legacy writer used')), \
             patch.object(s,'lesson_rollout_config',return_value={'stroke_playback':True}):
            s.native_text(PATH,ink_supported=True,story_supported=True,playback_supported=True)
            prepared=provision.call_args.args[1]
            self.assertEqual(prepared['mode'],'story')
            self.assertEqual(len(prepared['sources']),4)
            # The legacy fixture zips one source per stage. Stories may reuse
            # sources, so validate ALL uses, including the final branch.
            def remap(bundle,*args,validate_source):
                sources={x['source_page']:x['data'] for x in bundle['sources']}
                for b in bundle['blocks']:
                    if b['kind']=='ink':validate_source(b,sources[b['source_page']])
                return bundle
            with patch.object(s,'remap_imported_lesson',side_effect=remap):
                reply=s.native_text(PATH,ink_supported=True,story_supported=True,playback_supported=True,
                    imported={'request':REQUEST,'doc':PAGE})
            self.assertEqual(reply['label'],'Agent Pi Dog:')
            blocks=[b for b in reply['blocks'] if b['kind']=='ink']
            self.assertEqual([b['stage'] for b in blocks],['axes','curve','mark','axes','branch'])
            self.assertEqual(len({b['scene'] for b in blocks}),2)
            self.assertTrue(all('playback' in b for b in blocks))
            register.assert_called_once()
            self.assertEqual(register.call_args.args[3],reply['blocks'])
            with patch.object(s,'native_ink_proof',return_value={'state':'waiting'}) as proof:
                with self.assertRaisesRegex(ValueError,'drawing save'):
                    s.native_text(PATH,REQUEST,done=True)
                proof.assert_called_once_with(REQUEST)
            self.assertIn(PATH,s.ready)
            with patch.object(s,'native_ink_proof',return_value={'state':'persisted'}), \
                 patch.object(s,'settled_frame',side_effect=lambda frame,*args:frame), \
                 patch.object(s,'aligned_writing_box',return_value=(100,100,200,200)):
                self.assertEqual(s.native_text(PATH,REQUEST,done=True)['state'],'written')
            self.assertNotIn(PATH,s.ready)

    def test_changed_page_or_invalid_final_panel_never_reaches_foreground(self):
        s=self.s
        with self.server_job(response(),response_format='semantic-v1') as (provision,register,remote):
            s.native_text(PATH,ink_supported=True,story_supported=True)
            with patch.object(s,'native_ack_context',return_value=('other',(1,0,0,1,-702,0),10)):
                with self.assertRaisesRegex(ValueError,'Page or input changed'):
                    s.native_text(PATH,ink_supported=True,story_supported=True,
                        imported={'request':REQUEST,'doc':PAGE})
            register.assert_not_called();remote.assert_not_called()
        value=json.loads(response());value['panels']['branch']['items'][0]['to']=[1000,1000]
        with self.server_job(json.dumps(value),response_format='semantic-v1') as (provision,register,remote):
            with self.assertRaises(ValueError):s.native_text(PATH,ink_supported=True,story_supported=True)
            provision.assert_not_called();register.assert_not_called();remote.assert_not_called()
            self.assertFalse(Path(s.live_baseline(PATH)+'.native-attempt').exists())


if __name__=='__main__':unittest.main()
