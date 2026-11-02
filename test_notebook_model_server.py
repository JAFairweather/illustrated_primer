"""Direct model route integration: fake provider and tablet; real pending jobs."""
import contextlib
import copy
import os
import shutil
import time
import json
from pathlib import Path
import tempfile
import unittest
import threading
from unittest.mock import patch

from notebook_delivery import delivery_options, with_delivery
from notebook_model_transport import ModelTransportError
import test_notebook_renderer_fixture as fixture_tests
from test_notebook_renderer_fixture import DOC, PAGE, PATH
from test_notebook_model_transport import png, envelope

ROUTE = {'agent':'pidog','socket':'/private/example/pi.sock','deadline_ms':15000}
REAL_THREAD = threading.Thread
TEXT = '{"v":1,"mode":"answer","text":"One clear idea."}'


class ModelServerTests(unittest.TestCase):
    setUpClass = classmethod(fixture_tests.RendererFixtureTests.setUpClass.__func__)

    @contextlib.contextmanager
    def environment(self, route=ROUTE):
        s=self.s
        with fixture_tests.RendererFixtureTests.environment(self) as (context,capture,send,reader,_), \
             patch.object(s,'lesson_rollout_config',return_value={'notebooks':[DOC],'draft_check':False,
                          **({'model_transport':route} if route else {})}), \
             patch.object(s,'live_png',return_value=png()), \
             patch.object(s,'notebook_visual_input',return_value=('visual input','Latest plus visible context')), \
             patch.object(s.threading,'Thread') as thread:
            yield context,capture,send,reader,thread

    def dispatch(self, thread):
        result=self.s.respond(DOC,PAGE,live=True)
        self.assertIs(thread.call_args.kwargs['target'],self.s.notebook_model_answer)
        return result,thread.call_args.kwargs['args']

    def result(self, request):
        return dict(envelope(TEXT),request_id=request)

    def test_dispatch_carries_actual_image_and_pinned_protocol_without_shared_chat(self):
        s=self.s
        with self.environment() as (context,capture,send,reader,thread):
            response,args=self.dispatch(thread);job,route,image,before,image_context,prestart=args;self.assertIsNone(prestart)
            self.assertEqual(route,ROUTE);self.assertEqual(image,png())
            self.assertEqual(delivery_options(job),{'response_format':'semantic-v1','model_transport':'pi-socket-v1'})
            self.assertEqual(s.pend('')[PATH],job)
            self.assertEqual(response['to'],'pidog');self.assertEqual(s.notebook_names[job[4]],'pidog')
            def model(endpoint,request,png_bytes,question,**kw):
                self.assertEqual(endpoint,ROUTE['socket']);self.assertEqual(png_bytes,png())
                self.assertTrue(kw['is_current']());self.assertNotIn('/Users/',question)
                self.assertEqual(question,s.lesson_notes(image_context))  # the figure note goes to every lesson
                return self.result(request)
            with patch.object(s,'call_notebook_model',side_effect=model) as provider:
                s.notebook_model_answer(*args)
            provider.assert_called_once();send.assert_not_called();reader.assert_not_called()
            self.assertEqual(s.ready[PATH],TEXT);self.assertEqual(s.answers[PATH],'ready')
            self.assertIn('model_first_text',s.reply_timings[PATH])

    def test_unisolated_route_stops_before_capture_or_any_dispatch(self):
        s=self.s
        for route,live in ((None,True),(dict(ROUTE,agent='another-agent'),True),(ROUTE,False)):
            with self.subTest(route=route,live=live),self.environment(route) as (_,capture,send,reader,thread), \
                 patch.object(s,'render_page') as render,patch.object(s,'start_notebook_job') as start:
                previous={'respond':1,'written':2}
                s.reply_timings[PATH]=previous
                s.media_tests[PATH]={'asset':'keep','expires':float('inf')}
                with self.assertRaisesRegex(ValueError,'isolated model route'):
                    s.respond(DOC,PAGE,live=live)
                capture.assert_not_called();render.assert_not_called();reader.assert_not_called()
                send.assert_not_called();thread.assert_not_called();start.assert_not_called()
                self.assertEqual(s.pend(''),{});self.assertEqual(s.notebook_jobs,{})
                self.assertIs(s.reply_timings[PATH],previous)
                self.assertEqual(s.media_tests[PATH]['asset'],'keep')

    def test_isolated_dispatch_timings_do_not_relabel_previous_request_during_capture(self):
        s=self.s
        with self.environment() as (_,capture,send,reader,thread), \
             patch.object(s.time,'monotonic',side_effect=range(100,120)):
            previous={'respond':10,'written':20}
            s.reply_timings[PATH]=previous
            def frame(*_):
                self.assertIs(s.reply_timings[PATH],previous)
                return 'frame'
            capture.side_effect=frame
            self.dispatch(thread)
            self.assertEqual(s.reply_timings[PATH],dict(respond=100,metadata_ready=101,
                dispatch_resolved=102,reader_image_ready=103,submitted=104))
            send.assert_not_called();reader.assert_not_called()

    def test_visual_context_is_only_used_for_real_model_route_and_keeps_no_input_guard(self):
        s=self.s
        with self.environment() as (_,_,send,_,thread):
            with patch.object(s,'notebook_visual_input',return_value=(None,'no input')) as visual:
                with self.assertRaisesRegex(ValueError,'nothing new written'):
                    s.respond(DOC,PAGE,live=True)
                visual.assert_called_once_with('frame',None)
                thread.assert_not_called();send.assert_not_called()
        with self.environment() as (_,_,_,_,thread):
            s.arm_notebook_test(dict(doc=DOC,page=PAGE,fixture='integral'))
            with patch.object(s,'notebook_visual_input',side_effect=AssertionError('fixture image changed')):
                s.respond(DOC,PAGE,live=True)
                thread.assert_not_called()

    def test_capture_change_or_existing_request_never_starts_provider(self):
        s=self.s
        for case in ('ink','view','inactive','pending'):
            with self.subTest(case=case),self.environment() as (ctx,capture,send,reader,thread):
                if case=='pending':s.pend(PATH,['existing'])
                elif case=='inactive':ctx['active']=False
                else:
                    def change(*_):
                        if case=='ink':ctx['ink_revision']+=1
                        else:ctx['view']=[1,0,0,1,-702,100]
                        return 'frame'
                    capture.side_effect=change
                with self.assertRaises(ValueError):s.respond(DOC,PAGE,live=True)
                thread.assert_not_called();send.assert_not_called();reader.assert_not_called()
                self.assertEqual(s.notebook_jobs,{})

    def test_page_change_during_model_holds_without_publishing(self):
        s=self.s
        for key,value in (('ink_revision',3),('content_revision',2),('surface','new'),
                          ('page',DOC),('view',[1,0,0,1,0,100]),('active',False),('fresh',False)):
            with self.subTest(key=key),self.environment() as (ctx,_,_,_,thread):
                response,args=self.dispatch(thread)
                def model(*_,**kw):
                    self.assertTrue(kw['is_current']());ctx[key]=value
                    self.assertFalse(kw['is_current']())
                    return self.result(response['request'])
                with patch.object(s,'call_notebook_model',side_effect=model):s.notebook_model_answer(*args)
                self.assertNotIn(PATH,s.ready);self.assertEqual(s.answers[PATH],'failed')
                self.assertIsNone(s.pend('')[PATH][5])
                code = 'page_unavailable' if key in ('active','fresh') else 'page_changed'
                self.assertEqual(s.reply_errors[PATH],
                    'Notebook model '+code+'; request stopped before insertion; no automatic resend')

    def test_a_late_page_report_waits_but_a_long_silence_stops_the_model(self):
        s=self.s
        for age,current in ((3000,True),(7000,False)):
            with self.subTest(age=age),self.environment() as (ctx,_,_,_,thread):
                response,args=self.dispatch(thread)
                def model(*_,**kw):
                    ctx.update(fresh=False,available=True,age_ms=age)
                    self.assertEqual(kw['is_current'](),current)
                    return self.result(response['request'])
                with patch.object(s,'call_notebook_model',side_effect=model):s.notebook_model_answer(*args)

    def test_cancel_reason_is_retained_and_provider_cancel_is_not_a_page_change(self):
        s=self.s
        with self.environment() as (ctx,_,_,_,thread):
            response,args=self.dispatch(thread)
            def model(*_,**kw):
                original=ctx['page'];ctx['page']=DOC
                self.assertFalse(kw['is_current']())
                ctx['page']=original
                self.assertFalse(kw['is_current'](), 'a stopped request cannot revive')
                return self.result(response['request'])
            with patch.object(s,'call_notebook_model',side_effect=model):s.notebook_model_answer(*args)
            self.assertNotIn(PATH,s.ready)
            self.assertIn('page_changed',s.reply_errors[PATH])
        with self.environment() as (_,_,_,_,thread):
            _,args=self.dispatch(thread)
            with patch.object(s,'call_notebook_model',side_effect=ModelTransportError('cancelled')):
                s.notebook_model_answer(*args)
            self.assertNotIn(PATH,s.ready)
            self.assertNotIn('page_changed',s.reply_errors[PATH])

    def test_superseded_request_cannot_publish_or_fail_new_job(self):
        s=self.s
        with self.environment() as (_,_,_,_,thread):
            response,args=self.dispatch(thread)
            replacement=copy.deepcopy(args[0]);replacement[4]='notebook-'+'b'*32
            def model(*_,**kw):
                s.start_notebook_job(replacement)
                self.assertFalse(kw['is_current']())
                return self.result(response['request'])
            with patch.object(s,'call_notebook_model',side_effect=model):s.notebook_model_answer(*args)
            self.assertNotIn(PATH,s.ready);self.assertEqual(s.answers[PATH],'waiting')
            self.assertEqual(s.pend('')[PATH],replacement)

    def test_invalid_reply_and_provider_failure_never_fall_back(self):
        s=self.s
        for invalid in (False,True):
            with self.environment() as (_,_,send,reader,thread):
                response,args=self.dispatch(thread)
                with patch.object(s,'call_notebook_model') as model:
                    if invalid:model.return_value=dict(self.result(response['request']),text='{"v":1,"mode":"lesson"}')
                    else:model.side_effect=ModelTransportError('deadline')
                    s.notebook_model_answer(*args)
                model.assert_called_once();send.assert_not_called();reader.assert_not_called()
                self.assertNotIn(PATH,s.ready);self.assertEqual(s.answers[PATH],'failed')

    def test_rejected_observed_output_is_private_evidence_not_a_ready_reply(self):
        from notebook_model_transport import validate_model_result
        s=self.s
        with self.environment() as (_,_,send,reader,thread):
            response,args=self.dispatch(thread)
            raw=json.dumps(dict(envelope('{"v":1,"mode":"lesson"}'),request_id=response['request'])).encode()
            def invalid(endpoint,request,*_,**kw):
                return validate_model_result(raw,request,observe_response=kw['observe_response'])
            with patch.object(s,'call_notebook_model',side_effect=invalid) as model:
                s.notebook_model_answer(*args)
            files=list((Path(s.CACHE)/'rejected-replies').glob('*.json'))
            self.assertEqual(len(files),1);self.assertEqual(files[0].read_bytes(),raw)
            self.assertEqual(files[0].stat().st_mode & 0o777,0o600)
            self.assertEqual(s.answers[PATH],'failed');self.assertNotIn(PATH,s.ready)
            self.assertIsNone(s.pend('')[PATH][5])
            self.assertNotIn('"mode"',s.reply_errors[PATH])
            self.assertEqual(model.call_count,3)  # the checker's refusal earns two retries, refused each time
            send.assert_not_called();reader.assert_not_called()

    def test_success_does_not_retain_diagnostic_and_capture_failure_cannot_publish(self):
        s=self.s
        for fail in (False,True):
            with self.subTest(fail=fail),self.environment() as (_,_,_,_,thread):
                response,args=self.dispatch(thread)
                def model(*_,**kw):
                    kw['observe_response'](json.dumps(self.result(response['request'])).encode())
                    if fail:raise ModelTransportError('invalid_response')
                    return self.result(response['request'])
                with patch.object(s,'call_notebook_model',side_effect=model), \
                     patch.object(s,'retain_rejected_reply',side_effect=OSError('private detail')) as retain:
                    s.notebook_model_answer(*args)
                self.assertEqual(s.answers[PATH],'failed' if fail else 'ready')
                if fail:retain.assert_called_once();self.assertNotIn(PATH,s.ready)
                else:retain.assert_not_called()
                self.assertFalse((Path(s.CACHE)/'rejected-replies').exists())

    def test_a_refused_picture_is_directed_afresh_like_a_missing_one(self):
        s=self.s
        lesson={'v':1,'mode':'lesson','steps':[{'caption':'... a workshop.'},{'caption':'A captain.'}],
                'picture':{'base':'a workshop','edits':[]}}
        directed={'base':'a cozy workshop','edits':['a captain on the roof']}
        with self.environment() as (_,_,_,_,thread):
            response,args=self.dispatch(thread)
            result=dict(self.result(response['request']),text=json.dumps(lesson),
                        parsed={'mode':'lesson','picture_refused':'picture needs one edit per step after the first (1)'})
            config=dict(s.lesson_rollout_config(),picture='image')
            with patch.object(s,'call_notebook_model',return_value=result), \
                 patch.object(s,'lesson_rollout_config',return_value=config), \
                 patch.object(s,'direct_picture',return_value=directed) as direct, \
                 patch.object(s.notebook_image_model,'frames',return_value=[b'1',b'2']), \
                 patch.object(s,'notebook_reply') as reply:
                s.notebook_model_answer(*args)
        direct.assert_called_once()
        self.assertEqual(json.loads(reply.call_args.args[1])['picture'],directed)

    def test_a_refused_reply_gets_two_retries_told_why(self):
        s=self.s
        for second_ok in (True,False):
            with self.subTest(second_ok=second_ok),self.environment() as (_,_,send,reader,thread):
                response,args=self.dispatch(thread)
                contexts=[]
                def model(endpoint,request,png,context,**kw):
                    contexts.append(context)
                    kw['observe_response'](json.dumps(self.result(response['request'])).encode())
                    if len(contexts)==2 and second_ok:return self.result(response['request'])
                    error=ModelTransportError('invalid_response')
                    error.detail=('SemanticError: no clear connector route; simplify the scene' if len(contexts)==1
                                  else 'the reply was not valid JSON')
                    raise error
                with patch.object(s,'call_notebook_model',side_effect=model), \
                     patch.object(s,'retain_rejected_reply') as retain:
                    s.notebook_model_answer(*args)
                self.assertEqual(len(contexts),2 if second_ok else 3)
                self.assertNotIn('refused',contexts[0])
                self.assertIn('no clear connector route',contexts[1])
                self.assertTrue(contexts[1].startswith(contexts[0]))
                self.assertIn('scene family "drawing"',contexts[1])
                if not second_ok:self.assertIn('scene family "drawing"',contexts[2])
                self.assertLessEqual(len(contexts[1].encode()),12000)
                self.assertEqual(s.answers[PATH],'ready' if second_ok else 'failed')
                self.assertEqual(retain.call_count,0 if second_ok else 1)
                send.assert_not_called();reader.assert_not_called()

    def prestarted(self, result=None, error=None, observed=None, age=0):
        entry={'t':time.time()-age,'done':threading.Event(),'result':result,'error':error,'observed':observed,
               'current':lambda:True}
        entry['done'].set()
        self.s.primer_prestarts[PATH]=entry
        return entry

    def test_the_primers_answer_asked_while_it_wrote_is_used_by_its_press(self):
        s=self.s
        with self.environment() as (_,_,send,reader,thread):
            entry=self.prestarted(self.result('notebook-'+'a'*32))
            response,args=self.dispatch(thread)
            self.assertIs(args[-1],entry);self.assertNotIn(PATH,s.primer_prestarts)
            with patch.object(s,'call_notebook_model') as model:
                s.notebook_model_answer(*args)
            model.assert_not_called()
            self.assertEqual(s.answers[PATH],'ready')
            self.assertIsNot(entry['current'],self.s.primer_prestarts.get)  # the press's page check governs it
            send.assert_not_called();reader.assert_not_called()

    def test_a_refused_prestarted_answer_still_gets_its_one_retry_and_a_stale_one_is_not_used(self):
        s=self.s
        with self.environment() as (_,_,_,_,thread):
            error=ModelTransportError('invalid_json');error.detail='the reply was not valid JSON'
            self.prestarted(error=error,observed=b'{}')['context']='page notes. Current facts: a newer result.'
            response,args=self.dispatch(thread)
            contexts=[]
            def model(endpoint,request,png,context,**kw):
                contexts.append(context);return self.result(response['request'])
            with patch.object(s,'call_notebook_model',side_effect=model):
                s.notebook_model_answer(*args)
            self.assertEqual(len(contexts),1);self.assertIn('not valid JSON',contexts[0])
            self.assertIn('Current facts: a newer result.',contexts[0])  # the retry keeps what the search found
            self.assertEqual(s.answers[PATH],'ready')
        with self.environment() as (_,_,_,_,thread):
            self.prestarted(self.result('notebook-'+'a'*32),age=s.PRESTART_KEEP+1)
            response,args=self.dispatch(thread)
            self.assertIsNone(args[-1])

    def test_a_lesson_is_told_to_draw_what_its_answer_turns_on_within_the_context_bound(self):
        s=self.s
        config=dict(reader='James',reply_hand='primer',opening='once upon a time...',picture='image')
        with patch.object(s,'lesson_rollout_config',return_value=config):
            notes=s.lesson_notes(s.LATEST_IMAGE_CONTEXT)
            s.pending_sends['page']=dict(to=['My Dude'],text='x'*600,request='r',t=time.time())
            self.addCleanup(s.pending_sends.clear)
            waiting=s.lesson_notes(s.LATEST_IMAGE_CONTEXT,'page')
        self.assertIn('Picture:',waiting)
        for part in ('Sending:','Story:','Figure:','Picture:'):
            self.assertIn(part,notes)
        self.assertLess(notes.index('Figure:'),notes.index('Picture:'))
        facts=s.FACTS_NOTE%('October 30, 2026','x'*700)
        self.assertLessEqual(len((notes+facts+s.REPAIR_NOTE%('y'*400)+s.LAYOUT_REPAIR_NOTE).encode()),12000)

    def test_a_replay_puts_back_the_frames_its_reply_drew(self):
        s=self.s
        drew={'parsed':{'mode':'lesson','picture':{'base':'a lever','edits':['a push']}}}
        with patch.object(s.notebook_image_model,'replayed',return_value=2) as replayed, patch.object(s.trace,'event') as event:
            s.replay_picture('notebook-old',drew,'r','page')
            s.replay_picture('notebook-old',{'parsed':{'mode':'answer'}},'r','page')  # an answer with no picture
        replayed.assert_called_once_with('notebook-old','a lever',['a push'],scenes=False)
        self.assertEqual([c.args[1] for c in event.call_args_list],['replayed','not kept'])
        self.assertEqual(event.call_args_list[0].kwargs['frames'],2)
        # A refused picture was directed afresh then: the replay draws the directed one kept with the frames.
        # It was drawn as pictures of their own, so it is replayed as them; the reply's picture carries no such key.
        directed={'base':'a bay','edits':['a tide'],'scenes':True}
        refused={'text':json.dumps({'mode':'lesson','steps':[]}),'parsed':{'mode':'lesson','picture_refused':'edit count'}}
        with patch.object(s.notebook_image_model,'replayed',return_value=2) as replayed, \
             patch.object(s.notebook_image_model,'kept_picture',return_value=directed), patch.object(s.trace,'event'):
            s.replay_picture('notebook-old',refused,'r','page')
        replayed.assert_called_once_with('notebook-old','a bay',['a tide'],scenes=True)
        self.assertEqual(directed,{'base':'a bay','edits':['a tide']})
        self.assertEqual(refused['parsed'],{'mode':'lesson','picture':directed})
        self.assertEqual(json.loads(refused['text'])['picture'],directed)

    def test_a_tale_written_first_is_what_pi_dog_draws_and_without_one_it_gets_the_facts(self):
        s=self.s
        tale=dict(intent='Levers',takeaway='A lever trades distance for force.',
            steps=[dict(caption='... a mouse wanted an apple.',see='a log')]*4)
        tales=tempfile.mkdtemp();self.addCleanup(shutil.rmtree,tales)
        def told(config,story,facts='A new result.',question='How?'):
            with patch.object(s,'lesson_rollout_config',return_value=config), patch.object(s,'TALES',tales), \
                 patch.object(s.notebook_image_model,'facts',return_value=facts) as looked, \
                 patch.object(s.notebook_image_model,'story',**story) as wrote:
                return s.with_story('CTX'+opening,b'png',question,'r','page'),looked,wrote
        opening=s.OPENING_NOTE%'James, once upon a time...'
        context,looked,wrote=told(dict(story=True,reader='James'),dict(return_value=tale),question=None)
        looked.assert_not_called()  # handwriting alone: no text to search for
        self.assertTrue(context.startswith('CTX') and 'already written' in context and 'a mouse wanted' in context)
        self.assertNotIn(opening,context)  # its rules are for a tale Pi Dog would write itself
        self.assertEqual(wrote.call_args.kwargs['opening'],'James, once upon a time...')
        saved=json.loads(Path(tales,'page.json').read_text())  # for the R1 Primer to tell while Pi Dog draws
        self.assertEqual((saved['steps'],saved['takeaway']),(tale['steps'],tale['takeaway']))
        os.remove(Path(tales,'page.json'))
        context,_,wrote=told(dict(story=True,reader='James'),dict(return_value=tale))
        self.assertEqual(wrote.call_args.args[2],'A new result.')
        self.assertNotIn('A new result.',context)
        os.remove(Path(tales,'page.json'))
        for config,story in ((dict(story=True),dict(return_value=None)),(dict(story=True),dict(side_effect=RuntimeError('held'))),
                             ({},dict(side_effect=AssertionError('story is off')))):
            context,_,_=told(config,story)
            self.assertFalse(os.listdir(tales))
            self.assertIn('A new result.',context)
            self.assertIn(opening,context)
            self.assertNotIn('already written',context)

    def test_a_buzz_message_waits_on_its_page_and_goes_to_pi_dog_only_on_james_yes(self):
        s=self.s
        from notebook_semantic_reply import parse_semantic_reply
        def respond(reply, post=None):
            with self.environment() as (context,capture,send,reader,thread):
                _,args=self.dispatch(thread)
                result=dict(envelope(reply),request_id=args[0][4],parsed=parse_semantic_reply(reply))
                def model(*a,**kw):
                    kw['observe_response'](json.dumps(dict(envelope(reply),request_id=args[0][4])).encode())
                    return result
                with patch.object(s,'call_notebook_model',side_effect=model) as model, \
                     patch.object(s,'send',**({'side_effect':post} if post else {})) as pidog, \
                     patch.object(s,'notebook_reply') as page, patch.object(s,'keep_reply') as kept:
                    s.notebook_model_answer(*args)
            shown=json.loads(page.call_args.args[1])
            self.assertEqual(json.loads(json.loads(kept.call_args.args[1])['text']),shown)  # what the Primer speaks
            return model.call_args.args[3],pidog,shown
        self.addCleanup(s.pending_sends.clear)
        send='{"v":1,"mode":"send","to":["my dude"],"text":"Please add more pictures."}'
        yes='{"v":1,"mode":"confirm","send":true}'
        asked,pidog,shown=respond(send)
        self.assertIn('Sending:',asked);self.assertNotIn('Waiting on this page',asked)
        pidog.assert_not_called()  # nothing leaves the tablet before James's yes
        self.assertEqual(shown['mode'],'answer')
        self.assertIn('to @My Dude:\n\nPlease add more pictures.\n\nAnswer yes',shown['text'])
        self.assertEqual(s.pending_sends[PATH]['to'],['My Dude'])
        asked,pidog,shown=respond(yes)
        self.assertIn('a message to @My Dude, "Please add more pictures."',asked)
        pidog.assert_called_once()
        pane,text=pidog.call_args.args
        self.assertEqual(pane,'pane')
        self.assertTrue(text.endswith('mention ["My Dude"], and text exactly as follows, nothing added or changed: '
                                      '@My Dude Please add more pictures.'),text)
        self.assertIn('Handed to Pi Dog',shown['text']);self.assertNotIn(PATH,s.pending_sends)
        _,pidog,shown=respond(yes)  # one yes sends once
        pidog.assert_not_called();self.assertIn('no message waiting',shown['text'])
        respond(send)
        _,pidog,shown=respond('{"v":1,"mode":"confirm","send":false}')
        pidog.assert_not_called();self.assertIn('Not sent',shown['text']);self.assertNotIn(PATH,s.pending_sends)
        respond(send)
        _,pidog,shown=respond(yes,post=OSError('herdr gone'))
        self.assertIn('still waiting',shown['text']);self.assertIn(PATH,s.pending_sends)
        s.pending_sends[PATH]['t']-=s.SEND_KEEP+1
        asked,pidog,shown=respond(yes)
        pidog.assert_not_called();self.assertIn('Sending:',asked);self.assertIn('no message waiting',shown['text'])
        _,pidog,shown=respond('{"v":1,"mode":"send","to":["Dead Rabbit"],"text":"Hi."}')
        self.assertIn('could not find Dead Rabbit',shown['text']);self.assertNotIn(PATH,s.pending_sends)

    def test_a_handwritten_text_names_one_contact_and_goes_to_messages_only_on_james_yes(self):
        s=self.s
        from notebook_semantic_reply import parse_semantic_reply
        def respond(reply, people=(('Ada Park','+1 203 555 0142'),), sent=None, baseline='saved page'):
            with self.environment() as (context,capture,send,reader,thread):
                _,args=self.dispatch(thread)
                s.note_frames[PATH]=(s.note_frames[PATH][0],baseline)
                result=dict(envelope(reply),request_id=args[0][4],parsed=parse_semantic_reply(reply))
                with patch.object(s,'call_notebook_model',return_value=result) as model, \
                     patch.object(s.notebook_messages,'lookup',
                                  **({'side_effect':people} if isinstance(people,Exception) else {'return_value':list(people)})) as lookup, \
                     patch.object(s.notebook_messages,'send_picture',**({'side_effect':sent} if sent else {})) as messages, \
                     patch.object(s.notebook_handwritten_note,'note_png',return_value=b'note') as note, \
                     patch.object(s.notebook_handwritten_note,'written_png',return_value=b'written'), \
                     patch.object(s,'send') as pidog, patch.object(s,'notebook_reply') as page:
                    s.notebook_model_answer(*args)
                    waiting=s.pending_sends.get(PATH)
                    if waiting and waiting['request']==args[0][4]:  # made in this call's own cache
                        files.append((Path(waiting['png']).read_bytes(),Path(waiting['png']).stat().st_mode & 0o077))
            pidog.assert_not_called()
            return model.call_args.args[3],lookup,messages,note,json.loads(page.call_args.args[1])['text']
        files=[]
        self.addCleanup(s.pending_sends.clear)
        text='{"v":1,"mode":"send","via":"imessage","to":["Day"],"text":"Love you, back by six.","ink":"above"}'
        yes='{"v":1,"mode":"confirm","send":true}'
        asked,lookup,messages,note,shown=respond(text)
        self.assertIn('"via":"imessage"',asked)
        lookup.assert_called_once_with('Day');messages.assert_not_called()
        self.assertEqual(note.call_args.args[2],'above')
        self.assertIn('Ready to send to Ada Park by iMessage (number ending 0142): your handwritten note',shown)
        self.assertNotIn('555',shown)  # only the last four digits reach the page
        waiting=s.pending_sends[PATH]
        self.assertEqual(files[-1],(b'note',0))  # kept private to James's user
        asked,_,messages,_,shown=respond(yes)
        self.assertIn('a message to Ada Park by iMessage (number ending 0142), "Love you, back by six."',asked)
        messages.assert_called_once_with('imessage','+1 203 555 0142',waiting['png'],waiting['request'])
        self.assertIn('Handed to Messages',shown);self.assertNotIn(PATH,s.pending_sends)
        _,_,messages,_,shown=respond(yes)  # one yes sends once
        messages.assert_not_called();self.assertIn('no message waiting',shown)
        respond(text)
        _,_,messages,_,shown=respond(yes,sent=OSError('not allowed'))
        self.assertIn('still waiting',shown);self.assertIn(PATH,s.pending_sends)
        _,_,messages,_,shown=respond('{"v":1,"mode":"confirm","send":false}')
        messages.assert_not_called();self.assertIn('Not sent',shown);self.assertNotIn(PATH,s.pending_sends)
        for reply,baseline in ((text.replace('"above"','"none"'),'saved page'),(text,None)):
            _,_,_,note,shown=respond(reply,baseline=baseline)  # no saved page: only the words, never the whole page
            note.assert_not_called();self.assertIn('written out in your hand',shown)
            self.assertEqual(files[-1][0],b'written');s.pending_sends.pop(PATH)
        for people,words in (((),'could not find Day'),
                             ((('Day A','1'),('Day B','2')),'matches Day A, Day B'),
                             (OSError('-1743'),'permission to use Contacts')):
            with self.subTest(words=words):
                _,_,messages,_,shown=respond(text,people=people)
                self.assertIn(words,shown);self.assertNotIn(PATH,s.pending_sends)

    def test_a_prestart_checks_its_strokes_and_can_be_cancelled(self):
        s=self.s
        for strokes in ([],[[]],[[[10,99999]]],[[[1,2,3]]],'x',[[['a',2]]]):
            with self.subTest(strokes=strokes),self.assertRaises(ValueError):
                s.primer_prestart({'doc':DOC,'page':PAGE,'strokes':strokes})
        with self.assertRaises(ValueError):
            s.primer_prestart({'doc':'../x','page':PAGE,'cancel':True})
        entry=self.prestarted(self.result('notebook-'+'a'*32))
        self.assertEqual(s.primer_prestart({'doc':DOC,'page':PAGE,'cancel':True}),{'cancelled':True})
        self.assertNotIn(PATH,s.primer_prestarts);self.assertFalse(entry['current']())

    def test_valid_observation_with_downstream_publication_failure_is_not_model_rejection(self):
        from notebook_model_transport import validate_model_result
        s=self.s
        for error in (OSError('pending store unavailable'),ModelTransportError('invalid_response')):
            with self.subTest(error=type(error)),self.environment() as (_,_,send,reader,thread):
                response,args=self.dispatch(thread)
                raw=json.dumps(self.result(response['request'])).encode()
                def model(endpoint,request,*_,**kw):
                    return validate_model_result(raw,request,observe_response=kw['observe_response'])
                with patch.object(s,'call_notebook_model',side_effect=model), \
                     patch.object(s,'notebook_reply',side_effect=error), \
                     patch.object(s,'retain_rejected_reply') as retain:
                    s.notebook_model_answer(*args)
                retain.assert_not_called()
                self.assertEqual(s.answers[PATH],'failed');self.assertNotIn(PATH,s.ready)
                send.assert_not_called();reader.assert_not_called()

    def test_thread_start_failure_retains_request_as_failed_not_waiting(self):
        s=self.s
        with self.environment() as (_,_,send,_,thread):
            thread.return_value.start.side_effect=RuntimeError('worker cannot start')
            with self.assertRaisesRegex(ValueError,'worker unavailable'):s.respond(DOC,PAGE,live=True)
            self.assertEqual(s.answers[PATH],'failed');self.assertIsNone(s.pend('')[PATH][5])
            send.assert_not_called()

    def test_restart_never_resends_or_reads_chat_but_recovers_completed_answer(self):
        s=self.s
        with self.environment() as (_,_,send,_,thread):
            _,args=self.dispatch(thread);job=args[0]
            with patch.object(s.reply_reader,'answer',side_effect=AssertionError('shared chat read')):
                s.answer(*job)
                self.assertEqual(s.answers[PATH],'failed');self.assertNotIn(PATH,s.ready)
                completed=job[:];completed[5]=TEXT;s.pend(PATH,completed);s.notebook_jobs[job[4]]=completed
                s.answer(*completed)
                self.assertEqual(s.ready[PATH],TEXT)
            send.assert_not_called()

    def test_fixture_ignores_model_route_and_media_arm_is_not_consumed(self):
        s=self.s
        with self.environment() as (_,_,send,_,thread):
            s.arm_notebook_test(dict(doc=DOC,page=PAGE,fixture='integral'))
            response=s.respond(DOC,PAGE,live=True)
            self.assertEqual(response['to'],'Renderer Test');thread.assert_not_called();send.assert_not_called()
        with self.environment() as (_,_,_,_,thread):
            s.media_tests[PATH]={'expires':float('inf'),'asset':'keep'}
            with self.assertRaisesRegex(ValueError,'attachment'):s.respond(DOC,PAGE,live=True)
            self.assertIn(PATH,s.media_tests);thread.assert_not_called()

    def test_explicit_respond_replaces_failed_unanswered_model_only(self):
        s=self.s
        with self.environment() as (_,_,_,_,thread):
            first,args=self.dispatch(thread)
            with patch.object(s,'call_notebook_model',side_effect=ModelTransportError('deadline')):
                s.notebook_model_answer(*args)
            self.assertEqual(thread.call_count,1, 'failure must not resend')
            second,_=self.dispatch(thread)
            self.assertNotEqual(first['request'],second['request'])
            self.assertEqual(s.pend('')[PATH][4],second['request'])
            self.assertEqual(thread.call_count,2)

    def test_sweep_clears_only_stale_model_requests_and_says_why(self):
        s=self.s
        for state,age,cleared in (('waiting',100,False),('waiting',400,True),('ready',400,True),
                                  ('writing',400,False),('writing',700,True)):
            with self.subTest(state=state,age=age),self.environment() as (_,_,_,_,thread):
                _,args=self.dispatch(thread);job=copy.deepcopy(args[0])
                job[2]=int(time.time())-age;s.pend(PATH,job);s.answers[PATH]=state
                if state=='ready':s.ready[PATH]=TEXT
                s.sweep_pending()
                self.assertEqual(PATH not in s.pend(''),cleared)
                if cleared:
                    self.assertNotIn(PATH,s.ready)
                    self.assertIn('inspect the page' if state=='writing' else 'Timed out',s.reply_errors[PATH])
        with self.environment() as (_,_,_,_,thread):
            _,args=self.dispatch(thread);legacy=args[0][:7];legacy[2]=0;s.pend(PATH,legacy)
            s.sweep_pending()
            self.assertIn(PATH,s.pend(''))

    def test_new_respond_replaces_held_reply_but_not_a_started_one(self):
        # A held, never-inserted reply is cancelled up front by the next Respond. One whose insertion may have begun is
        # cleared but refused once ("inspect the page"); the press after that goes through. Legacy jobs stay refused.
        s=self.s
        for case,outcome in (('ready','replaced'),('reply','replaced'),('import','replaced'),
                             ('attempt','cleared'),('prepared','cleared'),('legacy','kept')):
            with self.subTest(case=case),self.environment() as (_,_,_,_,thread):
                _,args=self.dispatch(thread); job=args[0]
                s.answers[PATH]='failed'
                with contextlib.ExitStack() as stack:
                    if case=='ready':s.ready[PATH]=TEXT
                    if case=='reply':
                        job=copy.deepcopy(job);job[5]=TEXT;s.pend(PATH,job)
                    if case=='attempt':stack.enter_context(patch.object(s,'native_retry_safe',return_value=False))
                    if case=='prepared':stack.enter_context(patch.object(s.native_ink_runs,'require_unprepared',side_effect=ValueError('prepared')))
                    if case=='import':s.lesson_imports[PATH]={}
                    if case=='legacy':s.pend(PATH,job[:7])
                    before=s.pend('')
                    if outcome=='replaced':
                        response=s.respond(DOC,PAGE,live=True)
                        self.assertEqual(s.pend('')[PATH][4],response['request'])
                        self.assertNotIn(PATH,s.ready);self.assertNotIn(PATH,s.lesson_imports)
                        self.assertEqual(thread.call_count,2)
                        continue
                    with self.assertRaises(ValueError) as refused:s.respond(DOC,PAGE,live=True)
                    self.assertEqual(thread.call_count,1)
                    if outcome=='kept':
                        self.assertEqual(s.pend(''),before)
                        continue
                    self.assertIn('inspect the page',str(refused.exception))
                    self.assertNotIn(PATH,s.pend(''))
                s.respond(DOC,PAGE,live=True)
                self.assertEqual(thread.call_count,2)

    def test_failed_retry_rechecks_pending_identity_after_capture(self):
        s=self.s
        with self.environment() as (_,capture,_,_,thread):
            _,args=self.dispatch(thread);s.answers[PATH]='failed'
            replacement=copy.deepcopy(args[0]);replacement[4]='notebook-'+'c'*32
            def changed(*_):
                s.pend(PATH,replacement)
                return 'frame'
            capture.side_effect=changed
            with self.assertRaises(ValueError):s.respond(DOC,PAGE,live=True)
            self.assertEqual(s.pend('')[PATH],replacement)
            self.assertEqual(thread.call_count,1)

    def test_two_concurrent_explicit_retries_start_only_one_worker(self):
        s=self.s
        with self.environment() as (_,capture,_,_,worker):
            self.dispatch(worker);s.answers[PATH]='failed'
            barrier=threading.Barrier(2);results=[];errors=[]
            def captured(*_):
                barrier.wait(timeout=3)
                return 'frame'
            capture.side_effect=captured
            def respond():
                try:results.append(s.respond(DOC,PAGE,live=True))
                except Exception as error:errors.append(error)
            threads=[REAL_THREAD(target=respond) for _ in range(2)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(timeout=5)
            self.assertFalse(any(t.is_alive() for t in threads))
            self.assertEqual(len(results),1)
            self.assertEqual(len(errors),1)
            self.assertIsInstance(errors[0],ValueError)
            self.assertEqual(worker.call_count,2)  # original plus one retry
            self.assertEqual(s.pend('')[PATH][4],results[0]['request'])

    def test_operator_config_exact_fields_and_delivery_constraints(self):
        s=self.s
        with tempfile.TemporaryDirectory() as directory,patch.object(s,'LESSON_CONFIG',directory+'/config.json'):
            config={'notebooks':[DOC],'draft_check':False,'model_transport':ROUTE}
            path=Path(s.LESSON_CONFIG);path.write_text(json.dumps(config))
            self.assertEqual(s.lesson_rollout_config(),config)
            story_route=dict(ROUTE,response_format='story-panel-v1')
            path.write_text(json.dumps(dict(config,model_transport=story_route)))
            self.assertEqual(s.lesson_rollout_config()['model_transport'],story_route)
            path.write_text(json.dumps(dict(config,story=True)))
            self.assertIs(s.lesson_rollout_config()['story'],True)
            path.write_text(json.dumps(dict(config,story='yes')))
            with self.assertRaises(ValueError):s.lesson_rollout_config()
            for change in ({'agent':'another'},{'deadline_ms':True},{'socket':'relative'},
                           {'socket':'/private/../elsewhere'},{'model':'caller-selected'},
                           {'response_format':True},{'response_format':'unknown'},
                           {'response_format':'story-panel-v1','socket':'/private/notebook-eval.sock'}):
                path.write_text(json.dumps(dict(config,model_transport=dict(ROUTE,**change))))
                with self.assertRaises(ValueError):s.lesson_rollout_config()
        job=['pane',PATH,1,True,'notebook-'+'a'*32,None,True]
        for options in ({'model_transport':'pi-socket-v1'},
                        {'response_format':'semantic-v1','model_transport':'unknown'},
                        {'response_format':'semantic-v1','model_transport':'pi-socket-v1','renderer_fixture':True}):
            with self.assertRaises(ValueError):with_delivery(job,**options)

    def test_production_roles_use_owner_config_not_a_request_socket(self):
        from test_notebook_role_transport import roles, ProductionRoleTests
        route=dict(agent='pidog',response_format='role-production-v1',roles=roles(),deadline_ms=30000)
        s=self.s
        with tempfile.TemporaryDirectory() as directory,patch.object(s,'LESSON_CONFIG',directory+'/config.json'):
            config=dict(notebooks=[DOC],draft_check=False,model_transport=route)
            path=Path(s.LESSON_CONFIG);path.write_text(json.dumps(config))
            self.assertEqual(s.lesson_rollout_config(),config)
            for bad in [dict(route,socket='/private/notebook.sock'),dict(route,deadline_ms=30001),
                        dict(route,roles={'planner':route['roles']['planner']})]:
                path.write_text(json.dumps(dict(config,model_transport=bad)))
                with self.assertRaises((ValueError,ModelTransportError)):s.lesson_rollout_config()
        for changed in (False,True):
            fixture=ProductionRoleTests();fixture.setUp()
            with self.environment(route) as (context,_,send,reader,thread):
                _,args=self.dispatch(thread)
                def model(*a,**kw):
                    result=fixture.model(*a,**kw)
                    if changed and len(fixture.calls)==2:context['ink_revision']+=1
                    return result
                with patch('notebook_role_transport.call_production_role',side_effect=model), \
                     patch.object(s,'call_notebook_model',side_effect=AssertionError('legacy fallback')):
                    s.notebook_model_answer(*args)
                send.assert_not_called();reader.assert_not_called()
                if changed:
                    self.assertEqual(len(fixture.calls),2);self.assertNotIn(PATH,s.ready)
                    self.assertIn('page_changed',s.reply_errors[PATH])
                else:
                    self.assertEqual(len(fixture.calls),5);self.assertEqual(s.answers[PATH],'ready')
                    self.assertEqual(json.loads(s.ready[PATH])['mode'],'story-lesson')

    def stopped_reply(self, worker):
        response,_=self.dispatch(worker)
        self.s.notebook_reply(response['request'],TEXT)
        job=self.s.pend('')[PATH]
        attempt=Path(self.s.live_baseline(PATH)+'.native-attempt')
        attempt.write_text(job[4])
        self.s.answers[PATH]='failed'
        return job,attempt

    def test_explicit_new_question_retains_partial_reply_and_rejects_old_callbacks(self):
        s=self.s
        with self.environment() as (_,_,_,_,worker):
            old,attempt=self.stopped_reply(worker)
            with patch.object(s.native_ink_runs,'require_unprepared',side_effect=ValueError('prepared')):
                response=s.respond(DOC,PAGE,live=True,supersedes=old[4])
            self.assertNotEqual(response['request'],old[4])
            self.assertEqual(attempt.read_text(),old[4], 'must not clear the durable attempt')
            self.assertEqual(s.notebook_jobs[old[4]][5],TEXT, 'old answer is not rewritten')
            self.assertEqual(s.answers[PATH],'waiting');self.assertNotIn(PATH,s.ready)
            self.assertIsNone(s.incomplete_native_attempt(PATH))
            self.assertTrue(s.native_retry_safe(s.pend('')[PATH]))
            s.notebook_reply(response['request'],TEXT)
            self.assertIsNone(s.incomplete_native_attempt(PATH), 'old attempt must not warn on new reply')
            for callback in (lambda:s.notebook_reply(old[4],TEXT),
                             lambda:s.native_text_failed(PATH,old[4])):
                with self.assertRaises(ValueError):callback()
            self.assertEqual(s.pend('')[PATH][4],response['request'])
            self.assertEqual(worker.call_count,2)

    def test_new_question_without_exact_supersedes_follows_the_replacement_rule(self):
        # The old reply stopped mid-insertion (its attempt file names it). Without the exact supersedes, a new press is
        # refused once and the old request cleared; a reply being written now, a legacy job, a malformed id, or a
        # supersedes with nothing pending is refused with nothing changed. With no sign insertion began, it's replaced.
        s=self.s
        for case,outcome in (('missing-id','cleared'),('wrong-id','cleared'),('malformed','kept'),
                             ('wrong-attempt','replaced'),('absent-attempt','replaced'),('waiting','cleared'),
                             ('ready','cleared'),('writing','kept'),('written','cleared'),('legacy','kept'),
                             ('no-pending','kept')):
            with self.subTest(case=case),self.environment() as (_,_,_,_,worker):
                old,attempt=self.stopped_reply(worker);supersedes=old[4]
                if case=='missing-id':supersedes=''
                if case=='wrong-id':supersedes='notebook-'+'c'*32
                if case=='malformed':supersedes=True
                if case=='wrong-attempt':attempt.write_text('notebook-'+'c'*32)
                if case=='absent-attempt':attempt.unlink()
                if case in ('waiting','ready','writing','written'):s.answers[PATH]=case
                if case=='legacy':s.pend(PATH,old[:7])
                if case=='no-pending':s.pend(PATH,None)
                before=s.pend('')
                if outcome=='replaced':
                    response=s.respond(DOC,PAGE,live=True,supersedes=supersedes)
                    self.assertEqual(s.pend('')[PATH][4],response['request']);self.assertEqual(worker.call_count,2)
                    continue
                with self.assertRaises(ValueError):s.respond(DOC,PAGE,live=True,supersedes=supersedes)
                self.assertEqual(worker.call_count,1)
                if outcome=='kept':self.assertEqual(s.pend(''),before)
                else:self.assertNotIn(PATH,s.pend(''))

    def test_new_question_rechecks_page_and_failure_after_capture(self):
        s=self.s
        for case in ('ink','surface','view','state','attempt'):
            with self.subTest(case=case),self.environment() as (ctx,capture,_,_,worker):
                old,attempt=self.stopped_reply(worker)
                def changed(*_):
                    if case=='ink':ctx['ink_revision']+=1
                    elif case=='surface':ctx['surface']='changed'
                    elif case=='view':ctx['view'][5]+=100
                    elif case=='state':s.answers[PATH]='written'
                    else:attempt.write_text('notebook-'+'c'*32)
                    return 'frame'
                capture.side_effect=changed
                with self.assertRaises(ValueError):s.respond(DOC,PAGE,live=True,supersedes=old[4])
                self.assertEqual(s.pend('')[PATH],old);self.assertEqual(worker.call_count,1)

    def test_two_concurrent_new_questions_start_one_worker(self):
        s=self.s
        with self.environment() as (_,capture,_,_,worker):
            old,attempt=self.stopped_reply(worker)
            barrier=threading.Barrier(2);results=[];errors=[]
            def captured(*_):
                barrier.wait(timeout=3)
                return 'frame'
            capture.side_effect=captured
            def respond():
                try:results.append(s.respond(DOC,PAGE,live=True,supersedes=old[4]))
                except Exception as error:errors.append(error)
            threads=[REAL_THREAD(target=respond) for _ in range(2)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(timeout=5)
            self.assertFalse(any(t.is_alive() for t in threads))
            self.assertEqual(len(results),1);self.assertEqual(len(errors),1)
            self.assertEqual(worker.call_count,2)
            self.assertEqual(attempt.read_text(),old[4])

    def test_restart_restores_attempted_reply_as_failed_without_replay(self):
        s=self.s
        with self.environment() as (_,_,send,_,worker):
            old,attempt=self.stopped_reply(worker)
            s.answers.clear();s.ready.clear()
            s.answer(*old)
            self.assertEqual(s.answers[PATH],'failed');self.assertEqual(s.ready[PATH],TEXT)
            self.assertEqual(attempt.read_text(),old[4]);self.assertEqual(worker.call_count,1)
            self.assertEqual(s.pend('')[PATH][5],TEXT)
            response=s.respond(DOC,PAGE,live=True,supersedes=old[4])
            self.assertNotEqual(response['request'],old[4]);self.assertEqual(attempt.read_text(),old[4])
            send.assert_not_called()


if __name__=='__main__':unittest.main()
