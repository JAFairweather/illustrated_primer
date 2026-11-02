import unittest
import importlib.machinery
import importlib.util
from pathlib import Path
from unittest.mock import patch
from notebook_view_audit import ViewAudit


class ViewAuditTest(unittest.TestCase):
    def test_server_restricts_audit_to_foreground_isolated_page_and_idle_reply(self):
        loader = importlib.machinery.SourceFileLoader('view_audit_test_server',
                    str(Path(__file__).with_name('herd-board-serve')))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        server = importlib.util.module_from_spec(spec)
        loader.exec_module(server)
        context = self.context()
        context.update(doc='905df7ae-ff54-46b9-a71e-45bb02bef638',
                       page='3ad12986-0467-48fe-986d-d1bd480c4777')
        body = dict(doc=context['doc'], page=context['page'], dy=1000)
        path = body['doc']+'/'+body['page']+'.rm'
        with patch.object(server, 'view_audit', ViewAudit()), \
             patch.object(server.device_context, 'snapshot', return_value=context), \
             patch.object(server, 'answers', {path:'written'}):
            for update in ({'doc':'other'}, {'page':'other'}, {'extra':'forbidden'}):
                with self.assertRaises(ValueError):
                    server.arm_view_audit(dict(body, **update))
            server.answers[path] = 'writing'
            with self.assertRaisesRegex(ValueError, 'pending'):
                server.arm_view_audit(body)
            server.answers[path] = 'written'
            with patch.object(server.device_context, 'snapshot', return_value=dict(context, page='other')):
                with self.assertRaisesRegex(ValueError, 'foreground'):
                    server.arm_view_audit(body)
            self.assertTrue(server.arm_view_audit(body)['armed'])
            self.assertEqual(server.view_audit.command(context)['dy'],1000)

    def context(self):
        return dict(doc='doc', page='page', surface='surface', view=[1,0,0,1,-702,1200],
                    content_revision=12, ink_revision=20, available=True, fresh=True,
                    active=True, size=[1404,1872])

    def test_one_shot_bounded_view_only(self):
        audit = ViewAudit()
        context = self.context()
        armed = audit.arm(context, 1000)
        self.assertFalse(armed['content_write'])
        with self.assertRaises(ValueError):
            audit.arm(context, 1000)
        command = audit.command(context)
        self.assertEqual(command['id'], armed['id'])
        self.assertEqual(command['dy'], 1000)
        self.assertEqual(set(command), {'doc','page','surface','view','content_revision','ink_revision','id','dy'})
        self.assertIsNone(audit.command(context))
        for invalid in (True, 0, 1201, -1201, 1.5, '100'):
            with self.assertRaises(ValueError):
                audit.arm(context, invalid)

    def test_expiry_changed_view_navigation_input_or_busy_consumes_without_replay(self):
        for update in ({'doc':'other'}, {'page':'other'}, {'surface':'replacement'},
                       {'view':[1,0,0,1,-702,1201]}, {'ink_revision':21},
                       {'content_revision':13}, {'active':False}, {}):
            now = [0]
            audit = ViewAudit(clock=lambda: now[0])
            original = self.context()
            audit.arm(original, -1000)
            self.assertIsNone(audit.command(dict(original, **update), idle=bool(update)))
            self.assertIsNone(audit.command(original), 'a refused command is never replayed')
        audit = ViewAudit(clock=lambda: now[0])
        audit.arm(self.context(), 1000)
        now[0] = 3
        self.assertIsNone(audit.command(self.context()))

    def test_stale_or_zoomed_view_cannot_arm_and_snapshot_is_owned(self):
        audit = ViewAudit()
        for update in ({'fresh':False}, {'available':False}, {'active':False},
                       {'size':[1872,1404]}, {'view':[.5,0,0,.5,-702,1200]}):
            with self.assertRaises(ValueError):
                audit.arm(dict(self.context(), **update), 1000)
        context = self.context()
        audit.arm(context, 1000)
        context['view'][-1] = 0
        self.assertEqual(audit.command(self.context())['view'][-1], 1200)
