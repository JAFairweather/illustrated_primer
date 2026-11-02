import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from notebook_device import DeviceContext, project_storyboard
from notebook_storyboard import integral_storyboard
import math


class NativeContextTest(unittest.TestCase):
    def test_temporary_keep_awake_is_scoped_expiring_and_not_input_permission(self):
        now = [10]
        store = DeviceContext(clock=lambda: now[0])
        data = self.sample()
        body = {'doc': data['doc'], 'seconds': 180}
        with self.assertRaises(ValueError):
            store.keep_awake(body)
        store.update(data)
        self.assertFalse(store.keep_awake(body)['control_lease'])
        self.assertEqual(store.awake_seconds(data['doc']), 180)
        self.assertEqual(store.awake_seconds(data['page']), 0)
        now[0] += 121
        self.assertEqual(store.awake_seconds(data['doc']), 59)
        with self.assertRaises(ValueError):
            store.keep_awake(body)  # stale telemetry cannot refresh it
        now[0] += 60
        self.assertEqual(store.awake_seconds(data['doc']), 0)
        data['sequence'] += 1
        store.update(data)
        for seconds in (True, -1, 181, 1.5):
            with self.assertRaises(ValueError):
                store.keep_awake(dict(body, seconds=seconds))
        store.keep_awake(body)
        store.keep_awake(dict(body, doc=data['page'], seconds=0))
        self.assertEqual(store.awake_seconds(data['doc']), 180)
        store.keep_awake(dict(body, seconds=0))
        self.assertEqual(store.awake_seconds(data['doc']), 0)

    def test_projection_uses_native_scroll_transform_not_fixed_offsets(self):
        context = dict(self.sample(), available=True, fresh=True, control_lease=False)
        context['view'] = [1, 0, 0, 1, -702, 2821]
        result = project_storyboard(integral_storyboard(), context, (-468, 3031))
        self.assertEqual(result['bounds'], [234, 210, 834, 510])
        self.assertFalse(result['control_lease'])
        # A new response near the viewport bottom requires a native scroll first.
        with self.assertRaisesRegex(ValueError, 'scroll/reposition'):
            project_storyboard(integral_storyboard(), context, (-468, 4500))
        context['view'][-1] = 4290
        self.assertEqual(project_storyboard(integral_storyboard(), context, (-468, 4500))['bounds'],
                         [234, 210, 834, 510])

    def test_projection_densifies_after_zoom_and_preserves_additive_stage(self):
        context = dict(self.sample(), available=True, fresh=True)
        context['view'] = [.5, 0, 0, .5, 0, 0]
        result = project_storyboard(integral_storyboard(width=320), context, (100, 150), 'see')
        self.assertEqual(len(result['paths']), 2)
        self.assertTrue(all(math.dist(p, q) <= 2.001 for path in result['paths'] for p, q in zip(path, path[1:])))
        for update in ({'fresh': False}, {'active': False}, {'size': [1872, 1404]},
                       {'view': [1, 0, 0, 0, 0, 0]}):
            with self.assertRaises(ValueError):
                project_storyboard(integral_storyboard(), dict(context, **update), (100, 150))
        with self.assertRaises(ValueError):
            project_storyboard(integral_storyboard(width=320), context, (100, 150), 'missing')

    def test_repair_hint_only_for_current_explicit_never_inserted_reply(self):
        loader = importlib.machinery.SourceFileLoader('native_context_test_server',
                    str(Path(__file__).with_name('herd-board-serve')))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        server = importlib.util.module_from_spec(spec)
        loader.exec_module(server)
        body = self.sample()
        path = body['doc']+'/'+body['page']+'.rm'
        request = 'notebook-'+'a'*32
        job = ['pidog', path, 1, True, request, None, True]
        with patch.object(server, 'device_context', DeviceContext()), \
             patch.object(server, 'notebook_jobs', {request: job}), \
             patch.object(server, 'answers', {path: 'ready'}), \
             patch.object(server, 'ready', {path: 'held answer'}), \
             patch.object(server, 'retry_requests', {}), \
             patch.object(server, 'native_retry_safe', return_value=True) as safe:
            self.assertNotIn('repair', server.native_context_report(body))
            server.retry_requests[request] = 'explicit-token'
            body['sequence'] += 1
            self.assertEqual(server.native_context_report(body)['repair'],
                             {'request': request, 'token': 'explicit-token'})
            self.assertNotIn('repair', server.native_context_report(body), 'out-of-order report')
            safe.return_value = False
            body['sequence'] += 1
            self.assertNotIn('repair', server.native_context_report(body))
            safe.return_value = True
            server.answers[path] = 'writing'
            body['sequence'] += 1
            self.assertNotIn('repair', server.native_context_report(body))
            server.answers[path] = 'ready'
            body.update(sequence=body['sequence']+1, active=False)
            self.assertNotIn('repair', server.native_context_report(body))

    def sample(self):
        return dict(doc='d24b835f-529d-4360-a99d-3b2f3e8eca59',
                    page='67f65b34-42a5-498a-812d-f8f443e2ce26',
                    surface='1793050000000-123', sequence=1, active=True,
                    view=[1, 0, 0, 1, -702, 0], size=[1404, 1872],
                    text_bounds=[-460, 300, 1000, 200],
                    content_revision=0, ink_revision=0)

    def test_snapshot_expires_without_claiming_a_control_lease(self):
        now = [10]
        store = DeviceContext(clock=lambda: now[0])
        self.assertFalse(store.snapshot()['available'])
        data = self.sample()
        self.assertTrue(store.update(data)['accepted'])
        data['view'][0] = 42
        self.assertEqual(store.snapshot()['view'][0], 1)
        self.assertFalse(store.snapshot()['control_lease'])
        self.assertTrue(store.snapshot()['fresh'])
        now[0] += 2
        self.assertFalse(store.snapshot()['fresh'])

    def test_out_of_order_reports_do_not_refresh_age(self):
        now = [10]
        store = DeviceContext(clock=lambda: now[0])
        data = self.sample()
        store.update(data)
        now[0] = 20
        self.assertFalse(store.update(data)['accepted'])
        self.assertEqual(store.snapshot()['age_ms'], 10000)
        data.update(sequence=2, active=False)
        self.assertTrue(store.update(data)['accepted'])
        self.assertFalse(store.snapshot()['fresh'])

    def test_bounded_geometry_and_metadata_only(self):
        for key, value in (('view', [1, 0, 0, 0, 0, 0]),
                           ('view', [1, 0, 0, float('nan'), 0, 0]),
                           ('view', [True, 0, 0, 1, 0, 0]),
                           ('size', [1404, 5000]), ('text_bounds', [0, 0, -1, 1]),
                           ('sequence', True), ('surface', 'bad'),
                           ('doc', '../../notes'), ('active', 1), ('text', 'private')):
            body = self.sample()
            body[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                DeviceContext().update(body)

    def test_bounded_surface_memory_and_snapshot_immutability(self):
        store = DeviceContext()
        for i in range(40):
            data = self.sample()
            data['surface'] = '1793050000000-'+str(i)
            store.update(data)
        self.assertEqual(len(store.sequences), 32)
        snapshot = store.snapshot()
        snapshot['view'][0] = 22
        self.assertEqual(store.snapshot()['view'][0], 1)


if __name__ == '__main__':
    unittest.main()
