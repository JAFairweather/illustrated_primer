// Actual playback validation and successful commit handoff; no device required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
function definition(name) {
  const start = source.indexOf(`function ${name}(`);
  const ends = ['\n\t\t\t\tfunction ', '\n\t\t\t\tTimer {']
    .map(token => source.indexOf(token, start + 1)).filter(index => index >= 0);
  assert(start >= 0 && ends.length);
  return source.slice(start, Math.min(...ends));
}
const ctx = vm.createContext({});
vm.runInContext(['herdPlaybackProgram', 'herdInkFinish'].map(definition).join('\n'), ctx);
function block() {
  return {width:600, height:200, stroke_count:1, point_count:2,
    role:'equation', stage_index:0, stage_count:1,
    playback:{version:1, velocity:300, pen_up_ms:70, minimum_stroke_ms:50,
      paths:[[[20,20],[20,101.27]]], duration_ms:1000*81.27/300}};
}
function finish(mutate=()=>{}, error=null) {
  const b = block(), work = {job:{},blockNext:4,mediaBottom:300};
  const a = {block:b,work,origin:[0,500],playbackProgram:ctx.herdPlaybackProgram(b),
    ownsLock:true,view:{destroy(){}}};
  let continued=0, stopped=0;
  const failures=[];
  Object.assign(ctx,{herdInk:a,herdPasteBusy:true,herdInkTimer:{stop(){}},
    herdPlaybackStop(){stopped++;},herdLater(fn){fn();},herdTextDone(){continued++;},
    navigator:{herdFail(st,r){failures.push(r.error);}}});
  mutate(a);
  ctx.herdInkFinish(error);
  return {a,work,continued,stopped,failures};
}
const good=finish();
assert.equal(good.work.mediaBottom,632,'ceil(actual ink bottom) + unchanged 30-unit clearance');
assert.equal(good.a.block.height,200,'original playback and paste region is not resized');
assert.equal(good.a.playbackProgram.bottom,101.27);
assert.equal(good.work.blockNext,5);
assert.equal(good.work.job.nativeInkUsed,true);
assert.equal(good.continued,1);
assert.equal(good.stopped,1);
assert.equal(ctx.herdInk,null);
assert.equal(ctx.herdPasteBusy,false);
// All diagram stages, non-playback assets and malformed/unknown measurements
// retain full reservation; an earlier larger reservation is never reduced.
for (const mutate of [a=>delete a.block.role,a=>a.block.stage_count=2,
    a=>a.block.stage_index=1,a=>a.playbackProgram=null,
    ...[undefined,NaN,Infinity,-1,0,201,'101'].map(bottom=>a=>a.playbackProgram.bottom=bottom)]) {
  assert.equal(finish(mutate).work.mediaBottom,730);
}
assert.equal(finish(a=>a.work.mediaBottom=900).work.mediaBottom,900);
assert.equal(finish(a=>a.block.role='hand').work.mediaBottom,612,'handwritten words release unused canvas and run on with a 10-unit gap');
assert.equal(finish(a=>a.block.role='lesson').work.mediaBottom,730);
assert.equal(finish(a=>a.playbackProgram.bottom=199.9).work.mediaBottom,730);
const failed=finish(()=>{},'Native commit refused');
assert.equal(failed.work.mediaBottom,300);
assert.equal(failed.work.blockNext,4);
assert.equal(failed.work.job.nativeInkUsed,undefined);
assert.equal(failed.continued,0);
assert.deepEqual(failed.failures,['Native commit refused']);
// The extent comes from the same bounded points that are played/pasted, not
// optional block.bounds metadata. Existing point/time/bounds guards still fire.
const b=block(); b.bounds=[0,0,600,1];
assert.equal(ctx.herdPlaybackProgram(b).bottom,101.27);
for(const mutate of [b=>b.playback.paths[0][1][1]=201,
    b=>b.playback.paths[0][1][1]=NaN,b=>b.point_count=3,
    b=>b.playback.duration_ms=1,b=>b.height=199]) {
  const bad=block();mutate(bad);assert.throws(()=>ctx.herdPlaybackProgram(bad));
}
console.log('Native equation spacing: committed standalone math releases only unused bottom canvas; other reservations and failure guards preserved.');
