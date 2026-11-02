// A reply stopped before any of it reached the page is asked again by itself; one partly written never is.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
function definition(name, indent) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0, name);
  const ends = [`\n${indent}function `, `\n${indent}//`, `\n${indent}Timer {`, `\n${indent}property `]
    .map(token => source.indexOf(token, start + 1)).filter(i => i >= 0);
  return source.slice(start, Math.min(...ends));
}
function fail(touched, reply) {
  const posts = [];
  const job = {path: 'doc/page.rm', request: 'notebook-current', live: true, page: 'p', ...(touched ? {touched: true} : {})};
  const ctx = vm.createContext({console: {warn() {}}, herdJob: job, herdState: 'writing', herdNote: '',
    herdTimer: {restart() {}}, herdFailureNote() { return 'Reply may be incomplete'; },
    herdHttp(method, route, body, done) { posts.push({route, body}); done(200, reply(body)); }});
  vm.runInContext(definition('herdFail', '\t\t\t'), ctx);
  ctx.herdFail(0, {error: 'Native drawing page or input changed; reply held'});
  return {ctx, job, posts};
}
const echo = body => ({state: 'failed', request: body.request, ...(body.untouched ? {untouched: true} : {})});
let f = fail(false, echo);
assert.equal(f.posts[0].route, '/native-text-failed'); assert.equal(f.posts[0].body.untouched, true);
assert.equal(f.job.autoAsk, true); assert.equal(f.ctx.herdNote, 'Paused for your writing; asking again');
f = fail(true, echo);
assert.equal(f.posts[0].body.untouched, false); assert.notEqual(f.job.autoAsk, true, 'partly written: James looks first');
assert.equal(f.ctx.herdNote, 'Reply may be incomplete');
f = fail(false, body => ({state: 'failed', request: body.request}));
assert.notEqual(f.job.autoAsk, true, 'the server did not confirm (a drawing stage was claimed)');

function button(job) {
  const asks = [];
  let penUp = 5000, dismissed = 0;
  const nav = {herdJob: job, herdState: 'failed', herdNote: 'Paused for your writing; asking again',
    herdDismissFailure() { dismissed++; nav.herdJob = null; nav.herdState = ''; },
    herdRespond(doc, idx, page, supersedes) { asks.push({doc, idx, page, supersedes}); nav.herdJob = {page, request: 'notebook-next', autoAsk: false}; nav.herdState = 'saving'; }};
  const ctx = vm.createContext({console: {log() {}}, navigator: nav, herdMine: true, herdPage: 'p', herdAutoAsks: 0,
    herdIncompleteDismissed: '', herdIncompletePage: '',
    root: {inSuspend: false, currentPage: 3, currentPageId: 'p'}, LibraryController: {setLastOpenedPage() {}},
    sceneView: {isLoading: false, document: {id: 'doc'}, penClose: false, strokeHandler: {timeSincePenUp() { return penUp; }}},
    herdRequestInputSave() {}});
  vm.runInContext(['herdAutoAskTick', 'herdNewQuestionRequest'].map(n => definition(n, '\t\t\t\t')).join('\n'), ctx);
  return {ctx, nav, asks, setPen(ms) { penUp = ms; }, get dismissed() { return dismissed; }};
}
const b = button({page: 'p', request: 'notebook-current', autoAsk: true});
b.setPen(1000); b.ctx.herdAutoAskTick(); assert.equal(b.asks.length, 0, 'waits until the pen has been still 3 s');
b.ctx.sceneView.penClose = true; b.setPen(9000); b.ctx.herdAutoAskTick(); assert.equal(b.asks.length, 0);
b.ctx.sceneView.penClose = false; b.ctx.herdAutoAskTick();
assert.equal(b.asks.length, 1); assert.equal(b.dismissed, 1);
assert.equal(b.asks[0].supersedes, 'notebook-current', 'an explicit new question that supersedes the stopped one');
b.ctx.herdAutoAskTick(); assert.equal(b.asks.length, 1, 'once per stop');
const other = button({page: 'q', request: 'notebook-current', autoAsk: true});
other.ctx.herdAutoAskTick(); assert.equal(other.asks.length, 0, 'never on another page');
const plain = button({page: 'p', request: 'notebook-current'});
plain.ctx.herdAutoAskTick(); assert.equal(plain.asks.length, 0, 'only when the server confirmed nothing was written');
const third = button({page: 'p', request: 'notebook-current', autoAsk: true}); third.ctx.herdAutoAsks = 2;
third.ctx.herdAutoAskTick(); assert.equal(third.asks.length, 0, 'at most twice in a row');
assert.equal(third.nav.herdNote, 'Reply needs attention');
console.log('Auto re-ask: untouched stops ask again after the pen is still; partly written or unconfirmed stops never do.');
