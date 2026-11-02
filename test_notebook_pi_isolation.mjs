/** Two existing registrations, not a new runner or a live model call. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import {registerNotebookResponder} from './notebook_pi_lifecycle.mjs';

const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG9kAAAAASUVORK5CYII=';
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
function exchange(endpoint, extra={}) {
  return new Promise((resolve,reject)=>{
    const q={request_id:'notebook-'+'c'.repeat(32),context:'A new question.',
      image:{mime_type:'image/png',data:png},deadline_ms:1000,...extra};
    const client=net.createConnection(endpoint,()=>client.write(JSON.stringify(q)+'\n'));
    let data=''; client.on('data',chunk=>data+=chunk); client.on('error',reject);
    client.on('end',()=>{try{resolve(JSON.parse(data));}catch(e){reject(e);}});
  });
}
function fixture({onCall=()=>Promise.resolve(),find=()=>undefined,isUsingOAuth=()=>true}={}) {
  const directory=fs.mkdtempSync(path.join(process.cwd(),'.pe-'));
  fs.chmodSync(directory,0o700);
  const hooks=new Map(),calls=[],states={live:[],eval:[]};
  const pi={on(name,fn){
    if(!hooks.has(name))hooks.set(name,new Set());
    hooks.get(name).add(fn);return ()=>hooks.get(name).delete(fn);
  }};
  const model={id:'same-configured-model',provider:'openai-codex',input:['image']};
  const registry={find,isUsingOAuth,streamSimple(selected,ctx,options){
    const record={selected,ctx,options};calls.push(record);const gate=onCall(record);
    return {async *[Symbol.asyncIterator](){await gate;},result:async()=>({
      role:'assistant',provider:selected.provider,model:selected.id,stopReason:'stop',
      content:[{type:'text',text:JSON.stringify({v:1,mode:'answer',text:ctx.systemPrompt})}]})};
  }};
  const registrations=[];
  function add(name,prompt,options={}){
    const socketPath=path.join(directory,name==='live'?'l':'e');
    const lifecycle=registerNotebookResponder(pi,{socketPath,systemPrompt:prompt,
      onStatus:s=>states[name].push(s),...options});
    registrations.push(lifecycle);return {socketPath,lifecycle};
  }
  async function emit(event,eventData={}){
    for(const fn of hooks.get(event)??[])fn(eventData, {model,modelRegistry:registry,
      sessionManager:{private:'DO NOT COPY'},tools:['shell'],systemPrompt:'CHAT PROMPT'});
    await Promise.all(registrations.map(x=>x.settled()));
  }
  async function close(){
    await Promise.all(registrations.map(x=>x.close()));
    fs.rmSync(directory,{recursive:true});
  }
  return {directory,calls,states,model,add,emit,close};
}

test('existing lifecycle can host two fixed prompts without changing live state',async()=>{
  const f=fixture();const live=f.add('live','LIVE FIXED PROMPT');
  const candidate=f.add('eval','CANDIDATE FIXED PROMPT');
  try {
    assert.equal(f.calls.length,0);
    await f.emit('session_start');
    const liveIdentity=fs.lstatSync(live.socketPath);
    assert.equal(JSON.parse((await exchange(live.socketPath)).text).text,'LIVE FIXED PROMPT');
    assert.equal(JSON.parse((await exchange(candidate.socketPath)).text).text,'CANDIDATE FIXED PROMPT');
    assert.equal(JSON.parse((await exchange(candidate.socketPath)).text).text,'CANDIDATE FIXED PROMPT');
    assert.equal(f.calls.length,3);
    assert(f.calls.every(({selected,ctx,options})=>selected.id===f.model.id &&
      ctx.messages.length===1 && ctx.tools.length===0 && options.maxRetries===0 &&
      options.reasoning==='medium' && options.cacheRetention==='none'));
    assert.notEqual(f.calls[1].ctx,f.calls[2].ctx);
    assert(!JSON.stringify(f.calls).includes('DO NOT COPY'));
    assert(!JSON.stringify(f.calls).includes('CHAT PROMPT'));
    for(const overrides of [{systemPrompt:'override'},{model:'other'},{tools:['shell']}]) {
      assert.equal((await exchange(candidate.socketPath,overrides)).error,'invalid_request');
    }
    assert.equal(f.calls.length,3);
    await candidate.lifecycle.close();
    assert.equal(fs.existsSync(candidate.socketPath),false);
    assert.equal(fs.lstatSync(live.socketPath).ino,liveIdentity.ino);
    assert.equal(JSON.parse((await exchange(live.socketPath)).text).text,'LIVE FIXED PROMPT');
    assert.deepEqual(f.states.live,['ready']);
    await f.emit('session_shutdown');
    assert.equal(fs.existsSync(live.socketPath),false);
  } finally {await f.close();}
});

test('occupied candidate path cannot replace or shut down the live listener',async()=>{
  const f=fixture();const live=f.add('live','LIVE');
  fs.writeFileSync(path.join(f.directory,'e'),'PRESERVE EXISTING FILE');
  f.add('eval','CANDIDATE');
  try {
    await f.emit('session_start');
    assert.deepEqual(f.states.eval,['unavailable']);
    assert.deepEqual(f.states.live,['ready']);
    assert.equal(fs.readFileSync(path.join(f.directory,'e'),'utf8'),'PRESERVE EXISTING FILE');
    assert.equal(JSON.parse((await exchange(live.socketPath)).text).text,'LIVE');
    assert.equal(f.calls.length,1);
  } finally {await f.close();}
});

test('concurrent calls keep separate busy and cancellation state',async()=>{
  const liveGate=deferred(),evalGate=deferred(),liveStarted=deferred(),evalStarted=deferred();
  const f=fixture({onCall:({ctx})=>{
    if(ctx.systemPrompt==='LIVE'){liveStarted.resolve();return liveGate.promise;}
    evalStarted.resolve();return evalGate.promise;
  }});
  const live=f.add('live','LIVE'),candidate=f.add('eval','EVAL');
  try {
    await f.emit('session_start');
    let liveEnded=false;
    const liveRequest=exchange(live.socketPath).then(r=>{liveEnded=true;return r;});
    const evalRequest=exchange(candidate.socketPath);
    await Promise.all([liveStarted.promise,evalStarted.promise]);
    assert.equal((await exchange(live.socketPath)).error,'busy');
    evalGate.resolve();assert.equal(JSON.parse((await evalRequest).text).text,'EVAL');
    await candidate.lifecycle.close();
    assert.equal(liveEnded,false);
    assert.equal(f.calls.find(c=>c.ctx.systemPrompt==='LIVE').options.signal.aborted,false);
    liveGate.resolve();assert.equal(JSON.parse((await liveRequest).text).text,'LIVE');
    assert.equal(f.calls.length,2);
  } finally {liveGate.resolve();evalGate.resolve();await f.close();}
});

test('model-select replaces both listeners but preserves their fixed prompts',async()=>{
  const f=fixture(),live=f.add('live','LIVE'),candidate=f.add('eval','EVAL');
  try {
    await f.emit('session_start');
    await Promise.all([exchange(live.socketPath),exchange(candidate.socketPath)]);
    const replacement={...f.model,id:'owner-selected-next-model'};
    await f.emit('model_select',{model:replacement});
    const results=await Promise.all([exchange(live.socketPath),exchange(candidate.socketPath)]);
    assert(results.every(r=>r.metrics.model===replacement.id));
    assert.deepEqual(results.map(r=>JSON.parse(r.text).text),['LIVE','EVAL']);
    assert.deepEqual(f.states,{live:['ready','ready'],eval:['ready','ready']});
    assert.equal(f.calls.length,4);
    await f.emit('session_shutdown');
    assert.equal(fs.existsSync(live.socketPath),false);
    assert.equal(fs.existsSync(candidate.socketPath),false);
  } finally {await f.close();}
});

test('owner-fixed candidate model remains independent of live model selection',async()=>{
  const alternate={id:'alternate-evaluation-model',provider:'openai-codex',input:['image','text']};
  const lookups=[];
  const f=fixture({find:(provider,id)=>{lookups.push([provider,id]);return alternate;}});
  const selected={provider:alternate.provider,id:alternate.id};
  const live=f.add('live','LIVE'),candidate=f.add('eval','EVAL',{fixedModel:selected});
  // Snapshot owner configuration: a later caller mutation cannot retarget it.
  selected.id='mutated-after-registration';
  try {
    await f.emit('session_start');
    const first=await Promise.all([exchange(live.socketPath),exchange(candidate.socketPath)]);
    assert.deepEqual(first.map(r=>r.metrics.model),[f.model.id,alternate.id]);
    await f.emit('model_select',{model:{...f.model,id:'new-chat-model'}});
    const second=await Promise.all([exchange(live.socketPath),exchange(candidate.socketPath)]);
    assert.deepEqual(second.map(r=>r.metrics.model),['new-chat-model',alternate.id]);
    assert.deepEqual(lookups,Array(2).fill(['openai-codex',alternate.id]));
    assert.deepEqual(second.map(r=>JSON.parse(r.text).text),['LIVE','EVAL']);
    for(const field of ['model','fixedModel','systemPrompt']) {
      assert.equal((await exchange(candidate.socketPath,{[field]:selected})).error,'invalid_request');
    }
    assert.equal(f.calls.length,4);
    assert(f.calls.every(({ctx,options})=>ctx.messages.length===1 && ctx.tools.length===0 &&
      options.reasoning==='medium' && options.maxRetries===0));
    await candidate.lifecycle.close();
    assert.equal((await exchange(live.socketPath)).metrics.model,'new-chat-model');
  } finally {await f.close();}
});

test('missing, mismatched, text-only or unauthenticated fixed model never falls back to chat',async()=>{
  const selected={provider:'openai-codex',id:'alternate'};
  for(const behavior of ['missing','mismatch','text-only','no-auth','throws']) {
    const f=fixture({find:()=>{
      if(behavior==='throws')throw Error('PRIVATE registry details');
      if(behavior==='missing')return undefined;
      return {...selected,id:behavior==='mismatch'?'wrong':selected.id,
        input:behavior==='text-only'?['text']:['image']};
    },isUsingOAuth:model=>!(behavior==='no-auth' && model.id===selected.id)});
    const live=f.add('live','LIVE'),candidate=f.add('eval','EVAL',{fixedModel:selected});
    try {
      await f.emit('session_start');
      assert.deepEqual(f.states.eval,['unavailable'],behavior);
      assert.equal(fs.existsSync(candidate.socketPath),false);
      assert.equal(f.calls.length,0);
      assert.equal((await exchange(live.socketPath)).metrics.model,f.model.id);
      assert.equal(f.calls.length,1);
    } finally {await f.close();}
  }
});

test('fixed selection rejects extra configuration fields and invalid identities before registration',()=>{
  for(const fixedModel of [null,[],{},'alternate',
    {provider:'other',id:'alternate'}, {provider:'openai-codex',id:'a b'},
    {provider:'openai-codex',id:'alternate',systemPrompt:'override'}]) {
    const pi={on(){assert.fail('must reject before installing any hooks');}};
    assert.throws(()=>registerNotebookResponder(pi,{socketPath:'/unused',systemPrompt:'fixed',fixedModel}),
      /Invalid fixed notebook model/);
  }
});
