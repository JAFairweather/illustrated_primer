import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import {registerNotebookResponder} from './notebook_pi_lifecycle.mjs';

function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup({bindGate,drainGate,bindError=false}={}){
  const handlers=new Map(),entries=[],statuses=[];
  let active=0,maxActive=0;
  const pi={
    on(name,handler){handlers.set(name,handler);return ()=>handlers.delete(name);},
    registerTool(){throw Error('must not install tools');},
    sendUserMessage(){throw Error('must not mutate session');},
  };
  const dependencies={
    createResponder(options){
      if(!options.model)throw Error('PRIVATE runtime details');
      const entry={options,cancelled:false,closed:false};entries.push(entry);
      entry.responder={close(){entry.cancelled=true;return drainGate?.promise ?? Promise.resolve();}};
      return entry.responder;
    },
    async listen({responder,socketPath}){
      assert.equal(socketPath,'/private/owner/notebook.sock');
      if(bindError)throw Error('PRIVATE bind details');
      const entry=entries.find(e=>e.responder===responder);
      active++;maxActive=Math.max(active,maxActive);
      if(bindGate)await bindGate.promise;
      return {async close(){
        if(entry.closed)return;
        entry.closed=true;active--;await responder.close();
      }};
    },
  };
  const registration=registerNotebookResponder(pi,{socketPath:'/private/owner/notebook.sock',
    systemPrompt:'FIXED PROMPT',onStatus:state=>statuses.push(state)},dependencies);
  const emit=(name,ctx,event={})=>{
    assert.equal(handlers.get(name)(event,ctx),undefined,'Pi hooks must not wait for the notebook provider');
    return registration.settled();
  };
  return {registration,handlers,emit,entries,statuses,maxActive:()=>maxActive};
}
const context=id=>({model:{id},modelRegistry:{id:'registry-'+id},sessionManager:{private:'HISTORY'},
                   tools:['shell'],systemPrompt:'PRIVATE SESSION PROMPT'});

test('production roles require distinct named sockets and owner-fixed model',async()=>{
  for(const role of ['planner','drawer']) {
    const hooks=new Map(),calls=[];
    const pi={on(name,fn){hooks.set(name,fn);return ()=>hooks.delete(name);}};
    const config={socketPath:`/private/owner/notebook-${role}.sock`,systemPrompt:'FIXED',
      responseFormat:'role-production-v1',fixedModel:{provider:'openai-codex',id:`${role}-model`},
      production:{role,reasoning:'medium',outputTokens:4096}};
    for(const bad of ['notebook-eval.sock','notebook.sock',`notebook-${role==='planner'?'drawer':'planner'}.sock`])
      assert.throws(()=>registerNotebookResponder(pi,{...config,socketPath:'/private/owner/'+bad}));
    assert.throws(()=>registerNotebookResponder(pi,{...config,fixedModel:undefined}));
    assert.equal(hooks.size,0);
    const selected={...config.fixedModel,input:['image']};
    const handle=registerNotebookResponder(pi,config,{
      createResponder(options){calls.push(options);return {close:async()=>{}};},
      listen:async()=>({close:async()=>{}}),
    });
    config.production.reasoning='minimal';config.fixedModel.id='changed';
    hooks.get('session_start')({}, {model:{id:'chat'},modelRegistry:{find:()=>selected}});
    await handle.settled();
    assert.equal(calls[0].model.id,`${role}-model`);
    assert.deepEqual(calls[0].production,{role,reasoning:'medium',outputTokens:4096});
    assert(!('evaluation' in calls[0]));await handle.close();
  }
});

test('role evaluation requires eval-only socket and independently fixed model',async()=>{
  const hooks=new Map(),calls=[];
  const pi={on(name,fn){hooks.set(name,fn);return ()=>hooks.delete(name);}};
  const config={socketPath:'/private/owner/notebook-eval.sock',systemPrompt:'FIXED',
    responseFormat:'role-eval-v1',fixedModel:{provider:'openai-codex',id:'planner-model'},
    evaluation:{role:'planner',reasoning:'high',outputTokens:4096}};
  for(const bad of [{...config,socketPath:'/private/owner/notebook.sock'},
    {...config,fixedModel:undefined},{...config,responseFormat:'semantic-v1'}])
    assert.throws(()=>registerNotebookResponder(pi,bad));
  assert.equal(hooks.size,0);
  const selected={...config.fixedModel,input:['image','text']};
  const handle=registerNotebookResponder(pi,config,{
    createResponder(options){calls.push(options);return {close:async()=>{}};},
    listen:async()=>({close:async()=>{}}),
  });
  config.evaluation.reasoning='minimal';config.fixedModel.id='mutated';
  hooks.get('session_start')({}, {model:{id:'chat-model'},modelRegistry:{find:()=>selected}});
  await handle.settled();
  assert.equal(calls[0].model.id,'planner-model');
  assert.deepEqual(calls[0].evaluation,{role:'planner',reasoning:'high',outputTokens:4096});
  await handle.close();
});

test('owner-selected story/panel format reaches responder without request overrides',async()=>{
  let start,selected;
  const pi={on(name,fn){if(name==='session_start')start=fn;return ()=>{};}};
  const instance=registerNotebookResponder(pi,{socketPath:'/private/owner/notebook-eval.sock',
    systemPrompt:'FIXED STORY',responseFormat:'story-panel-v1'}, {
    createResponder(options){selected=options;return {close:async()=>{}};},
    listen:async()=>({close:async()=>{}}),
  });
  start({},context('selected'));await instance.settled();
  assert.equal(selected.responseFormat,'story-panel-v1');
  assert.equal(selected.systemPrompt,'FIXED STORY');
  await instance.close();
  assert.throws(()=>registerNotebookResponder(pi,{responseFormat:'unbounded'}),/Invalid notebook response format/);
});

test('no autostart; fresh registry/model only; shutdown and disposal are idempotent',async()=>{
  const f=setup();assert.equal(f.entries.length,0);
  await f.emit('model_select',context('before'),{model:{id:'before'}});
  assert.equal(f.entries.length,0);
  const ctx=context('first');await f.emit('session_start',ctx);
  assert.deepEqual(f.entries[0].options,{model:ctx.model,modelRegistry:ctx.modelRegistry,systemPrompt:'FIXED PROMPT',responseFormat:'semantic-v1'});
  assert.equal(f.statuses.at(-1),'ready');
  await f.emit('session_shutdown');await f.emit('session_shutdown');
  assert(f.entries[0].closed);assert(f.entries[0].cancelled);
  await f.registration.close();await f.registration.close();assert.equal(f.handlers.size,0);
});
test('model change uses event model with fresh registry and closes old host first',async()=>{
  const f=setup();await f.emit('session_start',context('first'));
  const ctx=context('next'),selected={id:'selected'};
  await f.emit('model_select',ctx,{model:selected});
  assert(f.entries[0].closed);assert.equal(f.entries[1].options.model,selected);
  assert.equal(f.entries[1].options.modelRegistry,ctx.modelRegistry);assert.equal(f.maxActive(),1);
  await f.registration.close();
});
test('shutdown during pending listen cancels immediately and never reports ready',async()=>{
  const bindGate=deferred(),f=setup({bindGate});
  const start=f.emit('session_start',context('first'));await tick();
  const stop=f.emit('session_shutdown');assert(f.entries[0].cancelled);
  bindGate.resolve();await start;await stop;
  assert(f.entries[0].closed);assert(!f.statuses.includes('ready'));
  await f.registration.close();
});
test('rapid replacement drops stale contexts rather than starting intermediate listeners',async()=>{
  const bindGate=deferred(),f=setup({bindGate});
  const first=f.emit('session_start',context('first'));await tick();
  const intermediate=f.emit('session_start',context('intermediate'));
  const last=f.emit('session_start',context('last'));
  bindGate.resolve();await Promise.all([first,intermediate,last]);
  assert.deepEqual(f.entries.map(e=>e.options.model.id),['first','last']);
  assert(f.entries[0].closed);assert.equal(f.maxActive(),1);
  await f.registration.close();
});
test('replacement waits for an abort-ignoring provider to actually finish',async()=>{
  const drainGate=deferred(),f=setup({drainGate});
  await f.emit('session_start',context('first'));
  const next=f.emit('session_start',context('next'));await tick();
  assert(f.entries[0].cancelled);assert.equal(f.entries.length,1);
  drainGate.resolve();await next;assert.equal(f.entries.length,2);
  await f.registration.close();
});
test('unavailable runtime or occupied endpoint is sanitized, without changing chat resources',async()=>{
  for(const bindError of [false,true]){
    const f=setup({bindError});await f.emit('session_start',bindError?context('first'):{});
    assert.deepEqual(f.statuses,['unavailable']);
    if(bindError)assert(f.entries[0].cancelled);
    await f.registration.close();
  }
});
test('actual lifecycle/core/socket rebind across models, with no external model call',async()=>{
  const directory=fs.mkdtempSync(path.join(process.cwd(),'.pi-life-'));fs.chmodSync(directory,0o700);
  const socketPath=path.join(directory,'s'),hooks=new Map(),calls=[];
  const model=id=>({id,provider:'openai-codex',input:['image','text']});
  const modelRegistry={isUsingOAuth:()=>true,streamSimple(selected,context){
    calls.push([selected,context]);
    return {async *[Symbol.asyncIterator](){},result:async()=>({role:'assistant',provider:selected.provider,
      model:selected.id,stopReason:'stop',content:[{type:'text',text:'{"v":1,"mode":"answer","text":"Read the image."}'}]})};
  }};
  const lifecycle=registerNotebookResponder({on(name,fn){hooks.set(name,fn);return ()=>hooks.delete(name);}},
    {socketPath,systemPrompt:'ONLY THIS PROMPT'});
  async function request(){
    return new Promise((resolve,reject)=>{
      const client=net.createConnection(socketPath,()=>client.write(JSON.stringify({
        request_id:'notebook-'+'b'.repeat(32),context:'question',deadline_ms:500,image:{mime_type:'image/png',
        data:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG9kAAAAASUVORK5CYII='}})+'\n'));
      let data='';client.on('data',chunk=>data+=chunk);client.on('error',reject);
      client.on('end',()=>{try{resolve(JSON.parse(data));}catch(error){reject(error);}});
    });
  }
  try{
    hooks.get('session_start')({}, {model:model('first'),modelRegistry});await lifecycle.settled();
    assert.equal((await request()).metrics.model,'first');
    hooks.get('model_select')({model:model('second')},{model:model('first'),modelRegistry});await lifecycle.settled();
    assert.equal((await request()).metrics.model,'second');
    assert.equal(calls.length,2);
    assert(calls.every(([,ctx])=>ctx.messages.length===1 && ctx.tools.length===0 && ctx.systemPrompt==='ONLY THIS PROMPT'));
    hooks.get('session_shutdown')();await lifecycle.settled();assert.equal(fs.existsSync(socketPath),false);
  }finally{await lifecycle.close();fs.rmSync(directory,{recursive:true});}
});
