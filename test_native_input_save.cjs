// Native deferred-work hint only; never infer that bytes have been saved.
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/xochitl/herdRespond.qmd', 'utf8');
const start = source.indexOf('function herdRequestInputSave(');
const end = source.indexOf('\n\t\t\t\tText {', start);
assert(start > 0 && end > start);
const doc = '905df7ae-ff54-46b9-a71e-45bb02bef638';
function setup() {
  const calls = [];
  const context = vm.createContext({
    root: {inSuspend: false, sceneController: {requestDeferredCompleted() { calls.push('hint'); }}},
    sceneView: {document: {id: doc}, isLoading: false}, herdPage: 'p',
    navigator: {herdJob: null, herdUuid: x => String(x).replace(/[{}]/g, '')},
    console: {warn() {}}
  });
  vm.runInContext(source.slice(start, end), context);
  return {context, calls};
}
let {context, calls} = setup();
assert.equal(context.herdRequestInputSave(), true);
assert.deepEqual(calls, ['hint']);
assert.equal(context.navigator.herdJob, null, 'no attempt, ACK or retry');
for (const change of ['other-doc', 'no-doc', 'no-page', 'suspended', 'loading', 'job', 'no-controller', 'missing', 'throws']) {
  const s = setup(), c = s.context;
  if (change === 'other-doc') c.sceneView.document.id = 'another';
  if (change === 'no-doc') c.sceneView.document = null;
  if (change === 'no-page') c.herdPage = '';
  if (change === 'suspended') c.root.inSuspend = true;
  if (change === 'loading') c.sceneView.isLoading = true;
  if (change === 'job') c.navigator.herdJob = {request: 'held'};
  if (change === 'no-controller') c.root.sceneController = null;
  if (change === 'missing') delete c.root.sceneController.requestDeferredCompleted;
  if (change === 'throws') c.root.sceneController.requestDeferredCompleted = () => { throw Error('unavailable'); };
  assert.equal(c.herdRequestInputSave(), false, change);
  assert.deepEqual(s.calls, [], change);
}
// Execute the actual click body: dismiss paths must never request a save/send.
const clickStart = source.indexOf('onClicked: {', end);
const clickEnd = source.indexOf('\n\t\t\t\t\t}', clickStart);
const click = source.slice(clickStart + 'onClicked: {'.length, clickEnd).trim().replace(/\}$/, '');
for (const state of ['normal', 'failed', 'incomplete']) {
  const actions = [];
  vm.runInNewContext('(function(){' + click + '})()', {
    root: {currentPage: 0, currentPageId: 'p'}, sceneView: {document: {id: doc}},
    LibraryController: {setLastOpenedPage() { actions.push('last-page'); }},
    navigator: {herdState: state, herdJob: {request: 'r', page: 'p'},
      herdDismissFailure() { actions.push('dismiss'); }, herdRespond() { actions.push('send'); }},
    herdButton: {herdMine: state === 'failed', herdDismissIncomplete() { return state === 'incomplete'; },
      herdNewQuestionRequest() { return ''; }, herdRequestInputSave() { actions.push('hint'); }}
  });
  assert.deepEqual(actions, state === 'normal' ? ['last-page', 'hint', 'send'] : state === 'failed' ? ['dismiss'] : []);
}
console.log('Input save hint: isolated document, once before send, unavailable no-op, dismissal paths untouched.');
