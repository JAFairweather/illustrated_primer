// Exercise the actual injected telemetry function without device side effects.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'xochitl/herdRespond.qmd'), 'utf8');
const begin = source.indexOf('function herdReportContext(');
const end = source.indexOf('\n\t\t\t\t// Read-only hidden asset', begin);
assert(begin > 0 && end > begin);
const calls = [];
let callback;
let resumes = 0;
const context = vm.createContext({
  herdContextBusy: false, herdContextSurface: '1793050000000-1',
  herdContextSequence: 0, herdContextRevision: 3, herdContextInk: 2,
  herdContextRepairSeen: '', herdResumeCheckedPage: 'page',
  herdContextLayoutSignature: '',
  herdAwakeUntil: 0, herdAwakeActive: false,
  herdResumeHeld() { resumes++; },
  herdObserveIncomplete() {}, // Exercised with actual QMD in test_native_incomplete.
  herdTitle: 'To pidog', herdPage: 'page',
  root: {inSuspend: false, sceneController: {rootDocumentBoundingRect: {x: -450, y: 300, width: 1000, height: 500}}},
  sceneView: {document: {id: 'document'}, isLoading: false, width: 1404, height: 1872,
    viewToScene(p) { return {x: p.x*.5-702, y: p.y*.5+936}; }},
  navigator: {herdUuid(v) { return String(v); }, herdHttp(method, route, body, done) {
    calls.push({method, route, body: JSON.parse(JSON.stringify(body))}); callback = done;
  }}, Qt: {point(x, y) { return {x, y}; }}
});
vm.runInContext(source.slice(begin, end), context);
context.herdReportContext();
assert.equal(calls.length, 1);
assert.equal(calls[0].route, '/native-context');
assert.deepEqual(calls[0].body.view, [.5, 0, 0, .5, -702, 936]);
assert.equal(calls[0].body.content_revision, 3);
assert.equal(calls[0].body.ink_revision, 2);
assert.equal(calls[0].body.active, true);
assert(!JSON.stringify(calls[0].body).includes('text:'));
context.herdReportContext();
assert.equal(calls.length, 1, 'never overlap in-flight reports');
callback(400, {});
assert.equal(context.herdContextBusy, false, 'telemetry failure cannot freeze notebook');
context.root.inSuspend = true;
context.herdReportContext();
assert.equal(calls[1].body.active, false);
callback(200, {});
context.herdTitle = 'Ordinary private notebook';
context.herdReportContext();
assert.equal(calls.length, 2, 'do not report non-agent notebooks');
context.herdTitle = 'To pidog';
context.root.inSuspend = false;
context.herdReportContext();
context.herdPage = 'other-page';
callback(200, {repair: {request:'held', token:'repair-1'}});
assert.equal(resumes, 0, 'late repair hint cannot follow navigation');
context.herdPage = 'page';
context.herdReportContext();
callback(200, {repair: {request:'held', token:'repair-1'}});
assert.equal(resumes, 1, 'explicit hint revalidates through existing resume GET');
assert.equal(context.herdResumeCheckedPage, '');
context.herdReportContext();
callback(200, {repair: {request:'held', token:'repair-1'}});
assert.equal(resumes, 1, 'same repair hint cannot repeat');
context.navigator.herdJob = {};
context.herdReportContext();
callback(200, {repair: {request:'held', token:'repair-2'}});
assert.equal(resumes, 1, 'never replace a current job');
context.root.sceneController.rootDocumentLength = 50;
context.herdReportContext();
assert(calls.at(-1).body.content_revision > 3, 'layout/length change increments revision even without a signal');
callback(200, {});
context.herdReportContext();
callback(200, {accepted: true, keep_awake_seconds: 180});
assert.equal(context.herdAwakeActive, true);
const expiry = context.herdAwakeUntil;
context.herdReportContext();
callback(200, {accepted: true, keep_awake_seconds: 181});
assert.equal(context.herdAwakeUntil, expiry, 'reject unbounded sleep inhibition');
context.herdReportContext();
callback(200, {accepted: true, keep_awake_seconds: 0});
assert.equal(context.herdAwakeActive, false, 'explicit disarm releases native inhibitor');
assert(source.includes('function onDocumentContentChanged() { herdButton.herdContextRevision++ }'));
assert(source.includes('function onStrokeCompleted() { herdButton.herdContextInk++ }'));
console.log('Native context: affine geometry, revision counters, no overlapping reports, inactive/private-notebook handling passed.');

// Explicit handoff must wait for the existing HTTP report acceptance, never
// confuse dispatch with delivery or accept an out-of-order sequence response.
let reported=[];
context.herdReportContext(ok=>reported.push(ok));
assert.deepEqual(reported,[]);
callback(200,{accepted:true});assert.deepEqual(reported,[true]);
context.herdReportContext(ok=>reported.push(ok));
callback(200,{accepted:false});assert.deepEqual(reported,[true,false]);
context.herdReportContext(ok=>reported.push(ok));
callback(500,{});assert.deepEqual(reported,[true,false,false]);
context.herdContextBusy=true;
context.herdReportContext(ok=>reported.push(ok));
assert.equal(reported.at(-1),false);
