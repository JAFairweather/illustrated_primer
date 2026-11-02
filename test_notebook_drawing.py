import copy
import unittest
import xml.etree.ElementTree as ET

from ink import append, strokes
from notebook_drawing import StoryboardRun, compile_storyboard, preview_svg
from notebook_storyboard import integral_storyboard


IDENTITY = ('request-1', 'document-1', 'page-1', 7, 3)


class RecordingAdapter:
    """Test double only; not a live tablet adapter."""
    capabilities = {'caption', 'stroke', 'annotation', 'equation'}

    def __init__(self):
        self.identity = IDENTITY
        self.events = []
        self.emitted = []
        self.persisted = True

    def reserve(self, program, identity):
        self.reserved = (program, identity)

    def current_identity(self):
        return self.identity

    def record(self, event):
        self.events.append(event)

    def emit(self, operation):
        self.emitted.append(operation)

    def verify(self, program):
        return self.persisted


class NotebookDrawingTest(unittest.TestCase):
    def test_compiles_additive_stages_deterministically_without_mutation(self):
        plan = integral_storyboard()
        original = copy.deepcopy(plan)
        program = compile_storyboard(plan)
        self.assertEqual(plan, original)
        self.assertEqual(program, compile_storyboard(plan))
        self.assertEqual(program['required_operations'], ['annotation', 'caption', 'equation', 'stroke'])
        self.assertEqual(len([o for o in program['operations'] if o['kind'] == 'caption']), 4)
        self.assertEqual(len([o for o in program['operations'] if o['kind'] == 'equation']), 1)
        self.assertEqual([o['stage'] for o in program['operations'] if o['kind'] == 'caption'],
                         ['see', 'measure', 'notice', 'conclude'])
        self.assertNotIn('text', next(o for o in program['operations'] if o['kind'] == 'stroke'))

    def test_rejects_bad_late_geometry_before_any_emission(self):
        mutations = [lambda p: p['stages'][-1].update(paths=[[(0, 0), (float('nan'), 0)]]),
                     lambda p: p['stages'][-1].update(paths=[[(0, 0), (1e8, 0)]]),
                     lambda p: p['stages'][-1].update(paths=[[(0, 0), (True, 0)]]),
                     lambda p: p['stages'][-1].update(paths=[[(0, 0), (10, 0)]]),
                     lambda p: p['stages'][-1].update(id='see'),
                     lambda p: p['stages'][-1].update(text='x'*1601),
                     lambda p: p['stages'][-1].update(annotations=[{'text': 'x', 'point': (0, -1)}])]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                plan = integral_storyboard()
                mutate(plan)
                with self.assertRaises(ValueError):
                    StoryboardRun(plan, IDENTITY)

    def test_native_stroke_format_round_trip_keeps_geometry_not_text(self):
        program = compile_storyboard(integral_storyboard())
        # Synthetic format fixture, not a deployable notebook or user page.
        header = b'reMarkable .lines file, version=6'.ljust(43, b' ')
        paths = [o['path'] for o in program['operations'] if o['kind'] == 'stroke']
        lines = [[(x-702, y+100, 2) for x, y in path] for path in paths]
        raw = append(header, lines, start=((0, 1), (1, 1)))
        decoded = strokes(raw)
        self.assertEqual(len(decoded), len(paths))
        for (_, points, ours), expected in zip(decoded, lines):
            self.assertTrue(ours)
            for actual, target in zip(points, expected):
                for a, b in zip(actual, target):
                    self.assertAlmostEqual(a, b, places=3)
        self.assertNotIn(b'The integral', raw)

    def test_executor_journals_intent_before_writing_and_verifies(self):
        adapter = RecordingAdapter()
        run = StoryboardRun(integral_storyboard(), IDENTITY)
        original_emit = adapter.emit
        def emit(operation):
            self.assertEqual(adapter.events[-1]['state'], 'intent')
            original_emit(operation)
        adapter.emit = emit
        result = run.run(adapter)
        self.assertEqual(result['state'], 'verified')
        self.assertEqual(result['operations'], len(adapter.emitted))
        self.assertEqual(len(adapter.events), 2*len(adapter.emitted))
        with self.assertRaisesRegex(RuntimeError, 'already attempted'):
            run.run(adapter)

    def test_rejects_unsupported_native_annotations_before_reservation(self):
        adapter = RecordingAdapter()
        adapter.capabilities = {'caption', 'stroke', 'equation'}
        with self.assertRaisesRegex(ValueError, 'every required'):
            StoryboardRun(integral_storyboard(), IDENTITY).run(adapter)
        self.assertFalse(hasattr(adapter, 'reserved'))
        self.assertEqual(adapter.emitted, [])

    def test_page_change_or_user_input_change_holds_without_replay(self):
        for changed in [('request-2', *IDENTITY[1:]),
                        (*IDENTITY[:2], 'page-2', *IDENTITY[3:]),
                        (*IDENTITY[:3], 8, 3), (*IDENTITY[:4], 4)]:
            adapter = RecordingAdapter()
            def emit(operation):
                adapter.emitted.append(operation)
                adapter.identity = changed
            adapter.emit = emit
            run = StoryboardRun(integral_storyboard(), IDENTITY)
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                run.run(adapter)
            self.assertEqual(run.state, 'attention')
            self.assertEqual(len(adapter.emitted), 1)
            with self.assertRaisesRegex(RuntimeError, 'already attempted'):
                run.run(adapter)

    def test_journal_failure_and_partial_emit_never_auto_retry(self):
        for failure in ('record', 'emit'):
            adapter = RecordingAdapter()
            def fail(value):
                raise OSError('injected interrupted output')
            setattr(adapter, failure, fail)
            run = StoryboardRun(integral_storyboard(), IDENTITY)
            with self.assertRaises(OSError):
                run.run(adapter)
            self.assertEqual(run.state, 'attention')
            self.assertEqual(run.completed, 0)
            with self.assertRaises(RuntimeError):
                run.run(adapter)
            if failure == 'record':
                self.assertEqual(adapter.emitted, [])

    def test_lease_rechecked_after_persistent_intent_and_final_proof_required(self):
        adapter = RecordingAdapter()
        def record(event):
            adapter.events.append(event)
            adapter.identity = (*IDENTITY[:4], 4)
        adapter.record = record
        with self.assertRaisesRegex(RuntimeError, 'before insertion'):
            StoryboardRun(integral_storyboard(), IDENTITY).run(adapter)
        self.assertEqual(adapter.emitted, [])
        adapter = RecordingAdapter()
        adapter.persisted = False
        run = StoryboardRun(integral_storyboard(), IDENTITY)
        with self.assertRaisesRegex(RuntimeError, 'persistence'):
            run.run(adapter)
        self.assertEqual(run.state, 'attention')

    def test_preview_is_cumulative_vectors_not_rasterized_prose(self):
        counts = []
        for stage in ('see', 'measure', 'notice', 'conclude'):
            svg = preview_svg(integral_storyboard(), stage)
            root = ET.fromstring(svg)
            counts.append(len(root.findall('{http://www.w3.org/2000/svg}polyline')))
            self.assertNotIn('<image', svg)
            self.assertNotIn('The integral measures', svg)
        self.assertEqual(counts, [2, 5, 8, 8])
        with self.assertRaises(ValueError):
            preview_svg(integral_storyboard(), 'unknown')


if __name__ == '__main__':
    unittest.main()
