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
function run(reply, status = 200) {
  const requests = [];
  const context = vm.createContext({
    herdJob: {path: 'doc/page.rm', request: 'notebook-current'},
    herdState: 'failed', herdNote: 'Old failure',
    herdTimer: {stop() {}, restart() {}},
    herdHttp(method, route, payload, done) { requests.push({method, route}); done(status, reply); }
  });
  vm.runInContext(definition('herdDismissFailure') + '\n' + definition('herdStep'), context);
  context.herdStep();
  assert(requests.every(r => r.method === 'GET'), 'recovery must never write or resend');
  return context;
}
const recovered = run({state: 'written', request: 'notebook-current'});
assert.equal(recovered.herdState, '');
assert.equal(recovered.herdJob, null);
assert.equal(recovered.herdNote, '');
for (const reply of [null, {state:'ready', request:'notebook-current'},
  {state:'written', request:'notebook-other'}, {state:'unknown'}]) {
  assert.equal(run(reply).herdState, 'failed');
}
assert.equal(run({state:'written', request:'notebook-current'}, 500).herdState, 'failed');
assert.equal(run({state:'ready', request:'notebook-current', retry_token:'explicit-repair'}).herdState, 'ready');
assert.equal(run({state:'ready', request:'notebook-other', retry_token:'explicit-repair'}).herdState, 'failed');
const resumeStart = source.indexOf('function herdResumeHeld(');
const resumeSource = source.slice(resumeStart, source.indexOf('\n\t\t\t\tfunction herdFollowLatest', resumeStart));
function resume(reply, changePage = false) {
  let done;
  const context = vm.createContext({
    herdPage:'page', herdTitle:'To pidog', herdResumeCheckedPage:'', herdResumeInFlight:false,
    root:{currentPage:0}, sceneView:{document:{id:'doc'}},
    navigator:{herdJob:null, herdState:'', herdUuid(x) {return x;},
      herdHttp(method, route, body, callback) {assert.equal(method,'GET'); done=callback;}}
  });
  vm.runInContext(resumeSource, context);
  context.herdResumeHeld();
  if (changePage) context.herdPage='other-page';
  done(200,reply);
  return context;
}
assert.equal(resume({state:'ready',request:'request'}).navigator.herdJob,null);
assert.equal(resume({state:'writing',request:'request',retry_token:'repair'}).navigator.herdJob,null);
assert.equal(resume({state:'ready',request:'request',retry_token:'repair'},true).navigator.herdJob,null);
const resumed=resume({state:'ready',request:'request',retry_token:'repair'});
assert.equal(resumed.navigator.herdState,'ready');
assert.equal(resumed.navigator.herdJob.path,'doc/page.rm');
assert.equal(resumed.navigator.herdJob.request,'request');
const pendingCallbacks = [];
const waiting = vm.createContext({
  herdJob: {path: 'doc/page.rm', request: 'notebook-current'},
  herdState: 'waiting', herdNote: 'Sent to pidog',
  herdTimer: {stop() {}, restart() {}},
  herdHttp(method, route, payload, done) { pendingCallbacks.push(done); }
});
vm.runInContext(definition('herdStep'), waiting);
waiting.herdStep(); waiting.herdStep();
pendingCallbacks.shift()(200, {state:'waiting', request:'notebook-other', media_pending:true});
assert.equal(waiting.herdNote, 'Sent to pidog', 'wrong request cannot change progress');
pendingCallbacks.shift()(200, {state:'waiting', request:'notebook-current', media_pending:true});
assert.equal(waiting.herdNote, 'Generating image…');
waiting.herdStep(); waiting.herdStep();
pendingCallbacks.shift()(200, {state:'ready', request:'notebook-current'});
assert.equal(waiting.herdState, 'ready');
waiting.herdState = 'writing';
pendingCallbacks.shift()(200, {state:'ready', request:'notebook-current'});
assert.equal(waiting.herdState, 'writing', 'second ready poll must not trigger another insertion');
waiting.herdState = 'waiting'; waiting.herdStep();
waiting.herdJob = {path:'doc/page.rm', request:'new-request'};
pendingCallbacks.shift()(200, {state:'ready', request:'notebook-current'});
assert.equal(waiting.herdState, 'waiting', 'superseded callback cannot start writing');
console.log('Native recovery: matching save clears errors; only explicit safe repair token retries; no resend or unarmed recovery.');

// Intentional page-change cancellation is not a generic delivery failure.
const notes = vm.createContext({});
vm.runInContext(definition('herdFailureNote'), notes);
assert.equal(notes.herdFailureNote({error:'Notebook model page_changed; request stopped before insertion; no automatic resend'}), 'Page changed — request stopped');
assert.equal(notes.herdFailureNote({error:'Notebook model page_unavailable; request stopped before insertion; no automatic resend'}), 'Page unavailable — request stopped');
for (const reply of [null, {}, {error:'provider diagnostics'}]) {
  assert.equal(notes.herdFailureNote(reply), 'Reply needs attention');
}
assert.equal(notes.herdFailureNote({error:'Notebook model cancelled; reply held, no automatic resend'}),'Request stopped');
const labelStart = source.indexOf('function herdStatusLabel(');
const labelEnd = source.indexOf('\n\t\t\t\tText {',labelStart);
assert(labelStart >= 0 && labelEnd > labelStart);
const label = vm.createContext({herdMine:true, herdPage:'current',
  herdIncompletePage:'', herdIncompleteRequest:'', herdIncompleteDismissed:'',
  navigator:{herdFailureNote:notes.herdFailureNote,herdState:'failed',herdNote:'Page changed — request stopped',herdJob:{live:true,page:'original'}}});
vm.runInContext(source.slice(labelStart,labelEnd),label);
assert.equal(label.herdStatusLabel(), 'Page changed — request stopped\nTap to dismiss');
label.navigator.herdState='ready';
assert.equal(label.herdStatusLabel(), 'Reply waiting on original page');
label.navigator.herdState='waiting';
assert.equal(label.herdStatusLabel(), 'Request on another page');
label.herdPage='original';label.navigator.herdNote='Sent to pidog';
assert.equal(label.herdStatusLabel(), 'Sent to pidog — waiting');
label.navigator.herdState='writing';label.navigator.herdNote='Saving reply…';
assert.equal(label.herdStatusLabel(), 'Saving reply…');
label.navigator.herdState='failed';label.navigator.herdNote='Unrecognized error';
assert.equal(label.herdStatusLabel(), 'Reply needs attention\nTap to dismiss');
label.herdMine=false;
assert.equal(label.herdStatusLabel(), 'RESPOND');
// The waiting-poll callback must use the mapper, not display arbitrary errors.
waiting.herdJob={path:'doc/page.rm',request:'notebook-current'};
waiting.herdState='waiting';waiting.herdFailureNote=notes.herdFailureNote;
waiting.herdStep();
pendingCallbacks.shift()(200,{state:'failed',request:'notebook-current',
  error:'Notebook model page_changed; request stopped before insertion; no automatic resend'});
assert.equal(waiting.herdNote,'Page changed — request stopped');
assert.equal(waiting.herdState,'failed');

for (const state of ['writing', 'waiting', 'failed']) {
  const posts = [];
  const failed = vm.createContext({console: {warn() {}},
    herdJob: {live:true, path:'doc/page.rm', request:'current'}, herdState:state, herdNote:'',
    herdTimer:{restart() {}},
    herdHttp(method, route, body, done) {posts.push({method,route,body}); done(500, null);}
  });
  vm.runInContext(definition('herdFailureNote')+'\n'+definition('herdFail'), failed);
  failed.herdFail(0, {error:'local diagnostic only'});
  assert.equal(failed.herdState, 'failed');
  assert.equal(posts.length, state === 'writing' ? 1 : 0);
  if (posts.length) {
    assert.equal(posts[0].route, '/native-text-failed');
    assert.equal(JSON.stringify(posts[0].body), '{"page":"doc/page.rm","request":"current"}');
    assert.equal(failed.herdNote, 'Reply needs attention');
  }
}

// Every bounded model error has a readable category, without showing provider
// details or suggesting that the user must rewrite a valid handwritten prompt.
const expectedNotes={deadline:'Agent timed out',busy:'Agent is busy',closed:'Agent connection failed',
  unavailable:'Agent connection failed',provider_error:'Agent service failed',
  incomplete_response:'Agent reply was cut short',cancelled:'Request stopped',
  invalid_json:"Reply format wasn't supported",invalid_response:"Reply format wasn't supported",
  reply_too_large:"Reply format wasn't supported",model_mismatch:"Reply format wasn't supported",
  tools_forbidden:"Reply format wasn't supported"};
for(const [code,expected] of Object.entries(expectedNotes)){
  const actual=notes.herdFailureNote({error:`Notebook model ${code}; reply held, no automatic resend`});
  assert.equal(actual,expected);
  assert.equal(notes.herdFailureNote({error:actual}),expected,'safe presentation is idempotent');
  label.herdMine=true;label.navigator.herdState='failed';label.navigator.herdNote=actual;
  assert(label.herdStatusLabel().startsWith(expected+'\n'));
}
assert.equal(notes.herdFailureNote(null,0),'Mac connection lost');
assert.equal(notes.herdFailureNote({},401),'Notebook connection needs setup');
assert.equal(notes.herdFailureNote({},403),'Notebook connection needs setup');
assert.equal(notes.herdFailureNote({},503),'Notebook service unavailable');
assert.equal(notes.herdFailureNote({error:'A notebook request is already pending on this page'}),'Previous reply is still pending');
assert.equal(notes.herdFailureNote({error:'unsupported native text anchor'}),"Reply couldn't be placed");
assert.equal(notes.herdFailureNote({error:'nothing new written since the last answer'}),'No new handwriting found');
assert.equal(notes.herdFailureNote({error:'Caption incomplete: page changed, private diagnostic'}),'Reply may be incomplete');
for(const error of ['Notebook model deadline; private diagnostic', '/private/example/file', '<b>busy</b>',{anything:1}]){
  assert.equal(notes.herdFailureNote({error}),'Reply needs attention');
}
label.navigator.herdNote='Reply may be incomplete';
assert.match(label.herdStatusLabel(),/Inspect the page/);
assert.doesNotMatch(label.herdStatusLabel(),/retry/,'never encourage replay of partial native output');
assert.match(source,/width: Math\.min\(660, herdLabel\.implicitWidth \+ 56\)/);
assert.match(source,/wrapMode: Text\.WordWrap/);
console.log('Native errors: bounded cause/action messages, wrapped labels, no diagnostic leakage or automatic retries.');
