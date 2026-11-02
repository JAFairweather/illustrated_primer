// A story's head is acknowledged with the next request id: the tablet keeps the job and waits for the rest.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
function definition(name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0);
  const ends = ['\n\t\t\tfunction ', '\n\t\t\t//', '\n\t\t\tTimer {']
    .map(token => source.indexOf(token, start + 1)).filter(i => i >= 0);
  return source.slice(start, Math.min(...ends));
}
const done = source.match(/navigator\.herdHttp\("POST", "\/native-text-done", [^\n]*function\(st, r\) \{\n([\s\S]*?)\n\t*\}\)\n/);
assert(done, 'native-text-done callback found');
function acknowledge(status, reply) {
  const timer = {interval: 2000, restarts: 0, restart() { this.restarts++; }, stop() {}};
  const job = {path: 'doc/page.rm', page: 'p', live: true, request: 'notebook-head', lastRetry: 't',
    nativePlots: {a: 1}, nativeInkUsed: true, nativeLesson: true, blankProse: true, inkFloor: 900};
  const failures = [];
  const navigator = vm.createContext({herdJob: job, herdState: 'writing', herdNote: '', herdTimer: timer});
  vm.runInContext(definition('herdAwaitRest'), navigator);
  navigator.herdFail = (st, r) => failures.push([st, r]);
  vm.runInNewContext('(function(st, r){' + done[1] + '})(status, reply)', {navigator, status, reply});
  return {navigator, job, timer, failures};
}
// The head: same job, the next request, waiting, poll restarted, last write's layout dropped.
let {navigator, job, timer, failures} = acknowledge(200, {state: 'written', page: 'doc/page.rm', next: 'notebook-rest'});
assert.equal(navigator.herdJob, job);
assert.equal(job.request, 'notebook-rest');
assert.equal(navigator.herdState, 'waiting');
assert.equal(navigator.herdNote, 'More of the story');
assert.equal(timer.interval, 250);
assert.equal(timer.restarts, 1);
for (const k of ['nativePlots', 'nativeInkUsed', 'nativeLesson', 'blankProse', 'inkFloor', 'lastRetry']) assert(!(k in job), k);
assert.equal(job.path, 'doc/page.rm');
assert.equal(failures.length, 0);
// An old server (no next) and the rest's own acknowledgement end the job as before.
for (const reply of [{state: 'written', page: 'doc/page.rm'}, null, {next: ''}, {next: null}]) {
  ({navigator, timer} = acknowledge(200, reply));
  assert.equal(navigator.herdJob, null);
  assert.equal(navigator.herdState, '');
  assert.equal(timer.restarts, 0);
}
// A refused acknowledgement fails as before, whatever it carries.
({navigator, failures, timer} = acknowledge(409, {error: 'x', next: 'notebook-rest'}));
assert.equal(failures.length, 1);
assert.equal(timer.restarts, 0);
console.log('A story head keeps its job for the rest; replies without next end the job as before.');
