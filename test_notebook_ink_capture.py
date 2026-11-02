"""Native layout trust boundary and complete saved-ink integration, no tablet."""
import copy
import json
import tempfile
import unittest

from ink import append
from notebook_ink_runs import InkRuns
from notebook_stroke_asset import storyboard_assets
from notebook_storyboard import integral_storyboard
from notebook_ink_catalog import InkCatalog
from test_notebook_ink_catalog import manifest
from test_notebook_ink_preservation import fixture, measurement, change_first_line, AUTHOR
from test_notebook_ink_runs import REQUEST, DOC, PAGE
KEY = b'synthetic-test-only-text-key-0001'


def context():
    return dict(fresh=True,active=True,doc=DOC,page=PAGE,surface='1793064000000-123',
                ink_revision=4,content_revision=8,text_bounds=[-468,500,936,100])


class CaptureTest(unittest.TestCase):
    def test_legacy_saved_length_is_opt_in_and_bound_to_the_exact_capture(self):
        from notebook_ink_preservation import layout_request
        _, raw = fixture()
        legacy = layout_request(raw)
        self.assertNotIn('length', legacy)
        extended = layout_request(raw, include_length=True)
        self.assertEqual(extended, dict(legacy, length=measurement(raw)['first'][3]))
        with tempfile.TemporaryDirectory() as directory:
            store = InkRuns(directory, KEY)
            command = store.begin_capture(REQUEST, 'after', raw, context())
            self.assertNotIn('anchors', command)
            self.assertEqual(command['length'], extended['length'])
            changed = dict(command, length=command['length']+1)
            with self.assertRaisesRegex(ValueError, 'matching outstanding capture'):
                store.finish_capture(dict(command=changed, first=measurement(raw)['first']), context, lambda _:raw)
            self.assertFalse(store.measurements)
            self.assertEqual(store.finish_capture(dict(command=command, first=measurement(raw)['first']), context, lambda _:raw), {'measured':True})

    def test_multi_adapter_fallback_is_explicit_and_never_for_validation_errors(self):
        from unittest.mock import patch, call
        from notebook_ink_runs import capture_layout
        from notebook_ink_preservation import layout_request, NativeLayoutUnsupported
        from test_notebook_multi_anchor import multi_fixture
        _, legacy = fixture()
        raw = multi_fixture()
        with patch('notebook_ink_runs.layout_request',wraps=layout_request) as query:
            legacy_plan = capture_layout(legacy)
            self.assertEqual(legacy_plan['indices'],[0])
            self.assertEqual(legacy_plan['length'], measurement(legacy)['first'][3])
            self.assertNotIn('anchors', legacy_plan)
            self.assertEqual(query.call_args_list,[call(legacy,include_length=True)])
            query.reset_mock()
            self.assertEqual(capture_layout(raw)['indices'],[0,2])
            self.assertEqual(query.call_args_list,[call(raw,include_length=True),call(raw,allow_multiple=True,include_length=True)])
        for exc in (ValueError('malformed topology'),ValueError('unsupported root text identity')):
            with patch('notebook_ink_runs.layout_request',side_effect=exc) as query:
                with self.assertRaises(ValueError): capture_layout(raw)
                self.assertEqual(query.call_args_list,[call(raw,include_length=True)])
        with patch('notebook_ink_runs.layout_request',side_effect=[
                NativeLayoutUnsupported('legacy anchor'),ValueError('ambiguous full text order')]) as query:
            with self.assertRaisesRegex(ValueError,'ambiguous full text order'): capture_layout(raw)
            self.assertEqual(query.call_count,2)

    def test_multi_capture_matches_server_plan_and_rejects_partial_or_legacy_reply(self):
        from test_notebook_multi_anchor import multi_fixture, measured
        raw=multi_fixture()
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory,KEY)
            command=store.begin_capture(REQUEST,'before',raw,context())
            self.assertEqual(command['indices'],[0,2])
            self.assertEqual(command['length'],3)
            samples=measured(raw)['samples']
            bad=[dict(command=command,first=samples[0][1:]),
                 dict(command=command,samples=samples[:1]),
                 dict(command=command,samples=samples*2),
                 dict(command=command,samples=samples+[[1,-464,300,32,3]]),
                 dict(command=dict(command,indices=[0,1]),samples=samples),
                 dict(command=dict(command,anchors=[]),samples=samples)]
            for reply in bad:
                with self.subTest(reply=reply),self.assertRaises(ValueError):
                    store.finish_capture(reply,context,lambda _:raw)
                self.assertFalse(store.measurements)
            reply=dict(command=command,samples=samples)
            self.assertEqual(store.finish_capture(reply,context,lambda _:raw),{'measured':True})
            self.assertEqual(store.measurements[(REQUEST,command['sha256'])]['measurement'],measured(raw))
            with self.assertRaises(ValueError):
                store.finish_capture(reply,context,lambda _:raw)

    def test_multi_capture_length_lag_waits_only_after_and_discards_samples(self):
        from test_notebook_multi_anchor import multi_fixture, measured
        raw=multi_fixture()
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory,KEY)
            for phase in ('before','after'):
                command=store.begin_capture(REQUEST,phase,raw,context())
                samples=copy.deepcopy(measured(raw)['samples'])
                for sample in samples: sample[4]+=1
                reply=dict(command=command,samples=samples)
                if phase=='before':
                    with self.assertRaisesRegex(ValueError,'length disagrees'):
                        store.finish_capture(reply,context,lambda _:raw)
                else:
                    self.assertEqual(store.finish_capture(reply,context,lambda _:raw)['state'],'waiting')
                    self.assertNotIn((REQUEST,phase),store.captures)
                self.assertFalse(store.measurements)
            command=store.begin_capture(REQUEST,'after',raw,context())
            reply=dict(command=command,samples=measured(raw)['samples'])
            changed=context();changed['content_revision']+=1
            with self.assertRaisesRegex(ValueError,'page or input changed'):
                store.finish_capture(reply,lambda:changed,lambda _:raw)

    def test_multi_capture_budget_holds_instead_of_selecting_subset(self):
        from unittest.mock import patch
        from test_notebook_multi_anchor import multi_fixture
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory,KEY)
            with patch('notebook_ink_runs.layout_request',return_value={'indices':list(range(65))}):
                with self.assertRaisesRegex(ValueError,'64 distinct anchors'):
                    store.begin_capture(REQUEST,'before',multi_fixture(),context())
            self.assertFalse(store.captures)

    def test_multi_capture_register_and_complete_full_preservation(self):
        from test_notebook_multi_anchor import multi_fixture,measured
        from ink import strokes
        before=multi_fixture()
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory,KEY)
            catalog=InkCatalog(manifest(str(AUTHOR)))
            blocks=[dict(kind='ink',**catalog.get('unit-square-integral',s)) for s in ('see','measure','notice')]
            waiting=store.register(REQUEST,DOC+'/'+PAGE+'.rm',context(),blocks,before,preservation=True)
            store.finish_capture(dict(command=waiting['measure_layout'],samples=measured(before)['samples']),context,lambda _:before)
            self.assertEqual(store.register(REQUEST,DOC+'/'+PAGE+'.rm',context(),blocks,before,preservation=True),{'registered':3})
            for b in blocks:
                q=dict(request=REQUEST,page=DOC+'/'+PAGE+'.rm',scene=b['scene'],stage=b['stage'],
                       surface=context()['surface'],ink_revision=4,revision=8,origin=[-468,630],ui_locked=True)
                store.claim(q,context,lambda *args:None)
                store.complete({k:q[k] for k in ('request','scene','stage')})
            assets={a['stage']:a['data'] for a in storyboard_assets(integral_storyboard(),str(AUTHOR),ink_labels=True)}
            paths=[p for raw in assets.values() for _,p,_ in strokes(raw)]
            after=append(before,[[(x,y+1000,w) for x,y,w in p] for p in paths])
            def proof(raw):return store.saved_proof(REQUEST,lambda _:raw,lambda b:assets[b['stage']],context)
            waiting=proof(after)
            store.finish_capture(dict(command=waiting['measure_layout'],samples=measured(after)['samples']),context,lambda _:after)
            self.assertEqual(proof(after)['state'],'persisted')
            # A valid multi-capture is not permission to move old strokes.
            import struct
            bad=change_first_line(after,lambda f:f.__setitem__(2,(4,struct.pack('<I',1))))
            waiting=proof(bad)
            store.finish_capture(dict(command=waiting['measure_layout'],samples=measured(bad)['samples']),context,lambda _:bad)
            self.assertIn('old native stroke',proof(bad)['reason'])

    def test_after_capture_requires_fresh_context_but_can_wait_without_acceptance(self):
        _,raw = fixture()
        for change in ('inactive','stale','inactive-during-read','stale-during-read'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                store = InkRuns(directory,KEY)
                command = store.begin_capture(REQUEST,'after',raw,context())
                reply = dict(command=command,first=measurement(raw)['first'])
                current = context()
                field = 'active' if change.startswith('inactive') else 'fresh'
                if not change.endswith('during-read'): current[field] = False
                def read(_):
                    current[field] = False
                    return raw
                result = store.finish_capture(reply,lambda:current,read)
                self.assertEqual(result['state'],'waiting')
                self.assertFalse(result['measured'])
                self.assertFalse(store.measurements)
                self.assertFalse(store.captures)
                # An unavailable context cannot conceal page/input changes.
                for key in ('doc','page','surface','content_revision','ink_revision'):
                    command = store.begin_capture(REQUEST,'after',raw,context())
                    bad = dict(current,**{key:'changed'})
                    with self.assertRaisesRegex(ValueError,'page or input changed'):
                        store.finish_capture(dict(command=command,first=reply['first']),lambda:bad,lambda _:raw)
                command = store.begin_capture(REQUEST,'after',raw,context())
                self.assertTrue(store.finish_capture(dict(command=command,first=reply['first']),context,lambda _:raw)['measured'])
                command = store.begin_capture(REQUEST,'before',raw,context())
                with self.assertRaisesRegex(ValueError,'fresh active'):
                    store.finish_capture(dict(command=command,first=reply['first']),lambda:current,lambda _:raw)

    def test_after_autosave_lag_waits_without_accepting_or_reusing_measurement(self):
        from ink import blocks, cid, i4, sub, vu
        from notebook_stroke_asset import _block
        from test_notebook_ink_preservation import _fields, encode, ANCHOR
        _, raw = fixture()
        text = next(b for k,b in blocks(raw) if k == 7)
        root = _fields(text[8:]); section = _fields(root[2][1])
        atom = sub(0,cid(2,*ANCHOR)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x02\x01\nA'))
        section[1] = (12,sub(1,vu(1)+atom)); root[2] = (12,encode(section))
        saved_later = raw.replace(text,_block(7,encode(root)))
        first = [*measurement(raw)['first'][:3],2]
        with tempfile.TemporaryDirectory() as directory:
            store = InkRuns(directory,KEY)
            for _ in range(2):
                command = store.begin_capture(REQUEST,'after',raw,context())
                reply = dict(command=command,first=first)
                waiting = store.finish_capture(reply,context,lambda _:raw)
                self.assertEqual(waiting['state'],'waiting')
                self.assertFalse(waiting['measured'])
                self.assertIn('native=2, saved=1, delta=1',waiting['reason'])
                self.assertFalse(store.measurements)
                self.assertFalse(store.captures)
                with self.assertRaises(ValueError):
                    store.finish_capture(reply,context,lambda _:raw)
            command = store.begin_capture(REQUEST,'after',saved_later,context())
            self.assertTrue(store.finish_capture(dict(command=command,first=first),context,lambda _:saved_later)['measured'])
            self.assertEqual(len(store.measurements),1)
            store.measurements.clear()
            # Autosave can also land during capture. Old coordinates are never
            # attached to new bytes; a fresh measurement remains mandatory.
            command = store.begin_capture(REQUEST,'after',raw,context())
            result = store.finish_capture(dict(command=command,first=first),context,lambda _:saved_later)
            self.assertEqual(result['state'],'waiting')
            self.assertIn('new measurement required',result['reason'])
            self.assertFalse(store.measurements)
            self.assertFalse(store.captures)
            # The pre-write baseline must NEVER use a mismatched native length.
            command = store.begin_capture(REQUEST,'before',raw,context())
            with self.assertRaisesRegex(ValueError,'length disagrees'):
                store.finish_capture(dict(command=command,first=first),context,lambda _:raw)
            with self.assertRaisesRegex(ValueError,'saved page or input changed'):
                store.finish_capture(dict(command=command,first=first),context,lambda _:saved_later)

    def test_server_snapshot_and_native_measurement_must_cover_same_bytes_and_input(self):
        _, raw = fixture()
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory,KEY)
            command=store.begin_capture(REQUEST,'after',raw,context())
            reply=dict(command=command,first=measurement(raw)['first'])
            for change in ('unrequested','hash','index','page','ink','revision','file','during-read'):
                body=copy.deepcopy(reply); current=context(); saved=raw
                if change=='unrequested': body['command']['request']='notebook-'+'8'*32
                if change=='hash': body['command']['sha256']='0'*64
                if change=='index': body['command']['indices']=[4]
                if change=='page': current['page']=DOC
                if change=='ink': current['ink_revision']+=1
                if change=='revision': current['content_revision']+=1
                if change=='file': saved+=b'changed'
                def read(path):
                    self.assertEqual(path,DOC+'/'+PAGE+'.rm')
                    if change=='during-read': current['ink_revision']+=1
                    return saved
                with self.subTest(change=change), self.assertRaises(ValueError):
                    store.finish_capture(body,lambda:current,read)
                self.assertFalse(store.measurements)
            self.assertTrue(store.finish_capture(reply,context,lambda _:raw)['measured'])
            with self.assertRaises(ValueError):
                store.finish_capture(reply,context,lambda _:raw)
            with self.assertRaises(ValueError):
                InkRuns(directory,KEY).finish_capture(reply,context,lambda _:raw)

    def setup_run(self,directory,before):
        store=InkRuns(directory,KEY)
        catalog=InkCatalog(manifest(str(AUTHOR)))
        blocks=[dict(kind='ink',**catalog.get('unit-square-integral',s)) for s in ('see','measure','notice')]
        result=store.register(REQUEST,DOC+'/'+PAGE+'.rm',context(),blocks,before,preservation=True)
        self.assertEqual(result,{'registered':3})
        for b in blocks:
            q=dict(request=REQUEST,page=DOC+'/'+PAGE+'.rm',scene=b['scene'],stage=b['stage'],
                   surface=context()['surface'],ink_revision=4,revision=8,origin=[-468,630],ui_locked=True)
            store.claim(q,context,lambda *args:None)
            store.complete({k:q[k] for k in ('request','scene','stage')})
        assets={a['stage']:a['data'] for a in storyboard_assets(integral_storyboard(),str(AUTHOR),ink_labels=True)}
        return store,assets

    def test_complete_lesson_accepts_regroup_but_holds_changed_old_ink(self):
        from ink import strokes
        before, regrouped = fixture()
        with tempfile.TemporaryDirectory() as directory:
            store,assets=self.setup_run(directory,before)
            paths=[p for raw in assets.values() for _,p,_ in strokes(raw)]
            after=append(regrouped,[[(x,y+1000,w) for x,y,w in p] for p in paths])
            read_source=lambda b:assets[b['stage']]
            proof=lambda raw:store.saved_proof(REQUEST,lambda _:raw,read_source,context)
            waiting=proof(after)
            self.assertEqual(waiting['state'],'waiting')
            store.finish_capture(dict(command=waiting['measure_layout'],first=measurement(after)['first']),context,lambda _:after)
            result=proof(after)
            self.assertEqual(result['state'],'persisted')
            self.assertEqual(result['strokes'],len(paths))
            # Measured transform does not let changed color/geometry sneak past.
            import struct
            bad=change_first_line(after,lambda f:f.__setitem__(2,(4,struct.pack('<I',1))))
            waiting=proof(bad)
            store.finish_capture(dict(command=waiting['measure_layout'],first=measurement(bad)['first']),context,lambda _:bad)
            held=proof(bad)
            self.assertEqual(held['state'],'waiting')
            self.assertIn('old native stroke',held['reason'])
            # Restart has no cached native coordinates; saved v3 baseline remains.
            self.assertIn('measure_layout',InkRuns(directory,KEY).saved_proof(REQUEST,lambda _:after,read_source,context))

    def test_writing_while_a_reply_draws_remeasures_and_still_proves_old_ink(self):
        from ink import strokes
        before, regrouped = fixture()
        with tempfile.TemporaryDirectory() as directory:
            store,assets=self.setup_run(directory,before)
            paths=[p for raw in assets.values() for _,p,_ in strokes(raw)]
            drawn=append(regrouped,[[(x,y+1000,w) for x,y,w in p] for p in paths])
            after=append(drawn,[[(100,1500,2),(140,1520,2)]])  # James's next question begins
            written=lambda:dict(context(),ink_revision=5,content_revision=9)
            read_source=lambda b:assets[b['stage']]
            proof=lambda raw,current:store.saved_proof(REQUEST,lambda _:raw,read_source,current)
            waiting=proof(after,written)
            self.assertEqual(waiting['measure_layout']['ink_revision'],5)
            store.finish_capture(dict(command=waiting['measure_layout'],first=measurement(after)['first']),written,lambda _:after)
            self.assertEqual(proof(after,written)['state'],'persisted')
            moved=lambda:dict(written(),page=DOC)
            self.assertIn('native page changed',proof(after,moved)['reason'])
            import struct
            bad=change_first_line(after,lambda f:f.__setitem__(2,(4,struct.pack('<I',1))))
            waiting=proof(bad,written)
            store.finish_capture(dict(command=waiting['measure_layout'],first=measurement(bad)['first']),written,lambda _:bad)
            self.assertIn('old native stroke',proof(bad,written)['reason'])

    def test_anchored_before_requires_capture_before_writing_baseline(self):
        _, before = fixture()
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory,KEY)
            catalog=InkCatalog(manifest(str(AUTHOR)))
            blocks=[dict(kind='ink',**catalog.get('unit-square-integral','see'))]
            r=store.register(REQUEST,DOC+'/'+PAGE+'.rm',context(),blocks,before,preservation=True)
            self.assertIn('measure_layout',r)
            self.assertEqual(r['layout_reason'], 'initial')
            from pathlib import Path
            self.assertEqual(list(Path(directory).iterdir()),[])
            store.finish_capture(dict(command=r['measure_layout'],first=measurement(before)['first']),context,lambda _:before)
            self.assertEqual(store.register(REQUEST,DOC+'/'+PAGE+'.rm',context(),blocks,before,preservation=True),{'registered':1})
            plan=store._plan(REQUEST)
            self.assertEqual(plan['baseline_version'],3)
            baseline=store._read(REQUEST+'.before-ids.json')
            self.assertEqual(baseline['sha256'],measurement(before)['sha256'])
            self.assertEqual(set(baseline['text']),{'chars','styles','length','layout','order','blank'})
            self.assertTrue(all(len(value)==64 for value in baseline['text']['chars'].values()))

    def test_recapture_reasons_do_not_relax_snapshot_or_context_binding(self):
        from pathlib import Path
        _, before = fixture()
        with tempfile.TemporaryDirectory() as directory:
            store = InkRuns(directory, KEY)
            catalog = InkCatalog(manifest(str(AUTHOR)))
            blocks = [dict(kind='ink', **catalog.get('unit-square-integral', 'see'))]
            register = lambda raw, ctx: store.register(REQUEST, DOC+'/'+PAGE+'.rm', ctx, blocks, raw, preservation=True)
            initial = register(before, context())
            store.finish_capture(dict(command=initial['measure_layout'], first=measurement(before)['first']), context, lambda _:before)
            changed_context = dict(context(), content_revision=context()['content_revision']+1)
            again = register(before, changed_context)
            self.assertEqual(again['layout_reason'], 'context_changed')
            self.assertEqual(again['measure_layout']['content_revision'], changed_context['content_revision'])
            changed_raw = append(before, [[(30, 40, 2), (50, 60, 2)]])
            again = register(changed_raw, context())
            self.assertEqual(again['layout_reason'], 'snapshot_changed')
            self.assertNotEqual(again['measure_layout']['sha256'], initial['measure_layout']['sha256'])
            self.assertEqual(list(Path(directory).iterdir()), [], 'no registration before a fresh matching capture')


if __name__=='__main__':
    unittest.main()
