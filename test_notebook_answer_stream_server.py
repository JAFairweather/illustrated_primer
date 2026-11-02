"""Pending-job streaming bridge; fake model, no tablet writes or model spend."""
import contextlib
import http.client
import json
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch

from notebook_model_transport import ModelTransportError
from notebook_auth import NotebookAuth
import test_notebook_model_server as model_tests
from test_notebook_model_server import ROUTE, TEXT, REAL_THREAD
from test_notebook_renderer_fixture import DOC, PAGE, PATH

STREAM_ROUTE = dict(ROUTE, response_format='story-stream-v1')


class AnswerStreamServerTests(unittest.TestCase):
    setUpClass = classmethod(model_tests.ModelServerTests.setUpClass.__func__)
    result = model_tests.ModelServerTests.result

    @contextlib.contextmanager
    def environment(self):
        with model_tests.ModelServerTests.environment(self, STREAM_ROUTE) as env, \
                patch.object(self.s,'notebook_answer_streams',{}):
            yield env

    def dispatch(self, worker):
        response = self.s.respond(DOC,PAGE,live=True,stream_supported=True)
        return response, worker.call_args.kwargs['args']

    def read(self, request, after=-1, **changes):
        return self.s.notebook_answer_stream(dict(request=request,page=PATH,after=after,**changes))

    def test_old_client_refused_before_capture_or_model_start(self):
        with self.environment() as (_,capture,send,reader,worker):
            for capability in (False,None,1,'1'):
                with self.assertRaisesRegex(ValueError,'streaming-capable'):
                    self.s.respond(DOC,PAGE,live=True,stream_supported=capability)
            capture.assert_not_called();worker.assert_not_called()
            send.assert_not_called();reader.assert_not_called()

    def test_readable_before_provider_completion_and_repeatable_without_delivery_claim(self):
        s=self.s
        with self.environment() as (_,_,_,_,worker):
            response,args=self.dispatch(worker); request=response['request']
            queued,release=threading.Event(),threading.Event()
            def model(*_,**options):
                options['on_answer'](dict(sequence=0,text='Equal parts let us compare the same whole.'))
                queued.set()
                if not release.wait(3): raise AssertionError('test did not consume early text')
                self.assertTrue(options['is_current']())
                return self.result(request)
            with patch.object(s,'generate_notebook_story',side_effect=model):
                running=REAL_THREAD(target=s.notebook_model_answer,args=args)
                running.start()
                try:
                    self.assertTrue(queued.wait(3));self.assertTrue(running.is_alive())
                    first=self.read(request)
                    self.assertEqual(first['state'],'waiting')
                    self.assertEqual(first['chunks'],[dict(sequence=0,text='Equal parts let us compare the same whole.')])
                    self.assertEqual(self.read(request),first,'lost response permits a repeated READ, not a second insertion')
                    self.assertEqual(self.read(request,0)['chunks'],[])
                    self.assertNotIn(PATH,s.ready)
                    self.assertIn('answer_chunk_queued',s.reply_timings[PATH])
                    self.assertNotIn('written',s.reply_timings[PATH])
                finally:
                    release.set();running.join(4)
            self.assertFalse(running.is_alive())
            self.assertEqual(s.ready[PATH],TEXT)
            self.assertEqual(self.read(request,0),dict(request=request,state='ready',chunks=[]))

    def test_late_failure_stops_new_reads_without_publishing_visual_success(self):
        s=self.s
        with self.environment() as (_,_,_,_,worker):
            response,args=self.dispatch(worker);request=response['request'];seen=[]
            def model(*_,**options):
                options['on_answer'](dict(sequence=0,text='We can compare equal-sized wholes.'))
                seen.extend(self.read(request)['chunks'])
                raise ModelTransportError('invalid_response')
            with patch.object(s,'generate_notebook_story',side_effect=model):s.notebook_model_answer(*args)
            self.assertEqual(len(seen),1)
            self.assertEqual(self.read(request),dict(request=request,state='failed',chunks=[]))
            self.assertNotIn(PATH,s.ready);self.assertEqual(s.answers[PATH],'failed')
            self.assertEqual(len(s.notebook_answer_streams[request]['chunks']),1,'preserve evidence, never replay it')

    def test_real_http_handler_returns_early_prose_only_with_tablet_capability(self):
        s=self.s
        with self.environment() as (_,_,_,_,worker), \
                patch.object(s,'notebook_auth',NotebookAuth({'local':'l'*43,'tablet':'t'*43})):
            response,args=self.dispatch(worker);request=response['request']
            server=HTTPServer(('127.0.0.1',0),s.Handler)
            serving=REAL_THREAD(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
            serving.start()
            responses=[]
            def fetch(headers):
                conn=http.client.HTTPConnection(*server.server_address,timeout=2)
                try:
                    conn.request('POST','/notebook-answer-stream',
                                 json.dumps(dict(request=request,page=PATH,after=-1)),headers)
                    reply=conn.getresponse()
                    result=reply.status,json.loads(reply.read())
                    responses.append(result)
                    return result
                except Exception as error:
                    responses.append((type(error).__name__,str(error)))
                    raise
                finally:conn.close()
            def model(*_,**options):
                options['on_answer'](dict(sequence=0,text='Compare the same whole.'))
                self.assertEqual(fetch({})[0],401)
                status,reply=fetch({'Authorization':'Bearer '+'t'*43})
                self.assertEqual(status,200);self.assertEqual(reply['state'],'waiting')
                self.assertEqual(reply['chunks'][0]['text'],'Compare the same whole.')
                self.assertNotIn(PATH,s.ready)
                return self.result(request)
            try:
                with patch.object(s,'generate_notebook_story',side_effect=model):s.notebook_model_answer(*args)
                self.assertEqual(s.answers[PATH],'ready',repr(responses))
            finally:
                server.shutdown();server.server_close();serving.join(3)
            self.assertFalse(serving.is_alive())

    def test_changed_page_or_input_stops_stream_and_cannot_revive(self):
        s=self.s
        for field,value in [('page',DOC),('surface','other'),('ink_revision',3),
                            ('content_revision',9),('view',[1,0,0,1,0,1]),('active',False),('fresh',False)]:
            with self.subTest(field=field),self.environment() as (context,_,_,_,worker):
                response,args=self.dispatch(worker);request=response['request']
                def model(*_,**options):
                    options['on_answer'](dict(sequence=0,text='Start with equal-sized wholes.'))
                    old=context[field];context[field]=value
                    self.assertEqual(self.read(request)['state'],'failed')
                    context[field]=old
                    self.assertFalse(options['is_current']())
                    self.assertEqual(self.read(request)['chunks'],[])
                    return self.result(request)
                with patch.object(s,'generate_notebook_story',side_effect=model):s.notebook_model_answer(*args)
                self.assertNotIn(PATH,s.ready)

    def test_revalidates_callback_and_rejects_wrong_identity_and_cursor(self):
        s=self.s
        for bad in [dict(sequence=True,text='No.'),dict(sequence=1,text='Skipped.'),
                    dict(sequence=0,text='**Markup**'),dict(sequence=0,text='x'*161),
                    dict(sequence=0,text='A.',path='/tmp/a'),dict(sequence=0,text='\ud800')]:
            with self.subTest(bad=repr(bad)),self.environment() as (_,_,_,_,worker):
                response,args=self.dispatch(worker)
                def model(*_,**options):
                    options['on_answer'](bad)
                    return self.result(response['request'])
                with patch.object(s,'generate_notebook_story',side_effect=model):s.notebook_model_answer(*args)
                self.assertEqual(s.answers[PATH],'failed');self.assertNotIn(PATH,s.ready)
                self.assertEqual(s.notebook_answer_streams[response['request']]['chunks'],[])
        with self.environment() as (_,_,_,_,worker):
            response,args=self.dispatch(worker);request=response['request']
            def model(*_,**options):
                options['on_answer'](dict(sequence=0,text='A clear beginning.'))
                for body in [dict(request='wrong',page=PATH,after=-1),
                             dict(request=request,page='wrong',after=-1),
                             dict(request=request,page=PATH,after=True),
                             dict(request=request,page=PATH,after=1),
                             dict(request=request,page=PATH,after=-1,extra=1)]:
                    with self.assertRaises(ValueError):s.notebook_answer_stream(body)
                # A repeated producer record is an error, unlike a repeated read.
                options['on_answer'](dict(sequence=0,text='A clear beginning.'))
            with patch.object(s,'generate_notebook_story',side_effect=model):s.notebook_model_answer(*args)
            self.assertEqual(s.answers[PATH],'failed')

    def test_restart_or_supersession_does_not_recreate_or_expose_a_stream(self):
        s=self.s
        with self.environment() as (_,_,_,_,worker):
            response,args=self.dispatch(worker);request=response['request']
            def model(*_,**options):
                options['on_answer'](dict(sequence=0,text='First idea.'))
                replacement=list(args[0]);replacement[4]='notebook-'+'f'*32
                s.start_notebook_job(replacement)
                with self.assertRaises(ValueError):self.read(request)
                return self.result(request)
            with patch.object(s,'generate_notebook_story',side_effect=model):s.notebook_model_answer(*args)
            self.assertEqual(s.answers[PATH],'waiting');self.assertNotIn(PATH,s.ready)
            s.notebook_answer_streams.clear()
            with self.assertRaises(ValueError):self.read(request)


if __name__=='__main__': unittest.main()
