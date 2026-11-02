const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
const start = source.indexOf('function herdLessonCurrent(');
const end = source.indexOf('\n\t\t\t\tTimer { id: herdLessonImportTimer;', start);
function harness() {
  let callback, imports=0, disconnected=0;
  const requests=[], failures=[];
  const job={doc:'destination',page:'page',path:'destination/page.rm'};
  const ctx=vm.createContext({
    herdLessonImport:null, herdMine:true, herdPage:'page', herdContextSurface:'surface',
    herdContextRevision:2,herdContextInk:3,
    sceneView:{document:{id:'destination'},isLoading:false},root:{inSuspend:false},
    herdLessonImportTimer:{stop(){},restart(){}},
    navigator:{herdJob:job,herdUuid:x=>x,herdFail:(status,result)=>failures.push(result)},
    Library:{entryAdded:{connect(fn){callback=fn;},disconnect(fn){assert.equal(fn,callback);disconnected++;}},
      entryForId:id=>({id,visibleName:id==='unrelated'?'Other':'Agent lesson source source',idForPage:i=>'native-page-'+i})},
    DocumentImporter:{importFromUrls(urls,parent){imports++;assert.equal(urls[0],'file:///home/root/.cache/herd-board/imports/source.rmdoc');assert.equal(parent,'folder');}},
    herdText:(body,frozen)=>requests.push({body,frozen})
  });
  vm.runInContext(source.slice(start,end),ctx);
  const frozen={job,surface:'surface',revision:2,ink:3};
  const reply={request:'request',import_source:{doc:'source',parent:'folder',pages:3}};
  return {ctx,frozen,reply,requests,failures,event:id=>callback(id),counts:()=>({imports,disconnected})};
}
let h=harness();
for(const count of [1,2,3,7]) {
  const small=harness();small.reply.import_source.pages=count;
  small.ctx.herdImportLesson(small.reply,small.frozen);
  small.event('native-document');small.ctx.herdLessonImportTick();
  assert.equal(small.requests.length,1);
}
for(const count of [0,20,1.5,'1',null,undefined,NaN]) {  // a lesson: 7 pictures and 12 handwritten regions at most
  const bad=harness();bad.reply.import_source.pages=count;
  assert.throws(()=>bad.ctx.herdImportLesson(bad.reply,bad.frozen));
  assert.equal(bad.counts().imports,0);
}
for(const count of [1,8,12]) {
  const story=harness();Object.assign(story.reply.import_source,{pages:count,story_version:1});
  story.ctx.herdImportLesson(story.reply,story.frozen);
  story.event('native-document');story.ctx.herdLessonImportTick();
  assert.equal(story.requests.length,1);
}
for(const spec of [{pages:13,story_version:1},{pages:20},{pages:3,story_version:2},
                   {pages:3,story_version:true},{pages:3,story_version:'1'}]) {
  const bad=harness();Object.assign(bad.reply.import_source,spec);
  assert.throws(()=>bad.ctx.herdImportLesson(bad.reply,bad.frozen));
  assert.equal(bad.counts().imports,0);
}
h.ctx.herdImportLesson(h.reply,h.frozen);
assert.equal(h.requests.length,0,'no foreground insertion before native import');
h.event('unrelated');h.ctx.herdLessonImportTick();assert.equal(h.requests.length,0);
h.event('native-document');h.event('native-document');h.ctx.herdLessonImportTick();
assert.equal(h.requests.length,1);
assert.equal(h.requests[0].body.doc,'native-document');
assert.equal(h.requests[0].body.request,'request');
assert.deepEqual(h.counts(),{imports:1,disconnected:1});
h.event('native-document');h.ctx.herdLessonImportTick();assert.equal(h.requests.length,1);
for(const change of [c=>c.herdPage='other',c=>c.herdContextInk++,c=>c.herdContextRevision++,
                    c=>c.navigator.herdJob={...c.navigator.herdJob},c=>c.root.inSuspend=true]) {
  h=harness();h.ctx.herdImportLesson(h.reply,h.frozen);change(h.ctx);
  h.event('native-document');h.ctx.herdLessonImportTick();
  assert.equal(h.requests.length,0);assert.equal(h.failures.length,1);
  assert.equal(h.counts().disconnected,1);
}
h=harness();h.ctx.herdImportLesson(h.reply,h.frozen);
for(let i=0;i<81;i++)h.ctx.herdLessonImportTick();
h.event('native-document');h.ctx.herdLessonImportTick();
assert.equal(h.requests.length,0);assert.equal(h.failures.length,1);
assert.equal(h.counts().imports,1,'timeout never reimports or resends');
console.log('Native lesson import: one import, native IDs, changed-input holds, duplicate/late callbacks and timeout passed.');
