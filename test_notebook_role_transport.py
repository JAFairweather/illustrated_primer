"""Fixed production roles: real IPC/fake providers, not tablet/quality proof."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import select
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from notebook_role_transport import validate_roles, validate_production_result, call_production_role
from notebook_role_eval_transport import validate_role_result
from notebook_story_generation import generate_notebook_story
from notebook_model_transport import ModelTransportError
from notebook_panel_examples import graph_reuse_example
from notebook_lesson_native import native_semantic_bundle
from test_notebook_model_transport import REQUEST, envelope, png


def roles(directory='/private'):
    return {role:dict(socket=f'{directory}/notebook-{role}.sock',expected=dict(
        role=role,harness='pi',provider='openai-codex',model=f'{role}-model',
        reasoning_requested='medium',requested_output_tokens=4096,
        prompt_sha256=hashlib.sha256(role.encode()).hexdigest())) for role in ('planner','drawer')}


class ProductionRoleTests(unittest.TestCase):
    def setUp(self):
        self.roles=roles();self.story,self.shapes=graph_reuse_example();self.calls=[];self.now=0

    def model(self, endpoint, identity, image, packet, *, expected, deadline_ms, is_current):
        self.assertTrue(is_current());self.assertEqual(image,png())
        packet=json.loads(packet);role='planner' if packet['task']=='story' else 'drawer'
        self.assertEqual(endpoint,self.roles[role]['socket']);self.assertEqual(expected,self.roles[role]['expected'])
        self.calls.append((role,deadline_ms));self.now+=1
        text=json.dumps(self.story if role=='planner' else self.shapes[self.story['panels'][len(self.calls)-2]['id']])
        result=envelope(text);result.update(request_id=identity,response_format='role-production-v1',
            production={k:expected[k] for k in ('role','harness','prompt_sha256')})
        result['metrics'].update({k:expected[k] for k in ('provider','model','reasoning_requested','requested_output_tokens')})
        return result

    def run_case(self,**kw):
        return generate_notebook_story(None,REQUEST,png(),roles=self.roles,
            call=kw.pop('call',self.model),clock=lambda:self.now,**kw)

    def test_two_distinct_models_one_deadline_and_whole_native_lesson(self):
        result=self.run_case()
        self.assertEqual(self.calls,[('planner',30000),('drawer',29000),('drawer',28000),('drawer',27000),('drawer',26000)])
        self.assertEqual(result['calls'],5);self.assertEqual(result['metrics']['elapsed_ms'],5000)
        self.assertNotIn('model',result['metrics'],'aggregate cannot be attributed to one role')
        self.assertEqual([m['model'] for m in result['role_calls']],['planner-model']+['drawer-model']*4)
        self.assertTrue(native_semantic_bundle(result['text'],playback=True)['blocks'])

    def test_identity_mismatch_eval_result_and_page_change_stop_without_fallback(self):
        for field in ('model','prompt_sha256','format'):
            self.setUp()
            def wrong(*args,**kw):
                reply=self.model(*args,**kw)
                if len(self.calls)==2:
                    if field=='model':reply['metrics']['model']='planner-model'
                    elif field=='format':reply['response_format']='role-eval-v1'
                    else:reply['production'][field]='0'*64
                return reply
            with self.subTest(field=field),self.assertRaises(ModelTransportError):self.run_case(call=wrong)
            self.assertEqual(len(self.calls),2)
        self.setUp()
        with self.assertRaisesRegex(ModelTransportError,'cancelled'):self.run_case(is_current=lambda:len(self.calls)<2)
        self.assertEqual(len(self.calls),2)
        self.setUp()
        with self.assertRaisesRegex(ModelTransportError,'deadline'):self.run_case(deadline_ms=1500)
        self.assertEqual(self.calls,[('planner',1500),('drawer',500)])

    def test_bad_configuration_refused_before_calls_and_input_cannot_override_settings(self):
        for field,value in [('socket','/private/notebook-eval.sock'),('socket','/private/../notebook-planner.sock'),
                             ('socket','relative/notebook-planner.sock'),('socket','/private//notebook-planner.sock')]:
            bad=deepcopy(self.roles);bad['planner'][field]=value
            with self.assertRaises(ModelTransportError):validate_roles(bad)
        for kw in ({'on_answer':lambda _:None},):
            with self.assertRaises(ModelTransportError):self.run_case(**kw)
        with self.assertRaises(ModelTransportError):
            generate_notebook_story('/private/notebook.sock',REQUEST,png(),roles=self.roles,call=self.model)
        self.assertEqual(self.calls,[])
        binding=self.roles['planner']
        with patch('notebook_role_transport._call') as invoke:
            for packet in ['{}',json.dumps(dict(task='panel',context={})),json.dumps(dict(task='story',context={},model='override'))]:
                with self.assertRaises(ModelTransportError):
                    call_production_role(binding['socket'],REQUEST,png(),packet,expected=binding['expected'])
            invoke.assert_not_called()

    def test_eval_and_production_envelopes_never_cross(self):
        expected=self.roles['planner']['expected']
        reply=self.model(self.roles['planner']['socket'],REQUEST,png(),'{"task":"story","context":{}}',
            expected=expected,deadline_ms=1000,is_current=lambda:True)
        raw=json.dumps(reply).encode()
        self.assertEqual(validate_production_result(raw,REQUEST,expected=expected),reply)
        with self.assertRaises(ModelTransportError):validate_role_result(raw,REQUEST,expected=expected)
        reply['response_format']='role-eval-v1';reply['evaluation']=reply.pop('production')
        with self.assertRaises(ModelTransportError):validate_production_result(json.dumps(reply).encode(),REQUEST,expected=expected)

    def test_actual_two_js_hosts_to_python_compilation(self):
        here=Path(__file__).resolve().parent
        source='''
import fs from 'node:fs';
import {createNotebookResponder} from CORE;
import {serveNotebookSocket} from HOST;
const c=JSON.parse(fs.readFileSync(0,'utf8'));const hosts=[];
for(const role of ['planner','drawer']) {
 const model={provider:'openai-codex',id:role+'-model',input:['image','text']};
 const modelRegistry={isUsingOAuth:()=>true,streamSimple(m,ctx,opts){
  if(ctx.tools.length || ctx.messages.length!==1 || opts.reasoning!=='medium' ||
     opts.maxTokens!==4096 || opts.maxRetries!==0)throw Error('isolation');
  const packet=JSON.parse(ctx.messages[0].content[0].text.split('\\n').slice(1).join('\\n'));
  const text=JSON.stringify(role==='planner'?c.story:c.shapes[packet.context.panel.id]);
  return {async *[Symbol.asyncIterator](){yield {type:'text_delta',delta:text};},
   result:async()=>({role:'assistant',provider:m.provider,model:m.id,stopReason:'stop',
    content:[{type:'text',text}],usage:{output:10}})};
 }};
 const responder=createNotebookResponder({modelRegistry,model,systemPrompt:role,
  responseFormat:'role-production-v1',production:{role,reasoning:'medium',outputTokens:4096}});
 hosts.push(await serveNotebookSocket({socketPath:c.roles[role].socket,responder}));
}
console.log('ready');process.on('SIGTERM',async()=>{for(const h of hosts)await h.close();process.exit(0);});
'''.replace('CORE',json.dumps((here/'notebook_pi_responder.mjs').as_uri())).replace('HOST',json.dumps((here/'notebook_pi_socket.mjs').as_uri()))
        with tempfile.TemporaryDirectory(prefix='prod-role-',dir='/tmp') as directory:
            bindings=roles(str(Path(directory).resolve()))
            child=subprocess.Popen(['node','--input-type=module','-e',source],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                child.stdin.write(json.dumps(dict(roles=bindings,story=self.story,shapes=self.shapes)).encode());child.stdin.close()
                self.assertTrue(select.select([child.stdout],[],[],3)[0]);self.assertEqual(child.stdout.readline(),b'ready\n')
                result=generate_notebook_story(None,REQUEST,png(),roles=bindings)
                self.assertEqual(result['calls'],5);self.assertEqual(result['parsed']['story'],self.story)
                self.assertTrue(native_semantic_bundle(result['text'],playback=True)['blocks'])
            finally:
                child.terminate()
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
                child.stdout.close();child.stderr.close()


if __name__=='__main__':unittest.main()
