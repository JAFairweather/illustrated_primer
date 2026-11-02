import copy
import json
import math
import tempfile
import unittest
from unittest.mock import patch

from ink import append, strokes
from notebook_ink_reveal import reveal_assets, reveal_source_paths, _partition
from notebook_ink_runs import InkRuns
from notebook_lesson_native import native_semantic_bundle
from notebook_semantic_examples import examples
from notebook_semantic import compile_semantic
from notebook_storyboard import _dense


AUTHOR = '4b4acc76-62ce-428b-8602-a7ad7ac9e330'
DOC = '905df7ae-ff54-46b9-a71e-45bb02bef638'
PAGE = 'e77f5e27-eef9-492e-a402-9f578ce161f1'
HEADER = b'reMarkable .lines file, version=6'.ljust(43, b' ')


def plan(paths=None):
    return dict(kind='native-pen-storyboard-plan', scene='reveal-test', width=600, height=360,
                stages=[dict(id='first', title='First', text='Follow the line.', annotations=[],
                             paths=_dense(paths or [[(20, 30), (500, 30)]]))])


class RevealTests(unittest.TestCase):
    def test_long_line_splits_in_order_with_exact_shared_joints(self):
        source = plan()
        original = copy.deepcopy(source)
        asset = reveal_assets(source, AUTHOR)[0]
        self.assertEqual(source, original)
        self.assertEqual(asset, reveal_assets(source, AUTHOR)[0])
        self.assertEqual(len(asset['reveal']), 4)
        actual = reveal_source_paths(asset, asset['data'])
        self.assertEqual([p[0][:2] for p in actual], [(20,30),(140,30),(260,30),(380,30)])
        self.assertEqual([p[-1][:2] for p in actual], [(140,30),(260,30),(380,30),(500,30)])
        self.assertAlmostEqual(sum(math.dist(a[:2],b[:2]) for p in actual for a,b in zip(p,p[1:])),480)
        self.assertEqual(asset['point_count'], sum(map(len, actual)))
        self.assertEqual(asset['stroke_count'], 4)
        # Source selection rectangles do not touch, even with their margin.
        for first, second in zip(asset['reveal'], asset['reveal'][1:]):
            self.assertLess(first['rect'][1]+first['rect'][3], second['rect'][1])

    def test_partition_retains_corners_lifts_and_zero_length_dots(self):
        paths = [[(0,0),(3,0),(3,4)],[(10,10),(10,10)],[(30,30),(36,38)]]
        chunks = _partition(paths,4)
        flattened = [p for group in chunks for p in group]
        vertices = [p for path in flattened for p in path]
        for path in paths:
            for point in path: self.assertIn(point, vertices)
        self.assertIn([(10,10),(10,10)], flattened)
        self.assertAlmostEqual(sum(math.dist(a,b) for p in flattened for a,b in zip(p,p[1:])),17)
        self.assertTrue(all(not (p[0]==(3,4) and p[-1]==(30,30)) for p in flattened))

    def test_last_invalid_stage_rejected_before_any_partition(self):
        p=plan(); p['stages'].append(dict(p['stages'][0],id='bad',paths=[[(0,0),(900,0)]]))
        with patch('notebook_ink_reveal._partition') as split:
            with self.assertRaises(ValueError): reveal_assets(p)
            split.assert_not_called()

    def test_extra_strokes_cannot_bypass_original_caps(self):
        # 64 valid strokes; partition boundary cuts inside a stroke, making 65+.
        p=plan([[(10,4*i),(11+i/100,4*i)] for i in range(64)])
        with self.assertRaisesRegex(ValueError,'budget'): reveal_assets(p)
        for chunks in (0,5,True,2.5):
            with self.assertRaises(ValueError): reveal_assets(plan(),chunks=chunks)

    def test_metadata_tampering_or_unassigned_geometry_is_rejected(self):
        asset=reveal_assets(plan(),AUTHOR)[0]
        for mutate in (
            lambda a:a['reveal'][1]['offset'].__setitem__(1, 0),
            lambda a:a['reveal'][0]['rect'].__setitem__(3, 1000),
            lambda a:a['reveal'][0]['bounds'].__setitem__(0, 21),
            lambda a:a['reveal'][0].__setitem__('stroke_count',True),
            lambda a:a['reveal'][0].__setitem__('point_count',2),
            lambda a:a['reveal'].pop(),
            lambda a:a.__setitem__('sha256','0'*64)):
            broken=copy.deepcopy(asset);mutate(broken)
            with self.assertRaises(ValueError):reveal_source_paths(broken,asset['data'])

    def test_native_bundle_keeps_one_source_and_caption_per_stage(self):
        response=json.dumps(examples()['integral'])
        plain=native_semantic_bundle(response)
        revealed=native_semantic_bundle(response,reveal=True)
        self.assertEqual(len(plain['sources']),len(revealed['sources']))
        self.assertEqual([b for b in plain['blocks'] if b['kind']!='ink'],
                         [b for b in revealed['blocks'] if b['kind']!='ink'])
        for block, source in zip([b for b in revealed['blocks'] if b['kind']=='ink'],revealed['sources']):
            self.assertEqual(len(reveal_source_paths(block,source['data'])),block['stroke_count'])
        self.assertTrue(all('reveal' not in b for b in plain['blocks']))

    def test_all_semantic_fixtures_fit_without_relaxing_limits(self):
        for name, spec in examples().items():
            with self.subTest(name=name):
                assets=reveal_assets(compile_semantic(spec))
                self.assertLessEqual(sum(a['point_count'] for a in assets),12000)
                for a in assets:
                    self.assertLessEqual(a['stroke_count'],64)
                    self.assertLessEqual(a['point_count'],3000)
                    self.assertLessEqual(a['point_count']*.009+a['stroke_count']*.070,30)
                    self.assertEqual(len(reveal_source_paths(a,a['data'])),a['stroke_count'])

    def test_persistence_matches_all_chunks_at_one_common_destination(self):
        asset=reveal_assets(plan(),AUTHOR)[0]
        block=dict(asset,kind='ink',scene='reveal-test',stage_index=0,stage_count=1,
                   source_doc=AUTHOR,source_page=PAGE)
        del block['data']
        points=reveal_source_paths(block,asset['data'])
        translated=[[(x-400,y+700,w) for x,y,w in p] for p in points]
        context=dict(fresh=True,active=True,doc=DOC,page=PAGE,surface='surface',
                     ink_revision=4,content_revision=8,text_bounds=[-468,500,936,100])
        request='notebook-'+'5'*32;path=DOC+'/'+PAGE+'.rm'
        with tempfile.TemporaryDirectory() as directory:
            store=InkRuns(directory)
            store.register(request,path,context,[block],HEADER)
            claim=dict(request=request,page=path,scene='reveal-test',stage='first',
                       surface='surface',ink_revision=4,revision=8,origin=[-468,630],ui_locked=True)
            store.claim(claim,lambda:context,lambda *args:None)
            store.complete({k:claim[k] for k in ('request','scene','stage')})
            def proof(paths):
                raw=append(HEADER,paths,start=((0,11),(1,14)))
                return store.saved_proof(request,lambda _:raw,lambda _:asset['data'])
            self.assertEqual(proof(translated)['state'],'persisted')
            self.assertEqual(proof(translated[:-1])['state'],'waiting')
            wrong=copy.deepcopy(translated)
            wrong[1]=[(x,y+40,w) for x,y,w in wrong[1]]
            self.assertEqual(proof(wrong)['state'],'waiting')


if __name__=='__main__':unittest.main()
