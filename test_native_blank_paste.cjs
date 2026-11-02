const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'xochitl/herdRespond.qmd'),'utf8');
const begin=source.indexOf('function herdBeginBlankPaste(');
const end=source.indexOf('\n\t\t\t\tfunction herdFinishProbe(',begin);
const definitions=source.slice(begin,end);
function run(change) {
  let pastes=0,commits=0,claims=0,claimDone;
  const states=[];
  const job={id:'attempt',doc:'doc',page:'page',surface:'surface',revision:1,expected_strokes:2};
  const editor={working:false,pendingEdit:{nativeType:'QTransform'},selectionItemCount:0,rootDocumentLength:0,currentLayer:0,
    cloneAddAndSelectItems(layer,items,scale,position){pastes++;assert.equal(items.opaque,true);this.selectionItemCount=2;ctx.sceneView.itemSelectionMode=true;},
    applyPendingEdit(){commits++;this.pendingEdit=false;},clearSelectedItems(){this.selectionItemCount=0;}};
  const surface={handler:null,toString(){return 'PenInputSurface(0x1)';}};
  const ctx=vm.createContext({herdProbeJob:job,herdProbePhase:'cloning',herdProbePasses:0,
    herdPasteBusy:false,herdPasteController:null,herdPasteLockPasses:0,herdProbeItems:{opaque:true},
    herdContextInk:0,herdContextRevision:1,herdContextSurface:'surface',herdPage:'page',
    root:{sceneController:editor,inSuspend:false,enabled:true},
    sceneView:{document:{id:'doc'},children:[surface],adjustViewActive:false,
      strokeHandler:{lineTool:42,timeSincePenUp(){return 5000;}},viewToScene(p){return {x:p.x-702,y:p.y};},
      endItemSelection(){editor.applyPendingEdit();editor.clearSelectedItems();this.itemSelectionMode=false;}},
    Qt:{point(x,y){return {x,y};}},Line:{SelectionTool:42},
    navigator:{herdUuid(x){return x;},herdHttp(method,route,body,done){claims++;assert.equal(route,'/native-probe-claim');claimDone=done;}},
    herdFinishProbe(state){states.push(state);ctx.herdPasteBusy=false;}
  });
  vm.runInContext(definitions,ctx);
  if(change)change(ctx,editor,surface);
  const started=ctx.herdBeginBlankPaste();
  return {ctx,editor,surface,states,started,counts:()=>({pastes,commits,claims}),
    lock(){ctx.root.enabled=false;ctx.sceneView.adjustViewActive=true;},grant(){claimDone(200,{claimed:true,id:'attempt'});}};
}
let h=run();assert.equal(h.started,true);h.lock();
h.ctx.herdBlankPasteTick();h.ctx.herdBlankPasteTick();
assert.deepEqual(h.counts(),{pastes:0,commits:0,claims:1},'no paste before durable grant');
h.grant();h.ctx.herdBlankPasteTick();h.ctx.herdBlankPasteTick();
assert.deepEqual(h.counts(),{pastes:1,commits:1,claims:1});assert.deepEqual(h.states,['pasted']);
for(const change of [c=>c.herdContextInk=1,(c,e)=>e.selectionItemCount=1,(c,e)=>e.rootDocumentLength=4,
  c=>c.sceneView.penClose=true,c=>c.navigator.herdJob={},c=>c.sceneView.adjustViewActive=true]){
  h=run(change);assert.equal(h.started,false);assert.equal(h.counts().pastes,0);
}
h=run();h.lock();h.surface.handler={};h.ctx.herdBlankPasteTick();
assert.deepEqual(h.states,['unavailable']);assert.equal(h.counts().claims,0,'busy flag alone is not a native pen lock');
h=run();h.lock();h.ctx.herdBlankPasteTick();h.ctx.herdBlankPasteTick();h.ctx.herdPage='other';h.grant();
assert.equal(h.counts().pastes,0,'late grant cannot follow navigation');
h=run();h.lock();h.ctx.herdContextRevision++;h.ctx.herdBlankPasteTick();assert.equal(h.counts().claims,0);
assert(source.includes('restoreMode: Binding.RestoreBindingOrValue'));
console.log('Native blank paste: real surface lock, idle/pristine checks, durable grant before one paste, native commit, page/revision guards passed.');
