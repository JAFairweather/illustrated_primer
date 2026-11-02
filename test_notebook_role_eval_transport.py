"""Real IPC with fake models: configuration/isolation proof, not model quality."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import select
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from notebook_model_transport import ModelTransportError, validate_model_result, _validated_envelope
from notebook_role_eval_transport import validate_candidate, validate_role_result, call_role_eval
from test_notebook_model_transport import REQUEST, envelope, png


class RoleEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.expected=dict(role='planner',harness='pi',provider='openai-codex',model='configured',
            reasoning_requested='medium',requested_output_tokens=4096,
            prompt_sha256=hashlib.sha256(b'FIXED').hexdigest())
        self.reply=envelope('bounded model text')
        self.reply['response_format']='role-eval-v1'
        self.reply['metrics'].update(reasoning_requested='medium',requested_output_tokens=4096)
        self.reply['evaluation']={k:self.expected[k] for k in ('role','harness','prompt_sha256')}

    def raw(self):return json.dumps(self.reply).encode()

    def test_exact_candidate_binding_and_unchanged_raw_observation(self):
        seen=[]
        self.assertEqual(validate_role_result(self.raw(),REQUEST,expected=self.expected,
            observe_response=seen.append),self.reply)
        self.assertEqual(seen,[self.raw()])
        for group,key,value in [('evaluation','role','drawer'),('evaluation','harness','other'),
            ('evaluation','prompt_sha256','0'*64),('metrics','model','other'),
            ('metrics','reasoning_requested','high'),('metrics','requested_output_tokens',2400)]:
            changed=deepcopy(self.reply);changed[group][key]=value;seen=[]
            with self.subTest(key=key),self.assertRaises(ModelTransportError):
                validate_role_result(json.dumps(changed).encode(),REQUEST,expected=self.expected,
                    observe_response=seen.append)
            self.assertEqual(seen,[])

    def test_role_results_never_pass_existing_production_or_control_envelopes(self):
        with self.assertRaises(ModelTransportError):validate_model_result(self.raw(),REQUEST)
        with self.assertRaises(ModelTransportError):_validated_envelope(self.raw(),REQUEST,'story-panel-v1')
        old=envelope();old['metrics']['reasoning_requested']='minimal'
        with self.assertRaises(ModelTransportError):validate_model_result(json.dumps(old).encode(),REQUEST)
        self.assertEqual(validate_model_result(json.dumps(envelope()).encode(),REQUEST)['metrics']['reasoning_requested'],'medium')

    def test_invalid_candidates_fail_before_socket_or_provider(self):
        for key,value in [('role','send'),('harness','unknown'),('provider','other'),('model',''),
            ('reasoning_requested','auto'),('requested_output_tokens',True),
            ('requested_output_tokens',8193),('prompt_sha256','bad')]:
            candidate=dict(self.expected,**{key:value})
            with self.subTest(key=key),patch('notebook_role_eval_transport._call') as call:
                with self.assertRaises(ModelTransportError):
                    call_role_eval('/unused/notebook-eval.sock',REQUEST,png(),'{}',expected=candidate)
                call.assert_not_called()
        for candidate in [None,[],{},dict(self.expected,tools=['shell'])]:
            with self.assertRaises(ModelTransportError):validate_candidate(candidate)

    def test_endpoint_and_settings_never_become_request_overrides(self):
        for endpoint in ['/unused/notebook.sock',None]:
            with patch('notebook_role_eval_transport._call') as call:
                with self.assertRaises(ModelTransportError):
                    call_role_eval(endpoint,REQUEST,png(),'{}',expected=self.expected)
                call.assert_not_called()
        with patch('notebook_role_eval_transport._call') as call:
            call_role_eval('/unused/notebook-eval.sock',REQUEST,png(),'question',expected=self.expected)
            self.assertEqual(call.call_args.args[3],'question')
            self.assertNotIn('expected',call.call_args.kwargs)

    def test_duplicate_wrong_binding_and_errors_are_bounded(self):
        for raw in [b'{}',b'[]',self.raw().replace(b'"role": "planner"',b'"role":"planner","role":"planner"'),
                    self.raw().replace(REQUEST.encode(),b'wrong'),b'x'*160001]:
            with self.assertRaises(ModelTransportError):validate_role_result(raw,REQUEST,expected=self.expected)
        for code,expected in [('deadline','deadline'),('SECRET','provider_error')]:
            with self.assertRaises(ModelTransportError) as caught:
                validate_role_result(json.dumps(dict(request_id=REQUEST,error=code)).encode(),REQUEST,expected=self.expected)
            self.assertEqual(caught.exception.code,expected)

    def test_real_pi_core_socket_and_python_role_binding(self):
        here=Path(__file__).resolve().parent
        source='''
import fs from 'node:fs';
import {createNotebookResponder} from CORE;
import {serveNotebookSocket} from HOST;
const config=JSON.parse(fs.readFileSync(0,'utf8'));
const model={provider:'openai-codex',id:'configured',input:['image','text']};
const modelRegistry={isUsingOAuth:()=>true,streamSimple(m,context,options){
 if(context.messages.length!==1 || context.tools.length || options.toolChoice!=='none' ||
    options.reasoning!=='medium' || options.maxTokens!==4096 || options.maxRetries!==0)
    throw Error('isolation/settings mismatch');
 return {async *[Symbol.asyncIterator](){},result:async()=>({role:'assistant',provider:m.provider,
 model:m.id,stopReason:'stop',content:[{type:'text',text:'role result'}],usage:{input:10,output:20}})};
}};
const responder=createNotebookResponder({modelRegistry,model,systemPrompt:'FIXED',
 responseFormat:'role-eval-v1',evaluation:{role:'planner',reasoning:'medium',outputTokens:4096}});
const host=await serveNotebookSocket({socketPath:config.endpoint,responder});console.log('ready');
process.on('SIGTERM',async()=>{await host.close();process.exit(0);});
'''.replace('CORE',json.dumps((here/'notebook_pi_responder.mjs').as_uri())).replace('HOST',json.dumps((here/'notebook_pi_socket.mjs').as_uri()))
        # Short socket path: the kernel counts UTF-8 bytes, not Python chars.
        with tempfile.TemporaryDirectory(prefix='role-',dir='/tmp') as directory:
            endpoint=str(Path(directory).resolve()/'notebook-eval.sock')
            child=subprocess.Popen(['node','--input-type=module','-e',source],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                child.stdin.write(json.dumps(dict(endpoint=endpoint)).encode());child.stdin.close()
                self.assertTrue(select.select([child.stdout],[],[],3)[0]);self.assertEqual(child.stdout.readline(),b'ready\n')
                result=call_role_eval(endpoint,REQUEST,png(),'question data',expected=self.expected)
                self.assertEqual(result['text'],'role result')
                self.assertEqual(result['metrics']['reasoning_requested'],'medium')
                self.assertEqual(result['evaluation']['prompt_sha256'],self.expected['prompt_sha256'])
            finally:
                child.terminate()
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
                child.stdout.close();child.stderr.close()


if __name__=='__main__':unittest.main()
