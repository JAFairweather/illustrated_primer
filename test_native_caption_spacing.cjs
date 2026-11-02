// Exercise actual caption handoff and append guards, including async cursors.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
function definition(name) {
  const start = source.indexOf(`function ${name}(`);
  const ends = ['\n\t\t\t\tfunction ', '\n\t\t\t\tTimer {']
    .map(token => source.indexOf(token, start + 1)).filter(index => index >= 0);
  return source.slice(start, Math.min(...ends));
}
function run(change = '', firstCaption = false) {
  const queue = [], errors = [], writes = [], positional = [];
  const original = firstCaption ? 'Agent Pi Dog:\n' : 'Earlier caption.\n';
  const job = {page:'page', nativeInkUsed:!firstCaption, nativeLesson:firstCaption};
  let buffer = original, index = 1, pending, completed = 0, ticks = 0, typed = 0;
  if(change === 'first-caption') { job.nativeInkUsed=false; job.nativeLesson=true; }
  const editor = {
    get rootDocumentLength() { return buffer.length; },
    get textCursorIndex() { return index; },
    get textCursorPosition() { return {x:-468, y:change === 'overlap' ? 590 : 750}; },
    rootDocumentBoundingRect:{x:-468,y:100,width:936,height:700}, textLineHeight:50,
    focusRootDocument() {},
    setCursorIndex(value) { pending = value; },
    setCursorPosition(point) { positional.push(point); },
    replaceText(text) { writes.push(text); buffer = buffer.slice(0,index)+text+buffer.slice(index); }
  };
  const ctx = vm.createContext({root:{sceneController:editor,enterTextMode(){},exitTextMode(){}},
    navigator:{herdJob:job,herdFail(st,r){errors.push(r.error);}},
    herdMine:true,herdPage:'page',herdLater(f){queue.push(f);},herdTextDone(){completed++;},
    herdStartTyping(work,text){typed++;editor.replaceText(text);completed++;},
    Qt:{point(x,y){return {x,y};}},SceneController:{MoveAnchor:0,OverscrollAlwaysAllowed:2},
    SceneParticipant:{RequestedByInputMethod:2},console:{warn(){}}});
  vm.runInContext(['herdLayout','herdOrdered'].map(definition).join('\n'),ctx);
  if(change === 'first-caption') {
    pending=buffer.length;
    ctx.herdLayout({job,reply:{request:'request',label:'Agent Pi Dog:',text:'First cue.'},
      continuation:true,compactInk:true,appendIndex:buffer.length,target:600,
      nativeGap:false,padding:0,passes:0,focusAttempts:0});
  } else ctx.herdOrdered({job,reply:{request:'request',label:'Agent Pi Dog:'},
    ordered:[{kind:'text',text:firstCaption ? 'First cue.' : 'The second step explains why.'}],
    blockNext:0,mediaBottom:firstCaption ? undefined : 600});
  if (change === 'text') buffer += 'New human text';
  if (change === 'page') ctx.herdPage = 'other';
  while(queue.length) {
    assert(++ticks < 20);
    // Deliberately leave a stale mid-paragraph cursor across two callbacks.
    if(ticks === 3 && change !== 'unsettled') index = pending;
    queue.shift()();
  }
  return {original,buffer,writes,errors,positional,completed,ticks,typed};
}
const good = run();
const first = run('first-caption');
assert.deepEqual(first.errors,[]);
assert.equal(first.typed,1,'first cue animates before any ink is inserted');
assert.equal(first.buffer,first.original+'First cue.\n');
// Go through the real ordered handoff, not just a manually compact herdLayout
// call. The first caption follows the label before nativeInkUsed becomes true.
const orderedFirst = run('',true);
assert.deepEqual(orderedFirst.errors,[]);
assert.equal(orderedFirst.typed,1);
assert.equal(orderedFirst.buffer,'Agent Pi Dog:\nFirst cue.\n');
assert.deepEqual(orderedFirst.writes,['First cue.\n']);
assert.equal(orderedFirst.positional.length,0,'first caption must not create a virtual blank paragraph');
assert(orderedFirst.ticks>=3,'first caption must wait for its end cursor too');
for(const kind of ['text','page','unsettled']) {
  const held=run(kind,true);
  assert.equal(held.writes.length,0,'first caption '+kind+' must hold');
  assert.equal(held.errors.length,1);
}
assert.match(source,/herdTypingTimer; interval: 31;/);
assert.deepEqual(good.errors,[]);
assert.equal(good.buffer,good.original+'The second step explains why.\n');
assert.deepEqual(good.writes,['The second step explains why.\n']);
assert.equal(good.completed,1);
assert.equal(good.positional.length,0,'no virtual point/gap before later captions');
assert(good.ticks >= 3,'append waits for native end cursor');
for(const kind of ['text','page','overlap','unsettled']) {
  const held = run(kind);
  assert.equal(held.writes.length,0,kind+' must hold before any content insertion');
  assert.equal(held.errors.length,1);
  assert.equal(held.completed,0);
  assert.equal(held.positional.length,0);
}
console.log('Native caption spacing: append only at settled unchanged text end below picture; changed page/text, overlap and timeout hold.');
