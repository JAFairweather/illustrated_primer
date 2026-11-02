const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
function definition(name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0);
  const ends = ['\n\t\t\t\tfunction ', '\n\t\t\t\t//', '\n\t\t\t\tproperty ']
    .map(token => source.indexOf(token, start + 1)).filter(i => i >= 0);
  return source.slice(start, Math.min(...ends));
}
// James turned the page while "Saving reply…": once every drawing stage had committed, the reply ends as left.
function run({saving, status = 200}) {
  const requests = [], failures = [];
  const job = {page: 'page-a', path: 'doc/page-a.rm'};
  const work = {job, reply: {request: 'notebook-r'}, saving};
  const context = vm.createContext({
    herdMine: true, herdPage: 'page-b', herdProofWork: work, console: {log() {}},
    root: {exitTextMode() {}},
    navigator: {herdJob: job, herdState: 'writing', herdNote: 'Saving reply…',
      herdFail(st, r) { failures.push(r && r.error); },
      herdHttp(method, route, body, done) { requests.push({method, route, body}); done(status, {state: 'left'}); }}
  });
  vm.runInContext(definition('herdLeftPage') + '\n' + definition('herdTextDone'), context);
  context.herdTextDone(work);
  context.herdTextDone(work);  // the quiet-check timer may ask again: still one request
  return {context, requests, failures};
}
const left = run({saving: true});
assert.equal(left.requests.length, 1);
assert.deepEqual([left.requests[0].method, left.requests[0].route], ['POST', '/native-text-left']);
assert.equal(left.requests[0].body.request, 'notebook-r');
assert.equal(left.context.navigator.herdJob, null);
assert.equal(left.context.navigator.herdState, '');
assert.equal(left.context.herdProofWork, null);
assert.deepEqual(left.failures, []);
// Before the save check began, leaving the page still holds the reply as before.
const early = run({saving: false});
assert.equal(early.requests.length, 0);
assert.match(early.failures[0], /Return to the original page/);
// A refused left stays a failure the page shows.
assert.equal(run({saving: true, status: 400}).failures.length, 1);
console.log('ok left page');
