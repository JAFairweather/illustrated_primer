// Exercise the actual QMD measurement/cleanup functions, never a substitute.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'xochitl/herdRespond.qmd'),'utf8');
const start = source.indexOf('function herdSavedLengthPending(');
const end = source.indexOf('\n\t\t\t\tTimer { id: herdLayoutCaptureTimer;',start);
const command = {request:'request',phase:'after',doc:'doc',page:'page',surface:'surface',
  content_revision:4,ink_revision:2,sha256:'a'.repeat(64),indices:[0]};
const routeExpression = source.match(/property: "handler"\s+value: ([^\n]+)/)[1];
assert.ok(source.includes('target: herdButton.herdPenSurface'));
assert.ok(!source.includes('target: herdButton.herdLayoutCapture ?'));
function harness(query=command) {
  const replies=[],failures=[];
  const handler={lineTool:9,timeSincePenUp:()=>2000};
  const pen={children:[],toString:()=> 'PenInputSurface'};
  const focus={children:[],activeFocus:true,forceActiveFocus(){this.activeFocus=true;}};
  const view={textModeEnabled:true};
  const controller={hasRootDocument:true,rootDocumentLength:23,textCursorIndex:17,working:false,
    hasTextSelection:false,selectionItemCount:0,textLineHeight:32,textCursorPosition:{x:-464,y:267.59375},
    focusRootDocument(){},setCursorIndex(i){assert(i >= 0);this.textCursorIndex=i;},
    setCursorVisible(visible){this.cursorVisible=visible;},
    createRootDocument(){throw Error('No document creation in capture');},
    replaceText(){throw Error('No text edits in capture');}};
  const scene={children:[pen,focus],document:{id:'doc'},sceneView:view,strokeHandler:handler,
    adjustViewActive:false,penClose:false,isLoading:false};
  const root={sceneController:controller,enabled:true,inSuspend:false};
  const context={herdLayoutCapture:null,herdMine:true,herdPage:'page',herdContextSurface:'surface',
    herdContextRevision:4,herdContextInk:2,herdInk:null,herdProbeJob:null,herdPenSurface:pen,root,sceneView:scene,
    herdInkView:()=>[1,0,0,1,-702,508],Line:{SelectionTool:8},SceneController:{MoveAnchor:0},
    herdLayoutCaptureTimer:{restart(){},stop(){}},Qt:{point:(x,y)=>({x,y})},console:{warn(){}},
    navigator:{herdJob:{request:'request'},herdUuid:x=>x,herdFail:(st,r)=>failures.push(r.error)}};
  let busy=false,penBlocked=false,wrongRoute=false;
  Object.defineProperty(pen,'handler',{get:()=>wrongRoute && !busy && !penBlocked ? {} : vm.runInNewContext(routeExpression,{sceneView:scene,herdButton:context}),
    set:()=>{wrongRoute=true;}});
  Object.defineProperty(context,'herdLayoutPenBlocked',{get:()=>penBlocked,set:x=>{penBlocked=x;}});
  Object.defineProperty(context,'herdPasteBusy',{get:()=>busy,set:x=>{
    busy=x;root.enabled=!x;scene.adjustViewActive=x;handler.lineTool=x?8:9;
  }});
  const ctx=vm.createContext(context);vm.runInContext(source.slice(start,end),ctx);
  return {ctx,controller,scene,root,focus,pen,handler,replies,failures,
    begin:()=>ctx.herdMeasureLayout(query,r=>replies.push(r)),tick:()=>ctx.herdLayoutCaptureTick()};
}
let h=harness();h.begin();assert.equal(h.scene.sceneView.textModeEnabled,false);
assert.equal(h.pen.handler,null);
h.tick();assert.equal(h.controller.textCursorIndex,0);
h.tick();assert.equal(h.controller.textCursorIndex,17);
h.tick();assert.equal(h.replies.length,0,'restore UI before callback');
assert.equal(h.pen.handler,null,'pen remains blocked across cleanup event-loop boundary');
assert.equal(h.root.enabled,false,'UI remains blocked while cursor restoration settles');
h.tick();assert.equal(h.replies.length,1);assert.equal(h.failures.length,0);
assert.deepEqual(Array.from(h.replies[0].first),[-464,267.59375,32,23]);
assert.equal(h.replies[0].command,command);
assert.equal(h.pen.handler,h.handler);assert.equal(h.root.enabled,true);
assert.equal(h.scene.sceneView.textModeEnabled,true);assert.equal(h.focus.activeFocus,true);

// Reopened pen-mode page: acquire the EXISTING root, wait for native focus,
// measure, and leave a hidden cursor at 0. No editor/keyboard entry or -1
// setCursorIndex call. This mock tests lifecycle, not firmware behavior.
for (const asyncFocus of [false,true]) {
  h=harness({...command,indices:[1]});h.controller.textCursorIndex=-1;
  h.scene.sceneView.textModeEnabled=false;
  let focuses=0;
  h.controller.focusRootDocument=function(point){
    assert(Number.isNaN(point.x) && Number.isNaN(point.y));focuses++;this.working=asyncFocus;
  };
  h.begin();h.tick();
  assert.equal(h.ctx.herdLayoutCapture.phase,'focusing');
  assert.equal(h.controller.textCursorIndex,-1);
  if(asyncFocus){h.tick();h.tick();assert.equal(h.controller.textCursorIndex,-1);}
  h.controller.working=false;h.tick();assert.equal(h.controller.textCursorIndex,1);
  for(let i=0;i<3;i++)h.tick();
  assert.equal(focuses,1);assert.equal(h.failures.length,0);assert.equal(h.replies.length,1);
  assert.equal(h.controller.textCursorIndex,0);assert.equal(h.controller.cursorVisible,false);
  assert.equal(h.scene.sceneView.textModeEnabled,false);assert.equal(h.pen.handler,h.handler);
}
for(const value of [undefined,null,'0',NaN,Infinity,-2,1.5,24]) {
  h=harness();h.controller.textCursorIndex=value;h.scene.sceneView.textModeEnabled=false;
  assert.throws(h.begin,/unavailable: cursor/);assert.equal(h.ctx.herdPasteBusy,false);
}
// Unknown visibility API and inactive text-editing state remain unsupported.
h=harness();h.controller.textCursorIndex=-1;h.scene.sceneView.textModeEnabled=false;
h.controller.setCursorVisible=undefined;assert.throws(h.begin,/unavailable: cursor/);
for(const change of ['page','ink','revision','viewport','timeout']) {
  h=harness();h.controller.textCursorIndex=-1;h.scene.sceneView.textModeEnabled=false;
  h.begin();h.tick();h.controller.working=true;
  if(change==='page')h.ctx.herdPage='other';
  if(change==='ink')h.ctx.herdContextInk++;
  if(change==='revision')h.ctx.herdContextRevision++;
  if(change==='viewport')h.ctx.herdInkView=()=>[1,0,0,1,-702,999];
  for(let i=0;i<40;i++)h.tick();
  assert.equal(h.replies.length,0,change);assert.equal(h.failures.length,1,change);
  assert.equal(h.scene.sceneView.textModeEnabled,false);
}

// This precheck may only defer an impossible after-measurement. It must not
// weaken before-capture validation or accept a malformed command as evidence.
for (const [query,pending] of [
  [{...command,anchors:[],length:20},true],
  [{...command,anchors:[],length:23},false],
  [{...command,anchors:[],length:25},true],
  [{...command,phase:'before',anchors:[],length:20},false],
  [{...command,length:20},true],
  [{...command,length:23},false],
  [command,false],
  [{...command,anchors:[],length:0},false],
  [{...command,anchors:[],length:NaN},false],
  [{...command,anchors:[],length:'20'},false],
  [null,false],
]) assert.equal(h.ctx.herdSavedLengthPending(query),pending);

// Run the actual finalization loop: stale length uses its existing bounded
// save poll, performs no cursor query, and never sends a completion ACK.
function saveLoop(alwaysStale=false,multiple=true,saveAtMs=null) {
  const queue=[],errors=[],calls=[];
  let polls=0,measurements=0,proofAccepted=false,elapsed=0;
  const timer={callback:null,interval:150,restart(){queue.push({fn:this.callback,delay:this.interval});}};
  const job={page:'page',path:'doc/page.rm',nativeInkUsed:true};
  const work={job,reply:{request:'request'},viewSettled:true};
  const c={rootDocumentLength:23,rootDocumentBoundingRect:{y:100,height:300},textCursorPosition:{x:0,y:400}};
  const ctx=vm.createContext({
    root:{sceneController:c,currentPage:0,exitTextMode(){}},herdMine:true,herdPage:'page',
    sceneView:{document:{id:'doc'},height:1872,sceneToView:p=>p,viewToScene:p=>p,tileManager:{moveViewBy(){}}},
    LibraryController:{setScrollPosition(){}},Qt:{point:(x,y)=>({x,y})},
    herdLayoutTimer:timer,herdStyle:()=>false,herdOrdered:()=>false,
    herdMeasureLayout(q,done){measurements++;assert.equal(q.length,23);done({command:q,samples:[]});},
    navigator:{herdJob:job,herdFail:(st,r)=>errors.push(r.error),
      herdHttp(method,route,payload,done){
        calls.push(route);
        if(route==='/notebook-ink-proof') {
          if(payload.layout){proofAccepted=true;done(200,{state:'persisted'});}
          else done(200,{state:'waiting',measure_layout:{...command,...(multiple?{anchors:[]}:{anchor:[1,1]}),length:alwaysStale||(saveAtMs===null?polls++<2:elapsed<saveAtMs)?20:23}});
        } else {
          assert.equal(route,'/native-text-done');assert(proofAccepted,'never ACK before proof');done(200,{});
        }
      }}
  });
  const helperEnd=source.indexOf('function herdFocusOwner(',start);
  const doneStart=source.indexOf('function herdTextDone(');
  const doneEnd=source.indexOf('function herdAuditView(',doneStart);
  const laterStart=source.indexOf('function herdLater(');
  vm.runInContext(source.slice(laterStart,helperEnd)+source.slice(doneStart,doneEnd),ctx);
  ctx.herdTextDone(work);
  let ticks=0;
  while(queue.length){assert(++ticks<100);const event=queue.shift();elapsed+=event.delay;event.fn();}
  return {errors,calls,measurements,proofAccepted,work,elapsed,interval:timer.interval};
}
let saved=saveLoop();assert.deepEqual(saved.errors,[]);assert.equal(saved.measurements,1);
assert.equal(saved.calls.filter(x=>x==='/notebook-ink-proof').length,4);
assert.equal(saved.calls.filter(x=>x==='/native-text-done').length,1);
assert.equal(saved.work.inkWaits,2);
saved=saveLoop(true);assert.equal(saved.measurements,0);assert.equal(saved.proofAccepted,false);
assert.equal(saved.calls.filter(x=>x==='/native-text-done').length,0);
assert.equal(saved.work.inkWaits,31);assert.match(saved.errors[0],/save not confirmed/);
assert.equal(saved.elapsed,30000,'permanent stale state stays bounded without exhausting at UI speed');
for (const multiple of [false,true]) {
  saved=saveLoop(false,multiple,12000);
  assert.deepEqual(saved.errors,[]);assert.equal(saved.measurements,1);
  assert.equal(saved.proofAccepted,true);assert.equal(saved.work.inkWaits,12);
  assert.equal(saved.elapsed,12150);assert.equal(saved.interval,150,'normal UI cadence restored after save');
}
saved=saveLoop(false,false);assert.deepEqual(saved.errors,[]);assert.equal(saved.measurements,1);
assert.equal(saved.work.inkWaits,2);assert.equal(saved.proofAccepted,true);
saved=saveLoop(true,false);assert.equal(saved.measurements,0);assert.equal(saved.proofAccepted,false);
assert.equal(saved.work.inkWaits,31);assert.match(saved.errors[0],/save not confirmed/);

// The command's exact leading-newline index is measured, not assumed zero.
h=harness({...command,indices:[1]});h.begin();h.tick();
assert.equal(h.controller.textCursorIndex,1);
for(let i=0;i<3;i++)h.tick();
assert.equal(h.replies.length,1);assert.equal(h.replies[0].command.indices[0],1);
assert.equal(h.controller.textCursorIndex,17);assert.equal(h.pen.handler,h.handler);
for(const indices of [[-1],[32],[23],[1.5],['1'],[],[0,1],[NaN]]) {
  h=harness({...command,indices});assert.throws(h.begin,/unavailable/);
  assert.equal(h.pen.handler,h.handler);assert.equal(h.root.enabled,true);
}

for(const scenario of ['page','surface','ink','revision','pen','viewport','exception','timeout','focus-loss','route-loss','surface-replaced']) {
  h=harness();h.begin();h.tick();
  if(scenario==='page')h.ctx.herdPage='other';
  if(scenario==='surface')h.ctx.herdContextSurface='other';
  if(scenario==='ink')h.ctx.herdContextInk++;
  if(scenario==='revision')h.ctx.herdContextRevision++;
  if(scenario==='pen')h.scene.penClose=true;
  if(scenario==='viewport')h.ctx.herdInkView=()=>[1,0,0,1,-702,700];
  if(scenario==='exception')h.controller.setCursorIndex=()=>{throw Error('native exception');};
  if(scenario==='timeout')h.controller.working=true;
  if(scenario==='focus-loss')h.focus.forceActiveFocus=()=>{h.focus.activeFocus=false;};
  if(scenario==='surface-replaced')h.ctx.herdPenSurface={};
  for(let i=0;i<35;i++) {
    if(scenario==='route-loss' && h.ctx.herdLayoutCapture?.phase==='cleanup')h.pen.handler=null;
    h.tick();
  }
  assert.equal(h.replies.length,0,scenario);
  assert.equal(h.failures.length,1,scenario);
  // A failed capture holds the reply, never the page: every guard is released.
  assert.equal(h.ctx.herdPasteBusy,false,scenario);
  assert.equal(h.ctx.herdLayoutPenBlocked,false,scenario);
  assert.equal(h.ctx.herdLayoutCapture,null,scenario);
}
// After a drawing, a hovering pen or James's writing hands input back and asks to measure again instead of failing.
for(const scenario of ['near','idle','ink','revision','near-and-page']) {
  h=harness();let retries=0;
  h.ctx.herdMeasureLayout(command,r=>h.replies.push(r),()=>retries++);h.tick();
  if(scenario!=='idle')h.scene.penClose=true;
  if(scenario==='idle')h.handler.timeSincePenUp=()=>400;
  if(scenario==='ink')h.ctx.herdContextInk++;
  if(scenario==='revision')h.ctx.herdContextRevision++;
  if(scenario==='near-and-page')h.ctx.herdPage='other';
  for(let i=0;i<35;i++)h.tick();
  assert.equal(h.replies.length,0,scenario);
  assert.equal(retries,scenario==='near-and-page'?0:1,scenario);
  assert.equal(h.failures.length,scenario==='near-and-page'?1:0,scenario);
  assert.equal(h.ctx.herdPasteBusy,false,scenario);
  assert.equal(h.ctx.herdLayoutPenBlocked,false,scenario);
  assert.equal(h.ctx.herdLayoutCapture,null,scenario);
  if(scenario!=='near-and-page')assert.equal(h.pen.handler,h.handler,scenario);
}
h=harness();h.focus.activeFocus=false;
assert.throws(h.begin,/unavailable/);assert.equal(h.ctx.herdPasteBusy,false);
h=harness();h.controller.hasTextSelection=true;
assert.throws(h.begin,/unavailable/);assert.equal(h.ctx.herdPasteBusy,false);
// Live13: refusal must identify its fixed precondition, without logging text,
// request IDs, cursor values or geometry. No lock/input mutation on refusal.
for(const [reason,change] of [
  ['request',h=>h.ctx.navigator.herdJob={}],
  ['controller',h=>h.root.sceneController=null],
  ['root-document',h=>h.controller.hasRootDocument=false],
  ['text-length',h=>h.controller.rootDocumentLength=NaN],
  ['working',h=>h.controller.working=true],
  ['selection',h=>h.controller.selectionItemCount=1],
  ['cursor',h=>h.controller.textCursorIndex=-1],
  ['busy',h=>h.ctx.herdProbeJob={}],
  ['focus',h=>h.focus.activeFocus=false],
  ['text-mode',h=>h.scene.sceneView.textModeEnabled=undefined],
  ['view-disabled',h=>h.root.enabled=false],
]) {
  h=harness();change(h);
  assert.throws(h.begin,new RegExp('unavailable: .*'+reason));
  assert.equal(h.ctx.herdLayoutCapture,null,reason);
  assert.equal(h.ctx.herdLayoutPenBlocked,false,reason);
  assert.equal(h.replies.length,0,reason);
}
for(const [reason,query] of [
  ['indices-shape',{...command,indices:[]}],
  ['anchors-shape',{...command,anchors:{}}],
  ['saved-length',{...command,anchors:[],length:NaN}],
  ['indices-range',{...command,indices:[-1]}],
  ['indices-order',{...command,indices:[1,1],anchors:[],length:23}],
  ['indices-saved-length',{...command,indices:[22],anchors:[],length:22}],
  ['indices-native-length',{...command,indices:[23]}],
  ['indices-range',{...command,indices:[262144,1],anchors:[],length:262144}],
  ['indices-shape',{...command,indices:[],anchors:{}}],
]) {
  h=harness(query);assert.throws(h.begin,new RegExp('unavailable: .*'+reason));
  assert.equal(h.ctx.herdLayoutCapture,null,reason);
  assert.equal(h.ctx.herdLayoutPenBlocked,false,reason);
  assert.equal(h.replies.length,0,reason);
}
// Installed firmware semantics remain active outside capture too.
h=harness();h.scene.adjustViewActive=true;assert.equal(h.pen.handler,null);
h.scene.adjustViewActive=false;assert.equal(h.pen.handler,h.handler);
h.scene.sceneView=null;assert.equal(h.pen.handler,null);
// Diagnose native lifecycle failures without weakening any existing guard.
for (const [reason,change] of [
  ['job',h=>h.ctx.navigator.herdJob={}],
  ['owner',h=>h.ctx.herdMine=false],
  ['suspended',h=>h.root.inSuspend=true],
  ['document',h=>h.scene.document.id='other'],
  ['pen-near',h=>h.scene.penClose=true],
  ['pen-idle-ms=0',h=>h.handler.timeSincePenUp=()=>0],
]) {
  h=harness();h.begin();change(h);h.tick();h.tick();
  assert.equal(h.replies.length,0,reason);
  assert.equal(h.failures.length,1,reason);
  assert.ok(h.failures[0].includes('locking: '+reason),h.failures[0]);
}
// Live08: setCursorIndex(original) temporarily makes isLoading true while
// restoring. Do not read/accept transient layout or release either input lock.
h=harness();h.begin();h.tick();h.tick();
assert.equal(h.ctx.herdLayoutCapture.phase,'restoring');
h.scene.isLoading=true;
for(let i=0;i<5;i++)h.tick();
assert.equal(h.replies.length,0);assert.equal(h.failures.length,0);
assert.equal(h.ctx.herdLayoutCapture.phase,'restoring');
assert.equal(h.pen.handler,null);assert.equal(h.root.enabled,false);
h.scene.isLoading=false;h.tick();h.tick();
assert.equal(h.replies.length,1);assert.equal(h.failures.length,0);
assert.equal(h.pen.handler,h.handler);assert.equal(h.root.enabled,true);
// Loading is not permission to ignore a page/input change or to wait forever.
for(const changed of ['page','ink','revision','surface','viewport','timeout']) {
  h=harness();h.begin();h.tick();h.tick();h.scene.isLoading=true;
  if(changed==='page')h.ctx.herdPage='other';
  if(changed==='ink')h.ctx.herdContextInk++;
  if(changed==='revision')h.ctx.herdContextRevision++;
  if(changed==='surface')h.ctx.herdContextSurface='other';
  if(changed==='viewport')h.ctx.herdInkView=()=>[1,0,0,1,-702,700];
  for(let i=0;i<35;i++)h.tick();
  assert.equal(h.replies.length,0,changed);
  assert.equal(h.failures.length,1,changed);
  if(changed==='timeout')assert.ok(h.failures[0].includes('timed out'));
}
// Populated-page capture: one exact server-issued index per tick, one input
// transaction and one final callback only after the original cursor is restored.
const multi={...command,indices:[1,21,272,375],length:376,
  anchors:[{id:[1,66],index:1},{id:[1,152],index:21},{id:[1,421],index:272},{id:[0,281474976710655],index:375}]};
function multiHarness(query=multi) {
  const h=harness(query);h.controller.rootDocumentLength=376;
  h.controller.setCursorIndex=function(i){this.textCursorIndex=i;this.textCursorPosition={x:-464+i,y:200+i};};
  return h;
}
h=multiHarness();h.begin();h.tick();
for(const index of multi.indices) {
  assert.equal(h.controller.textCursorIndex,index);
  assert.equal(h.pen.handler,null);assert.equal(h.root.enabled,false);
  h.tick();assert.equal(h.replies.length,0);
}
assert.equal(h.controller.textCursorIndex,17);
h.tick();assert.equal(h.replies.length,0);h.tick();
assert.equal(h.failures.length,0);assert.equal(h.replies.length,1);
assert.deepEqual(JSON.parse(JSON.stringify(h.replies[0].samples)),multi.indices.map(i=>[i,-464+i,200+i,32,376]));
assert.equal(h.replies[0].first,undefined);
assert.equal(h.pen.handler,h.handler);assert.equal(h.scene.sceneView.textModeEnabled,true);

// The index may update before its metrics. While native working is true, no
// stale position can enter the sample vector. This models the readiness flag;
// its real-device behavior still needs the isolated foreground test.
h=multiHarness();
h.controller.setCursorIndex=function(i){this.textCursorIndex=i;this.working=true;};
h.begin();h.tick();
for(const index of multi.indices) {
  const count=h.ctx.herdLayoutCapture.samples.length;
  h.controller.textCursorPosition={x:999,y:999};
  h.tick();h.tick();
  assert.equal(h.ctx.herdLayoutCapture.samples.length,count);
  assert.equal(h.replies.length,0);
  h.controller.textCursorPosition={x:-464+index,y:200+index};
  h.controller.working=false;h.tick();
}
assert.equal(h.controller.textCursorIndex,17);
h.controller.working=false;h.tick();h.tick();
assert.deepEqual(JSON.parse(JSON.stringify(h.replies[0].samples)),multi.indices.map(i=>[i,-464+i,200+i,32,376]));
assert.equal(h.failures.length,0);assert.equal(h.pen.handler,h.handler);

// Invalid query sets never lock input or silently truncate requested anchors.
for(const indices of [[],[1,1],[21,1],[-1],[376],[262144],[1.2],['1'],[NaN],Array.from({length:65},(_,i)=>i)]) {
  h=multiHarness({...multi,indices});assert.throws(h.begin,/unavailable/);
  assert.equal(h.pen.handler,h.handler);assert.equal(h.root.enabled,true);
}
for(const length of [0,NaN,Infinity,3.5,'376',375,262145]) {
  h=multiHarness({...multi,length});assert.throws(h.begin,/unavailable/);
}
// Any change between samples discards the complete vector, never a partial
// callback. Owner/routing failures continue to retain the existing input hold.
for(const scenario of ['page','surface','ink','revision','viewport','pen','length','line-height','exception','timeout']) {
  h=multiHarness();h.begin();h.tick();h.tick();
  assert.equal(h.ctx.herdLayoutCapture.samples.length,1);
  if(scenario==='page')h.ctx.herdPage='changed';
  if(scenario==='surface')h.ctx.herdContextSurface='changed';
  if(scenario==='ink')h.ctx.herdContextInk++;
  if(scenario==='revision')h.ctx.herdContextRevision++;
  if(scenario==='viewport')h.ctx.herdInkView=()=>[1,0,0,1,-702,999];
  if(scenario==='pen')h.scene.penClose=true;
  if(scenario==='length')h.controller.rootDocumentLength++;
  if(scenario==='line-height')h.controller.textLineHeight=NaN;
  if(scenario==='exception')h.controller.setCursorIndex=()=>{throw Error('native exception');};
  if(scenario==='timeout')h.controller.working=true;
  for(let i=0;i<40;i++)h.tick();
  assert.equal(h.replies.length,0,scenario);assert.equal(h.failures.length,1,scenario);
}
// More than 30 samples can complete within the explicit 30+N tick budget.
const many={...multi,indices:Array.from({length:64},(_,i)=>i)};
h=multiHarness(many);h.begin();
for(let i=0;i<67;i++)h.tick();
assert.equal(h.replies.length,1);assert.equal(h.replies[0].samples.length,64);
assert.equal(h.failures.length,0);assert.equal(h.pen.handler,h.handler);
h=multiHarness(many);h.begin();h.controller.working=true;
for(let i=0;i<94;i++)h.tick();
assert.equal(h.failures.length,0);h.tick();h.tick();
assert.equal(h.failures.length,1);assert.equal(h.replies.length,0);
console.log('Native layout capture: legacy/multiple samples, exact query budget, full cursor/focus/input restoration and intermediate failure holds passed.');
