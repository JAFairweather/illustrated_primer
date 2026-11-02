const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
const start = source.indexOf('function herdStartProbe(');
const end = source.indexOf('\n\t\t\t\tTimer { id: herdProbeTimer;', start);
const definitions = source.slice(start, end);
const job = {id:'probe-1', doc:'target', page:'target-page', surface:'surface', source_doc:'asset', source_page:'asset-page'};
function harness() {
  let created=0, destroyed=0;
  const reports=[];
  const c={working:false, cloneSelectedItems(){throw Error('probe must not clone');},
    addSelectionRect(){throw Error('probe must not select');}};
  const view={status:1,pageStatus:1,controller:c,destroy(){destroyed++;}};
  const ctx=vm.createContext({herdProbeJob:null,herdProbeView:null,herdProbeSeen:'',herdProbePasses:0,herdPasteBusy:false,herdInk:null,
    herdContextSurface:'surface',herdPage:'target-page',herdProbeImportCallback:null,herdProbeImportDoc:'',
    root:{inSuspend:false},sceneView:{document:{id:'target'}},herdButton:{},
    Library:{entryForId(id){assert.equal(id,'asset');return {id};}},
    herdAssetScene:{createObject(parent,args){created++; assert(['asset-page','remapped-page'].includes(args.pageId)); return view;}},
    herdProbeTimer:{restart(){},stop(){}},SceneView:{Active:1},Page:{Ready:1},
    SceneController:{InitalSelection:0},Qt:{rect(x,y,width,height){return {x,y,width,height};}},
    navigator:{herdUuid(x){return x;},herdHttp(method,route,body){reports.push({method,route,body});}}
  });
  vm.runInContext(definitions,ctx);
  return {ctx,c,view,reports,counts:()=>({created,destroyed})};
}
let h=harness();
h.ctx.herdStartProbe(job); h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'loaded');
assert.equal(h.reports[0].body.clone_selected,true);
assert.equal(h.reports[0].body.select_rect,true);
assert.equal(h.reports[0].body.select_all,false);
assert.deepEqual(h.counts(),{created:1,destroyed:1});
h.ctx.herdStartProbe(job);
assert.equal(h.counts().created,1,'same probe is never retried');
h=harness(); h.ctx.herdStartProbe({...job,page:'other'});
assert.equal(h.counts().created,0);
h.ctx.herdStartProbe(job); h.ctx.herdPage='other'; h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'unavailable');
h=harness();h.view.status=0;h.ctx.herdStartProbe(job);
for(let i=0;i<80;i++)h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'timeout');
assert.equal(h.counts().destroyed,1);
h=harness();
let selected=0,cloned=0;
h.c.addSelectionRect=(rect,mode)=>{assert.equal(rect.width,920);assert.equal(mode,0);selected++;h.c.selectionItemCount=2;};
h.c.cloneSelectedItems=(layer,scale)=>{assert.equal(scale,1);cloned++;return [{},{}];};
h.ctx.herdStartProbe({...job,operation:'clone-source',expected_strokes:2});
h.ctx.herdProbeTick();assert.equal(cloned,0,'selection and cloning wait separate worker ticks');
h.ctx.herdProbeTick();
assert.equal(selected,1);assert.equal(cloned,1);
assert.equal(h.reports[0].body.state,'cloned');
assert.equal(h.reports[0].body.selected,2);assert.equal(h.reports[0].body.cloned,2);
h=harness();h.c.addSelectionRect=()=>{h.c.selectionItemCount=2;};
h.c.cloneSelectedItems=()=>({opaqueNativeValue:true});
h.ctx.herdStartProbe({...job,operation:'clone-source',expected_strokes:2});
h.ctx.herdProbeTick();h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.clone_value,true,'native typed lists need not have a JS length');
assert.equal(h.reports[0].body.cloned,0,'unknown list length must not be invented');
assert.equal(h.reports[0].body.state,'cloned');
console.log('Native asset probe: guarded hidden load/source-only clone; no clipboard or foreground paste; timeout and page guard passed.');

h=harness();
let callback, imports=0, disconnected=0;
h.ctx.Library.entryAdded={connect(fn){callback=fn;},disconnect(fn){assert.equal(fn,callback);disconnected++;}};
h.ctx.DocumentImporter={importFromUrls(urls,parent){imports++;assert.equal(parent,'folder');assert.equal(urls[0],'file:///home/root/.cache/herd-board/imports/asset.rmdoc');}};
h.ctx.Library.entryForId=id=>({id,visibleName:id==='other'?'unrelated':'Agent lesson source asset',idForPage(i){assert.equal(i,0);return 'remapped-page';}});
h.c.addSelectionRect=()=>{h.c.selectionItemCount=2;};
h.c.cloneSelectedItems=()=>({opaque:true});
const importJob={...job,operation:'import-source',source_parent:'folder',expected_strokes:2};
h.ctx.herdStartProbe(importJob);
assert.equal(imports,1);assert.equal(h.counts().created,0);
callback('other');assert.equal(h.counts().created,0);
callback('native-remapped-id');
callback('native-remapped-id');
assert.equal(h.counts().created,1,'duplicate completion must not create another source view');
h.ctx.herdProbeTick();h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'cloned');
assert.equal(h.reports[0].body.imported_doc,'native-remapped-id');
assert.equal(h.reports[0].body.imported_page,'remapped-page');
assert.equal(disconnected,1);
callback('native-remapped-id');assert.equal(h.counts().created,1);

h=harness();disconnected=0;
h.ctx.Library.entryAdded={connect(fn){callback=fn;},disconnect(){disconnected++;}};
h.ctx.DocumentImporter={importFromUrls(){}};
h.ctx.herdStartProbe(importJob);
for(let i=0;i<80;i++)h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'timeout');assert.equal(disconnected,1);
callback('native-remapped-id');assert.equal(h.counts().created,0);

// Text-anchor diagnostics touch only a hidden existing document's cursor.
// All editing and selection entrypoints throw if accidentally invoked.
function anchorHarness() {
  const h=harness();
  h.ctx.herdContextRevision=7; h.ctx.herdContextInk=4;
  h.c.hasRootDocument=true;h.c.rootDocumentLength=23;h.c.textCursorIndex=-1;
  h.c.textCursorPosition={x:-464,y:267.59375};h.c.textLineHeight=69.55;
  h.c.focusRootDocument=()=>{};
  h.c.setCursorIndex=(i)=>{assert.equal(i,0);h.c.textCursorIndex=i;};
  h.c.createRootDocument=h.c.replaceText=h.c.pasteItems=()=>{throw Error('diagnostic must not edit');};
  return h;
}
const anchorJob={...job,operation:'text-anchor',revision:7,ink:4};
h=anchorHarness();h.ctx.herdStartProbe(anchorJob);
h.ctx.herdProbeTick();assert.equal(h.reports.length,0,'wait for native cursor update');
h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'text-anchor');
assert.deepEqual(Array.from(h.reports[0].body.text_anchor),[-464,267.59375,69.55,23]);
assert.deepEqual(h.counts(),{created:1,destroyed:1});
for(const change of ['revision','ink','surface','missing-text','foreground-controller']) {
  h=anchorHarness();h.ctx.herdStartProbe(anchorJob);h.ctx.herdProbeTick();
  if(change==='revision')h.ctx.herdContextRevision++;
  if(change==='ink')h.ctx.herdContextInk++;
  if(change==='surface')h.ctx.herdContextSurface='changed';
  if(change==='missing-text')h.c.hasRootDocument=false;
  if(change==='foreground-controller')h.ctx.root.sceneController=h.c;
  h.ctx.herdProbeTick();assert.equal(h.reports[0].body.state,'unavailable',change);
  assert.equal(h.reports[0].body.text_anchor,undefined);
}
h=anchorHarness();h.ctx.herdStartProbe({...anchorJob,source_doc:job.doc,source_page:job.page});
assert.equal(h.counts().created,0,'never focus the foreground source');
h=anchorHarness();h.c.setCursorIndex=()=>{};h.ctx.herdStartProbe(anchorJob);
for(let i=0;i<82;i++)h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'timeout');
console.log('Hidden text-anchor probe: index zero only, no edits or ink selection, source/page/input guards and timeout passed.');

for (const index of [1,21,23]) {
  h=anchorHarness();
  h.c.setCursorIndex=i=>{assert.equal(i,index);h.c.textCursorIndex=i;};
  // Use the actual SceneController property already exercised by native-context.
  // Deliberately do not define a rootDocumentBounds alias in the mock.
  h.c.rootDocumentBoundingRect={x:-468,y:234,width:936,height:300};
  h.c.itemsBoundingRect={x:-264,y:100,width:100,height:2};
  h.ctx.herdStartProbe({...anchorJob,cursor_index:index});
  h.ctx.herdProbeTick();assert.equal(h.reports.length,0);
  h.ctx.herdProbeTick();
  assert.equal(h.reports[0].body.state,'text-anchor');
  assert.equal(h.reports[0].body.text_cursor_index,index);
  assert.deepEqual(Array.from(h.reports[0].body.text_bounds),[-468,234,936,300]);
  assert.deepEqual(Array.from(h.reports[0].body.ink_bounds),[-264,100,100,2]);
  assert.deepEqual(h.counts(),{created:1,destroyed:1});
}
for (const index of [-1,24,262145,1.5,NaN,'1',true]) {
  h=anchorHarness();h.ctx.herdStartProbe({...anchorJob,cursor_index:index});
  h.ctx.herdProbeTick();assert.equal(h.reports[0].body.state,'unavailable');
  assert.equal(h.reports[0].body.text_anchor,undefined);
}
h=anchorHarness();h.c.setCursorIndex=i=>{h.c.textCursorIndex=i;};
h.c.rootDocumentBounds={x:-468,y:234,width:936,height:300};
h.ctx.herdStartProbe({...anchorJob,cursor_index:21});
h.ctx.herdProbeTick();h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'unavailable','missing actual native bounds are never inferred from an invented alias');
assert.equal(h.reports[0].body.text_bounds,undefined);
console.log('Hidden indexed cursor probe: exact bounded index including document end, native bounds only, no foreground edits.');
for (const rect of [{x:0,y:NaN,width:2,height:2},{x:0,y:0,width:-1,height:2}]) {
  h=anchorHarness();h.c.rootDocumentBoundingRect={x:0,y:0,width:100,height:100};
  h.c.itemsBoundingRect=rect;h.ctx.herdStartProbe({...anchorJob,cursor_index:0});
  h.ctx.herdProbeTick();h.ctx.herdProbeTick();
  assert.equal(h.reports[0].body.state,'unavailable');
  assert.equal(h.reports[0].body.ink_bounds,undefined);
}
h=anchorHarness();h.c.rootDocumentBoundingRect={x:0,y:0,width:100,height:100};
h.ctx.herdProbeInkBounds=[99,99,99,99];
h.ctx.herdStartProbe({...anchorJob,cursor_index:0});
h.ctx.herdProbeTick();h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'text-anchor');
assert.equal(h.reports[0].body.ink_bounds,undefined,'no stale bounds from a previous source');
h=anchorHarness();h.c.rootDocumentBoundingRect={x:0,y:0,width:100,height:100};
Object.defineProperty(h.c,'itemsBoundingRect',{get(){throw Error('native item bounds read failed');}});
h.ctx.herdStartProbe({...anchorJob,cursor_index:0});
h.ctx.herdProbeTick();h.ctx.herdProbeTick();
assert.equal(h.reports[0].body.state,'unavailable','native getter exception fails the whole indexed report');
for (const field of ['text_anchor','text_cursor_index','text_bounds','ink_bounds']) {
  assert.equal(h.reports[0].body[field],undefined,'no partial measurement after native getter exception: '+field);
}
assert.deepEqual(h.counts(),{created:1,destroyed:1});
