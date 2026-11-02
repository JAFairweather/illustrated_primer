const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
const start = source.indexOf('function herdAuditView(');
const end = source.indexOf('\n\t\t\t\t// Geometry only:', start);
assert(start > 0 && end > start);
function fixture() {
  const moves = [];
  const job = {id:'a'.repeat(32),doc:'905df7ae-ff54-46b9-a71e-45bb02bef638',
    page:'3ad12986-0467-48fe-986d-d1bd480c4777',surface:'surface',
    view:[1,0,0,1,-702,1200],content_revision:5,ink_revision:8,dy:1000};
  const c = vm.createContext({herdAuditSeen:'',herdPage:job.page,herdContextSurface:'surface',
    herdContextRevision:5,herdContextInk:8,herdInk:null,herdPasteBusy:false,herdProbeJob:null,
    root:{inSuspend:false,sceneController:{working:false}},
    sceneView:{document:{id:job.doc},isLoading:false,penClose:false,
      strokeHandler:{timeSincePenUp(){return 2000;}},
      tileManager:{moveViewBy(point){moves.push(point);}}},
    navigator:{herdJob:null,herdUuid(x){return x;}},
    herdInkView(){return [1,0,0,1,-702,1200];},
    Qt:{point(x,y){return {x,y};}},Date:{now(){return 10000;}}});
  vm.runInContext(source.slice(start,end),c);
  return {c,job,moves};
}
let {c,job,moves} = fixture();
assert.equal(c.herdAuditView(job,9000),true);
assert.deepEqual(moves,[{x:0,y:1000}]);
assert.equal(c.herdAuditView(job,9000),false,'never replay');
for (const mutate of [
  f=>f.job.dy=1201, f=>f.job.dy=0, f=>f.job.dy=NaN, f=>f.job.dy=1.5,
  f=>f.job.dy='100', f=>f.job.doc='other',f=>f.job.page='other',f=>f.job.surface='other',
  f=>f.job.view[5]++,f=>f.job.view[0]=NaN,f=>f.job.view=[1,0],
  f=>f.job.ink_revision++,f=>f.job.content_revision++,f=>f.c.herdPage='other',
  f=>f.c.herdContextSurface='other',f=>f.c.navigator.herdJob={},
  f=>f.c.herdInk={},f=>f.c.herdPasteBusy=true,f=>f.c.herdProbeJob={},
  f=>f.c.root.inSuspend=true,f=>f.c.sceneView.isLoading=true,
  f=>f.c.root.sceneController.working=true,f=>f.c.sceneView.penClose=true,
  f=>f.c.sceneView.strokeHandler.timeSincePenUp=()=>0,
  f=>f.c.herdInkView=()=>[.5,0,0,.5,-702,1200],
]) {
  const f=fixture();mutate(f);
  assert.equal(f.c.herdAuditView(f.job,9000),false);
  assert.equal(f.moves.length,0);
  assert.equal(f.c.herdAuditView(f.job,9000),false,'refusal is terminal for that command');
}
for (const reportedAt of [6999,10001,undefined,NaN,'9000']) {
  const f=fixture();assert.equal(f.c.herdAuditView(f.job,reportedAt),false);assert.equal(f.moves.length,0);
}
assert(source.includes('r.accepted && r.audit_view) herdAuditView(r.audit_view, reportedAt)'));
console.log('Native view audit: one bounded view-only move; expiry, page/surface/revision/affine, pen-idle and busy guards passed.');
