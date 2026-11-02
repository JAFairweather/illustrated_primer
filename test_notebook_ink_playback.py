import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from ink import append, strokes
from notebook_ink_runs import InkRuns
from notebook_ink_playback import playback_assets, validate_playback
from notebook_lesson_native import native_semantic_bundle
from notebook_semantic_examples import examples
from notebook_semantic import compile_semantic
from notebook_storyboard import _dense


AUTHOR = '4b4acc76-62ce-428b-8602-a7ad7ac9e330'


def plan(paths=None):
    return dict(kind='native-pen-storyboard-plan', scene='playback-test', width=600, height=360,
                stages=[dict(id='first', title='First', text='Follow the line.', annotations=[],
                             paths=_dense(paths or [[(20, 30), (500, 30)]]))])


class PlaybackTests(unittest.TestCase):
    def test_exact_native_paths_and_constant_velocity(self):
        source = plan([[(20,30),(260,30),(260,270)],[(300,30),(420,30)]])
        original = copy.deepcopy(source)
        asset = playback_assets(source,AUTHOR)[0]
        self.assertEqual(source,original)
        self.assertEqual(asset,playback_assets(source,AUTHOR)[0])
        descriptor = validate_playback(asset,asset['data'])
        self.assertEqual(descriptor['paths'],[[[x,y] for x,y,_ in p] for _,p,_ in strokes(asset['data'])])
        self.assertEqual(descriptor['velocity'],600)
        self.assertAlmostEqual(descriptor['duration_ms'],1012)
        self.assertEqual(asset['stroke_count'],2)
        self.assertNotIn('reveal',asset)

    def test_faster_default_changes_only_timing_not_geometry_or_saved_ink(self):
        source = plan()
        old = playback_assets(source, AUTHOR, velocity=250)[0]
        new = playback_assets(source, AUTHOR)[0]
        self.assertEqual(new['data'], old['data'])
        self.assertEqual(new['playback']['paths'], old['playback']['paths'])
        self.assertAlmostEqual(new['playback']['duration_ms'], old['playback']['duration_ms']/2.4)
        # An already-issued slower descriptor must remain valid after tuning.
        validate_playback(old, old['data'])
        validate_playback(new, new['data'])

    def test_dots_have_bounded_dwell_and_pen_up(self):
        asset = playback_assets(plan([[(20,30),(20,30)],[(40,50),(40,50)]]),AUTHOR)[0]
        self.assertEqual(asset['playback']['duration_ms'],32)

    def test_tampering_cannot_differ_from_saved_native_ink(self):
        asset=playback_assets(plan(),AUTHOR)[0]
        for mutate in (
            lambda a:a['playback']['paths'][0][0].__setitem__(0,21),
            lambda a:a['playback'].__setitem__('duration_ms',1),
            lambda a:a['playback'].__setitem__('extra','ignored?'),
            lambda a:a['playback'].__setitem__('pen_up_ms',0),
            lambda a:a['playback'].__setitem__('version',True),
            lambda a:a.__setitem__('reveal',[]),
            lambda a:a.__setitem__('stroke_count',2),
            lambda a:a.__setitem__('point_count',2),
            lambda a:a.__setitem__('sha256','0'*64)):
            broken=copy.deepcopy(asset); mutate(broken)
            with self.assertRaises(ValueError): validate_playback(broken,asset['data'])

    def test_velocity_and_time_limits(self):
        for value in (True,None,49,2001,float('nan'),float('inf')):
            with self.assertRaises(ValueError): playback_assets(plan(),AUTHOR,value)
        # Valid dense geometry may still take too long at the chosen pen velocity.
        long=plan([[(20,y),(500,y)] for y in (30,60,90,120)])
        with self.assertRaisesRegex(ValueError,'thirty seconds'): playback_assets(long,AUTHOR,50)

    def test_bad_final_stage_rejected_before_descriptor_creation(self):
        p=plan();p['stages'].append(dict(p['stages'][0],id='bad',paths=[[(0,0),(900,0)]]))
        with patch('notebook_ink_playback._descriptor') as describe:
            with self.assertRaises(ValueError): playback_assets(p)
            describe.assert_not_called()

    def test_semantic_bundle_retains_native_order_and_explicit_opt_in(self):
        response=json.dumps(examples()['integral'])
        plain=native_semantic_bundle(response)
        played=native_semantic_bundle(response,playback=True)
        self.assertEqual(len(plain['sources']),len(played['sources']))
        self.assertEqual([b for b in plain['blocks'] if b['kind']!='ink'],
                         [b for b in played['blocks'][1:] if b['kind']!='ink'])
        self.assertEqual(played['blocks'][0],dict(kind='text',text='',styles=[]))
        for block,source in zip([b for b in played['blocks'] if b['kind']=='ink'],played['sources']):
            validate_playback(block,source['data'])
        self.assertTrue(all('playback' not in b for b in plain['blocks']))
        for kwargs in ({'playback':1},{'playback':True,'reveal':True}):
            with self.assertRaises(ValueError):native_semantic_bundle(response,**kwargs)

    def test_semantic_fixtures_fit_original_caps_and_actual_playback_time(self):
        for name,spec in examples().items():
            with self.subTest(name=name):
                for asset in playback_assets(compile_semantic(spec),AUTHOR):
                    self.assertLessEqual(asset['stroke_count'],64)
                    self.assertLessEqual(asset['point_count'],3000)
                    self.assertLessEqual(asset['playback']['duration_ms'],30000)
                    validate_playback(asset,asset['data'])

    def test_claim_and_overlay_do_not_count_as_persisted_native_strokes(self):
        doc='905df7ae-ff54-46b9-a71e-45bb02bef638'
        page='e77f5e27-eef9-492e-a402-9f578ce161f1'
        header=b'reMarkable .lines file, version=6'.ljust(43,b' ')
        asset=playback_assets(plan([[(20,30),(500,30)],[(20,70),(300,70)]]),AUTHOR)[0]
        block=dict(asset,kind='ink',scene='playback-test',stage_index=0,stage_count=1,
                   source_doc=AUTHOR,source_page=page)
        del block['data']
        paths=[[(x-400,y+700,w) for x,y,w in p] for _,p,_ in strokes(asset['data'])]
        context=dict(fresh=True,active=True,doc=doc,page=page,surface='surface',
                     ink_revision=4,content_revision=8,text_bounds=[-468,500,936,100])
        request='notebook-'+'6'*32;path=doc+'/'+page+'.rm'
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory)
            store.register(request,path,context,[block],header)
            claim=dict(request=request,page=path,scene='playback-test',stage='first',
                       surface='surface',ink_revision=4,revision=8,origin=[-468,630],ui_locked=True)
            store.claim(claim,lambda:context,lambda *args:None)
            store.complete({k:claim[k] for k in ('request','scene','stage')})
            def proof(ink):
                raw=append(header,ink,start=((0,11),(1,14)))
                return store.saved_proof(request,lambda _:raw,lambda _:asset['data'])
            self.assertEqual(proof([])['state'],'waiting')
            self.assertEqual(proof(paths[:-1])['state'],'waiting')
            self.assertEqual(proof(paths)['state'],'persisted')
            wrong=copy.deepcopy(paths);wrong[1]=[(x,y+20,w) for x,y,w in wrong[1]]
            self.assertEqual(proof(wrong)['state'],'waiting')


if __name__ == '__main__': unittest.main()
