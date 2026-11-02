const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
// Declarative contract only: this cannot prove physical e-ink refresh quality.
const canvasDeclaration=source.slice(source.indexOf('id: herdStrokeCanvasComponent'),source.indexOf('function herdTextDone('));
assert.match(canvasDeclaration,/Epaper\.ScreenModeItem\s*\{\s*anchors\.fill: parent\s*mode: Epaper\.ScreenModeItem\.Animation\s*visible: playbackCanvas\.visible\s*\}/);
assert.doesNotMatch(canvasDeclaration,/screenDriver\s*\.\s*globalMode\s*=/);
// Firmware selection chrome must disappear only for our locked ink insertion.
// The native selection preview stays visible and its commit path is untouched.
const quietStart = source.indexOf('function herdQuietInkSelection(');
const quietEnd = source.indexOf('\n\t\t\t\tConnections {', quietStart);
assert(quietStart >= 0 && quietEnd > quietStart);
{
  let writes=0, visible=true;
  const selection={previewVisible:true};
  const ctx=vm.createContext({sceneView:{selectionHandler:selection},herdInk:null,herdPasteBusy:false});
  Object.defineProperty(selection,'controlsAreVisible',{
    get(){return visible;},set(value){writes++;visible=value;ctx.herdQuietInkSelection();}
  });
  vm.runInContext(source.slice(quietStart,quietEnd),ctx);
  ctx.herdQuietInkSelection(); assert.equal(writes,0,'leave ordinary selection alone');
  ctx.herdPasteBusy=true; ctx.herdQuietInkSelection();
  assert.equal(writes,0,'layout/probe lock alone is not automatic ink');
  ctx.herdInk={ownsLock:false}; ctx.herdQuietInkSelection(); assert.equal(writes,0);
  ctx.herdInk.ownsLock=true; ctx.herdQuietInkSelection();
  assert.equal(writes,1,'synchronous change signal does not recurse indefinitely');
  assert.equal(visible,false); assert.equal(selection.previewVisible,true);
  assert.equal(ctx.herdPasteBusy,true); assert.equal(ctx.herdInk.ownsLock,true);
  visible=true;ctx.herdQuietInkSelection();assert.equal(writes,2,'each next native open is quieted');
  ctx.herdInk=null;visible=true;ctx.herdQuietInkSelection();
  assert.equal(visible,true,'normal selection after insertion retains its controls');
  ctx.sceneView.selectionHandler=null;ctx.herdQuietInkSelection();
  assert(source.includes('function onControlsAreVisibleChanged() { herdButton.herdQuietInkSelection() }'));
  assert(source.includes('function onSelectionHandlerChanged() { herdButton.herdQuietInkSelection() }'));
}
const start = source.indexOf('function herdInkView(');
const end = source.indexOf('\n\t\t\t\tTimer { id: herdInkTimer;', start);
const playbackStart = source.indexOf('function herdPlaybackProgram(');
const playbackEnd = source.indexOf('\n\t\t\t\tTimer { id: herdPlaybackTimer;', playbackStart);
function harness() {
  const errors=[], calls=[], queue=[], pastes=[];
  let destroyed=0, committed=0, claim, ack;
  const job={page:'page',path:'doc/page.rm'};
  const work={job,reply:{request:'request'},blockNext:1};
  const block={scene:'integral',stage:'see',stage_index:0,source_doc:'source',source_page:'source-page',
    stroke_count:2,width:900,height:500,bounds:[80,50,700,450]};
  const controller={working:false,selectionItemCount:0,hasTextSelection:false,currentLayer:0,
    pendingEdit:{nativeTransform:true},
    cloneAddAndSelectItems(layer,items,scale,point){
      assert.equal(items.opaque,true);assert.equal(scale,1);pastes.push(point);
      this.selectionItemCount=items.count;ctx.sceneView.itemSelectionMode=true;
    }};
  const v={status:1,pageStatus:1,controller:{working:false,selectionItemCount:0,currentLayer:0,
    addSelectionRect(rect){this.lastRect=rect;this.selectionItemCount=this.expectedCount||2;},
    clearSelectedItems(){this.selectionItemCount=0;},
    cloneSelectedItems(){return {opaque:true,count:this.selectionItemCount};}},
    destroy(){destroyed++;}};
  const surface={handler:null,toString(){return 'PenInputSurface(0x1)';}};
  const ctx=vm.createContext({console:{log(){}},herdInk:null,herdPasteBusy:false,herdProbeJob:null,
    herdMine:true,herdPage:'page',herdContextInk:0,herdContextRevision:3,herdContextSurface:'surface',herdContextBusy:false,
    herdButton:{},herdReportContext(){},herdTextDone(w){queue.push(w);},herdLater(f){f();},
    root:{sceneController:controller,inSuspend:false,enabled:true,exitTextMode(){}},
    sceneView:{document:{id:'doc'},width:1404,height:1872,adjustViewActive:false,children:[surface],
      strokeHandler:{lineTool:42,timeSincePenUp(){return 5000;}},
      viewToScene(p){return {x:p.x-702,y:p.y};},sceneToView(p){return {x:p.x+702,y:p.y};},
      tileManager:{moveViewBy(){throw Error('fixture already fits viewport');}},
      endItemSelection(){committed++;controller.selectionItemCount=0;this.itemSelectionMode=false;}},
    Library:{entryForId(id){return {id};}},herdAssetScene:{createObject(){return v;}},
    herdInkTimer:{restart(){},stop(){}},SceneView:{Active:1},Page:{Ready:1},Line:{SelectionTool:42},
    SceneController:{InitalSelection:0},Qt:{point(x,y){return {x,y};},rect(x,y,width,height){return {x,y,width,height};}},
    navigator:{herdJob:job,herdUuid(x){return x;},herdFail(st,r){errors.push(r.error);},
      herdHttp(method,route,body,done){calls.push({route,body});
        if(route==='/native-ink-claim')claim=done;
        else if(route==='/native-ink-done')ack=done;
        else throw Error(route);
      }}
  });
  vm.runInContext(source.slice(start,end),ctx);
  vm.runInContext(source.slice(playbackStart,playbackEnd),ctx);
  function ticks(n=1){for(let i=0;i<n;i++)ctx.herdInkTick();}
  function begin(){ctx.herdBeginInk(work,block,{x:-468,y:100,width:936,height:200});}
  function lock(){ticks(10);assert.equal(ctx.herdInk.phase,'locking');ctx.root.enabled=false;ctx.sceneView.adjustViewActive=true;ticks(5);}
  function grant(){claim(200,{claimed:true,request:'request',scene:block.scene,stage:block.stage});}
  return {ctx,work,block,controller,v,surface,errors,calls,pastes,queue,begin,lock,grant,ticks,
    ack(){ack(200,{accepted:true,persisted:false});},lose(st=0){ack(st,null);},counts(){return {destroyed,committed};}};
}
// A wide handwriting region (1140) is selected whole, not through a fixed 900-wide window.
{const w=harness();w.block.width=1140;w.block.height=300;w.begin();w.ticks();
assert.deepEqual(w.v.controller.lastRect,{x:-10,y:-10,width:1160,height:320});w.ctx.herdInkFinish('test cleanup');}
let h=harness();h.begin();h.lock();
assert.equal(h.pastes.length,0,'durable claim must precede paste');
assert.equal(h.calls[0].body.origin[1],330,'reserve below the latest native text');
h.grant();h.grant();assert.equal(h.pastes.length,1,'late duplicate grant cannot paste twice');
assert.equal(h.pastes[0].x,-78);assert.equal(h.pastes[0].y,580,'paste at translated source bbox centre');
h.ticks(2);assert.equal(h.counts().committed,1);assert.equal(h.ctx.herdPasteBusy,true,'hold native lock through commit ACK');
h.ack();assert.equal(h.ctx.herdPasteBusy,false);assert.equal(h.work.blockNext,2);
assert.equal(h.work.mediaBottom,860);assert.equal(h.work.job.nativeInkUsed,true);
assert.equal(h.counts().destroyed,1);assert.equal(h.queue.length,1);
// Subsequent additive stage must reuse the entire plot origin, not its caption's bottom.
h.block={...h.block}; // begin closes over original descriptor, mutate it instead below.
const b=h.work.job.nativePlots.integral;
h.ctx.herdBeginInk(h.work,{...h.block,stage:'measure',stage_index:1,bounds:[120,140,740,450]}, {x:-468,y:1000,width:936,height:200});
assert.deepEqual(h.ctx.herdInk.origin,b);h.ctx.herdInkFinish('test cleanup');
for(const change of [x=>x.ctx.herdPage='other',x=>x.ctx.herdContextInk++,x=>x.ctx.herdContextRevision++,
  x=>x.surface.handler={},x=>x.ctx.sceneView.viewToScene=p=>({x:p.x-700,y:p.y})]){
  h=harness();h.begin();h.lock();change(h);h.grant();
  assert.equal(h.pastes.length,0,'late claim cannot cross page/input/layout/native-lock change');
  assert.equal(h.errors.length,1);assert.equal(h.ctx.herdPasteBusy,false);
}
h=harness();h.begin();h.ctx.sceneView.penClose=true;h.ticks();assert.equal(h.errors.length,1);assert.equal(h.calls.length,0);
h=harness();h.v.status=0;h.begin();h.ticks(251);assert.match(h.errors[0],/timed out/);assert.equal(h.pastes.length,0);
h=harness();h.ctx.Library.entryForId=()=>null;h.begin();
assert.equal(h.ctx.herdInk,null);assert.equal(h.calls.length,0);assert.equal(h.queue.length,1);
h.ctx.Library.entryForId=id=>({id});h.begin();h.lock();h.grant();
assert.equal(h.pastes.length,1,'source discovery wait does not repeat foreground insertion');
h=harness();h.ctx.Library.entryForId=()=>null;
for(let i=0;i<30;i++)h.begin();
assert.throws(()=>h.begin(),/source is not loaded/);assert.equal(h.pastes.length,0);assert.equal(h.calls.length,0);
assert(source.includes('ink_version: 1'));
assert(source.includes('"/notebook-ink-proof"'), 'native ink requires saved geometry proof before completion');
// Atlas reveal reuses one source, one stage claim, one actual lock, one final ACK.
function revealed() {
  const h=harness();h.block.stroke_count=3;h.block.point_count=18;
  h.block.reveal=[0,1,2].map(i=>({offset:[0,i*540],rect:[-10,i*540-10,920,520],
    bounds:[80+i*100,50,180+i*100,50],stroke_count:1,point_count:6}));
  h.v.controller.expectedCount=1;
  return h;
}
h=revealed();h.begin();h.lock();h.grant();h.grant();
assert.equal(h.pastes.length,1);assert.equal(h.ctx.herdInk.chunk,0);
h.ticks(2);
assert.equal(h.ctx.herdInk.phase,'selecting-next');assert.equal(h.ctx.herdPasteBusy,true);
assert.equal(h.v.controller.lastRect.y,530);
assert.equal(h.calls.filter(c=>c.route==='/native-ink-done').length,0);
h.ticks(3);assert.equal(h.ctx.herdInk.chunk,2);assert.equal(h.pastes.length,2);
assert.equal(h.v.controller.lastRect.y,1070);
h.ticks(3);assert.equal(h.pastes.length,3);assert.equal(h.counts().committed,3);
assert.equal(h.calls.filter(c=>c.route==='/native-ink-claim').length,1);
assert.equal(h.calls.filter(c=>c.route==='/native-ink-done').length,1);
assert.deepEqual(h.pastes.map(p=>p.x),[-338,-238,-138]);
assert.deepEqual(h.pastes.map(p=>p.y),[380,380,380],'source atlas offsets must not reach notebook');
assert.equal(h.ctx.herdPasteBusy,true);h.ack();h.ack();
assert.equal(h.work.blockNext,2);assert.equal(h.queue.length,1);assert.equal(h.counts().destroyed,1);
for(const change of [x=>x.ctx.herdPage='other',x=>x.ctx.herdContextInk++,
  x=>x.surface.handler={},x=>x.ctx.sceneView.viewToScene=p=>({x:p.x-700,y:p.y})]) {
  h=revealed();h.begin();h.lock();h.grant();h.ticks(2);change(h);h.ticks();
  assert.equal(h.pastes.length,1,'changed state cannot emit the next chunk');
  assert.equal(h.calls.filter(c=>c.route==='/native-ink-done').length,0);
  assert.equal(h.errors.length,1);assert.equal(h.queue.length,0);
}
// The hidden source view's controller can go away and come back between chunks (5fdba26e): wait, select again.
h=revealed();h.begin();h.lock();h.grant();h.ticks(2);
assert.equal(h.ctx.herdInk.phase,'selecting-next');
const source1=h.v.controller;h.v.controller=null;h.ticks(10);
assert.equal(h.errors.length,0,'a briefly missing source is waited for');assert.equal(h.pastes.length,1);
h.v.controller={...source1,selectionItemCount:0,lastRect:null};h.ticks();
assert.equal(h.v.controller.lastRect.y,530,'the current chunk is selected again in the new source');
h.ticks(6);assert.equal(h.pastes.length,3);assert.equal(h.counts().committed,3);assert.equal(h.errors.length,0);
h.ack();assert.equal(h.work.blockNext,2);
// After the paste the source may unload for good (673a2723): the commit and ACK do not need it.
h=harness();h.begin();h.lock();h.grant();h.v.controller=null;h.ticks(45);
assert.equal(h.errors.length,0,'a pasted drawing commits without its source');
assert.equal(h.calls.filter(c=>c.route==='/native-ink-done').length,1);
// A lost commit ACK is sent again on the next tick; a refused one fails at once (ae12839f).
h=harness();h.begin();h.lock();h.grant();h.ticks(2);
const acks=()=>h.calls.filter(c=>c.route==='/native-ink-done').length;
assert.equal(acks(),1);h.ticks(2);assert.equal(acks(),1,'no resend while the ACK is open');
h.lose();assert.equal(h.errors.length,0);h.ticks();assert.equal(acks(),2,'a lost ACK is sent again');
h.lose(502);h.ticks();assert.equal(acks(),3);h.ack();
assert.equal(h.errors.length,0);assert.equal(h.work.blockNext,2);assert.equal(h.counts().committed,1);
h=harness();h.begin();h.lock();h.grant();h.ticks(2);h.lose();h.ticks();h.lose();h.ticks();h.lose();h.ticks();h.lose();
assert.equal(acks(),4);assert.equal(h.errors.length,1,'four lost ACKs fail');
h=harness();h.begin();h.lock();h.grant();h.ticks(2);h.lose(400);
assert.equal(h.errors.length,1,'a refused ACK is not sent again');
// Gone at the commit before the next chunk: that chunk is selected once the source is back.
h=revealed();h.begin();h.lock();h.grant();const source2=h.v.controller;h.v.controller=null;h.ticks(12);
assert.equal(h.ctx.herdInk.phase,'selecting-next');assert.equal(h.errors.length,0);assert.equal(h.pastes.length,1);
h.v.controller={...source2,selectionItemCount:0,lastRect:null};h.ticks();
assert.equal(h.v.controller.lastRect.y,530);
h.ticks(6);assert.equal(h.pastes.length,3);assert.equal(h.errors.length,0);
h=revealed();h.begin();h.lock();h.grant();h.ticks(2);h.v.controller=null;h.ticks(95);
assert.match(h.errors[0],/source closed/);assert.equal(h.pastes.length,1);
h=revealed();h.begin();h.lock();h.grant();h.ticks(2);h.ctx.herdInk.controller=null;h.ticks();
assert.match(h.errors[0],/page or input changed|destination page closed/);assert.equal(h.pastes.length,1);
h=revealed();h.block.reveal[1].rect[1]=0;
assert.throws(()=>h.begin(),/Invalid native reveal geometry/);assert.equal(h.pastes.length,0);
h=revealed();h.block.point_count=17;
assert.throws(()=>h.begin(),/counts changed/);assert.equal(h.calls.length,0);

// Timed playback is an overlay only; the ordinary source is pasted exactly once.
function playbackHarness() {
  const h=harness();let now=1000;const paintCalls=[];
  const painter=new Proxy({}, {get(target,key){return target[key] || ((...args)=>paintCalls.push([key,...args]));}});
  h.ctx.Date={now(){return now;}};
  h.ctx.herdPlaybackTimer={restart(){},stop(){}};
  const canvas={visible:false,paintOwner:null,width:1404,height:1872,
    requestPaint(){},getContext(){return painter;}};
  h.ctx.herdStrokeCanvas=null;
  h.ctx.herdStrokeCanvasComponent={createObject(parent){assert.equal(parent,h.ctx.sceneView);h.canvasCreations++;return canvas;}};
  h.canvasCreations=0;
  h.block.point_count=5;
  h.block.playback={version:1,velocity:240,pen_up_ms:35,minimum_stroke_ms:25,duration_ms:1535,
    paths:[[[20,30],[140,30],[140,150]],[[200,30],[320,30]]]};
  h.block.bounds=[20,30,320,150];
  h.advance=(ms=40)=>{now+=ms;h.ctx.herdPlaybackTick();};
  h.paint=()=>h.ctx.herdPlaybackPaint(h.ctx.herdStrokeCanvas);
  h.painted=()=>h.ctx.herdPlaybackPainted(h.ctx.herdStrokeCanvas);
  h.frame=()=>{h.paint();h.painted();};
  h.paintCalls=paintCalls;
  return h;
}
const clean=x=>JSON.parse(JSON.stringify(x));
h=playbackHarness();
const program=h.ctx.herdPlaybackProgram(h.block);
assert.deepEqual(clean(h.ctx.herdPlaybackFrame(program,750)),[[[20,30],[140,30],[140,90]]], 'follow the corner, not a chord');
assert.deepEqual(clean(h.ctx.herdPlaybackFrame(program,1020)),[[[20,30],[140,30],[140,150]]], 'pen up draws no travel line');
assert.deepEqual(clean(h.ctx.herdPlaybackFrame(program,1285)),[[[20,30],[140,30],[140,150]],[[200,30],[260,30]]]);
assert.deepEqual(clean(h.ctx.herdPlaybackFrame(program,1535)),h.block.playback.paths);
const paced=(pen_up_ms,minimum_stroke_ms,duration_ms)=>({...h.block,playback:{...h.block.playback,pen_up_ms,minimum_stroke_ms,duration_ms}});
assert.equal(h.ctx.herdPlaybackProgram(paced(12,10,1512)).duration,1512,'the server sets the pen lift, within bounds');
for(const [up,least] of [[9,25],[36,25],[12.5,25],[35,9],[35,26]])
  assert.throws(()=>h.ctx.herdPlaybackProgram(paced(up,least,1535)),/Invalid native stroke playback/);
h.begin();h.lock();assert.equal(h.canvasCreations,0,'no Canvas during notebook or source initialization');h.grant();h.grant();
assert.equal(h.canvasCreations,1,'lazy Canvas is created only after the actual input lock and claim');
assert.equal(h.ctx.herdInk.phase,'playback');assert.equal(h.pastes.length,0);
h.advance(40);assert.equal(h.ctx.herdInk.playback.elapsed,0,'must receive initial Qt painted signal');
h.frame();
while(h.ctx.herdInk.playback.elapsed<1535){h.advance();h.frame();}
assert.equal(h.pastes.length,0,'the final paint is not a saved/native reply');
h.advance();assert.equal(h.pastes.length,1);h.advance();assert.equal(h.errors.length,0,'late timer after handoff is harmless');
h.ticks(2);assert.equal(h.ctx.herdStrokeCanvas.visible,true,'retain overlay through native commit ACK');
h.ack();h.ack();assert.equal(h.ctx.herdStrokeCanvas.visible,false);assert.equal(h.pastes.length,1);
assert.equal(h.queue.length,1);assert.equal(h.work.blockNext,2);
assert.equal(h.calls.filter(c=>c.route==='/native-ink-claim').length,1);
assert.equal(h.calls.filter(c=>c.route==='/native-ink-done').length,1);
assert(h.paintCalls.some(c=>c[0]==='clip'));
assert(h.paintCalls.some(c=>c[0]==='setTransform' && c[5]===0 && c[6]===0));
assert.equal(h.ctx.herdStrokeCanvas.x,234);assert.equal(h.ctx.herdStrokeCanvas.y,330);
assert.equal(h.ctx.herdStrokeCanvas.width,900);assert.equal(h.ctx.herdStrokeCanvas.height,500);
for(const change of [x=>x.ctx.herdPage='other',x=>x.ctx.herdContextInk++,x=>x.ctx.herdContextRevision++,
  x=>x.surface.handler={},x=>x.ctx.root.inSuspend=true,x=>x.ctx.sceneView.penClose=true,
  x=>x.ctx.sceneView.viewToScene=p=>({x:p.x-700,y:p.y})]){
  h=playbackHarness();h.begin();h.lock();h.grant();h.frame();change(h);h.advance();
  assert.equal(h.pastes.length,0);assert.equal(h.errors.length,1);assert.equal(h.ctx.herdStrokeCanvas.visible,false);
  assert.equal(h.queue.length,0);assert.equal(h.ctx.herdPasteBusy,false);
}
for(const delay of [-1,10001]){
  h=playbackHarness();h.begin();h.lock();h.grant();h.frame();h.advance(delay);
  assert.match(h.errors[0],/clock stalled/);assert.equal(h.pastes.length,0);
}
h=playbackHarness();h.begin();h.lock();h.grant();h.frame();h.advance(3000);
assert.equal(h.errors.length,0,'a busy tablet pauses the drawing, not the reply');
assert.equal(h.ctx.herdInk.playback.elapsed,500,'a pause advances at most 500 ms');
h=playbackHarness();h.begin();h.lock();h.grant();h.frame();h.advance(500);h.paint();
assert.equal(h.ctx.herdInk.playback.painted,0,'onPaint submission is not Qt painted completion');
h.advance(40);assert.equal(h.ctx.herdInk.playback.elapsed,500);
h.painted();h.advance(40);assert.equal(h.ctx.herdInk.playback.elapsed,580);
h.ctx.herdInkFinish('cleanup');
for(const mutate of [b=>b.width=NaN,b=>b.height=501,b=>b.playback.duration_ms++,b=>b.playback.velocity=true,
  b=>b.playback.paths[0][0][0]=-1,b=>b.playback.paths[0][0][1]=Infinity,b=>b.point_count++,b=>b.reveal=[]]){
  h=playbackHarness();mutate(h.block);assert.throws(()=>h.begin());assert.equal(h.calls.length,0);
}
for(const transform of [p=>({x:NaN,y:p.y}),p=>({x:1404-(p.x+702),y:p.y}),p=>({x:p.x+702,y:p.y+2000})]){
  h=playbackHarness();h.begin();h.lock();h.ctx.sceneView.sceneToView=transform;h.grant();
  assert.equal(h.pastes.length,0);assert.equal(h.errors.length,1);
}
h=playbackHarness();h.begin();h.lock();h.grant();h.ctx.herdStrokeCanvas.getContext=()=>null;h.paint();
assert.match(h.errors[0],/unavailable/);assert.equal(h.pastes.length,0);
h=playbackHarness();h.ctx.herdStrokeCanvasComponent.createObject=()=>null;h.begin();h.lock();h.grant();
assert.equal(h.pastes.length,0);assert.equal(h.errors.length,1);assert.equal(h.ctx.herdPasteBusy,false);
h=playbackHarness();h.block.playback.paths[1]=[[200,30],[200,30]];h.block.playback.duration_ms=1060;
h.begin();h.lock();h.grant();h.frame();
while(h.ctx.herdInk.playback.elapsed<1060){h.advance();h.frame();}
assert(h.paintCalls.some(c=>c[0]==='arc'),'zero-length native dot remains a dot');
h.ctx.herdInkFinish('cleanup');
// A caption may scroll the picture away. Reposition before locking every playback stage.
h=playbackHarness();h.block.stage_index=1;h.work.job.nativePlots={integral:[-468,330]};
let offset=-1000,moves=0;
h.ctx.sceneView.sceneToView=p=>({x:p.x+702,y:p.y+offset});
h.ctx.sceneView.viewToScene=p=>({x:p.x-702,y:p.y-offset});
h.ctx.sceneView.tileManager.moveViewBy=p=>{offset+=p.y;moves++;};
h.begin();h.lock();h.grant();assert.equal(moves,1);assert.equal(h.ctx.herdInk.phase,'playback');
assert.deepEqual(clean(h.ctx.herdInk.origin),[-468,330],'viewport movement does not move saved diagram origin');
h.ctx.herdInkFinish('cleanup');
assert(source.includes('playback_version: 1'),'capability is reported through source import and reply requests');
assert(/Component\s*\{\s*id: herdStrokeCanvasComponent\s*Canvas\s*\{/.test(source),'Canvas is a deferred component, not a child reparented at notebook construction');
console.log('Ordered native ink: shared origin, opaque clone, actual native lock, one-shot grant, native commit, safe failures passed.');
