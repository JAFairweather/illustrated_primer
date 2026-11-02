import test from 'node:test';
import assert from 'node:assert/strict';
import {createNotebookResponder} from './notebook_pi_responder.mjs';

const model={provider:'openai-codex',id:'fixture',input:['image']};
const request={request_id:'notebook-'+'a'.repeat(32),context:'question',deadline_ms:1000,
  image:{mime_type:'image/png',data:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG9kAAAAASUVORK5CYII='}};
const text='{"v":1,"mode":"answer-chunk","seq":0,"text":"A useful explanation."}\n{"v":1,"mode":"story"}';
function fixture(format='story-stream-v1',gate=Promise.resolve()) {
  let options,calls=0;
  const registry={isUsingOAuth:()=>true,streamSimple(m,ctx,opts){
    options=opts;calls++;
    return {async *[Symbol.asyncIterator](){
      yield {type:'thinking_delta',delta:'private reasoning'};
      yield {type:'text_delta',delta:text.slice(0,12)};
      yield {type:'text_delta',delta:text.slice(12,text.indexOf('\n')+1)};
      await gate;
      yield {type:'text_delta',delta:text.slice(text.indexOf('\n')+1)};
    },result:async()=>({role:'assistant',provider:m.provider,model:m.id,stopReason:'stop',
      content:[{type:'text',text}],usage:{output:20}})};
  }};
  const runner=createNotebookResponder({model,modelRegistry:registry,systemPrompt:'fixed',responseFormat:format});
  return {runner,get calls(){return calls;},get options(){return options;}};
}

test('complete records emit before provider completion; thinking and partial records do not',async()=>{
  let release;const gate=new Promise(resolve=>release=resolve),records=[];
  const f=fixture('story-stream-v1',gate);
  const result=await f.runner.respond(request,{onRecord(record){records.push(record);release();}});
  assert.equal(records.length,2);assert.equal(records[0].sequence,0);assert.equal(records[1].sequence,1);
  assert.equal(records.map(r=>r.record).join(''),text);assert.equal(result.text,text);
  assert(!JSON.stringify(records).includes('private reasoning'));assert.equal(f.calls,1);
});

test('legacy formats never emit early records even if a callback is supplied',async()=>{
  for(const format of ['semantic-v1','story-panel-v1']) {
    const f=fixture(format);let records=0;
    const result=await f.runner.respond(request,{onRecord(){records++;}});
    assert.equal(records,0);assert.equal(result.response_format,format);
  }
});

test('failed stream consumer aborts provider; streaming cannot silently buffer without a consumer',async()=>{
  const f=fixture();
  await assert.rejects(f.runner.respond(request),e=>e.code==='invalid_request');assert.equal(f.calls,0);
  await assert.rejects(f.runner.respond(request,{onRecord(){throw Error('client gone');}}),e=>e.code==='cancelled');
  assert(f.options.signal.aborted);assert.equal(f.calls,1);
});
