// Actual injected functions; geometry releases sequencing, never persistence.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/xochitl/herdRespond.qmd','utf8');
function definition(name){
  const start=source.indexOf('function '+name+'(');
  const end=source.indexOf('\n\t\t\t\tfunction ',start+1);
  assert(start>=0 && end>start);return source.slice(start,end);
}
function setup(){
  const c={itemsBoundingRect:{x:20,y:30,width:100,height:150},
    rootDocumentBoundingRect:{x:0,y:0,width:300,height:240},working:false};
  const ctx=vm.createContext({root:{sceneController:c,inSuspend:false},
    herdContextSurface:'surface',herdContextInk:4,
    sceneView:{penClose:false,isLoading:false,strokeHandler:{timeSincePenUp:()=>2000}}});
  vm.runInContext(['herdImageGeometry','herdImageGeometryReady'].map(definition).join('\n'),ctx);
  const work={job:{nativeInkUsed:true},blockTextBottom:240};
  work.blockImageGeometry=ctx.herdImageGeometry(work,{width:150,height:80},0,270);
  assert.deepEqual(Array.from(work.blockImageGeometry.expected),[0,30,150,320]);
  return {c,ctx,work};
}
let {c,ctx,work}=setup();
assert.equal(ctx.herdImageGeometryReady(work),false,'unchanged old bounds are not completion');
c.itemsBoundingRect={x:0,y:30,width:150,height:320};
assert.equal(ctx.herdImageGeometryReady(work),false,'one native sample is insufficient');
assert.equal(ctx.herdImageGeometryReady(work),true);
assert.equal(work.mediaVerified,undefined);
for(const invalidate of [
  s=>s.c.itemsBoundingRect.height+=1,
  s=>s.c.itemsBoundingRect.x=NaN,
  s=>s.c.itemsBoundingRect=null,
  s=>s.c.working=true,
  s=>s.ctx.sceneView.isLoading=true,
]){
  const s=setup();s.c.itemsBoundingRect={x:0,y:30,width:150,height:320};
  assert.equal(s.ctx.herdImageGeometryReady(s.work),false);
  invalidate(s);
  assert.equal(s.ctx.herdImageGeometryReady(s.work),false);
  assert.equal(s.work.blockImageGeometry.samples,0,'every mismatch resets consecutive samples');
}
for(const change of [
  s=>s.ctx.herdContextInk++,s=>s.ctx.herdContextSurface='other',
  s=>s.ctx.root.sceneController={...s.c},s=>s.ctx.root.inSuspend=true,
  s=>s.ctx.sceneView.penClose=true,s=>s.ctx.sceneView.strokeHandler.timeSincePenUp=()=>10,
  s=>s.c.rootDocumentBoundingRect.height++,
]){
  const s=setup();change(s);
  assert.throws(()=>s.ctx.herdImageGeometryReady(s.work),/changed/);
}
for(const change of [
  s=>s.work.job.nativeInkUsed=false,
  s=>s.c.itemsBoundingRect.height=300, // overlaps intended destination
  s=>s.c.itemsBoundingRect.width=-1,
  s=>s.c.itemsBoundingRect.x=Infinity,
]){
  const s=setup();change(s);
  assert.equal(s.ctx.herdImageGeometry(s.work,{width:150,height:80},0,270),null,
    'unqualified geometry must retain the existing persisted-image gate');
}
console.log('Native image geometry: exact extending union, two samples, native idle, page/pen/text guards; no persistence shortcut.');
