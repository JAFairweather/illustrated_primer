// Run the actual injected layout functions against a deliberately non-advancing
// native editor mock. This catches repeatedly inserting spacing at one cursor.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
assert(source.includes('anchors.top: parent.top') && source.includes('anchors.topMargin: 112'), 'Respond must stay below the close X at top right');
assert(!source.includes('anchors.bottomMargin: 40'), 'Respond must not occupy the lower writing area');
assert(source.includes('onTriggered: herdButton.herdFollowLatest()'), 'nested timer must call its owner explicitly');

function definition(name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0);
  const boundaries = ['\n\t\t\t\tfunction ', '\n\t\t\t\tTimer {']
    .map(token => source.indexOf(token, start + 1)).filter(index => index >= 0);
  return source.slice(start, Math.min(...boundaries));
}

function run(target, body, inactive = false, wrongPage = false, media = [], imageLoads = true, staleCursor = false, nativeGap = false, snapDown = false, styles = [], asyncCursor = false, initialText = '', blocks = undefined, nativeGeometry = false, lateGapTicks = 0, label = 'Agent Pi Dog:') {
  const queue = [], moves = [], errors = [], insertedImages = [], savedPositions = [], styled = [], events = [], requests = [];
  const job = {page: 'page', path: 'doc/page.rm', nativeInkUsed:nativeGeometry};
  let buffer = initialText, index = inactive ? -1 : 0, virtualLines = 0, replacements = 0;
  let pendingIndex, lateGap, clock = 0;
  const editor = {
    get textCursorIndex() { return index; },
    get rootDocumentLength() { return buffer.length; },
    get textCursorPosition() {
      return {x: 250, y: index < 0 ? 0 : (staleCursor && insertedImages.length === 0 && buffer.includes('Agent Pi Dog:'))
        ? 100 : 100 + ((buffer.slice(0, index).match(/\n/g) || []).length + virtualLines) * 50};
    },
    get rootDocumentBoundingRect() {
      return {x: 250, y: 100, width: 1000, height: ((buffer.match(/\n/g) || []).length + 1) * 50};
    },
    textLineHeight: 50,
    focusRootDocument(point) {
      if (nativeGap && point) {
        index = buffer.length;
        virtualLines = Math.max(0, (snapDown ? Math.floor : Math.ceil)((point.y - (100 + (buffer.match(/\n/g) || []).length * 50)) / 50));
      }
    },
    setCursorPosition(point) { this.focusRootDocument(point); },
    selectionContainsImage: false,
    itemsBoundingRect: {x:250,y:50,width:600,height:50},
    pendingEdit: false,
    insertImageFileAsSceneItem(url, position) {
      insertedImages.push({url, position});
      events.push({kind: 'image', url, position});
      this.selectionContainsImage = imageLoads;
      this.pendingEdit = imageLoads;
      if(nativeGeometry) {
        const item=media.find(m=>m.url===url), b=this.itemsBoundingRect;
        const left=Math.min(b.x,position.x-item.width/2), right=Math.max(b.x+b.width,position.x+item.width/2);
        // Native geometry can be ready while the saved image is still absent.
        this.itemsBoundingRect={x:left,y:b.y,width:right-left,height:position.y+item.height/2-b.y};
      }
    },
    applyPendingEdit() { this.pendingEdit = false; },
    clearSelectedItems() { this.selectionContainsImage = false; },
    setCursorIndex(next) {
      const wanted = Math.max(0, Math.min(next, buffer.length));
      if (asyncCursor) pendingIndex = wanted;
      else index = wanted;
    },
    get textParagraphStyle() { return {matchesButtonStyle() { return false; }}; },
    cycleParagraphStyle(type) { styled.push({index, type}); },
    replaceText(text) {
      replacements++;
      events.push({kind: 'text', text});
      assert(index >= 0, 'must not insert without a cursor');
      if (virtualLines && lateGapTicks) {
        // On the device the blank lines above a reply placed at a point can
        // materialise a few ticks after replaceText returns (request 8ef5c0b9).
        lateGap = {at: index, text: '\n'.repeat(virtualLines), due: clock + lateGapTicks};
        virtualLines = 0;
      }
      if (virtualLines) {
        const gap = '\n'.repeat(virtualLines);
        buffer = buffer.slice(0, index) + gap + buffer.slice(index);
        index += gap.length;
        virtualLines = 0;
      }
      buffer = buffer.slice(0, index) + text + buffer.slice(index);
      // Intentionally leave the cursor in place, as in the failed device flow.
    }
  };
  const navigator = {
    herdState: 'writing', herdNote: '', herdJob: job,
    herdFail(status, reply) { errors.push(reply.error); },
    herdHttp(method, route, payload, callback) {
      requests.push({route,payload});
      callback(200, {state: route === '/notebook-media-proof'
        ? (imageLoads ? 'persisted' : 'waiting') : route === '/notebook-ink-proof' ? 'persisted' : 'written'});
    }
  };
  const context = vm.createContext({
    root: {sceneController: editor, currentPage: 0, enterTextMode() {}, exitTextMode() {}}, navigator,
    LibraryController: {setScrollPosition(...args) { savedPositions.push(args); }},
    herdMine: true, herdPage: wrongPage ? 'other-page' : 'page',
    herdContextSurface:'surface', herdContextInk:0,
    herdSavedLengthPending:()=>false,
    herdLater(callback) { queue.push(callback); },
    // This suite tests placement/media sequencing; character-level async
    // appends/cancellation are executed from QMD in test_native_typewriter.
    herdStartTyping(work,text) {
      editor.replaceText(text);
      work.endIndex=editor.rootDocumentLength;
      queue.push(()=>context.herdTextDone(work));
    },
    sceneView: {document: {id: 'doc'}, strokeHandler:{timeSincePenUp:()=>2000}, height: 1872, sceneToView(point) { return point; }, viewToScene(point) { return point; }, tileManager: {
      moveViewBy(point) { moves.push(point); }
    }},
    SceneController: {MoveAnchor: 0, OverscrollAlwaysAllowed: 2}, SceneParticipant: {RequestedByInputMethod: 2},
    ParagraphStyle: {Type: {Subheading2: 2, Paragraph: 0}},
    Qt: {point(x, y) { return {x, y}; }}, console: {warn() {}}
  });
  vm.runInContext(['herdLayout', 'herdStyle', 'herdImageObservation', 'herdImageGeometry', 'herdImageGeometryReady', 'herdOrdered', 'herdTextDone'].map(definition).join('\n'), context);
  if (blocks && blocks.length) {
    blocks = blocks.slice();
    if (blocks[0].kind !== 'text') blocks.unshift({kind: 'text', text: '', styles: []});
    body = blocks[0].text;
    styles = blocks[0].styles || [];
  }
  context.herdLayout({job, ordered: blocks, blockNext: 1, reply: {
    label, text: body, request: 'notebook-test', media, styles
  }, target, inkBottom: target - 75, targetPoint: {x: 250, y: target}, nativeGap, padding: 0, passes: 0, focusAttempts: 0});
  let ticks = 0;
  while (queue.length) {
    assert(++ticks < 300, 'layout must terminate');
    if (pendingIndex !== undefined) { index = pendingIndex; pendingIndex = undefined; }
    if (lateGap && ++clock >= lateGap.due) {
      buffer = buffer.slice(0, lateGap.at) + lateGap.text + buffer.slice(lateGap.at);
      if (index >= lateGap.at) index += lateGap.text.length;
      lateGap = undefined;
    }
    queue.shift()();
  }
  return {buffer, index, moves, errors, navigator, insertedImages, savedPositions, replacements, styled, events, requests};
}

const heading = run(650, 'An idea 🐕.\n\nWhy it works\nThe body.', false, false, [], true,
  false, true, false, [{paragraph: 2, style: 'subheading'}], true, 'Existing paragraph stays unchanged.\n');
assert.deepEqual(heading.errors, []);
assert.deepEqual(heading.styled, [
  {index: heading.buffer.indexOf('Agent Pi Dog:'), type: 2},
  {index: heading.buffer.indexOf('Why it works'), type: 2},
  {index: heading.buffer.length, type: 0}
], 'styles must use settled native cursor indices and UTF-16 offsets inside the newly appended reply');
assert.equal(heading.replacements, 1, 'styling must not insert another copy of the response');
assert.equal(heading.index, heading.buffer.length, 'formatting must leave body style at the reply end');
assert(heading.styled.every(item => item.index >= 'Existing paragraph stays unchanged.\n'.length));

for (const inactive of [false, true]) {
  const result = run(650, 'Reply below the note.', inactive);
  assert.deepEqual(result.errors, []);
  assert.equal(result.navigator.herdState, '');
  assert.equal(result.savedPositions.length, 1, 'final viewport must be explicitly saved');
  const labelIndex = result.buffer.indexOf('Agent Pi Dog:');
  const labelY = 100 + (result.buffer.slice(0, labelIndex).match(/\n/g) || []).length * 50;
  assert(labelY >= 650, 'label must be below target');
  assert.equal(result.index, result.buffer.length, 'scroll must follow reply end');
  assert.equal(result.buffer.split('Agent Pi Dog:').length - 1, 1);
}
const snapped = run(2475, 'Below ink despite cursor line rounding.', false, false, [], true, false, true, true);
assert.deepEqual(snapped.errors, []);
assert.equal(snapped.replacements, 1, 'snapped native target above ink must not require padding');
const extended = run(2400, Array(35).fill('A long reply.').join('\n'));
assert.deepEqual(extended.errors, []);
assert(extended.moves.some(point => point.y < 0), 'long reply must scroll down');
const staleText = run(650, Array(35).fill('A long reply.').join('\n'), false, false, [], true, true);
assert.deepEqual(staleText.errors, []);
const staleTextBottom = 100 + ((staleText.buffer.match(/\n/g) || []).length + 1) * 50;
assert(staleText.moves.some(point => point.y === 1872 - 450 - staleTextBottom),
  'long reply must follow full bounds and leave writing space even when cursor is stale');
for (const inactive of [false, true]) {
  const native = run(2400, 'Native placement.', inactive, false, [], true, false, true);
  assert.deepEqual(native.errors, []);
  assert.equal(native.replacements, 1, 'native gap path must not manually insert padding paragraphs');
  assert.equal(native.index, native.buffer.length, 'native preliminary gap commits can change final index');
}
const movedPage = run(650, 'Do not write here.', false, true);
assert.equal(movedPage.buffer, '');
assert.equal(movedPage.errors.length, 1);
const media = [{asset: 'test', url: 'file:///controlled/asset.png', width: 600, height: 300}];
const leadingEquation = run(650, '', false, false, media, true, false, true, false, [], false, '',
  [{kind: 'media', ...media[0]}, {kind: 'text', text: 'A native explanation.', styles: []}]);
assert.deepEqual(leadingEquation.errors, []);
assert.equal(leadingEquation.events[0].text, '\nAgent Pi Dog:\n', 'leading equation must not receive an empty body paragraph');
assert.deepEqual(leadingEquation.events.map(e => e.kind), ['text', 'image', 'text']);
assert.equal(leadingEquation.buffer.split('Agent Pi Dog:').length - 1, 1);
assert.equal(leadingEquation.navigator.herdState, '');
const blocks = [
  {kind: 'text', text: 'Antiderivative\nUse the power rule.', styles: [{paragraph: 0, style: 'subheading'}]},
  {kind: 'media', ...media[0]},
  {kind: 'text', text: 'Result\nEvaluate both limits.', styles: [{paragraph: 0, style: 'subheading'}]},
  {kind: 'media', ...media[0], asset: 'second', url: 'file:///controlled/second.png'},
  {kind: 'text', text: 'That is the area.', styles: []}
];
const ordered = run(650, 'Ignored flat text', false, false, [media[0], blocks[3]], true, false, true, false, [], true, 'Existing text.\n', blocks);
assert.deepEqual(ordered.errors, []);
assert.deepEqual(ordered.events.map(e => e.kind), ['text', 'image', 'text', 'image', 'text']);
assert.equal(ordered.buffer.split('Agent Pi Dog:').length - 1, 1, 'one label for the whole composed reply');
assert(ordered.events[0].text.includes('Antiderivative'));
assert(ordered.events[2].text.includes('Result'));
assert(ordered.events[4].text.includes('That is the area.'));
assert.equal(ordered.styled.filter(s => s.type === 2).length, 3, 'label and two headings, no duplicate label styling');
assert.equal(ordered.navigator.herdState, '', 'acknowledge only after all ordered blocks');
// A lesson's later caption appends at the document end. When the first caption
// went in at a point below the ink, wait for its blank lines to land before
// taking the end as the anchor, instead of holding a reply that is fine.
for (const late of [0, 2, 3, 4]) {
  const captions = [{kind: 'text', text: 'A friendly dog.', styles: []}, {kind: 'text', text: 'It trots to the bowl.', styles: []}];
  const settled = run(650, '', false, false, [], true, false, true, false, [], false, 'Existing text.\n', captions, true, late);
  assert.deepEqual(settled.errors, [], 'late gap ' + late);
  assert.match(settled.buffer, /Existing text\.\n\n+\nAgent Pi Dog:\nA friendly dog\.\nIt trots to the bowl\.\n$/);
}
{
  // A reply whose reader's name is handwritten has no typed label: an empty label paragraph, then the reply.
  const captions = [{kind: 'text', text: 'A friendly dog.', styles: []}, {kind: 'text', text: 'It trots to the bowl.', styles: []}];
  const unlabeled = run(650, '', false, false, [], true, false, true, false, [], false, 'Existing text.\n', captions, true, 3, '');
  assert.deepEqual(unlabeled.errors, []);
  assert.match(unlabeled.buffer, /Existing text\.\n\n+\n\nA friendly dog\.\nIt trots to the bowl\.\n$/);
}
const heldOrdered = run(650, '', false, false, media, false, false, true, false, [], false, '', blocks.slice(0, 3));
assert.equal(heldOrdered.errors.length, 1);
assert.deepEqual(heldOrdered.events.map(e => e.kind), ['text', 'image'], 'do not insert later prose or resend an unconfirmed image');
assert.notEqual(heldOrdered.navigator.herdState, '');
const earlyGeometry=run(650,'',false,false,media,false,false,true,false,[],false,'',blocks.slice(0,3),true);
assert.deepEqual(earlyGeometry.events.map(e=>e.kind),['text','image','text'],'settled native image permits the next caption before disk save');
assert.equal(earlyGeometry.insertedImages.length,1,'never repeat insertion during a save wait');
assert.equal(earlyGeometry.errors.length,1,'missing saved pixels must STILL fail final verification');
assert.notEqual(earlyGeometry.navigator.herdState,'','geometry alone never acknowledges the reply');
assert(!earlyGeometry.requests.some(r=>r.route==='/native-text-done'));
const savedGeometry=run(650,'',false,false,media,true,false,true,false,[],false,'',blocks.slice(0,3),true);
assert.deepEqual(savedGeometry.errors,[]);
assert.deepEqual(savedGeometry.requests.map(r=>r.route),['/notebook-media-proof','/notebook-ink-proof','/native-text-done']);
assert.equal(savedGeometry.requests[0].payload.assets,undefined,'final image check must include ALL assets');
// Diagnostic snapshots are bounded, data-minimal and never substitute for the
// saved-image gate above. In particular, selected-image=true is not completion.
const observations = [];
let observeTime = 100;
const observedController = {working:false, selectionItemCount:0, selectionContainsImage:false,
  itemCount:NaN, itemsBoundingRect:{x:0,y:0,width:20,height:30}};
const observed = vm.createContext({root:{sceneController:observedController},
  Date:{now:()=>observeTime}, console:{warn:line=>observations.push(line)}});
vm.runInContext(definition('herdImageObservation'),observed);
const observationWork = {reply:{text:'PRIVATE NOTE',media:[{url:'file:///private/asset.png'}]}};
observed.herdImageObservation(observationWork,'before');
observeTime = 120;
observedController.selectionContainsImage = true;
observed.herdImageObservation(observationWork,'returned');
for(let n=0;n<30;n++) observed.herdImageObservation(observationWork,'poll');
assert.equal(observations.length,2,'unchanged polling must not flood the journal');
assert(observations[1].includes('elapsed=20'));
assert(!observations.join('').includes('PRIVATE') && !observations.join('').includes('file:'));
assert.equal(observationWork.mediaVerified,undefined,'observation cannot approve persistence');
Object.defineProperty(observedController,'itemsBoundingRect',{get(){throw Error('unavailable');}});
assert.doesNotThrow(()=>observed.herdImageObservation(observationWork,'poll'));
const illustrated = run(650, 'An equation follows.', false, false, media);
assert.deepEqual(illustrated.errors, []);
assert.equal(illustrated.insertedImages.length, 1);
const position = illustrated.insertedImages[0].position;
assert.equal(position.x, 250 + media[0].width / 2, 'image centre must preserve the text left edge');
assert(position.y > 650 + media[0].height / 2, 'image must be below prose, not centred across it');
const missingImage = run(650, 'Keep the reply held on image failure.', false, false, media, false);
assert.equal(missingImage.errors.length, 1);
assert.notEqual(missingImage.navigator.herdState, '');
const stale = run(650, 'Several lines\nof prose\nbefore the image.', false, false, media, true, true);
assert.deepEqual(stale.errors, []);
const proseBottom = 100 + ((stale.buffer.match(/\n/g) || []).length + 1) * 50;
assert(stale.insertedImages[0].position.y - media[0].height / 2 >= proseBottom + 50,
  'image must clear full text bounds even with a stale cursor');
const openMoves = [];
const opening = vm.createContext({
  herdTitle: 'To pidog', herdPage: 'page', herdFollowedPage: '', herdMine: false,
  herdOpenPasses: 0, herdOpenTimer: {stop() {}},
  herdResumeHeld() {}, // recovery requests have their own request/page-guard suite
  navigator: {herdUuid(value) { return value; }},
  root: {sceneController: {pageId: 'page', itemsBoundingRect: {y: 0, height: 3200},
    rootDocumentBoundingRect: {y: 0, height: 2500}}},
  sceneView: {height: 1872, sceneToView(point) { return point; },
    tileManager: {moveViewBy(point) { openMoves.push(point); }}},
  Qt: {point(x, y) { return {x, y}; }}
});
vm.runInContext(definition('herdFollowLatest'), opening);
opening.herdFollowLatest();
assert.equal(openMoves.length, 1);
assert.equal(openMoves[0].y, 1872 - 450 - 3200, 'reopen must follow last ink/image, not just text');
opening.herdFollowLatest();
assert.equal(openMoves.length, 1, 'must not override subsequent manual scrolling');
opening.herdFollowedPage = ''; opening.root.sceneController.pageId = 'other';
opening.herdFollowLatest();
assert.equal(openMoves.length, 1, 'must not follow stale bounds from another page');
console.log('Native layout: padding, focus, scroll, page guard, images, explicit viewport save and one-shot latest-on-open passed.');

// Exercise the real ordered caption handoff, without changing the established
// handwriting-to-first-reply placement or weakening its minimum ink boundary.
let caption;
const captionJob={nativeInkUsed:true};
const captions=vm.createContext({root:{sceneController:{rootDocumentBoundingRect:{x:-468,y:100,width:936,height:200},textLineHeight:70,
  focusRootDocument(){},setCursorPosition(){}},enterTextMode(){}},
  Qt:{point(x,y){return {x,y};}},SceneController:{MoveAnchor:0,OverscrollAlwaysAllowed:2},
  herdLayout(work){caption=work;}});
vm.runInContext(definition('herdOrdered'),captions);
captions.herdOrdered({job:captionJob,reply:{request:'request'},ordered:[{kind:'text',text:'Caption.'}],blockNext:0,mediaBottom:600});
assert.equal(caption.target,630);assert.equal(caption.inkBottom,600);
assert.equal(caption.compactInk,true);assert.equal(caption.continuation,true);
assert(source.includes('work.compactInk ? "" : "\\n"'),'compact native caption must not add a redundant blank paragraph');

// A before-layout capture may leave a hidden cursor parked at 0. The actual
// reply entry MUST establish the server's below-ink point before layout can
// insert anything. Exercise both plain and ordered replies through herdText.
for (const ordered of [false,true]) {
  const events=[], job={request:'req',path:'doc/page.rm',page:'page'};
  const c={hasRootDocument:true,textCursorIndex:0,rootDocumentLength:100,
    textCursorPosition:{x:0,y:234},
    setCursorPosition(point){events.push('position');this.textCursorPosition=point;this.textCursorIndex=100;},
    replaceText(){throw Error('No insertion before target positioning');}};
  const ctx=vm.createContext({
    root:{sceneController:c,enterTextMode(requestFocus,point){assert.equal(requestFocus,true);assert.equal(point.y,900);events.push('focus');}},
    navigator:{herdJob:job,herdHttp(method,route,payload,done){
      assert.equal(route,'/native-text');done(200,{request:'req',top:900,inkBottom:850,text:'Answer',
        ...(ordered?{blocks:[{kind:'text',text:'Caption'},{kind:'ink',playback:{}}]}:{})});
    },herdFail(){throw Error('unexpected failure');}},
    herdContextSurface:'surface',herdContextRevision:2,herdContextInk:0,
    herdLessonCurrent:()=>true,herdStopLessonImport(){},
    sceneView:{viewToScene:p=>p},Qt:{point:(x,y)=>({x,y})},
    SceneController:{MoveAnchor:0,OverscrollAlwaysAllowed:2},console:{warn(){}},
    herdLayout(work){assert.deepEqual(events,['focus','position']);assert.equal(c.textCursorIndex,100);
      assert.equal(work.target,900);assert.equal(work.inkBottom,850);events.push('layout');}
  });
  vm.runInContext(definition('herdText'),ctx);
  ctx.herdText(null,null,{command:{phase:'before'},samples:[]});
  assert.deepEqual(events,['focus','position','layout']);
}
