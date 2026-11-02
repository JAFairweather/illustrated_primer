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
// A drawing that would land below the screen scrolls the view down once, waits, then draws (2026-11-01 22:30).
function run(textBottom) {
  const moves = [], later = [], opened = [];
  let shift = 0;
  const work = {job: {nativePlots: {}}, mediaBottom: 0};
  const block = {kind: 'ink', role: 'hand', scene: 'hand-a', stage: 'hand', stage_index: 0, width: 900, height: 300,
                 source_doc: 'src', source_page: 'p1'};
  const context = vm.createContext({
    herdPasteBusy: false, herdProbeJob: null, herdInk: null, herdPage: 'page', herdContextSurface: 's',
    herdContextInk: 0, herdButton: {},
    root: {inSuspend: false, sceneController: {}},
    Library: {entryForId: () => ({})},
    navigator: {herdUuid: id => id},
    Qt: {point: (x, y) => ({x, y})},
    sceneView: {height: 1872, width: 1404, document: {id: 'doc'},
      sceneToView: p => ({x: p.x, y: p.y + shift}), viewToScene: p => ({x: p.x, y: p.y - shift}),
      tileManager: {moveViewBy(p) { moves.push(p.y); shift += p.y; }}},
    herdAssetScene: {createObject(parent, props) { opened.push(props.pageId); return {}; }},
    herdInkTimer: {restart() {}},
    herdLater(callback, waiting) { later.push(waiting); },
    herdTextDone() {}
  });
  vm.runInContext(definition('herdBeginInk') + '\nthis.begin = herdBeginInk', context);
  const bounds = {x: 200, y: 300, width: 936, height: textBottom - 300};
  context.begin(work, block, bounds);
  const first = {moves: moves.slice(), later: later.slice(), opened: opened.slice()};
  context.herdInk = null;
  context.begin(work, block, bounds);  // the wait is over: draws, never scrolls twice
  return {first, moves, opened, bottom: work.job.nativePlots['hand-a'][1] + block.height + shift};
}
const low = run(1600);
assert.equal(low.first.moves.length, 1);
assert.deepEqual(low.first.later, [true]);
assert.deepEqual(low.first.opened, []);
assert.equal(low.moves.length, 1);
assert.deepEqual(low.opened, ['p1']);
assert(low.bottom <= 1872 - 90, low.bottom);
const high = run(600);
assert.equal(high.moves.length, 0);
assert.deepEqual(high.first.opened, ['p1']);
console.log('ok ink scroll');
