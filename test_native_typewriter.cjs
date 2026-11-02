// Execute the actual QMD functions with delayed native insertion/cursor updates.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'xochitl/herdRespond.qmd'),'utf8');
function definition(name) {
  const start=source.indexOf(`function ${name}(`);
  const ends=['\n\t\t\t\tfunction ','\n\t\t\t\tproperty ','\n\t\t\t\tTimer {']
    .map(t=>source.indexOf(t,start+1)).filter(i=>i>=0);
  return source.slice(start,Math.min(...ends));
}
function setup(text='This is 2/3.\n', gap=false, nativeCursor=false, options={}) {
  const original='James’s earlier note.\n', writes=[], errors=[], queue=[];
  let buffer=original,index=buffer.length,pending=null,cursor=null,done=0,now=0,active=false,moved=false;
  const job={page:'p'}, editor={working:false,hasTextSelection:false,selectionItemCount:0,
    get rootDocumentLength(){return buffer.length;},get textCursorIndex(){return index;},
    textCursorPosition:{x:20,y:300},setCursorIndex(i){cursor=i;},
    replaceText(t){assert.equal(pending,null);writes.push(t);pending=t;}};
  const ctx=vm.createContext({root:{sceneController:editor,inSuspend:false,exitTextMode(){}},
    navigator:{herdJob:job,herdState:'writing',herdFail(s,r){errors.push(r.error);}},
    herdTyping:null,herdMine:true,herdPage:'p',herdContextSurface:'s',herdContextInk:10,herdContextRevision:3,
    sceneView:{isLoading:false,penClose:false,strokeHandler:{timeSincePenUp(){return 2000;}},
      sceneToView(p){return p;},height:1872,tileManager:{moveViewBy(){}}},
    herdTypingTimer:{restart(){active=true;},stop(){active=false;}},
    herdLater(f){queue.push(f);},herdTextDone(){done++;},SceneController:{MoveAnchor:0},
    SceneParticipant:{RequestedByInputMethod:2},Date:{now(){return now;}},Qt:{point(x,y){return{x,y};}}});
  vm.runInContext(['herdPenNear','herdPenHold','herdTypingUnits','herdStartTyping','herdStopTyping','herdTypingCompleted','herdTypingTick'].map(definition).join('\n'),ctx);
  ctx.herdStartTyping({job,nativeGap:gap,...options},text);
  let first=true,ticks=0;
  function tick(apply=true, elapsed=40) {
    now+=elapsed;ticks++;
    if(apply && pending!==null){
      const insert=(gap&&first?'\n\n':'')+pending;
      if(nativeCursor){
        buffer=buffer.slice(0,index)+insert+buffer.slice(index);
        // replaceText's cursor=0 leaves the cursor before its inserted unit,
        // but materialized preliminary newlines shift that starting index.
        index+=insert.length-pending.length;
      } else buffer+=insert;
      pending=null;first=false;
    }
    if(apply && cursor!==null){index=cursor;cursor=null;}
    if(moved)index=0;
    ctx.herdTypingTick();
  }
  function flush(){queue.splice(0).forEach(f=>f());}
  function finish(defer=false){while(active&&ticks<10000)tick();if(!defer)flush();assert(ticks<10000);}
  return {ctx,editor,writes,errors,tick,finish,flush,original,get buffer(){return buffer;},
    get done(){return done;},get active(){return active;},changeText(){buffer+='unexpected';},
    timeout(){now=91000;},moveCursor(){moved=true;}};
}
for(const gap of [false,true]) {
  const s=setup('Hello, café!\n',gap); s.tick();
  assert.equal(s.writes.join(''),'H','only first character, not complete caption');
  s.tick(false);assert.equal(s.writes.join(''),'H','wait for asynchronous text');
  s.finish();assert.deepEqual(s.errors,[]);
  assert.equal(s.buffer,s.original+(gap?'\n\n':'')+'Hello, café!\n');assert.equal(s.done,1);
}
{ // A pen near the page pauses the typing; it resumes when the pen has been away 1.5 s.
  const s=setup();s.tick();s.tick();const count=s.writes.length;
  s.ctx.sceneView.penClose=true;for(let i=0;i<50;i++)s.tick();
  assert.equal(s.writes.length,count,'nothing typed while the pen is near');assert.deepEqual(s.errors,[]);
  s.ctx.sceneView.penClose=false;s.finish();assert.deepEqual(s.errors,[]);assert.equal(s.done,1);
  assert.equal(s.buffer,s.original+'This is 2/3.\n');
  const held=setup();held.tick();held.tick();const n=held.writes.length;
  held.ctx.sceneView.penClose=true;held.finish();
  assert.equal(held.writes.length,n);assert.equal(held.errors.length,1,'a pen left near for a minute holds the reply');
}
for(const change of ['page','job','surface','ink','suspend','selection','state','controller','text','timeout']) {
  const s=setup();s.tick();s.tick();
  const count=s.writes.length;
  if(change==='page')s.ctx.herdPage='other';
  if(change==='job')s.ctx.navigator.herdJob={page:'p'};
  if(change==='surface')s.ctx.herdContextSurface='other';
  if(change==='ink')s.ctx.herdContextInk++;
  if(change==='pen')s.ctx.sceneView.penClose=true;
  if(change==='suspend')s.ctx.root.inSuspend=true;
  if(change==='selection')s.editor.hasTextSelection=true;
  if(change==='state')s.ctx.navigator.herdState='failed';
  if(change==='controller')s.ctx.root.sceneController={};
  if(change==='text')s.changeText();
  if(change==='timeout')s.timeout();
  s.finish();assert.equal(s.writes.length,count,change);assert.equal(s.errors.length,1,change);
  assert.equal(s.done,0);assert(s.buffer.startsWith(s.original));
  s.ctx.herdTypingTick();assert.equal(s.writes.length,count,'no automatic replay');
}
const unicode=setup();
for(const value of ['e\u0301','👩🏽‍🔬','🇺🇸','𝑥']) {
  assert.deepEqual(Array.from(unicode.ctx.herdTypingUnits(value)),[value]);
}
assert.deepEqual(Array.from(unicode.ctx.herdTypingUnits('नमस्ते')),['नमस्ते']);
assert.throws(()=>unicode.ctx.herdTypingUnits('x'.repeat(2001)));
const cursor=setup();cursor.tick();cursor.tick();cursor.tick();cursor.tick();cursor.moveCursor();
cursor.finish();assert.equal(cursor.errors.length,1);assert.equal(cursor.done,0);
console.log('Native typewriter: ordered native appends, delayed cursor, Unicode, virtual gaps, cancellation and no replay pass.');

// A realistic slow native editor can cross the former fixed 90s deadline
// without being stuck. The text is still bounded; no whole-block fallback.
const long=setup('a'.repeat(1999)+'\n');
for(let i=0;i<4100 && long.active;i++) long.tick(true,100);
long.finish();
assert.deepEqual(long.errors,[]);
assert.equal(long.buffer,long.original+'a'.repeat(1999)+'\n');
assert.equal(long.done,1);
const stalled=setup();stalled.tick();
for(let i=0;i<101&&stalled.active;i++)stalled.tick(false,100);
assert.equal(stalled.active,false);
assert.equal(stalled.writes.length,1);
assert.match(stalled.errors[0],/Caption incomplete: text stopped advancing/);
assert.equal(stalled.done,0);
console.log('Typewriter timing: >90s advancing captions finish; unacknowledged insertion stops after 10s without replay.');

// Firmware SceneView.isLoading includes controller.working and pending tiles.
// A normal append can make it true; pause, without replaying or dropping guards.
for(const busy of ['editor','tiles']) {
  const s=setup();s.tick();const count=s.writes.length;
  s.ctx.sceneView.isLoading=true;s.editor.working=busy==='editor';
  for(let i=0;i<5;i++)s.tick();
  assert.equal(s.writes.length,count);assert.deepEqual(s.errors,[]);
  s.ctx.sceneView.isLoading=false;s.editor.working=false;s.finish();
  assert.equal(s.done,1);assert.equal(s.buffer,s.original+'This is 2/3.\n');
}
const changedWhileLoading=setup();changedWhileLoading.tick();
changedWhileLoading.ctx.sceneView.isLoading=true;changedWhileLoading.ctx.herdPage='other';
changedWhileLoading.tick();assert.equal(changedWhileLoading.errors.length,1);
assert.equal(changedWhileLoading.writes.length,1);
const stuckLoading=setup();stuckLoading.tick();stuckLoading.ctx.sceneView.isLoading=true;
for(let i=0;i<101&&stuckLoading.active;i++)stuckLoading.tick(false,100);
assert.equal(stuckLoading.writes.length,1);assert.equal(stuckLoading.errors.length,1);
assert.match(stuckLoading.errors[0],/text stopped advancing/);
console.log('Typewriter native reflow: waits for editor/tiles, retains page guards and 10s no-progress bound.');

// Physical editor leaves its input-method cursor before the first inserted
// character. A gap moves that position. Explicit advancement must retain order.
for(const gap of [false,true]) {
  const s=setup('Start with equal-sized wholes.\n',gap,true);
  s.finish();assert.deepEqual(s.errors,[]);assert.equal(s.done,1);
  assert.equal(s.buffer,s.original+(gap?'\n\n':'')+'Start with equal-sized wholes.\n');
  assert.equal(s.writes.join(''),'Start with equal-sized wholes.\n');
}
const changedTerminal=setup('Caption\n',true,true);changedTerminal.tick();changedTerminal.moveCursor();
changedTerminal.finish();assert.equal(changedTerminal.done,0);assert.equal(changedTerminal.errors.length,1);
assert.equal(changedTerminal.writes.length,1,'moved cursor cannot be adopted as new insertion location');
console.log('Typewriter native cursor: virtual-gap start advances after character; unexpected cursor still holds.');

// The same native writer can hand a settled opening back to a stream owner,
// without claiming final lesson success or re-emitting the opening on retry.
for(const gap of [false,true]) {
  const records=[], prefix='\nAgent Pi Dog:\n', body='  Equal parts make comparison possible.\n';
  const s=setup(prefix+body,gap,true,{prefixLength:prefix.length,onTextSettled(r){records.push(r);}});
  s.tick();s.tick(false);
  assert.equal(s.ctx.herdTyping.firstAnswerAt,null,'unacknowledged label is not an answer');
  while(s.ctx.herdTyping && s.ctx.herdTyping.acknowledged<=prefix.length+2) {
    assert.equal(s.ctx.herdTyping.firstAnswerAt,null,'label and whitespace do not count');
    s.tick();
  }
  const first=s.ctx.herdTyping.firstAnswerAt;
  assert.equal(typeof first,'number');
  s.finish();assert.deepEqual(s.errors,[]);assert.equal(s.done,0);
  assert.equal(records.length,1);assert.equal(records[0].firstAnswerAt,first);
  assert.equal(records[0].start,s.original.length+(gap?2:0));
  assert.equal(records[0].end,s.buffer.length);assert.equal(records[0].gap,gap?2:0);
  assert.equal(records[0].characters,(prefix+body).length);
  assert(records[0].completedAt>=first);s.flush();assert.equal(records.length,1);
  assert.equal(s.buffer,s.original+(gap?'\n\n':'')+prefix+body);
}
for(const change of ['page','job','surface','ink','revision','length','cursor','pen','suspend','busy','state']) {
  const records=[],s=setup('A streamed opening.',false,true,{onTextSettled(r){records.push(r);}});
  s.finish(true);const count=s.writes.length;
  if(change==='page')s.ctx.herdPage='other';
  if(change==='job')s.ctx.navigator.herdJob={page:'p'};
  if(change==='surface')s.ctx.herdContextSurface='other';
  if(change==='ink')s.ctx.herdContextInk++;
  if(change==='revision')s.ctx.herdContextRevision++;
  if(change==='length')s.changeText();
  if(change==='cursor'){s.moveCursor();s.tick();}
  if(change==='pen')s.ctx.sceneView.penClose=true;
  if(change==='suspend')s.ctx.root.inSuspend=true;
  if(change==='busy')s.editor.working=true;
  if(change==='state')s.ctx.navigator.herdState='failed';
  s.flush();assert.equal(records.length,0,change);
  if(change==='pen'){ // the acknowledgement waits for the pen to leave, then settles
    assert.deepEqual(s.errors,[],change);s.ctx.sceneView.penClose=false;s.flush();
    assert.equal(records.length,1,change);assert.deepEqual(s.errors,[],change);continue;
  }
  assert.equal(s.errors.length,1,change);
  assert.equal(s.writes.length,count,change);assert.equal(s.done,0,change);
}
let calls=0;
const failedCallback=setup('Keep this partial answer.',false,true,{onTextSettled(){calls++;throw Error('ack failed');}});
const completedState=failedCallback.ctx.herdTyping;
failedCallback.finish();failedCallback.flush();failedCallback.ctx.herdTypingCompleted(completedState);assert.equal(calls,1);
assert.equal(failedCallback.errors.length,1);assert.equal(failedCallback.done,0);
assert.equal(failedCallback.buffer,failedCallback.original+'Keep this partial answer.');
for(const prefixLength of [-1,1.5,NaN,Infinity,true,'1',200]) {
  assert.throws(()=>setup('Bounded text.',false,true,{prefixLength,onTextSettled(){}}),/exact end-of-document/);
}
const onlyLabel=[];
setup('Agent Pi Dog:\n',false,true,{prefixLength:14,onTextSettled(r){onlyLabel.push(r);}}).finish();
assert.equal(onlyLabel[0].firstAnswerAt,null,'label-only insertion cannot satisfy answer latency');
const displaced=setup();displaced.ctx.herdStopTyping('test setup stop');
displaced.moveCursor();displaced.tick();
assert.throws(()=>displaced.ctx.herdStartTyping({job:displaced.ctx.navigator.herdJob,onTextSettled(){}},'Do not overwrite.'),/exact end-of-document/);
console.log('Native stream handoff: exact settled append range, label-excluded timing, queued-edit refusal and no completion replay pass.');
