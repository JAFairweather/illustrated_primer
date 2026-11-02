const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(__dirname+'/xochitl/herdRespond.qmd','utf8');
const begin = source.indexOf('function herdSubmitLayout('), end = source.indexOf('function herdLater(',begin);
assert(source.includes('herdMeasureLayout(r.measure_layout, function(result) { herdSubmitLayout(imported, frozen, result) })'));
function setup() {
  let now=0, ack;
  const events=[], submitted=[], failed=[], queue=[];
  const job={doc:'doc',page:'page'}, frozen={job,surface:'surface',revision:4,ink:2};
  const result={command:{sha256:'original',request:'r'},samples:[[1,2,3,4]]};
  const handler={timeSincePenUp:()=>2000};
  const ctx=vm.createContext({Date:{now:()=>now},console:{warn(){}}, herdMine:true,herdPage:'page',
    herdContextSurface:'surface',herdContextRevision:4,herdContextInk:2,herdContextBusy:false,
    herdPasteBusy:false,herdLayoutPenBlocked:false,herdLayoutCapture:null,herdPenSurface:{handler},
    root:{inSuspend:false,enabled:true,sceneController:{working:false}},
    sceneView:{document:{id:'doc'},isLoading:false,adjustViewActive:false,penClose:false,strokeHandler:handler},
    navigator:{herdJob:job,herdUuid:x=>x,herdFail:(st,r)=>failed.push(r.error)},
    herdLater(fn){queue.push(fn);},
    herdReportContext(fn){events.push('report');ack=fn;},
    herdText(imported, f, r){events.push('submit');assert.equal(f,frozen);assert.equal(r,result);submitted.push(r);}
  });
  // Use the actual unchanged frozen-page guard, not a permissive stub.
  const currentStart=source.indexOf('function herdLessonCurrent(');
  vm.runInContext(source.slice(currentStart,source.indexOf('function herdStopLessonImport(',currentStart))+source.slice(begin,end),ctx);
  return {ctx,events,submitted,failed,frozen,result,begin:()=>ctx.herdSubmitLayout(null,frozen,result),
    ack:ok=>ack(ok),tick(ms=150){now+=ms;queue.shift()?.();},drain(){while(queue.length)this.tick();}};
}
let h=setup();h.begin();assert.deepEqual(h.events,['report']);assert.equal(h.submitted.length,0);
h.tick();assert.deepEqual(h.events,['report'],'no duplicate report while awaiting HTTP');
h.ack(true);h.ack(true);h.drain();assert.deepEqual(h.events,['report','submit']);
assert.deepEqual(h.failed,[]);
for(const waiting of ['loading','working','busy']) {
  h=setup();
  if(waiting==='loading')h.ctx.sceneView.isLoading=true;
  if(waiting==='working')h.ctx.root.sceneController.working=true;
  if(waiting==='busy')h.ctx.herdContextBusy=true;
  h.begin();h.tick();assert.deepEqual(h.events,[]);
  h.ctx.sceneView.isLoading=false;h.ctx.root.sceneController.working=false;h.ctx.herdContextBusy=false;
  h.tick();assert.deepEqual(h.events,['report']);h.ack(true);h.drain();assert.equal(h.submitted.length,1);
}
for(const change of ['page','doc','surface','revision','ink','job','suspend','owner']) {
  h=setup();h.begin();
  if(change==='page')h.ctx.herdPage='another';
  if(change==='doc')h.ctx.sceneView.document.id='another';
  if(change==='surface')h.ctx.herdContextSurface='another';
  if(change==='revision')h.ctx.herdContextRevision++;
  if(change==='ink')h.ctx.herdContextInk++;
  if(change==='job')h.ctx.navigator.herdJob={};
  if(change==='suspend')h.ctx.root.inSuspend=true;
  if(change==='owner')h.ctx.herdMine=false;
  h.tick();h.ack(true);h.drain();assert.equal(h.submitted.length,0,change);assert.equal(h.failed.length,1,change);
}
h=setup();h.begin();h.ack(false);h.drain();assert.equal(h.submitted.length,0);assert.equal(h.failed.length,1);
h=setup();h.begin();h.tick(3000);h.ack(true);h.drain();assert.equal(h.submitted.length,0);assert.equal(h.failed.length,1);
h=setup();h.ctx.sceneView.isLoading=true;h.begin();h.drain();assert.equal(h.events.length,0);assert.equal(h.failed.length,1);
h=setup();h.begin();h.ctx.sceneView.isLoading=true;h.ack(true);h.drain();assert.equal(h.submitted.length,0);assert.equal(h.failed.length,1);
for(const change of ['locked','pen-near','pen-recent','route','working','disabled']) {
  h=setup();h.begin();
  if(change==='locked')h.ctx.herdLayoutPenBlocked=true;
  if(change==='pen-near')h.ctx.sceneView.penClose=true;
  if(change==='pen-recent')h.ctx.sceneView.strokeHandler.timeSincePenUp=()=>0;
  if(change==='route')h.ctx.herdPenSurface.handler={};
  if(change==='working')h.ctx.root.sceneController.working=true;
  if(change==='disabled')h.ctx.root.enabled=false;
  h.ack(true);h.drain();assert.equal(h.submitted.length,0,change);assert.equal(h.failed.length,1,change);
}
console.log('Layout handoff: accepted fresh context precedes original measurement; bounded idle/HTTP wait; changes and late callbacks hold.');
