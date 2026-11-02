"""Offline real Unix/Node/Python round trip; model provider is an explicit fake."""
import base64
import io
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import unittest

from PIL import Image
from notebook_model_transport import model_request, validate_model_result, call_notebook_model, ModelTransportError, mend_number_words
from notebook_semantic_examples import examples
from notebook_semantic_prompt import semantic_reply_instructions

HERE = Path(__file__).resolve().parent
REQUEST = 'notebook-'+'a'*32


def png():
    out=io.BytesIO();Image.new('RGB',(16,16),'white').save(out,'PNG');return out.getvalue()


def envelope(text='{"v":1,"mode":"answer","text":"One idea."}'):
    return dict(request_id=REQUEST,response_format='semantic-v1',text=text,metrics={
        'elapsed_ms':2,'first_text_ms':1,'provider':'openai-codex','model':'configured',
        'reasoning_requested':'medium','requested_output_tokens':8192,'usage':{'input':20,'output':10}})


class ModelTransportTests(unittest.TestCase):
    def test_captured_png_is_validated_and_transmitted_as_bytes(self):
        image=png();request=model_request(REQUEST,image,'question')
        self.assertEqual(base64.b64decode(request['image']['data']),image)
        for bad in [b'file:///private/photo.png',image[:40],b'not png']:
            with self.assertRaises(ModelTransportError):model_request(REQUEST,bad,'question')
        for rid,context,deadline in [('other','q',15),(REQUEST,'a'*12001,15),(REQUEST,'\ud800',15),(REQUEST,None,15),(REQUEST,'q',True),(REQUEST,'q',90001)]:
            with self.assertRaises(ModelTransportError):model_request(rid,image,context,deadline)

    def test_full_semantic_compiler_runs_before_result_is_released(self):
        spec=examples()['integral']
        parsed=validate_model_result(json.dumps(envelope(json.dumps(spec))).encode(),REQUEST)
        self.assertEqual(parsed['parsed']['mode'],'lesson')
        spec['claims'][-1]['value']['numerator']=99
        with self.assertRaises(ModelTransportError):validate_model_result(json.dumps(envelope(json.dumps(spec))).encode(),REQUEST)

    def test_offline_observation_preserves_rejection_without_bypassing_validation(self):
        spec=examples()['integral']
        spec['claims'][-1]['value']['numerator']=99
        raw=json.dumps(envelope(json.dumps(spec))).encode()
        seen=[]
        with self.assertRaises(ModelTransportError):
            validate_model_result(raw,REQUEST,observe_response=seen.append)
        self.assertEqual(seen,[raw])
        self.assertIsInstance(seen[0],bytes)
        seen.clear()
        for bad in [b'{}',json.dumps(dict(envelope(),request_id='wrong')).encode(),
                    json.dumps(dict(envelope(),metrics={})).encode()]:
            with self.assertRaises(ModelTransportError):
                validate_model_result(bad,REQUEST,observe_response=seen.append)
        self.assertEqual(seen,[])

    def test_request_binding_strict_json_and_failure_codes(self):
        good=envelope()
        with self.assertRaisesRegex(ModelTransportError,'request_mismatch'):
            validate_model_result(json.dumps(good).encode(),'notebook-'+'b'*32)
        for raw in [b'{}',b'[]',json.dumps(dict(good,response_format='other')).encode(),
                    json.dumps(dict(good,text='{"v":1,"mode":"answer","text":"a","text":"b"}')).encode(),
                    json.dumps(good).replace('"elapsed_ms": 2','"elapsed_ms": NaN').encode(),
                    json.dumps(dict(good,metrics={'private':'must not leak'})).encode(),
                    b'x'*160001]:
            with self.assertRaises(ModelTransportError):validate_model_result(raw,REQUEST)
        with self.assertRaisesRegex(ModelTransportError,'deadline'):
            validate_model_result(json.dumps({'request_id':REQUEST,'error':'deadline'}).encode(),REQUEST)

    def test_an_object_closed_one_brace_early_is_mended_and_other_bad_json_says_where(self):
        spec=examples()['integral']
        text=json.dumps(spec)
        early=text[:-1]+'},"extra":{"a":1}}'  # the lesson closed before its last key, as the model sometimes writes it
        with self.assertRaisesRegex(ModelTransportError,'invalid_response'):  # mended to JSON; the compiler still refuses "extra"
            validate_model_result(json.dumps(envelope(early)).encode(),REQUEST)
        for bad in [text+'}', text[:-1]+'},{"a":1}', text.replace('"numerator": 1','"numerator": uno',1)]:
            with self.assertRaisesRegex(ModelTransportError,'invalid_json') as caught:
                validate_model_result(json.dumps(envelope(bad)).encode(),REQUEST)
            self.assertIn('not valid JSON',caught.exception.detail)
        picture='"picture":{"base":"A wide pond with three nested rings.","edits":["Add four arrows around the rings."]}'
        result=validate_model_result(json.dumps(envelope(text[:-1]+'},'+picture+'}')).encode(),REQUEST)
        self.assertEqual(result['parsed']['mode'],'lesson')
        self.assertEqual(json.loads(result['text']),dict(spec,**json.loads('{'+picture+'}')))

    def test_unavailable_socket_never_falls_back(self):
        with tempfile.TemporaryDirectory(prefix='.pi-client-',dir=HERE) as tmp:
            path=Path(tmp)/'s';path.write_text('not a socket')
            with self.assertRaisesRegex(ModelTransportError,'unavailable'):
                call_notebook_model(str(path),REQUEST,png(),'question')
            self.assertEqual(path.read_text(),'not a socket')

    def test_real_node_socket_core_to_python_compiler(self):
        # No API call/auth lookup: fake model registry inspects the actual context
        # after Python sends image bytes across the real owner-only Unix socket.
        source = '''
import fs from 'node:fs';
import {createNotebookResponder} from CORE;
import {serveNotebookSocket} from HOST;
const config=JSON.parse(fs.readFileSync(0,'utf8'));
const model={provider:'openai-codex',id:'configured',input:['image','text']};
let responseIndex=0;
const registry={isUsingOAuth:()=>true,streamSimple(m,context,options){
 if(context.systemPrompt!==config.prompt || context.messages.length!==1 || context.tools.length ||
    options.toolChoice!=='none' || context.messages[0].content[1].data!==config.image ||
    JSON.stringify(context).includes('SESSION_SENTINEL'))throw Error('context isolation failed');
 const text=config.replies[responseIndex++];
 return {async *[Symbol.asyncIterator](){yield {type:'text_delta',delta:text};},result:async()=>({
   role:'assistant',provider:m.provider,model:m.id,stopReason:'stop',content:[{type:'text',text}],usage:{input:20,output:10}})};
}};
const responder=createNotebookResponder({modelRegistry:registry,model,systemPrompt:config.prompt});
const host=await serveNotebookSocket({socketPath:config.endpoint,responder});
console.log('ready');
process.on('SIGTERM',async()=>{await host.close();process.exit(0);});
'''.replace('CORE',json.dumps((HERE/'notebook_pi_responder.mjs').as_uri())).replace('HOST',json.dumps((HERE/'notebook_pi_socket.mjs').as_uri()))
        with tempfile.TemporaryDirectory(prefix='.pi-client-',dir=HERE) as tmp:
            endpoint=str(Path(tmp)/'s');image=png()
            spec=examples()['integral-variant']
            invalid=['```json\n{}\n```','{"v":1,','[]','{"v":1,"mode":"other"}',
                     '{"v":1,"mode":"answer","text":"a","text":"b"}']
            config=dict(endpoint=endpoint,image=base64.b64encode(image).decode(),
                        replies=[json.dumps(spec),*invalid],prompt=semantic_reply_instructions())
            child=subprocess.Popen(['node','--input-type=module','-e',source],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                child.stdin.write(json.dumps(config).encode());child.stdin.close()
                self.assertTrue(select.select([child.stdout],[],[],3)[0],'Node host did not start')
                self.assertEqual(child.stdout.readline(),b'ready\n')
                self.assertEqual(os.stat(endpoint).st_mode & 0o777,0o600)
                observed=[]
                result=call_notebook_model(endpoint,REQUEST,image,'Explain the area under x cubed from zero to two.',
                                           observe_response=observed.append)
                self.assertEqual(len(observed),1)
                self.assertEqual(json.loads(observed[0])['text'],json.dumps(spec))
                self.assertEqual(result['parsed']['mode'],'lesson')
                self.assertEqual(result['metrics']['usage'],{'input':20,'output':10})
                self.assertEqual(json.loads(result['text'])['claims'][-1]['value'],{'numerator':4,'denominator':1})
                for index,text in enumerate(invalid):
                    rejected=[]
                    with self.assertRaisesRegex(ModelTransportError,'invalid_json' if index<2 else 'invalid_response'):
                        call_notebook_model(endpoint,REQUEST,image,'question',observe_response=rejected.append)
                    self.assertEqual(len(rejected),1)
                    self.assertEqual(json.loads(rejected[0])['text'],text,
                                     'bad output reaches diagnostics unchanged but never passes validation')
                with self.assertRaisesRegex(ModelTransportError,'cancelled'):
                    call_notebook_model(endpoint,REQUEST,image,'question',is_current=lambda:False)
            finally:
                child.terminate()
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
                child.stdout.close();child.stderr.close()


class NumberWordTests(unittest.TestCase):
    def test_bare_number_words_become_digits_only_outside_strings(self):
        text = '{"draw": [{"op": "circle", "center": [105, thirty], "radius": sixty}], "caption": "sixty birds, one hundred five"}'
        mended = json.loads(mend_number_words(text))
        self.assertEqual(mended['draw'][0], {'op': 'circle', 'center': [105, 30], 'radius': 60})
        self.assertEqual(mended['caption'], 'sixty birds, one hundred five')

    def test_compound_number_words(self):
        for words, value in (('twenty-five', 25), ('one hundred five', 105), ('three hundred', 300),
                             ('nine hundred ninety-nine', 999), ('zero', 0), ('nineteen', 19)):
            self.assertEqual(json.loads(mend_number_words('{"x": %s}' % words))['x'], value)

    def test_valid_or_unrepairable_text_is_returned_unchanged(self):
        for text in ('{"x": 1, "ok": true}', '{"x": banana}', '{"x": sixty', '[sixty]', '{"x": twenty-zero}'):
            self.assertEqual(mend_number_words(text), text)

    def test_a_reply_with_spelled_numbers_reaches_the_compiler_as_digits(self):
        text = '{"v":1,"mode":"answer","text":"One clear idea.","n":forty}'
        self.assertEqual(json.loads(mend_number_words(text))['n'], 40)


if __name__=='__main__':unittest.main()
