import copy
import json
from pathlib import Path
import tempfile
import unittest

from notebook_pen_session import PenLease, StageJournal, execute_stage


REQUEST, DIGEST = 'notebook-'+'a'*32, 'b'*64


class PenSessionTest(unittest.TestCase):
    def context(self):
        # Test double for a FUTURE native reservation, not deployed UI behavior.
        return dict(doc='d24b835f-529d-4360-a99d-3b2f3e8eca59',
                    page='67f65b34-42a5-498a-812d-f8f443e2ce26', surface='surface-1',
                    fresh=True, active=True, age_ms=10, control_lease=True,
                    view=[1, 0, 0, 1, -702, 2821],
                    reservation=dict(ui_locked=True, request=REQUEST, digest=DIGEST,
                                     stage='see', tool=17, layer='agent-layer'))

    def geometry(self):
        return dict(kind='projected-native-pen-plan', digest=DIGEST, stage='see',
                    paths=[[(230, 310), (231, 311)], [(250, 310), (251, 311)]])

    def test_production_telemetry_cannot_authorize_pen_input(self):
        context = self.context()
        context.update(control_lease=False)
        context.pop('reservation')
        with self.assertRaisesRegex(RuntimeError, 'reservation'):
            PenLease(lambda: context, REQUEST, DIGEST, 'see')

    def test_page_view_tool_layer_expiry_or_identity_change_cancels(self):
        for change in ('page', 'surface', 'view', 'tool', 'layer', 'active', 'age', 'stage', 'deadline'):
            with self.subTest(change=change):
                context, now = self.context(), [1]
                lease = PenLease(lambda: context, REQUEST, DIGEST, 'see', clock=lambda: now[0])
                if change in ('page', 'surface'):
                    context[change] = 'different'
                elif change == 'view':
                    context['view'][-1] += 1
                elif change in ('tool', 'layer', 'stage'):
                    context['reservation'][change] = 'different'
                elif change == 'active':
                    context['active'] = False
                elif change == 'age':
                    context['age_ms'] = 751
                else:
                    now[0] += 31
                with self.assertRaises(RuntimeError):
                    lease.check()

    def test_journal_is_durable_private_and_blocks_new_instance_replay(self):
        context = self.context()
        lease = PenLease(lambda: context, REQUEST, DIGEST, 'see')
        emitted = []
        with tempfile.TemporaryDirectory() as directory:
            def emit(path, guard):
                guard()
                journal = next(Path(directory).iterdir())
                self.assertEqual(journal.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(journal.read_text().splitlines()[0])['state'], 'intent')
                emitted.append(path)
            result = execute_stage(lease, self.geometry(), directory, emit, lambda geometry: True)
            self.assertEqual(result, {'state': 'visible', 'strokes': 2, 'persisted': False})
            states = [json.loads(line)['state'] for line in next(Path(directory).iterdir()).read_text().splitlines()]
            self.assertEqual(states, ['intent', 'stroke', 'stroke', 'visible'])
            with self.assertRaises(FileExistsError):
                StageJournal(directory, REQUEST, 'see', 'c'*64)
            with self.assertRaises(FileExistsError):
                execute_stage(PenLease(lambda: context, REQUEST, DIGEST, 'see'), self.geometry(), directory, emit, lambda _: True)
            self.assertEqual(len(emitted), 2)

    def test_invalid_late_geometry_never_claims_or_opens_input(self):
        context = self.context()
        lease = PenLease(lambda: context, REQUEST, DIGEST, 'see')
        for bad in ([(230, 310), (float('nan'), 311)], [(230, 310), (231, 2000)],
                    [(230, 310), (300, 310)], [(230, 310)]):
            geometry = self.geometry()
            geometry['paths'][-1] = bad
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    execute_stage(lease, geometry, directory,
                                  lambda *_: self.fail('invalid geometry emitted'), lambda _: True)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_partial_input_and_failed_visible_proof_hold_without_replay(self):
        for failure in ('emit', 'proof'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                context = self.context()
                lease = PenLease(lambda: context, REQUEST, DIGEST, 'see')
                calls = []
                def emit(path, guard):
                    calls.append(path)
                    if failure == 'emit':
                        context['active'] = False
                    guard()  # Production emitter must check before EVERY event.
                with self.assertRaises(RuntimeError):
                    execute_stage(lease, self.geometry(), directory, emit, lambda _: False)
                events = [json.loads(line) for line in next(Path(directory).iterdir()).read_text().splitlines()]
                self.assertEqual(events[-1]['state'], 'attention')
                self.assertEqual(len(calls), 1 if failure == 'emit' else 2)
                self.assertNotIn('visible', [event['state'] for event in events])

    def test_public_journal_directory_is_rejected_before_input(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'private'):
                StageJournal(directory, REQUEST, 'see', DIGEST)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
