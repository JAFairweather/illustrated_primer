import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import {serveNotebookSocket,MAX_WIRE} from './notebook_pi_socket.mjs';
import {createNotebookResponder} from './notebook_pi_responder.mjs';

const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG9kAAAAASUVORK5CYII=';
const req=()=>({request_id:'notebook-'+'a'.repeat(32),image:{mime_type:'image/png',data:png},context:'question',deadline_ms:500});
function exchange(endpoint,raw){
  return new Promise((resolve,reject)=>{
    const client=net.createConnection(endpoint,()=>client.write(raw));
    let reply='';client.on('data',data=>reply+=data);client.on('error',reject);
    client.on('end',()=>{try{resolve(JSON.parse(reply));}catch(e){reject(e);}});
  });
}
async function fixture(fn,responder){
  const dir=fs.mkdtempSync(path.join(process.cwd(),'.pi-test-'));
  fs.chmodSync(dir,0o700);
  const endpoint=path.join(dir,'s');let host;
  try {host=await serveNotebookSocket({socketPath:endpoint,responder});await fn(endpoint,host,dir);}
  finally {await host?.close();fs.rmSync(dir,{recursive:true});}
}
test('real Unix framing through isolated model core, one response, private socket',async()=>{
  let context;
  const model={provider:'openai-codex',id:'configured',input:['image']};
  const responder=createNotebookResponder({model,systemPrompt:'fixed',modelRegistry:{isUsingOAuth:()=>true,
    streamSimple(_model,ctx){context=ctx;return {async *[Symbol.asyncIterator](){},result:async()=>({
      role:'assistant',provider:model.provider,model:model.id,stopReason:'stop',
      content:[{type:'text',text:'{"v":1,"mode":"answer","text":"Understood."}'}]})};}}});
  await fixture(async endpoint=>{
    assert.equal(fs.lstatSync(endpoint).mode&0o777,0o600);
    const response=await exchange(endpoint,JSON.stringify(req())+'\n');
    assert.equal(response.request_id,req().request_id);assert.equal(response.response_format,'semantic-v1');
    assert.deepEqual(context.tools,[]);assert.equal(context.messages[0].content[1].data,png);
    assert.equal((await exchange(endpoint,JSON.stringify({...req(),model:'override'})+'\n')).error,'invalid_request');
  },responder);
});
test('malformed, extra frames, invalid UTF8 and oversized input never invoke model',async()=>{
  let calls=0;const responder={close(){},async respond(){calls++;return {};}};
  await fixture(async endpoint=>{
    for(const raw of ['no json\n','{}\n{}\n',Buffer.from([255,10])])assert.equal((await exchange(endpoint,raw)).error,'invalid_request');
    const response=await exchange(endpoint,'x'.repeat(MAX_WIRE+1)+'\n');assert.equal(response.error,'request_too_large');
    assert.equal(calls,0);
  },responder);
});
test('disconnect and shutdown cancel only that connection; shutdown is idempotent',async()=>{
  let start,abort,closed=0;
  const begun=new Promise(resolve=>start=resolve),aborted=new Promise(resolve=>abort=resolve);
  const responder={close(){closed++;},async respond(_request,{signal}){
    signal.addEventListener('abort',abort,{once:true});start();return new Promise(()=>{});
  }};
  await fixture(async(endpoint,host)=>{
    const client=net.createConnection(endpoint,()=>client.write(JSON.stringify(req())+'\n'));
    await begun;client.destroy();await aborted;
    await host.close();await host.close();assert.equal(closed,1);
  },responder);
});
test('existing files and nonprivate/symlink parents are refused without overwrite',async()=>{
  const dir=fs.mkdtempSync(path.join(process.cwd(),'.pi-test-'));fs.chmodSync(dir,0o700);
  const responder={close(){},respond(){}};
  try {
    const endpoint=path.join(dir,'s');fs.writeFileSync(endpoint,'preserve');
    await assert.rejects(serveNotebookSocket({socketPath:endpoint,responder}),/already exists/);
    assert.equal(fs.readFileSync(endpoint,'utf8'),'preserve');
    const sub=path.join(dir,'sub');fs.mkdirSync(sub,{mode:0o755});fs.chmodSync(sub,0o755);
    await assert.rejects(serveNotebookSocket({socketPath:path.join(sub,'s'),responder}),/owner-only/);
    const link=path.join(dir,'link');fs.symlinkSync(sub,link);
    await assert.rejects(serveNotebookSocket({socketPath:path.join(link,'s'),responder}));
  } finally {fs.rmSync(dir,{recursive:true});}
});
