import unittest
import tempfile
from pathlib import Path
from notebook_native_probe import NativeProbe


class NativeProbeTest(unittest.TestCase):
    def sample(self):
        return dict(doc='d24b835f-529d-4360-a99d-3b2f3e8eca59',
                    page='67f65b34-42a5-498a-812d-f8f443e2ce26', surface='1793050000000-123',
                    source_doc='519b63da-2ccc-4194-b84d-983846853aaf',
                    source_page='6c7c337b-b118-4734-8355-c409ca3e5bca')

    def test_only_exact_fresh_page_gets_bounded_probe(self):
        now = [0]
        probe = NativeProbe(clock=lambda: now[0])
        body = self.sample()
        context = dict(body, fresh=True, active=True)
        result = probe.arm(body, context)
        self.assertEqual(probe.command(context)['id'], result['id'])
        self.assertIsNone(probe.command(dict(context, page=body['source_page'])))
        self.assertIsNone(probe.command(dict(context, active=False)))
        self.assertIsNone(probe.command(dict(context, surface='other')))
        with self.assertRaises(ValueError):
            probe.arm(body, context)
        now[0] = 61
        self.assertIsNone(probe.command(context))
        self.assertEqual(probe.snapshot()['state'], 'expired')

    def test_result_is_metadata_only_and_once(self):
        probe = NativeProbe()
        body = self.sample()
        context = dict(body, fresh=True, active=True)
        identity = probe.arm(body, context)['id']
        report = dict(id=identity, state='loaded', view_active=True, page_ready=True,
                      controller=True, working=False, clone_selected=True,
                      select_rect=True, select_area=False, select_all=False)
        with self.assertRaises(ValueError):
            probe.complete(dict(report, text='private notebook text'))
        with self.assertRaises(ValueError):
            probe.complete(dict(report, id='wrong'))
        self.assertTrue(probe.complete(report)['accepted'])
        self.assertIsNone(probe.command(context))
        report['controller'] = False
        self.assertTrue(probe.snapshot()['result']['controller'])
        with self.assertRaises(ValueError):
            probe.complete(report)

    def test_import_probe_requires_preflight_and_cannot_paste(self):
        body = dict(self.sample(), operation='import-source', expected_strokes=2,
                    source_parent='a7a7e181-7b6b-4a84-a169-3bc7e5fe35da')
        context = dict(body, fresh=True, active=True)
        probe = NativeProbe()
        with self.assertRaises(ValueError):
            probe.arm(body, context)
        identity = probe.arm(body, context, 'a'*64)['id']
        self.assertEqual(probe.command(context)['source_parent'], body['source_parent'])
        report = dict(id=identity, state='cloned', view_active=True, page_ready=True,
                      controller=True, working=False, clone_selected=True, clone_value=True,
                      select_rect=True, select_area=True, select_all=False, selected=2, cloned=0,
                      imported_doc=body['source_doc'], imported_page=body['source_page'])
        with self.assertRaises(ValueError):
            probe.complete(dict(report, imported_doc=body['doc']))
        with self.assertRaises(ValueError):
            probe.complete(dict(report, state='pasted'))
        self.assertTrue(probe.complete(report)['accepted'])

    def test_cannot_arm_stale_or_foreground_source_or_invalid_fields(self):
        body = self.sample()
        context = dict(body, fresh=True, active=True)
        for change in ({'fresh': False}, {'page': body['source_page']}, {'active': False}):
            with self.assertRaises(ValueError):
                NativeProbe().arm(body, dict(context, **change))
        for change in ({'source_doc': body['doc']}, {'source_page': '../../page'}, {'extra': True}):
            with self.assertRaises(ValueError):
                NativeProbe().arm(dict(body, **change), context)

    def test_source_clone_requires_exact_counts_and_bounded_command(self):
        probe = NativeProbe()
        body = dict(self.sample(), operation='clone-source', expected_strokes=2)
        context = dict(body, fresh=True, active=True)
        identity = probe.arm(body, context)['id']
        report = dict(id=identity, state='cloned', view_active=True, page_ready=True,
                      controller=True, working=False, clone_selected=True,
                      select_rect=True, select_area=True, select_all=False, selected=2, cloned=1)
        with self.assertRaises(ValueError):
            probe.complete(report)
        report['cloned'] = 2
        self.assertTrue(probe.complete(report)['accepted'])
        for change in ({'operation': 'paste'}, {'expected_strokes': True}, {'expected_strokes': 65}, {'expected_strokes': 0}):
            with self.assertRaises(ValueError):
                NativeProbe().arm(dict(body, **change), context)

    def test_blank_paste_claim_is_durable_private_and_destination_wide(self):
        body = dict(self.sample(), operation='paste-blank-test', expected_strokes=2)
        context = dict(body, fresh=True, active=True, content_revision=1, ink_revision=0)
        with tempfile.TemporaryDirectory() as directory:
            claims = Path(directory)/'claims'
            store = NativeProbe(claims=claims)
            identity = store.arm(body, context, 'a'*64)['id']
            claim = {k: body[k] for k in ('doc', 'page', 'surface')}
            claim.update(id=identity, ui_locked=True)
            self.assertTrue(store.claim(claim, context)['claimed'])
            self.assertEqual(claims.stat().st_mode & 0o777, 0o700)
            files = list(claims.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                store.claim(claim, context)
            # Fresh server/job ID cannot bypass the destination-wide attempt.
            fresh = NativeProbe(claims=claims)
            claim['id'] = fresh.arm(body, context, 'a'*64)['id']
            with self.assertRaises(FileExistsError):
                fresh.claim(claim, context)

    def test_text_anchor_is_bounded_source_metadata_not_a_paste_result(self):
        body = dict(self.sample(), operation='text-anchor', expected_strokes=0)
        body['source_doc'] = body['doc']  # a DIFFERENT page in the same fixture
        context = dict(body, fresh=True, active=True)
        probe = NativeProbe()
        with self.assertRaises(ValueError):
            probe.arm(body, context)  # independent saved-source preflight required
        with self.assertRaises(ValueError):
            probe.arm(dict(body, source_page=body['page']), context, 'a'*64)
        with self.assertRaises(ValueError):
            probe.arm(dict(body, expected_strokes=1), context, 'a'*64)
        identity = probe.arm(body, context, 'a'*64)['id']
        report = dict(id=identity, state='text-anchor', view_active=True, page_ready=True,
                      controller=True, working=False, clone_selected=True, clone_value=False,
                      select_rect=True, select_area=False, select_all=False, selected=0, cloned=0,
                      text_anchor=[-464, 267.59375, 69.55, 23])
        for change in ({'text_anchor': [0, float('nan'), 1, 2]}, {'text_anchor': [0, 1, 0, 2]},
                       {'text_anchor': [0, 1, 2, True]}, {'text_anchor': [0, 1, 2, 0]},
                       {'text_anchor': [0, 1000001, 2, 3]}, {'state': 'pasted'},
                       {'selected': 1}, {'clone_value': True}, {'page_ready': False}, {'working': True}):
            with self.assertRaises(ValueError):
                probe.complete(dict(report, **change))
        missing = dict(report); del missing['text_anchor']
        with self.assertRaises(ValueError):
            probe.complete(missing)
        self.assertTrue(probe.complete(report)['accepted'])
        other = NativeProbe()
        report['id'] = other.arm(self.sample(), context)['id']
        with self.assertRaises(ValueError):
            other.complete(report)

    def test_blank_paste_refuses_no_preflight_lease_revision_or_private_journal(self):
        body = dict(self.sample(), operation='paste-blank-test', expected_strokes=2)
        context = dict(body, fresh=True, active=True, content_revision=1, ink_revision=0)
        with self.assertRaises(ValueError):
            NativeProbe().arm(body, context)
        with tempfile.TemporaryDirectory() as directory:
            store = NativeProbe(claims=Path(directory)/'claims')
            identity = store.arm(body, context, 'a'*64)['id']
            claim = {k: body[k] for k in ('doc', 'page', 'surface')}
            claim.update(id=identity, ui_locked=True)
            for update in ({'fresh': False}, {'ink_revision': 1}, {'content_revision': 2}, {'surface': 'other'}):
                with self.assertRaises(ValueError):
                    store.claim(claim, dict(context, **update))
            with self.assertRaises(ValueError):
                store.claim(dict(claim, ui_locked=False), context)
            self.assertFalse(store.claims.exists(), 'unsafe claim cannot even create a journal directory')
            store.claims.mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                store.claim(claim, context)

    def test_read_only_cursor_query_is_bounded_exact_and_cannot_be_paste(self):
        body = dict(self.sample(), operation='text-anchor', expected_strokes=0, cursor_index=23)
        context = dict(body, fresh=True, active=True)
        for index in (-1,262145,True,1.5,'1',None):
            with self.assertRaises(ValueError):
                NativeProbe().arm(dict(body,cursor_index=index),context,'a'*64)
        with self.assertRaises(ValueError):
            NativeProbe().arm(dict(body,operation='load'),context,'a'*64)
        probe = NativeProbe()
        identity = probe.arm(body,context,'a'*64)['id']
        self.assertEqual(probe.command(context)['cursor_index'],23)
        report = dict(id=identity,state='text-anchor',view_active=True,page_ready=True,
                      controller=True,working=False,clone_selected=True,clone_value=False,
                      select_rect=True,select_area=False,select_all=False,selected=0,cloned=0,
                      text_anchor=[-464,500,32,23],text_cursor_index=23,text_bounds=[-468,234,936,300])
        for change in ({'text_cursor_index':22},{'text_cursor_index':True},
                       {'text_anchor':[-464,500,32,22]},{'state':'pasted'},
                       {'text_bounds':[0,0,1,float('nan')]},{'text_bounds':[0,0,0,2]},
                       {'text_bounds':[0,0,1,-1]},{'selected':1}):
            with self.assertRaises(ValueError):
                probe.complete(dict(report,**change))
        missing = dict(report); del missing['text_bounds']
        with self.assertRaises(ValueError):
            probe.complete(missing)
        self.assertTrue(probe.complete(report)['accepted'])
        for bounds in ([0,0,1,-1],[0,0,True,2],[0,0,1,float('inf')],[0,0,1],None):
            check=NativeProbe(); entry=check.arm(body,context,'a'*64)['id']
            with self.assertRaises(ValueError):
                check.complete(dict(report,id=entry,ink_bounds=bounds))
        check=NativeProbe(); entry=check.arm(body,context,'a'*64)['id']
        self.assertTrue(check.complete(dict(report,id=entry,ink_bounds=[-264,100,100,2]))['accepted'])
        old = NativeProbe(); without_index = dict(body); del without_index['cursor_index']
        report['id'] = old.arm(without_index,context,'a'*64)['id']
        with self.assertRaises(ValueError):
            old.complete(report)
        legacy_report = dict(report, ink_bounds=[-264,100,100,2])
        del legacy_report['text_cursor_index']
        del legacy_report['text_bounds']
        with self.assertRaises(ValueError):
            old.complete(legacy_report)
        indexed = NativeProbe()
        legacy_report['id'] = indexed.arm(body,context,'a'*64)['id']
        with self.assertRaises(ValueError):
            indexed.complete(legacy_report)
        legacy_report.pop('ink_bounds')
        legacy_report['id'] = report['id']
        self.assertTrue(old.complete(legacy_report)['accepted'], 'legacy cursor query remains supported')


if __name__ == '__main__':
    unittest.main()
