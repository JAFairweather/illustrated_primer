"""Request-bound semantic delivery; every tablet operation is mocked."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from notebook_delivery import delivery_options,semantic_delivery,revision_pending,with_delivery
from notebook_semantic_examples import examples
import test_notebook_lesson_server as legacy_server
from notebook_lesson_examples import EXAMPLES

DOC,PATH,REQUEST,PAGE=(getattr(legacy_server,name) for name in ('DOC','PATH','REQUEST','PAGE'))
EXAMPLES_RAW=EXAMPLES['integral']()


class DeliveryMetadataTests(unittest.TestCase):
    def test_legacy_and_revision_metadata_remain_compatible(self):
        job=['pane',PATH,1,True,REQUEST,None,True]
        self.assertEqual(delivery_options(job),{})
        self.assertFalse(semantic_delivery(job))
        revised=with_delivery(job,revision_pending=True)
        self.assertEqual(revised,job+[None,{'revision_pending':True}])
        self.assertTrue(revision_pending(revised))
        self.assertEqual(with_delivery(revised,revision_pending=None),job+[None])

    def test_format_survives_revision_transitions_without_mutating_input(self):
        original=['pane',PATH,1,True,REQUEST,None,True]
        semantic=with_delivery(original,response_format='semantic-v1')
        before=copy.deepcopy(semantic)
        revised=with_delivery(semantic,revision_pending=True)
        self.assertEqual(with_delivery(revised,revision_pending=None),semantic)
        self.assertTrue(semantic_delivery(revised))
        self.assertEqual(semantic,before)
        self.assertEqual(len(original),7)

    def test_unknown_delivery_values_fail_closed(self):
        job=['pane',PATH,1,True,REQUEST,None,True,None]
        for options in ({'response_format':'unknown'}, {'response_format':True},
                        {'response_format':None},{'revision_pending':False},
                        {'revision_pending':1},{'url':'file:///tmp/response'},'semantic-v1'):
            with self.subTest(options=options),self.assertRaises(ValueError):
                delivery_options(job+[options])
        with self.assertRaises(ValueError):delivery_options(job+[{},None])

    def test_renderer_fixture_label_is_durable_and_cannot_mark_legacy_jobs(self):
        job=['pane',PATH,1,True,REQUEST,None,True]
        for value in (True,False,'integral'):
            with self.assertRaises(ValueError):with_delivery(job,renderer_fixture=value)
        test=with_delivery(job,response_format='semantic-v1',renderer_fixture=True)
        self.assertTrue(delivery_options(with_delivery(test,revision_pending=True))['renderer_fixture'])
        with self.assertRaises(ValueError):with_delivery(test,response_format=None)


class SemanticServerDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        legacy_server.LessonServerTest.setUpClass()
        cls.s=legacy_server.LessonServerTest.s

    server_job=legacy_server.LessonServerTest.server_job
    finish_native=legacy_server.LessonServerTest.finish_native

    def test_lesson_uses_existing_import_and_saved_proof_not_coordinate_text(self):
        s=self.s;raw=json.dumps(examples()['odd-squares'])
        with self.server_job(raw,response_format='semantic-v1') as (provision,registered,remote), \
             patch.object(s,'prepare_native_lesson',side_effect=AssertionError('legacy parser called')):
            reply=self.finish_native()
            self.assertEqual([b['kind'] for b in reply['blocks']],['ink','text']*4+['media','text'])
            self.assertEqual(reply['label'],'Agent Pi Dog:')
            self.assertNotIn('"mode"',reply['text'])
            self.assertEqual(reply['styles'],[])
            provision.assert_called_once();registered.assert_called_once()
            self.assertEqual(len(provision.call_args.args[1]['sources']),4)
            self.assertTrue(semantic_delivery(s.notebook_jobs[REQUEST]))
            self.assertTrue(semantic_delivery(s.pend('')[PATH]),'equation attachments must not discard format')
            self.assertTrue(s.pend('')[PATH][7])
            with patch.object(s,'native_media_proof',return_value={'state':'persisted'}), \
                 patch.object(s,'native_ink_proof',return_value={'state':'waiting'}) as proof:
                with self.assertRaisesRegex(ValueError,'drawing save'):
                    s.native_text(PATH,REQUEST,done=True)
                proof.assert_called_once_with(REQUEST)

    def test_text_modes_have_no_import_ink_or_legacy_markup_interpretation(self):
        s=self.s
        for mode in ('answer','clarify'):
            raw=json.dumps(dict(v=1,mode=mode,text='Is the upper limit one?'))
            with self.subTest(mode=mode),self.server_job(raw,response_format='semantic-v1') as (provision,registered,remote):
                reply=s.native_text(PATH)
                self.assertEqual(reply['text'],'Is the upper limit one?')
                self.assertEqual(reply['blocks'],[dict(kind='text',text=reply['text'],styles=[])])
                self.assertEqual(reply['media'],[])
                provision.assert_not_called();registered.assert_not_called();remote.assert_not_called()

    def test_fixture_label_survives_lost_in_memory_dispatch_name(self):
        s=self.s;raw=json.dumps(examples()['integral'])
        with self.server_job(raw,response_format='semantic-v1'):
            job=with_delivery(s.pend('')[PATH],renderer_fixture=True)
            s.pend(PATH,job);s.notebook_jobs[REQUEST]=job;s.notebook_names.clear()
            reply=self.finish_native()
            self.assertEqual(reply['label'],'Agent Renderer Test:')

    def test_reveal_requires_advertised_native_capability_through_import(self):
        s=self.s;raw=json.dumps(examples()['integral'])
        with self.server_job(raw,response_format='semantic-v1') as (provision,registered,remote):
            s.native_text(PATH,ink_supported=True,reveal_supported=True)
            bundle=provision.call_args.args[1]
            self.assertTrue(all('reveal' in b for b in bundle['blocks'] if b['kind']=='ink'))
            with patch.object(s,'remap_imported_lesson') as remap:
                with self.assertRaisesRegex(ValueError,'capability changed'):
                    s.native_text(PATH,ink_supported=True,imported={'request':REQUEST,'doc':PAGE})
                remap.assert_not_called()
            reply=s.native_text(PATH,ink_supported=True,reveal_supported=True,
                                imported={'request':REQUEST,'doc':PAGE})
            self.assertTrue(all(len(b['reveal'])<=4 for b in reply['blocks'] if b['kind']=='ink'))
            registered.assert_called_once()
        with self.server_job(raw,response_format='semantic-v1'):
            reply=self.finish_native()
            self.assertTrue(all('reveal' not in b for b in reply['blocks']))

    def test_playback_capability_survives_import_and_supersedes_chunk_reveal(self):
        s=self.s;raw=json.dumps(examples()['integral'])
        with self.server_job(raw,response_format='semantic-v1') as (provision,registered,remote), \
             patch.object(s,'lesson_rollout_config',return_value={'notebooks':[DOC],'draft_check':False,'stroke_playback':True}):
            s.native_text(PATH,ink_supported=True,reveal_supported=True,playback_supported=True)
            bundle=provision.call_args.args[1]
            self.assertTrue(all('playback' in b and 'reveal' not in b for b in bundle['blocks'] if b['kind']=='ink'))
            with patch.object(s,'remap_imported_lesson') as remap:
                with self.assertRaisesRegex(ValueError,'playback client capability changed'):
                    s.native_text(PATH,ink_supported=True,reveal_supported=True,
                                  imported={'request':REQUEST,'doc':PAGE})
                remap.assert_not_called()
            with patch.object(s,'lesson_rollout_config',return_value={'notebooks':[DOC],'draft_check':False,'stroke_playback':False}):
                with self.assertRaisesRegex(ValueError,'playback client capability changed'):
                    s.native_text(PATH,ink_supported=True,playback_supported=True,
                                  imported={'request':REQUEST,'doc':PAGE})
            reply=s.native_text(PATH,ink_supported=True,playback_supported=True,
                                imported={'request':REQUEST,'doc':PAGE})
            self.assertTrue(all('playback' in b and 'reveal' not in b for b in reply['blocks'] if b['kind']=='ink'))
            registered.assert_called_once()
        with self.server_job(raw,response_format='semantic-v1'):
            reply=self.finish_native()
            self.assertTrue(all('playback' not in b for b in reply['blocks']))

    def test_playback_capability_without_operator_opt_in_keeps_chunk_mode(self):
        s=self.s;raw=json.dumps(examples()['integral'])
        with self.server_job(raw,response_format='semantic-v1') as (provision,registered,remote), \
             patch.object(s,'lesson_rollout_config',return_value={'notebooks':[DOC],'draft_check':False}):
            s.native_text(PATH,ink_supported=True,reveal_supported=True,playback_supported=True)
            bundle=provision.call_args.args[1]
            self.assertTrue(all('reveal' in b and 'playback' not in b for b in bundle['blocks'] if b['kind']=='ink'))

    def test_malformed_semantic_never_falls_back_or_touches_tablet(self):
        s=self.s
        for raw in ('{"v":1,"mode":"lesson"',EXAMPLES_RAW,'[[notebook-media-pending]]',
                    '{"v":1,"mode":"answer","text":"[[notebook-ink:fake]]"}'):
            with self.subTest(raw=raw),self.server_job(raw,response_format='semantic-v1') as (provision,registered,remote), \
                 patch.object(s,'live_capture') as capture:
                with self.assertRaises(ValueError):s.native_text(PATH,ink_supported=True)
                self.assertEqual(s.ready[PATH],raw)
                self.assertEqual(s.answers[PATH],'ready')
                self.assertFalse(Path(s.live_baseline(PATH)+'.native-attempt').exists())
                provision.assert_not_called();registered.assert_not_called();remote.assert_not_called();capture.assert_not_called()
                with patch.object(s,'write_answer') as legacy:
                    with self.assertRaisesRegex(ValueError,'native writer'):s.write_ready(PATH)
                    legacy.assert_not_called()

    def test_restart_preserves_protocol_and_invalid_revision_hold(self):
        s=self.s;bad='{"v":1,"mode":"lesson"';correct=json.dumps(examples()['integral'])
        with self.server_job(bad,response_format='semantic-v1') as (provision,registered,remote):
            s.native_text_failed(PATH,REQUEST)
            s.revise_notebook_response(REQUEST,hashlib.sha256(bad.encode()).hexdigest(),correct)
            saved=s.pend('')[PATH]
            self.assertTrue(semantic_delivery(saved));self.assertTrue(revision_pending(saved))
            s.ready.clear();s.answers.clear();s.reply_errors.clear()
            s.notebook_jobs={REQUEST:saved}
            s.answer(*saved)
            self.assertNotIn(PATH,s.ready)
            self.assertEqual(s.answers[PATH],'revision-held')
            s.retry_notebook_response(REQUEST)
            self.assertEqual(s.ready[PATH],correct)
            self.assertTrue(semantic_delivery(s.pend('')[PATH]))
            self.assertFalse(revision_pending(s.pend('')[PATH]))
            self.assertEqual(s.pend('')[PATH][8],{'response_format':'semantic-v1'})
            provision.assert_not_called();registered.assert_not_called();remote.assert_not_called()

    def test_recovered_semantic_answer_remains_bound_and_cannot_use_file_writer(self):
        s=self.s;raw=json.dumps(dict(v=1,mode='answer',text='Hello.'))
        with self.server_job(raw,response_format='semantic-v1'):
            saved=s.pend('')[PATH]
            s.ready.clear();s.answers.clear();s.answer(*saved)
            self.assertEqual(s.ready[PATH],raw)
            with patch.object(s,'write_answer') as legacy:
                s.pend(PATH)  # even lost durable pending state must not emit raw JSON
                with self.assertRaisesRegex(ValueError,'native writer'):s.write_ready(PATH)
                with self.assertRaisesRegex(ValueError,'held live'):
                    s.answer(*saved[:3],hold=False,marker=REQUEST,live=True)
                legacy.assert_not_called()

    def test_stale_import_or_page_change_cannot_register_semantic_ink(self):
        s=self.s;raw=json.dumps(examples()['odd-squares'])
        for case in ('request','page','revision'):
            with self.subTest(case=case),self.server_job(raw,response_format='semantic-v1') as (provision,registered,remote):
                s.native_text(PATH,ink_supported=True)
                callback={'request':REQUEST,'doc':PAGE}
                if case=='request':callback['request']='notebook-'+'d'*32
                with patch.object(s,'native_ack_context',return_value=(None if case=='page' else ('surface',(1,0,0,1,-702,0),10))), \
                     patch.object(s.device_context,'snapshot',return_value={'content_revision':7} if case=='revision' else {}):
                    with self.assertRaises(ValueError):s.native_text(PATH,ink_supported=True,imported=callback)
                registered.assert_not_called()
                self.assertFalse(Path(s.live_baseline(PATH)+'.native-attempt').exists())

    def test_semantic_start_requires_live_enabled_and_cannot_rebind(self):
        s=self.s
        with self.server_job('Existing legacy response.'):
            old=copy.deepcopy(s.notebook_jobs[REQUEST])
            for mutate in (lambda j:j.__setitem__(3,False),lambda j:j.__setitem__(6,False)):
                job=old[:];job[4]='notebook-'+'d'*32;job[5]=None;mutate(job)
                with self.assertRaisesRegex(ValueError,'held live'):s.start_notebook_job(job,response_format='semantic-v1')
            job=old[:];job[5]=None
            with self.assertRaisesRegex(ValueError,'rebind'):s.start_notebook_job(job,response_format='semantic-v1')
            job[4]='notebook-'+'d'*32
            with patch.object(s,'LESSON_NOTEBOOKS',''):
                with self.assertRaises(ValueError):s.start_notebook_job(job,response_format='semantic-v1')
            with self.assertRaisesRegex(ValueError,'unsupported'):s.start_notebook_job(job,response_format='unknown')
            self.assertEqual(s.notebook_jobs[REQUEST],old)
            self.assertEqual(s.pend('')[PATH],old)
        with self.server_job(json.dumps(dict(v=1,mode='answer',text='Hello.')),response_format='semantic-v1'):
            job=s.notebook_jobs[REQUEST][:7];job[5]=None
            with self.assertRaisesRegex(ValueError,'rebind'):s.start_notebook_job(job)

    def test_protocol_is_not_inferred_from_model_json(self):
        s=self.s;raw=json.dumps(examples()['integral'])
        with self.server_job(raw) as (provision,registered,remote):
            self.assertFalse(semantic_delivery(s.notebook_jobs[REQUEST]))
            with patch.object(s,'prepare_semantic_reply') as semantic:
                s.native_text(PATH)
                semantic.assert_not_called();provision.assert_not_called();registered.assert_not_called()

    def test_expired_or_changed_binding_refuses_before_any_device_io(self):
        s=self.s;raw=json.dumps(examples()['integral'])
        for case in ('expired','durable-format','ready-text','missing-memory'):
            with self.subTest(case=case),self.server_job(raw,response_format='semantic-v1') as (provision,registered,remote), \
                 patch.object(s,'live_capture') as capture:
                if case=='expired':
                    s.notebook_jobs[REQUEST][2]-=s.ANSWER_WAIT
                    s.pend(PATH,s.notebook_jobs[REQUEST])
                elif case=='durable-format':s.pend(PATH,s.notebook_jobs[REQUEST][:8])
                elif case=='ready-text':s.ready[PATH]=json.dumps(dict(v=1,mode='answer',text='Different answer.'))
                else:s.notebook_jobs.clear()
                with self.assertRaisesRegex(ValueError,'binding'):s.native_text(PATH,ink_supported=True)
                provision.assert_not_called();registered.assert_not_called();remote.assert_not_called();capture.assert_not_called()

    def test_reply_callback_cannot_restore_missing_or_downgraded_binding(self):
        s=self.s;raw=json.dumps(dict(v=1,mode='answer',text='Hello.'))
        for removed in (False,True):
            with self.subTest(removed=removed),self.server_job(raw,response_format='semantic-v1'):
                s.ready.clear()
                s.pend(PATH,None if removed else s.notebook_jobs[REQUEST][:8])
                with self.assertRaisesRegex(ValueError,'binding'):s.notebook_reply(REQUEST,raw)
                self.assertNotIn(PATH,s.ready)

    def test_start_persists_before_publishing_or_clearing_existing_state(self):
        s=self.s
        with self.server_job('Previous response.'):
            before=copy.deepcopy(s.notebook_jobs);ready=copy.deepcopy(s.ready)
            job=s.notebook_jobs[REQUEST][:];job[4]='notebook-'+'d'*32;job[5]=None
            with patch.object(s,'pend',side_effect=OSError('offline test disk failure')):
                with self.assertRaises(OSError):s.start_notebook_job(job,response_format='semantic-v1')
            self.assertEqual(s.notebook_jobs,before)
            self.assertEqual(s.ready,ready)
            self.assertEqual(s.pend('')[PATH],before[REQUEST])

    def test_new_semantic_request_cannot_start_with_a_completed_reply_or_revision(self):
        s=self.s
        with self.server_job('Previous response.'):
            for correction in (False,True):
                job=s.notebook_jobs[REQUEST][:];job[4]='notebook-'+'d'*32
                job=with_delivery(job,response_format='semantic-v1')
                if correction:
                    job[5]=None;job=with_delivery(job,revision_pending=True)
                with self.assertRaisesRegex(ValueError,'new unanswered'):s.start_notebook_job(job)

    def test_byte_budget_and_duplicate_callbacks_preserve_held_semantic_reply(self):
        s=self.s;raw=json.dumps(dict(v=1,mode='answer',text='Hello.'))
        with self.server_job(raw,response_format='semantic-v1'):
            before=copy.deepcopy(s.pend('')[PATH])
            self.assertEqual(s.notebook_reply(REQUEST,raw),{'state':'ready'})
            with self.assertRaisesRegex(ValueError,'byte budget'):
                s.notebook_reply(REQUEST,'é'*12001)
            with self.assertRaisesRegex(ValueError,'different answer'):
                s.notebook_reply(REQUEST,json.dumps(dict(v=1,mode='answer',text='Different.')))
            self.assertEqual(s.pend('')[PATH],before)
            self.assertEqual(s.ready[PATH],raw)


if __name__=='__main__':unittest.main()
