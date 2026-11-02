"""Fake-model generation tests; no model quality or tablet claims."""
from copy import deepcopy
import json
from pathlib import Path
import select
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from notebook_story_generation import generate_notebook_story
from notebook_model_transport import ModelTransportError,call_story_panel_model
from notebook_panel_examples import graph_reuse_example
from notebook_lesson_native import native_semantic_bundle
from test_notebook_model_transport import png,envelope,REQUEST
import test_notebook_model_server as model_server_tests

ROUTE,PATH=model_server_tests.ROUTE,model_server_tests.PATH


class StoryGenerationTests(unittest.TestCase):
    def setUp(self):
        self.story,self.shapes=graph_reuse_example();self.calls=[];self.now=0
        self.replies=[json.dumps(self.story),*[json.dumps(self.shapes[p['id']]) for p in self.story['panels']]]

    def model(self,endpoint,identity,image,packet,*,deadline_ms,is_current):
        self.assertTrue(is_current());self.assertEqual(image,png())
        self.calls.append(dict(identity=identity,packet=json.loads(packet),deadline=deadline_ms))
        self.now+=1
        result=envelope(self.replies[len(self.calls)-1])
        result.update(request_id=identity,response_format='story-panel-v1')
        return result

    def run_case(self,**kwargs):
        return generate_notebook_story('/unused/notebook.sock',REQUEST,png(),call=self.model,
            clock=lambda:self.now,**kwargs)

    def test_complete_story_uses_small_calls_exact_bases_and_one_total_deadline(self):
        result=self.run_case()
        self.assertEqual(result['calls'],5)
        self.assertEqual([c['deadline'] for c in self.calls],[30000,29000,28000,27000,26000])
        self.assertEqual(len({c['identity'] for c in self.calls}),5)
        self.assertEqual(self.calls[0]['identity'],REQUEST)
        self.assertNotIn('question',self.calls[0]['packet']['context'],'image is primary input')
        self.assertEqual([x['id'] for x in self.calls[-1]['packet']['context']['base_items']],['ax'])
        self.assertEqual([x['id'] for x in self.calls[-2]['packet']['context']['base_items']],['ax','square'])
        self.assertEqual(result['parsed']['story'],self.story)
        self.assertEqual(result['metrics']['elapsed_ms'],5000)
        self.assertEqual(result['metrics']['usage']['output'],50)
        bundle=native_semantic_bundle(result['text'],playback=True)
        self.assertEqual([b['stage'] for b in bundle['blocks'] if b['kind']=='ink'],
                         ['axes','curve','mark','axes','branch'])

    def test_invalid_final_panel_returns_no_partial_reply_or_retry(self):
        bad=deepcopy(self.shapes['branch']);bad['items'][0]['to']=[1000,1000]
        self.replies[-1]=json.dumps(bad)
        with self.assertRaises(ValueError):self.run_case()
        self.assertEqual(len(self.calls),5)

    def test_visual_input_description_follows_image_on_every_isolated_call(self):
        self.run_case(image_context='Left latest input; right same-page reference.')
        self.assertTrue(all(c['packet']['context']['image_context'] ==
            'Left latest input; right same-page reference.' for c in self.calls))

    def test_invalid_visual_description_fails_before_provider(self):
        with self.assertRaises(ModelTransportError):
            self.run_case(image_context='x'*12001)
        self.assertEqual(self.calls,[])

    def test_cancellation_and_deadline_stop_between_calls(self):
        with self.assertRaisesRegex(ModelTransportError,'cancelled'):
            self.run_case(is_current=lambda:len(self.calls)<2)
        self.assertEqual(len(self.calls),2)
        self.calls=[];self.now=0
        with self.assertRaisesRegex(ModelTransportError,'deadline'):
            self.run_case(deadline_ms=1500)
        self.assertEqual(len(self.calls),2)
        self.assertEqual([c['deadline'] for c in self.calls],[1500,500])

    def test_explicit_unavailable_becomes_clarification_without_partial_lesson(self):
        for index in (0,2):
            self.setUp();self.replies[index]=json.dumps(dict(v=1,mode='unavailable',reason='Please clarify the handwritten limit.'))
            result=self.run_case()
            self.assertEqual(result['parsed'],dict(mode='clarify',text='Please clarify the handwritten limit.'))
            self.assertEqual(len(self.calls),index+1)

    def test_model_binding_changes_fail_without_continuation(self):
        for field,value in (('model','changed'),('response_format','semantic-v1'),('request_id','wrong')):
            self.setUp();model=self.model
            def changed(*args,**kwargs):
                result=model(*args,**kwargs)
                if len(self.calls)==2:
                    if field=='model':result['metrics']['model']=value
                    else:result[field]=value
                return result
            with self.subTest(field=field),self.assertRaises(ModelTransportError):
                generate_notebook_story('/unused/notebook.sock',REQUEST,png(),call=changed,clock=lambda:self.now)
            self.assertEqual(len(self.calls),2)

    def test_dedicated_production_transport_preserves_cancellation_and_wire_format(self):
        with patch('notebook_model_transport._call') as transport:
            check=lambda:True
            call_story_panel_model('/unused/notebook.sock',REQUEST,png(),'{}',is_current=check)
            self.assertIs(transport.call_args.kwargs['is_current'],check)
            validate=transport.call_args.kwargs['validate']
            result=envelope();result['response_format']='story-panel-v1'
            self.assertEqual(validate(json.dumps(result).encode(),REQUEST,observe_response=None),result)
            result['response_format']='semantic-v1'
            with self.assertRaises(ModelTransportError):validate(json.dumps(result).encode(),REQUEST,observe_response=None)
        with patch('notebook_model_transport._call') as transport:
            with self.assertRaises(ModelTransportError):
                call_story_panel_model('/unused/notebook-eval.sock',REQUEST,png(),'{}')
            transport.assert_not_called()

    def test_real_unix_host_runs_producer_with_fake_provider_and_actual_image_bytes(self):
        here=Path(__file__).resolve().parent
        source='''
import fs from 'node:fs';
import {createNotebookResponder} from CORE;
import {serveNotebookSocket} from HOST;
const c=JSON.parse(fs.readFileSync(0,'utf8'));let n=0;
const model={provider:'openai-codex',id:'fake',input:['image','text']};
const modelRegistry={isUsingOAuth:()=>true,streamSimple(m,ctx,opts){
 if(ctx.messages.length!==1 || ctx.tools.length || opts.maxRetries!==0 ||
    ctx.messages[0].content[1].data!==c.image)throw Error('isolation/image changed');
 const text=c.replies[n++];
 return {async *[Symbol.asyncIterator](){yield {type:'text_delta',delta:text};},
 result:async()=>({role:'assistant',provider:m.provider,model:m.id,stopReason:'stop',
 content:[{type:'text',text}],usage:{output:20}})};
}};
const responder=createNotebookResponder({modelRegistry,model,systemPrompt:'Fixture, no paid model',responseFormat:'story-panel-v1'});
const host=await serveNotebookSocket({socketPath:c.endpoint,responder});console.log('ready');
process.on('SIGTERM',async()=>{await host.close();process.exit(0);});
'''.replace('CORE',json.dumps((here/'notebook_pi_responder.mjs').as_uri())).replace('HOST',json.dumps((here/'notebook_pi_socket.mjs').as_uri()))
        import base64
        with tempfile.TemporaryDirectory(prefix='story-prod-',dir=Path(tempfile.gettempdir()).resolve()) as tmp:
            endpoint=str(Path(tmp)/'notebook.sock')
            child=subprocess.Popen(['node','--input-type=module','-e',source],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                child.stdin.write(json.dumps(dict(endpoint=endpoint,replies=self.replies,
                    image=base64.b64encode(png()).decode())).encode());child.stdin.close()
                self.assertTrue(select.select([child.stdout],[],[],3)[0])
                self.assertEqual(child.stdout.readline(),b'ready\n')
                result=generate_notebook_story(endpoint,REQUEST,png())
                self.assertEqual(result['calls'],5)
                self.assertEqual(result['parsed']['story'],self.story)
                self.assertEqual(result['metrics']['usage']['output'],100)
                self.assertEqual(native_semantic_bundle(result['text'])['mode'],'story')
            finally:
                child.terminate()
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
                child.stdout.close();child.stderr.close()


class StoryWorkerTests(unittest.TestCase):
    setUpClass=classmethod(model_server_tests.ModelServerTests.setUpClass.__func__)
    environment=model_server_tests.ModelServerTests.environment
    dispatch=model_server_tests.ModelServerTests.dispatch

    def test_respond_worker_uses_complete_producer_and_page_change_stops_panel_calls(self):
        for changed in (False,True):
            fixture=StoryGenerationTests();fixture.setUp()
            with self.environment(dict(ROUTE,response_format='story-panel-v1')) as (context,_,send,reader,thread):
                _,args=self.dispatch(thread)
                def model(*a,**kw):
                    result=fixture.model(*a,**kw)
                    if changed and len(fixture.calls)==2:context['ink_revision']+=1
                    return result
                with patch('notebook_story_generation.call_story_panel_model',side_effect=model), \
                     patch.object(self.s,'call_notebook_model',side_effect=AssertionError('legacy call')):
                    self.s.notebook_model_answer(*args)
                send.assert_not_called();reader.assert_not_called()
                if changed:
                    self.assertEqual(len(fixture.calls),2)
                    self.assertNotIn(PATH,self.s.ready)
                    self.assertIn('page_changed',self.s.reply_errors[PATH])
                else:
                    self.assertEqual(len(fixture.calls),5)
                    self.assertEqual(json.loads(self.s.ready[PATH])['mode'],'story-lesson')
                    self.assertEqual(self.s.answers[PATH],'ready')


if __name__=='__main__':unittest.main()
