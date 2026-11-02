"""Offline server integration: all device calls are mocked, never a live test."""
import contextlib
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import patch
from PIL import Image

from notebook_lesson_examples import EXAMPLES
from notebook_media import AssetStore
from notebook_lesson_native import native_lesson_bundle, lesson_source_archive
from notebook_ink_runs import InkRuns

DOC = '905df7ae-ff54-46b9-a71e-45bb02bef638'
PAGE = '3ad12986-0467-48fe-986d-d1bd480c4777'
PATH = DOC+'/'+PAGE+'.rm'
REQUEST = 'notebook-'+'c'*32


class LessonServerTest(unittest.TestCase):
    def test_preflight_timings_retain_first_pass_and_fixed_recapture_reasons(self):
        s = self.s
        layout = dict(command=dict(request=REQUEST, phase='before'), samples=[])
        with self.server_job(EXAMPLES['integral']()) as (_, registered, _), \
             patch.object(s.native_ink_runs, 'finish_capture', return_value={'measured': True}):
            registered.side_effect = [dict(measure_layout=layout['command'], layout_reason=reason)
                                      for reason in ('initial', 'snapshot_changed', 'context_changed')] + [{'registered': 3}]
            s.native_text(PATH, ink_supported=True, preservation_supported=True)
            first = s.reply_timings[PATH]['native_requested_first']
            for index in range(4):
                result = s.native_text(PATH, ink_supported=True, preservation_supported=True,
                                      imported={'request': REQUEST, 'doc': PAGE},
                                      layout=layout if index else None)
                self.assertEqual('measure_layout' in result, index < 3)
                self.assertEqual(Path(s.live_baseline(PATH)+'.native-attempt').exists(), index == 3)
                self.assertEqual(s.reply_timings[PATH]['native_requested_first'], first)
            stages = s.reply_timings[PATH]
            self.assertGreater(stages['native_requested'], first)
            self.assertLessEqual(stages['native_before_layout_received_first'],
                                 stages['native_before_layout_measured_first'])
            for reason in ('initial', 'snapshot_changed', 'context_changed'):
                self.assertIn('native_before_layout_'+reason, stages)
            # Existing timing_status is still entirely relative milliseconds.
            stages['respond'] = first
            self.assertEqual(s.timing_status(PATH)['native_requested_first'], 0)
            self.assertTrue(all(type(value) is int for value in s.timing_status(PATH).values()))

    def test_successful_final_ack_clears_hint_for_every_native_reply_mode(self):
        from notebook_semantic_examples import examples
        s=self.s
        cases=[('legacy-text','Plain reply',None,False),
               ('legacy-lesson',EXAMPLES['integral'](),None,False),
               ('answer',json.dumps(dict(v=1,mode='answer',text='Plain reply')),'semantic-v1',False),
               ('clarify',json.dumps(dict(v=1,mode='clarify',text='Which limit?')),'semantic-v1',False),
               ('raster-math',json.dumps(examples()['fractions-variant']),'semantic-v1',False),
               ('pen-math',json.dumps(examples()['fractions-variant']),'semantic-v1',True)]
        for name,response,fmt,pen in cases:
            with self.subTest(name=name),self.server_job(response,response_format=fmt), \
                 patch.object(s,'native_media_proof',return_value={'state':'persisted'}), \
                 patch.object(s,'native_ink_proof',return_value={'state':'persisted'}), \
                 patch.object(s,'settled_frame',side_effect=lambda frame,*args:frame), \
                 patch.object(s,'aligned_writing_box',return_value=(100,100,200,200)), \
                 patch.object(s,'lesson_rollout_config',return_value={'stroke_playback':True}):
                if name in ('legacy-text','answer','clarify'):
                    s.native_text(PATH)
                else:
                    s.native_text(PATH,ink_supported=True,playback_supported=pen,pen_equations_supported=pen)
                    s.native_text(PATH,ink_supported=True,playback_supported=pen,pen_equations_supported=pen,
                                  imported={'request':REQUEST,'doc':PAGE})
                attempt=Path(s.live_baseline(PATH)+'.native-attempt')
                saved_attempt=attempt.read_bytes()
                # No final ACK yet: this is uncertainty, not proof of missing ink.
                self.assertEqual(s.incomplete_native_attempt(PATH),{'request':REQUEST})
                final=s.native_text(PATH,REQUEST,done=True)
                self.assertEqual(final['state'],'written')
                self.assertEqual(s.answer_status(PATH)['state'],'written')
                self.assertNotIn(PATH,s.ready)
                self.assertNotIn(PATH,s.pend(''))
                self.assertIsNone(s.incomplete_native_attempt(PATH))
                self.assertEqual(attempt.read_bytes(),saved_attempt,'retain no-replay evidence')
                # Covers final response lost AFTER server accepted completion:
                # a late client failure must not demote the recorded success.
                self.assertEqual(s.native_text_failed(PATH,REQUEST)['state'],'written')
                self.assertIsNone(s.incomplete_native_attempt(PATH))

    def test_incomplete_hint_only_in_accepted_active_context(self):
        s=self.s
        with self.server_job(EXAMPLES['integral']()), \
             patch.object(s.device_context,'update') as update, \
             patch.object(s.device_context,'awake_seconds',return_value=0), \
             patch.object(s.view_audit,'command',return_value=None), \
             patch.object(s.native_probe,'command',return_value=None):
            Path(s.live_baseline(PATH)+'.native-attempt').write_text(REQUEST)
            for accepted,active in ((False,True),(True,False),(True,True)):
                update.return_value={'accepted':accepted}
                result=s.native_context_report({'active':active,'doc':DOC,'page':PAGE})
                if accepted and active:
                    self.assertEqual(result['incomplete_reply'],{'request':REQUEST})
                    self.assertNotIn('repair',result)
                else:
                    self.assertNotIn('incomplete_reply',result)

    def test_incomplete_hint_reuses_existing_attempt_after_restart(self):
        s=self.s
        with self.server_job(EXAMPLES['integral']()) as (provision,registered,remote):
            self.assertIsNone(s.incomplete_native_attempt(PATH))
            attempt=Path(s.live_baseline(PATH)+'.native-attempt')
            attempt.write_text(REQUEST)
            original=attempt.read_bytes()
            for state in ('writing','failed','ready'): # ready is resume() after backend restart
                s.answers[PATH]=state
                self.assertEqual(s.incomplete_native_attempt(PATH),{'request':REQUEST})
                self.assertEqual(attempt.read_bytes(),original)
                self.assertEqual(s.answers[PATH],state,'hint never changes delivery state')
            s.answers[PATH]='written'
            self.assertIsNone(s.incomplete_native_attempt(PATH))
            s.answers[PATH]='ready';attempt.write_text('notebook-'+'b'*32)
            self.assertIsNone(s.incomplete_native_attempt(PATH),'superseded attempt')
            provision.assert_not_called();registered.assert_not_called();remote.assert_not_called()

    def test_pen_equations_require_capability_and_are_frozen_across_import(self):
        from notebook_semantic_examples import examples
        response=json.dumps(examples()['fractions-variant'])
        s=self.s
        with self.server_job(response,response_format='semantic-v1') as (provision,registered,remote):
            with patch.object(s,'lesson_rollout_config',return_value={'stroke_playback':True}):
                s.native_text(PATH,ink_supported=True,playback_supported=True,pen_equations_supported=True)
                bundle=provision.call_args.args[1]
                self.assertEqual(bundle['blocks'][-2]['role'],'equation')
                self.assertFalse(any(b['kind']=='media' for b in bundle['blocks']))
                with self.assertRaisesRegex(ValueError,'pen-equation client capability'):
                    s.native_text(PATH,ink_supported=True,playback_supported=True,
                                  imported={'request':REQUEST,'doc':PAGE})
                registered.assert_not_called()
                reply=s.native_text(PATH,ink_supported=True,playback_supported=True,pen_equations_supported=True,
                                    imported={'request':REQUEST,'doc':PAGE})
                self.assertEqual(reply['blocks'][-2]['role'],'equation')
                registered.assert_called_once()

    def test_handwritten_takeaway_requires_config_and_capability_frozen_across_import(self):
        from notebook_semantic_examples import examples
        response=json.dumps(examples()['fractions-variant'])
        s=self.s
        for config,supported,role in (({'stroke_playback':True},True,None),
                                      ({'stroke_playback':True,'reply_hand':'primer'},False,None),
                                      ({'stroke_playback':True,'reply_hand':'primer'},True,'hand')):
            with self.subTest(config=config,supported=supported), \
                 self.server_job(response,response_format='semantic-v1') as (provision,registered,remote), \
                 patch.object(s,'lesson_rollout_config',return_value=config):
                s.native_text(PATH,ink_supported=True,playback_supported=True,pen_equations_supported=True,
                              hand_supported=supported)
                self.assertEqual(provision.call_args.args[1]['blocks'][-1].get('role'),role)
                if role:
                    with self.assertRaisesRegex(ValueError,'handwriting client capability'):
                        s.native_text(PATH,ink_supported=True,playback_supported=True,pen_equations_supported=True,
                                      imported={'request':REQUEST,'doc':PAGE})
                    registered.assert_not_called()
                    reply=s.native_text(PATH,ink_supported=True,playback_supported=True,
                                        pen_equations_supported=True,hand_supported=True,
                                        imported={'request':REQUEST,'doc':PAGE})
                    self.assertEqual(reply['blocks'][-1]['role'],'hand')
                    registered.assert_called_once()

    def test_a_printed_reply_region_holds_more_strokes_than_a_drawing_stage_through_import(self):
        from notebook_semantic_examples import examples
        from notebook_drawing import HAND_STROKES
        lesson=dict(examples()['fractions-variant'],takeaway='A cat purrs by twitching the muscles of its voice box '
                    'many times a second, so the air it breathes in and out buzzes, and it purrs when it is happy, when '
                    'it is hurt and when it wants its kittens close.')
        s=self.s
        with self.server_job(json.dumps(lesson),response_format='semantic-v1') as (provision,registered,remote), \
             patch.object(s,'lesson_rollout_config',return_value={'stroke_playback':True,'reply_hand':'letter'}):
            kwargs=dict(ink_supported=True,playback_supported=True,pen_equations_supported=True,hand_supported=True)
            s.native_text(PATH,**kwargs)
            hands=[b for b in provision.call_args.args[1]['blocks'] if b.get('role')=='hand']
            self.assertTrue(any(64<b['stroke_count']<=HAND_STROKES for b in hands),[b['stroke_count'] for b in hands])
            reply=s.native_text(PATH,imported={'request':REQUEST,'doc':PAGE},**kwargs)
            self.assertEqual(reply['blocks'][-1]['role'],'hand')
            registered.assert_called_once()

    def test_a_named_reader_replaces_the_agent_label_and_opens_a_handwritten_reply(self):
        from notebook_semantic_examples import examples
        response=json.dumps(examples()['fractions-variant'])
        s=self.s
        config={'stroke_playback':True,'reply_hand':'primer','reader':'James'}
        with self.server_job(response,response_format='semantic-v1') as (provision,registered,remote), \
             patch.object(s,'lesson_rollout_config',return_value=config):
            s.native_text(PATH,ink_supported=True,playback_supported=True,pen_equations_supported=True,
                          hand_supported=True)
            blocks=provision.call_args.args[1]['blocks']
            from notebook_hand_ink import hand_plans
            self.assertEqual(blocks[1]['scene'],hand_plans('James, once upon a time...','primer',
                                                           place=len(examples()['fractions-variant']['steps'])+1)[0]['scene'])
            self.assertEqual(s.reply_label('Pi Dog',blocks),'')
            self.assertEqual(s.reply_label('Pi Dog',[dict(kind='text',text='Hello.',styles=[])]),'James,')
        with patch.object(s,'lesson_rollout_config',return_value={'stroke_playback':True}):
            self.assertEqual(s.reply_label('Pi Dog',blocks),'Agent Pi Dog:')

    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader('lesson_server_test',
                    str(Path(__file__).with_name('herd-board-serve')))
        cls.s = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(cls.s)

    @contextlib.contextmanager
    def server_job(self, response, enabled=True, response_format=None):
        s = self.s
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            values = dict(PENDING=directory+'/pending.json', ready={}, answers={}, notebook_jobs={},
                          reply_errors={}, reply_timings={}, retry_requests={}, lesson_imports={},
                          LESSON_NOTEBOOKS=DOC if enabled else '',
                          native_ink_runs=InkRuns(directory+'/ink-runs'),
                          media_store=AssetStore(directory+'/assets'), notebook_names={REQUEST:'pidog'})
            for key,value in values.items():
                stack.enter_context(patch.object(s,key,value))
            stack.enter_context(patch.object(s,'live_baseline',return_value=directory+'/baseline.png'))
            stack.enter_context(patch.object(s,'native_ack_context',return_value=('surface',(1,0,0,1,-702,0),10)))
            stack.enter_context(patch.object(s,'live_capture',return_value=Image.new('L',(1404,1872),255)))
            stack.enter_context(patch.object(s,'native_image_resources',return_value=[]))
            stack.enter_context(patch.object(s,'native_ink_source'))
            registered = stack.enter_context(patch.object(s.native_ink_runs,'register'))
            provision = stack.enter_context(patch.object(s,'prepare_notebook_lesson_import',
                return_value=dict(context=('surface',(1,0,0,1,-702,0),10), content_revision=None,
                    command=dict(doc=PAGE,parent=PAGE,pages=3))))
            def remap(bundle,*args,validate_source):
                for source,block in zip(bundle['sources'],(b for b in bundle['blocks'] if b['kind']=='ink')):
                    validate_source(block,source['data'])
                return bundle
            stack.enter_context(patch.object(s,'remap_imported_lesson',side_effect=remap))
            remote = stack.enter_context(patch.object(s,'tablet',return_value=b'mocked saved page'))
            job = ['pane',PATH,int(time.time()),True,REQUEST,None,True]
            s.start_notebook_job(job,response_format=response_format)
            s.notebook_reply(REQUEST,response)
            yield provision,registered,remote

    def finish_native(self):
        self.s.native_text(PATH, ink_supported=True)
        return self.s.native_text(PATH, ink_supported=True, imported={'request':REQUEST,'doc':PAGE})

    def test_native_response_contains_interleaved_stages_and_registered_equation(self):
        s = self.s
        with self.server_job(EXAMPLES['integral']()) as (provision,registered,remote):
            reply = self.finish_native()
            self.assertEqual(reply['label'],'Agent Pi Dog:')
            self.assertEqual([b['kind'] for b in reply['blocks']],
                             ['ink','text','ink','text','ink','text','media','text'])
            self.assertNotIn('board-step',reply['text'])
            provision.assert_called_once()
            registered.assert_called_once()
            self.assertEqual(registered.call_args.args[0],REQUEST)
            self.assertEqual(registered.call_args.args[1],PATH)
            self.assertTrue(reply['blocks'][-2]['url'].startswith('file:///home/root/.cache/'))
            self.assertEqual(len({b['scene'] for b in reply['blocks'] if b['kind']=='ink'}),1)
            with patch.object(s,'native_media_proof',return_value={'state':'persisted'}), \
                 patch.object(s,'native_ink_proof',return_value={'state':'waiting'}) as proof:
                with self.assertRaisesRegex(ValueError,'drawing save'):
                    s.native_text(PATH,REQUEST,done=True)
                proof.assert_called_once_with(REQUEST)

    def test_unprovable_anchor_places_the_words_and_says_the_drawing_was_left_out(self):
        s = self.s
        with self.server_job(EXAMPLES['integral']()) as (provision,registered,remote), \
             patch.object(s,'ink_fallbacks',set()):
            registered.side_effect = ValueError('unsupported native text anchor 1:29')
            reply = self.finish_native()
            self.assertNotIn('ink',[b['kind'] for b in reply['blocks']])
            self.assertEqual(reply['blocks'][0]['kind'],'text')
            self.assertIn('drawing could not be placed',reply['blocks'][0]['text'])
            self.assertIn(REQUEST,s.ink_fallbacks)
            self.assertEqual(s.answers[PATH],'writing')
            with patch.object(s,'native_media_proof',return_value={'state':'persisted'}), \
                 patch.object(s,'native_ink_proof') as proof:
                with self.assertRaises(ValueError):
                    s.native_text(PATH,REQUEST,done=True)
                proof.assert_not_called()
        with self.server_job(EXAMPLES['integral']()) as (provision,registered,remote), \
             patch.object(s,'ink_fallbacks',set()):
            registered.side_effect = ValueError('page changed under the drawing')
            with self.assertRaisesRegex(ValueError,'page changed'):
                self.finish_native()
            self.assertFalse(s.ink_fallbacks)

    def test_drawing_outside_the_catalog_is_left_out_before_registration_or_claim(self):
        s = self.s
        with self.server_job(EXAMPLES['integral']()) as (provision,registered,remote), \
             patch.object(s,'ink_fallbacks',set()), patch.object(s,'ink_scene_known',return_value=False):
            reply = self.finish_native()
            registered.assert_not_called()
            self.assertNotIn('ink',[b['kind'] for b in reply['blocks']])
            self.assertIn('drawing was left out',reply['blocks'][0]['text'])
            self.assertIn(REQUEST,s.ink_fallbacks)
        block = dict(scene='equation-'+'a'*24, stage='s0', source_doc=DOC, source_page=PAGE)
        with patch.object(s,'native_ink_current'), patch.object(s,'native_ink_source'):
            with self.assertRaisesRegex(ValueError,'not in the catalog'):
                s.native_ink_preflight(block, {'request':REQUEST}, {}, True)
            self.assertTrue(s.ink_scene_known(dict(block, role='equation')))
            self.assertTrue(s.ink_scene_known(dict(block, scene='unit-square-integral')))

    def test_revise_invalid_stopped_lesson_without_import_insert_or_retry(self):
        s = self.s
        original = EXAMPLES['integral']().replace('Takeaway:', 'Invalid end:')
        correction = EXAMPLES['integral']()
        digest = hashlib.sha256(original.encode()).hexdigest()
        with self.server_job(original) as (provision, registered, remote):
            before_job = copy.deepcopy(s.notebook_jobs[REQUEST])
            attempt = Path(s.live_baseline(PATH)+'.native-attempt')
            older = 'notebook-'+'e'*32
            attempt.write_text(older)
            s.native_text_failed(PATH, REQUEST)
            result = s.revise_notebook_response(REQUEST, digest, correction)
            self.assertTrue(result['revised'])
            self.assertFalse(result['retry_armed'])
            self.assertNotIn(PATH, s.ready)
            self.assertEqual(result['state'], 'revision-held')
            self.assertEqual(s.held_notebook_response(REQUEST)['text'], correction)
            self.assertEqual(s.pend('')[PATH][5], correction)
            self.assertEqual(s.notebook_jobs[REQUEST], before_job[:5]+[correction]+before_job[6:]+[None, {'revision_pending': True}])
            self.assertEqual(attempt.read_text(), older)
            self.assertFalse(s.retry_requests)
            self.assertIn('explicit retry', s.reply_errors[PATH])
            provision.assert_not_called(); registered.assert_not_called(); remote.assert_not_called()
            with self.assertRaisesRegex(ValueError, 'current unexpired live held reply'):
                s.revise_notebook_response(REQUEST, digest, correction)
            with self.assertRaisesRegex(ValueError, 'no live answer'):
                s.native_text(PATH, ink_supported=True)
            with self.assertRaisesRegex(ValueError, 'no answer waiting'):
                s.write_ready(PATH)
            # Recovered delivery uses the existing pending job, never another send.
            saved_job = s.pend('')[PATH]
            s.answers.clear(); s.reply_timings.clear(); s.reply_errors.clear()
            s.answer(*saved_job)
            self.assertEqual(s.answers[PATH], 'revision-held')
            self.assertNotIn(PATH, s.ready)
            self.assertIsNone(s.answer_status(PATH)['retry_token'])
            with self.assertRaisesRegex(ValueError, 'pending revision'):
                s.notebook_reply(REQUEST, original)
            s.retry_notebook_response(REQUEST)
            self.assertEqual(s.ready[PATH], correction)
            self.assertEqual(len(s.pend('')[PATH]), 8)
            self.assertTrue(s.answer_status(PATH)['retry_token'])

    def test_revision_refusals_preserve_all_held_state(self):
        s = self.s
        valid = EXAMPLES['integral']()
        invalid = valid.replace('Takeaway:', 'Invalid end:')
        for case in ('valid-original', 'plain-original', 'disabled', 'expired',
                     'pending-missing', 'superseded', 'writing', 'written', 'nonlive',
                     'import', 'armed', 'matching-attempt', 'malformed-attempt',
                     'journal', 'capture', 'measurement', 'hash', 'invalid-new', 'bad-equation', 'missing-new'):
            original = valid if case == 'valid-original' else 'plain' if case == 'plain-original' else invalid
            with self.subTest(case=case), self.server_job(original, case != 'disabled') as (provision, registered, remote):
                s.native_text_failed(PATH, REQUEST)
                correction = valid
                digest = hashlib.sha256(original.encode()).hexdigest()
                if case == 'expired':
                    s.notebook_jobs[REQUEST][2] -= s.ANSWER_WAIT
                    s.pend(PATH, s.notebook_jobs[REQUEST])
                elif case == 'pending-missing': s.pend(PATH)
                elif case == 'superseded':
                    newer = list(s.notebook_jobs[REQUEST]); newer[4] = 'notebook-'+'d'*32
                    s.pend(PATH, newer)
                elif case in ('writing', 'written'): s.answers[PATH] = case
                elif case == 'nonlive':
                    s.notebook_jobs[REQUEST][6] = False
                    s.pend(PATH, s.notebook_jobs[REQUEST])
                elif case == 'import': s.lesson_imports[PATH] = {'request': REQUEST}
                elif case == 'armed': s.retry_requests[REQUEST] = 'existing-hint'
                elif case in ('matching-attempt', 'malformed-attempt'):
                    Path(s.live_baseline(PATH)+'.native-attempt').write_text(REQUEST if case == 'matching-attempt' else '?')
                elif case == 'journal': s.native_ink_runs._write_once(REQUEST+'.plan.json', {'request': REQUEST})
                elif case == 'capture': s.native_ink_runs.captures[(REQUEST, 'before')] = 'existing'
                elif case == 'measurement': s.native_ink_runs.measurements[(REQUEST, 'hash')] = 'existing'
                elif case == 'hash': digest = '0'*64
                elif case == 'invalid-new': correction = invalid
                elif case == 'bad-equation': correction = valid.replace('```math\n', '```math\n\\unknown ')
                elif case == 'missing-new': correction = None
                before = copy.deepcopy((s.ready, s.notebook_jobs, s.answers, s.retry_requests, s.lesson_imports,
                                        s.reply_timings, s.reply_errors))
                pending = Path(s.PENDING).read_bytes()
                with self.assertRaises(ValueError):
                    s.revise_notebook_response(REQUEST, digest, correction)
                self.assertEqual((s.ready, s.notebook_jobs, s.answers, s.retry_requests, s.lesson_imports,
                                  s.reply_timings, s.reply_errors), before)
                self.assertEqual(Path(s.PENDING).read_bytes(), pending)
                provision.assert_not_called(); registered.assert_not_called(); remote.assert_not_called()

    def test_pending_revision_retry_rechecks_state_and_never_publishes_on_failure(self):
        s = self.s
        original = EXAMPLES['integral']().replace('Takeaway:', 'Invalid end:')
        digest = hashlib.sha256(original.encode()).hexdigest()
        for case in ('expired', 'claim', 'import', 'journal', 'pending-write'):
            with self.subTest(case=case), self.server_job(original) as (provision, registered, remote):
                # Safe even before the client polls: the invalid original never
                # authorizes insertion and correction is withheld from ready.
                s.revise_notebook_response(REQUEST, digest, EXAMPLES['integral']())
                if case == 'expired':
                    s.notebook_jobs[REQUEST][2] -= s.ANSWER_WAIT
                    s.pend(PATH, s.notebook_jobs[REQUEST])
                elif case == 'claim': Path(s.live_baseline(PATH)+'.native-attempt').write_text(REQUEST)
                elif case == 'import': s.lesson_imports[PATH] = {'request': REQUEST}
                elif case == 'journal': s.native_ink_runs._write_once(REQUEST+'.before-ids.json', {'existing': True})
                saved = Path(s.PENDING).read_bytes()
                real_pend = s.pend
                def faulty_pend(path, job=None):
                    if case == 'pending-write' and job is not None: raise OSError('disk full')
                    return real_pend(path, job)
                with patch.object(s, 'pend', side_effect=faulty_pend), self.assertRaises((ValueError, OSError)):
                    s.retry_notebook_response(REQUEST)
                self.assertNotIn(PATH, s.ready)
                self.assertEqual(s.answers[PATH], 'revision-held')
                self.assertFalse(s.retry_requests)
                self.assertEqual(Path(s.PENDING).read_bytes(), saved)
                provision.assert_not_called(); registered.assert_not_called(); remote.assert_not_called()

    def test_revision_rereads_attempt_and_fails_closed_on_storage_errors(self):
        s = self.s
        original = EXAMPLES['integral']().replace('Takeaway:', 'Invalid end:')
        digest = hashlib.sha256(original.encode()).hexdigest()
        for target in ('attempt', 'journal', 'pending'):
            with self.subTest(target=target), self.server_job(original):
                s.native_text_failed(PATH, REQUEST)
                before_job = copy.deepcopy(s.notebook_jobs[REQUEST])
                pending = Path(s.PENDING).read_bytes()
                if target == 'attempt':
                    fault = patch.object(s, 'native_retry_safe', side_effect=[True, False])
                elif target == 'journal':
                    fault = patch.object(s.native_ink_runs, 'require_unprepared', side_effect=[None, OSError('unreadable')])
                else:
                    real_pend = s.pend
                    def faulty_pend(path, job=None):
                        if job is not None: raise OSError('disk full')
                        return real_pend(path)
                    fault = patch.object(s, 'pend', side_effect=faulty_pend)
                with fault, self.assertRaises((ValueError, OSError)):
                    s.revise_notebook_response(REQUEST, digest, EXAMPLES['integral']())
                self.assertEqual(s.ready[PATH], original)
                self.assertEqual(s.notebook_jobs[REQUEST], before_job)
                self.assertEqual(Path(s.PENDING).read_bytes(), pending)

    def test_after_capture_wait_returns_to_bounded_poll_without_saved_proof(self):
        s = self.s
        layout = dict(command=dict(request=REQUEST,phase='after'),first=[0,0,32,12])
        waiting = dict(measured=False,state='waiting',reason='native=12, saved=10, delta=2')
        with patch.object(s,'native_ink_current') as current, \
             patch.object(s.native_ink_runs,'finish_capture',return_value=waiting) as capture, \
             patch.object(s.native_ink_runs,'saved_proof') as proof:
            self.assertEqual(s.native_ink_proof(REQUEST,layout),waiting)
            self.assertEqual(current.call_count,2)
            capture.assert_called_once()
            proof.assert_not_called()
            # A superseded request is not turned into an autosave wait.
            current.side_effect = [None,ValueError('superseded')]
            with self.assertRaisesRegex(ValueError,'superseded'):
                s.native_ink_proof(REQUEST,layout)
            proof.assert_not_called()

    def test_disabled_client_or_invalid_final_step_prevents_provisioning_and_all_remote_io(self):
        for enabled, supported, text in (
                (False,True,EXAMPLES['integral']()),
                (True,False,EXAMPLES['integral']()),
                (True,True,EXAMPLES['integral']().replace('Takeaway:','Invalid end:'))):
            with self.subTest(enabled=enabled,supported=supported), \
                 self.server_job(text,enabled) as (provision,registered,remote):
                with self.assertRaises(ValueError):
                    self.s.native_text(PATH,ink_supported=supported)
                provision.assert_not_called(); registered.assert_not_called(); remote.assert_not_called()

    def test_native_failure_is_correlated_idempotent_and_never_authorizes_replay(self):
        s = self.s
        with self.server_job(EXAMPLES['integral']()):
            self.assertTrue(s.native_text_failed(PATH, REQUEST)['held'])
            self.finish_native()
            attempt = Path(s.live_baseline(PATH)+'.native-attempt')
            before = attempt.read_bytes()
            response = s.ready[PATH]
            for unused in range(2):
                self.assertEqual(s.native_text_failed(PATH, REQUEST)['state'], 'failed')
            self.assertEqual(s.answer_status(PATH)['state'], 'failed')
            self.assertIsNone(s.answer_status(PATH)['retry_token'])
            self.assertEqual(s.ready[PATH], response)
            self.assertEqual(attempt.read_bytes(), before)
            s.answers[PATH] = 'ready'  # resume() after a backend restart
            self.assertEqual(s.native_text_failed(PATH, REQUEST)['state'], 'failed')
            self.assertEqual(attempt.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, 'already attempted'):
                s.native_text(PATH, ink_supported=True)
            with self.assertRaises(ValueError):
                s.native_text_failed(PATH, 'wrong-request')
            with self.assertRaises(ValueError):
                s.native_text_failed('other/page.rm', REQUEST)
            s.answers[PATH] = 'written'
            self.assertEqual(s.native_text_failed(PATH, REQUEST)['state'], 'written')
            newer = list(s.notebook_jobs[REQUEST])
            newer[4] = 'notebook-'+'d'*32
            s.start_notebook_job(newer)
            with self.assertRaisesRegex(ValueError, 'superseded'):
                s.native_text_failed(PATH, REQUEST)
            self.assertEqual(s.answers[PATH], 'waiting')

    def test_preparation_failure_consumes_only_current_retry_hint_and_preserves_answer(self):
        s = self.s
        with self.server_job(EXAMPLES['integral']()) as (provision, registered, remote):
            raw = s.ready[PATH]
            attempt = Path(s.live_baseline(PATH)+'.native-attempt')
            # An older request's durable claim must remain intact as well.
            older = 'notebook-'+'e'*32
            attempt.write_text(older)
            s.retry_requests[older] = 'unrelated-hint'
            s.lesson_imports[REQUEST] = {'state': 'already-requested'}
            s.retry_notebook_response(REQUEST)
            self.assertTrue(s.answer_status(PATH)['retry_token'])
            for unused in range(2):
                result = s.native_text_failed(PATH, REQUEST)
                self.assertEqual(result, dict(state='ready', request=REQUEST, held=True))
                self.assertIsNone(s.answer_status(PATH)['retry_token'])
                self.assertEqual(s.ready[PATH], raw)
                self.assertEqual(attempt.read_text(), older)
                self.assertEqual(s.lesson_imports[REQUEST], {'state': 'already-requested'})
                self.assertEqual(s.retry_requests, {older: 'unrelated-hint'})
                self.assertIn('held', s.reply_errors[PATH])
            provision.assert_not_called(); registered.assert_not_called(); remote.assert_not_called()
            s.retry_notebook_response(REQUEST)  # explicit admin re-arm still required
            self.assertTrue(s.answer_status(PATH)['retry_token'])
            with patch.object(s, 'native_retry_safe', return_value=False):
                before = dict(s.retry_requests)
                with self.assertRaisesRegex(ValueError, 'matching native insertion'):
                    s.native_text_failed(PATH, REQUEST)
                self.assertEqual(s.retry_requests, before)
            s.answers[PATH] = 'writing'
            with self.assertRaisesRegex(ValueError, 'matching native insertion'):
                s.native_text_failed(PATH, REQUEST)

    def test_import_probe_preflights_fresh_archive_and_verifies_native_readback(self):
        s = self.s
        parent = 'a7a7e181-7b6b-4a84-a169-3bc7e5fe35da'
        bundle = native_lesson_bundle(EXAMPLES['integral']())
        doc, archive = lesson_source_archive(bundle, {'cPages':{},'fileType':'notebook'}, parent)
        block = bundle['blocks'][0]
        body = dict(doc=DOC, page=PAGE, surface='surface', source_doc=doc,
                    source_page=block['source_page'], source_parent=parent,
                    operation='import-source', expected_strokes=block['stroke_count'])
        replies = [b'fresh', json.dumps({'type':'CollectionType','visibleName':'Storyboard tests (Codex)'}).encode(), archive]
        with patch.object(s,'tablet',side_effect=replies) as remote, patch.object(s.native_probe,'arm') as arm:
            s.arm_native_probe(body)
            self.assertEqual(arm.call_args.kwargs['source_sha256'], block['sha256'])
            self.assertTrue(all(len(c.args)==1 for c in remote.call_args_list), 'preflight must be read-only')
        with patch.object(s,'tablet',return_value=b'') as remote, patch.object(s.native_probe,'arm') as arm:
            with self.assertRaisesRegex(ValueError,'already exists'):
                s.arm_native_probe(body)
            arm.assert_not_called()
            self.assertEqual(remote.call_count,1)
        job = dict(body,id='probe-id',source_sha256=block['sha256'])
        report = dict(id='probe-id',state='cloned',imported_doc=doc,imported_page=PAGE)
        metadata = json.dumps({'visibleName':'Agent lesson source '+doc,'parent':parent}).encode()
        content = json.dumps({'cPages':{'pages':[{'id':PAGE}]}}).encode()
        with patch.object(s.native_probe,'current_job',return_value=job), \
             patch.object(s.native_probe,'complete') as complete, \
             patch.object(s,'tablet',side_effect=[metadata,content,bundle['sources'][0]['data']]):
            s.complete_native_probe(report)
            complete.assert_called_once_with(report)
        for change in ({'imported_doc':DOC}, {'id':'stale'}):
            with patch.object(s.native_probe,'current_job',return_value=job), patch.object(s,'tablet') as remote:
                with self.assertRaises(ValueError):
                    s.complete_native_probe(dict(report,**change))
                remote.assert_not_called()
        with patch.object(s.native_probe,'current_job',return_value=job), \
             patch.object(s.native_probe,'complete') as complete, \
             patch.object(s,'tablet',side_effect=[metadata,content,b'changed']):
            with self.assertRaisesRegex(ValueError,'bytes changed'):
                s.complete_native_probe(report)
            complete.assert_not_called()

    def test_change_after_source_preparation_holds_before_insertion_claim(self):
        with self.server_job(EXAMPLES['odd-squares']()) as (provision,registered,remote):
            self.s.native_text(PATH,ink_supported=True)
            self.s.native_ack_context.return_value = ('surface',(1,0,0,1,-702,0),11)
            with self.assertRaisesRegex(ValueError,'changed during lesson import'):
                self.s.native_text(PATH,ink_supported=True,imported={'request':REQUEST,'doc':PAGE})
            registered.assert_not_called()
            self.assertEqual(self.s.answers[PATH],'ready')

    def test_rollout_is_exact_uuid_list_and_disabled_by_default(self):
        s = self.s
        for configured,enabled in (('',False),(DOC,True),(PAGE,False),(DOC+','+PAGE,True)):
            with patch.object(s,'LESSON_NOTEBOOKS',configured):
                self.assertEqual(s.lesson_enabled(DOC),enabled)
        for configured in ('*','all',DOC+',','../path'):
            with patch.object(s,'LESSON_NOTEBOOKS',configured), self.assertRaises(ValueError):
                s.lesson_enabled(DOC)

    def test_full_lesson_transport_budget_is_not_legacy_prose_limit(self):
        response = EXAMPLES['integral']()+' '*17000
        with self.server_job(response):
            self.assertEqual(self.s.ready[PATH],response.strip())
        for text in (EXAMPLES['integral']()+' '*48000,'x'*16001):
            with self.assertRaises(ValueError), self.server_job(text):
                pass

    def test_local_rollout_file_does_not_require_launchd_environment_changes(self):
        s = self.s
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(s,'LESSON_NOTEBOOKS',None), patch.object(s,'LESSON_CONFIG',directory+'/rollout.json'):
            config = Path(s.LESSON_CONFIG)
            self.assertFalse(s.lesson_enabled(DOC))
            self.assertIsNone(s.lesson_draft_tool(REQUEST))
            config.write_text(json.dumps([DOC]))
            self.assertTrue(s.lesson_enabled(DOC))
            self.assertFalse(s.lesson_enabled(PAGE))
            self.assertIsNone(s.lesson_draft_tool(REQUEST),'legacy list must leave previews off')
            config.write_text(json.dumps({'notebooks':[DOC],'draft_check':True}))
            self.assertTrue(s.lesson_enabled(DOC))
            self.assertIsNotNone(s.lesson_draft_tool(REQUEST))
            config.write_text(json.dumps({'notebooks':[DOC],'draft_check':False,'stroke_playback':True}))
            self.assertIs(s.lesson_rollout_config()['stroke_playback'],True)
            self.assertEqual(s.notebook_lesson.label_hand,'plotter')
            config.write_text(json.dumps({'notebooks':[DOC],'draft_check':False,'label_hand':'primer'}))
            s.lesson_rollout_config()
            self.assertEqual(s.notebook_lesson.label_hand,'primer')
            config.write_text(json.dumps({'notebooks':[DOC],'draft_check':False}))
            s.lesson_rollout_config()
            self.assertEqual(s.notebook_lesson.label_hand,'plotter')
            with patch.object(s,'LESSON_NOTEBOOKS',''):
                self.assertFalse(s.lesson_enabled(DOC),'explicit empty env overrides file')
            for invalid in ('{}','[false]','["*"]','not json',' '*16385,
                            '{"notebooks":[],"draft_check":1}',
                            '{"notebooks":[],"draft_check":true,"unknown":true}',
                            '{"notebooks":[],"draft_check":false,"stroke_playback":1}',
                            '{"notebooks":[],"draft_check":false,"reader":"james"}',
                            '{"notebooks":[],"draft_check":false,"reader":"James","opening":"Once upon a time"}',
                            '{"notebooks":[],"draft_check":false,"label_hand":"comic sans"}',
                            '{"notebooks":[false],"draft_check":true}'):
                config.write_text(invalid)
                with self.assertRaises(ValueError):
                    s.lesson_enabled(DOC)

    def test_busy_preparation_never_blocks_telemetry_or_dispatches_controls(self):
        s = self.s
        locked, release = threading.Event(), threading.Event()
        def busy():
            with s.pending_lock:
                locked.set()
                release.wait(2)
        worker = threading.Thread(target=busy)
        worker.start()
        try:
            self.assertTrue(locked.wait(1))
            with patch.object(s.device_context,'update',return_value={'accepted':True}) as update, \
                 patch.object(s.device_context,'awake_seconds',return_value=0), \
                 patch.object(s.view_audit,'command') as audit, patch.object(s.native_probe,'command') as probe:
                started = time.monotonic()
                result = s.native_context_report({'active':True,'doc':DOC})
                self.assertLess(time.monotonic()-started,.5)
                self.assertTrue(result['accepted'])
                update.assert_called_once()
                audit.assert_not_called(); probe.assert_not_called()
                self.assertNotIn('repair',result)
        finally:
            release.set()
            worker.join(2)

    def test_provisioning_rechecks_page_after_template_reads(self):
        s = self.s
        parent = 'a7a7e181-7b6b-4a84-a169-3bc7e5fe35da'
        context = ('surface',(1,0,0,1,-702,0),10)
        replies = [json.dumps({'parent':parent}).encode(),
                   json.dumps({'visibleName':'Storyboard tests (Codex)'}).encode(),
                   json.dumps({'cPages':{}}).encode()]
        with patch.object(s,'native_ack_context',side_effect=[context,context,('new-surface',context[1],10)]), \
             patch.object(s,'tablet',side_effect=replies), \
             patch.object(s,'lesson_source_archive',return_value=(PAGE,b'archive')):
            with self.assertRaisesRegex(ValueError,'changed during lesson preparation'):
                s.prepare_notebook_lesson_import(PATH,{})

    def test_import_first_phase_has_no_foreground_claim_or_registered_ink(self):
        s = self.s
        with self.server_job(EXAMPLES['integral']()) as (provision,registered,remote):
            with self.assertRaisesRegex(ValueError,'not enabled'):
                s.native_text(PATH,ink_supported=True,import_supported=False)
            provision.assert_not_called()
            reply = s.native_text(PATH,ink_supported=True)
            self.assertEqual(reply['request'],REQUEST)
            self.assertIn('import_source',reply)
            self.assertNotIn('blocks',reply)
            self.assertFalse(Path(s.live_baseline(PATH)+'.native-attempt').exists())
            registered.assert_not_called(); remote.assert_not_called()
            self.assertEqual(s.answers[PATH],'ready')
            with self.assertRaisesRegex(ValueError,'already requested'):
                s.native_text(PATH,ink_supported=True)
            for callback in ({'request':'stale','doc':PAGE}, {}, 'bad'):
                with self.assertRaisesRegex(ValueError,'stale or superseded'):
                    s.native_text(PATH,ink_supported=True,imported=callback)
            registered.assert_not_called()
            with patch.object(s,'remap_imported_lesson',side_effect=ValueError('bad last page')):
                with self.assertRaisesRegex(ValueError,'bad last page'):
                    s.native_text(PATH,ink_supported=True,imported={'request':REQUEST,'doc':PAGE})
            registered.assert_not_called()
            self.assertFalse(Path(s.live_baseline(PATH)+'.native-attempt').exists())

    def test_retry_after_lost_import_callback_does_not_clear_or_repeat_import(self):
        s = self.s
        with self.server_job(EXAMPLES['integral']()) as (provision, registered, remote):
            s.native_text(PATH, ink_supported=True)
            prepared = s.lesson_imports[PATH]
            baseline = Path(s.live_baseline(PATH))
            baseline.write_bytes(b'original saved input snapshot')
            attempt = Path(str(baseline)+'.native-attempt')
            older = 'notebook-'+'e'*32
            attempt.write_text(older)
            # A UI reload loses the callback, not the server's prepared source.
            # Re-arm is deliberately not a source-import reset or reuse route.
            s.native_text_failed(PATH, REQUEST)
            result = s.retry_notebook_response(REQUEST)
            self.assertTrue(result['retry_armed'])
            with self.assertRaisesRegex(ValueError, 'already requested'):
                s.native_text(PATH, ink_supported=True)
            self.assertIs(s.lesson_imports[PATH], prepared)
            self.assertEqual(baseline.read_bytes(), b'original saved input snapshot')
            self.assertEqual(attempt.read_text(), older)
            self.assertEqual(s.answers[PATH], 'ready')
            provision.assert_called_once()
            registered.assert_not_called()
            remote.assert_not_called()
            # A current insertion claim still prohibits re-arm altogether.
            attempt.write_text(REQUEST)
            with self.assertRaisesRegex(ValueError, 'insertion may already have started'):
                s.retry_notebook_response(REQUEST)
            self.assertEqual(attempt.read_text(), REQUEST)
            self.assertIs(s.lesson_imports[PATH], prepared)

    def test_import_callback_after_restart_or_typed_edit_is_held(self):
        s = self.s
        with self.server_job(EXAMPLES['integral']()) as (provision,registered,remote):
            callback = {'request':REQUEST,'doc':PAGE}
            with self.assertRaisesRegex(ValueError,'stale or superseded'):
                s.native_text(PATH,ink_supported=True,imported=callback)
            s.native_text(PATH,ink_supported=True)
            with patch.object(s.device_context,'snapshot',return_value={'content_revision':42}):
                with self.assertRaisesRegex(ValueError,'input changed'):
                    s.native_text(PATH,ink_supported=True,imported=callback)
            registered.assert_not_called()

    def test_dynamic_lesson_uses_registered_region_and_existing_blank_guard(self):
        s = self.s
        context = dict(doc=DOC,page=PAGE,fresh=True,active=True,available=True,
                       size=[1404,1872],view=[1,0,0,1,-702,0],text_bounds=[-468,100,936,200])
        query = dict(request=REQUEST,origin=[-468,330])
        block = dict(scene='lesson-'+'a'*24,width=600,height=360)
        frame = Image.new('L',(1404,1872),255)
        with patch.object(s,'LESSON_NOTEBOOKS',DOC), patch.object(s,'native_ink_current'), \
             patch.object(s,'native_ink_source'), patch.object(s,'live_capture_region',side_effect=lambda remote,box:frame.crop(box)):
            s.native_ink_preflight(block,query,context,True)
            frame.putpixel((400,400),0)
            with self.assertRaisesRegex(ValueError,'existing content'):
                s.native_ink_preflight(block,query,context,True)
        with patch.object(s,'LESSON_NOTEBOOKS',''), patch.object(s,'native_ink_current'), \
             patch.object(s,'native_ink_source'), patch.object(s,'live_capture_region') as capture:
            with self.assertRaisesRegex(ValueError,'not enabled'):
                s.native_ink_preflight(block,query,context,True)
            capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
