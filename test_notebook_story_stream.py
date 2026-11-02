"""Actual Node/Python IPC with a gated fake provider; no tablet/model claims."""
from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile
import unittest

from notebook_story_stream import AnswerRecords
from notebook_story_generation import generate_notebook_story
from notebook_panel_examples import graph_reuse_example
from notebook_model_transport import ModelTransportError
from test_notebook_model_transport import png, envelope, REQUEST


def line(value): return json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n'
def opening(seq=0,text='A graph links each input to its output.'):
    return dict(v=1,mode='answer-chunk',seq=seq,text=text)


class AnswerRecordsTests(unittest.TestCase):
    def setUp(self):
        self.seen=[];self.current=True
        self.reader=AnswerRecords(REQUEST,task='story',on_answer=self.seen.append,
                                  is_current=lambda:self.current)

    def feed(self,value,**overrides):
        self.reader.accept(dict(request_id=REQUEST,response_format='story-stream-v1',
                                sequence=len(self.reader.raw),record=line(value),**overrides))

    def test_prose_early_terminal_only_after_full_matching_envelope(self):
        self.feed(opening())
        self.assertEqual(self.seen,[dict(sequence=0,text=opening()['text'])])
        story,_=graph_reuse_example();self.feed(story)
        result=envelope(''.join(self.reader.raw));result['response_format']='story-stream-v1'
        self.assertEqual(json.loads(self.reader.finish(json.dumps(result).encode())['text']),story)
        self.assertEqual(len(self.seen),1)
        result['text']+=' '
        with self.assertRaises(ModelTransportError): self.reader.finish(json.dumps(result).encode())

    def test_sequence_markup_control_and_excessive_text_rejected_before_callback(self):
        bad=[opening(seq=1),opening(seq=True),opening(text='```python'),
             opening(text='**bold**'),opening(text='x'*161),opening(text='a\nb'),
             dict(opening(),command='draw'),dict(opening(),v=True)]
        for value in bad:
            self.setUp()
            with self.subTest(value=value),self.assertRaises(ValueError): self.feed(value)
            self.assertEqual(self.seen,[])
        self.setUp();self.feed(opening());
        with self.assertRaises(ValueError): self.feed(opening())
        self.assertEqual(len(self.seen),1)

    def test_chunk_total_and_terminal_order_are_bounded(self):
        self.feed(opening(text='x'*150));self.feed(opening(1,'y'*150))
        with self.assertRaises(ValueError): self.feed(opening(2,'z'*150))
        self.setUp();self.feed(opening());story,_=graph_reuse_example();self.feed(story)
        with self.assertRaises(ValueError): self.feed(opening())
        self.assertEqual(len(self.seen),1)
        self.setUp()
        with self.assertRaises(ValueError): self.feed(story)
        self.assertEqual(self.seen,[])

    def test_page_change_after_first_chunk_stops_second_and_terminal(self):
        def consume(chunk): self.seen.append(chunk);self.current=False
        self.reader.on_answer=consume
        with self.assertRaisesRegex(ModelTransportError,'cancelled'): self.feed(opening())
        with self.assertRaisesRegex(ModelTransportError,'cancelled'): self.feed(opening(1))
        self.assertEqual(len(self.seen),1)

    def test_panel_task_cannot_emit_prose_and_drawing_cannot_be_an_answer(self):
        self.reader=AnswerRecords(REQUEST,task='panel',on_answer=None,is_current=lambda:True)
        with self.assertRaises(ValueError): self.feed(opening())
        self.assertEqual(self.seen,[])
        self.setUp()
        with self.assertRaises(ValueError): self.feed(dict(v=1,mode='panel-shapes',items=[]))
        self.assertEqual(self.seen,[])

    def test_duplicate_json_keys_and_wrong_request_rejected(self):
        for raw,rid in [('{"v":1,"v":1,"mode":"answer-chunk","seq":0,"text":"hello"}\n',REQUEST),
                        (line(opening()),'notebook-'+'b'*32)]:
            with self.assertRaises(ValueError):
                self.reader.accept(dict(request_id=rid,response_format='story-stream-v1',sequence=0,record=raw))
        self.assertEqual(self.seen,[])


class StreamingIPCTests(unittest.TestCase):
    def run_stream(self,*,bad_diagram=False,page_change=False,bad_completion=False):
        story,shapes=graph_reuse_example()
        if bad_diagram: shapes['branch']['items'][0]['to']=[999,999]
        here=Path(__file__).resolve().parent
        source='''
import fs from 'node:fs';
import {createNotebookResponder} from CORE;
import {serveNotebookSocket} from HOST;
const c=JSON.parse(fs.readFileSync(0,'utf8'));let calls=0,release;
const gate=new Promise(resolve=>release=resolve);
process.on('SIGUSR1',()=>release());
const model={provider:'openai-codex',id:'fixture',input:['image']};
const registry={isUsingOAuth:()=>true,streamSimple(m,ctx,opts){
 const index=calls++,text=c.replies[index];console.error('call');
 if(ctx.tools.length || opts.maxRetries!==0 || ctx.messages[0].content[1].data!==c.image)throw Error('fixture isolation');
 return {async *[Symbol.asyncIterator](){
   if(index===0){
     const at=text.indexOf('\\n')+1,first=text.slice(0,at);
     yield {type:'thinking_delta',delta:'not user text'};
     for(const delta of first)yield {type:'text_delta',delta};
     await gate; // Cannot finish until Python's early-answer callback runs.
     yield {type:'text_delta',delta:text.slice(at)};
   }else yield {type:'text_delta',delta:text};
 },result:async()=>({role:'assistant',provider:m.provider,model:m.id,stopReason:'stop',
   content:[{type:'text',text:text+(c.badCompletion&&index===0?'different':'')}],usage:{output:20}})};
}};
const responder=createNotebookResponder({modelRegistry:registry,model,systemPrompt:'Fake provider only',responseFormat:'story-stream-v1'});
const host=await serveNotebookSocket({socketPath:c.endpoint,responder});console.log('ready');
process.on('SIGTERM',async()=>{release();await host.close();process.exit(0);});
'''.replace('CORE',json.dumps((here/'notebook_pi_responder.mjs').as_uri())).replace('HOST',json.dumps((here/'notebook_pi_socket.mjs').as_uri()))
        seen=[];current=True
        with tempfile.TemporaryDirectory(prefix='stream-',dir=Path(tempfile.gettempdir()).resolve()) as tmp:
            endpoint=str(Path(tmp)/'notebook.sock')
            child=subprocess.Popen(['node','--input-type=module','-e',source],stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                replies=[line(opening(text='Each input has an output—even café counts as text.'))+line(story),
                         *[line(shapes[p['id']]) for p in story['panels']]]
                config=dict(endpoint=endpoint,replies=replies,badCompletion=bad_completion,
                            image=base64.b64encode(png()).decode())
                child.stdin.write(json.dumps(config).encode());child.stdin.close()
                self.assertTrue(select.select([child.stdout],[],[],3)[0])
                self.assertEqual(child.stdout.readline(),b'ready\n')
                def answer(chunk):
                    nonlocal current
                    seen.append(chunk)
                    if page_change: current=False
                    os.kill(child.pid,signal.SIGUSR1)
                result=None;error=None
                try:
                    result=generate_notebook_story(endpoint,REQUEST,png(),deadline_ms=4000,
                        is_current=lambda:current,on_answer=answer)
                except ValueError as exc: error=exc
            finally:
                child.terminate();child.wait(timeout=5)
                logs=child.stderr.read();child.stderr.close();child.stdout.close()
        return result,error,seen,logs.count(b'call\n')

    def test_early_answer_crosses_real_socket_before_provider_can_complete(self):
        result,error,seen,calls=self.run_stream()
        self.assertIsNone(error)
        self.assertEqual(calls,5)
        self.assertEqual(len(seen),1)
        self.assertIn('café',seen[0]['text'])
        self.assertNotIn('answer-chunk',result['text'])
        self.assertEqual(result['parsed']['mode'],'lesson')
        self.assertEqual(result['answer_stream']['chunks'],1)
        self.assertIsNone(result['answer_stream']['respond_to_first_visible_answer_ms'])
        self.assertLessEqual(result['answer_stream']['first_validated_answer_ms'],result['metrics']['elapsed_ms'])

    def test_late_invalid_diagram_keeps_prose_but_returns_no_visual_success(self):
        result,error,seen,calls=self.run_stream(bad_diagram=True)
        self.assertIsNone(result);self.assertIsInstance(error,ValueError)
        self.assertEqual(len(seen),1);self.assertEqual(calls,5)

    def test_page_change_after_first_chunk_cancels_before_any_drawer_call(self):
        result,error,seen,calls=self.run_stream(page_change=True)
        self.assertIsNone(result);self.assertEqual(error.code,'cancelled')
        self.assertEqual(len(seen),1);self.assertEqual(calls,1)

    def test_completed_text_cannot_rewrite_already_emitted_answer(self):
        result,error,seen,calls=self.run_stream(bad_completion=True)
        self.assertIsNone(result);self.assertEqual(error.code,'invalid_response')
        self.assertEqual(len(seen),1);self.assertEqual(calls,1)


if __name__=='__main__': unittest.main()
