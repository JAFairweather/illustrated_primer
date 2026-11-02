import copy
import json
import unittest
import hashlib
import uuid
from notebook_semantic import compile_semantic, SemanticError
from notebook_lesson import compile_lesson
from notebook_lesson_native import (native_semantic_bundle, source_document_files,
                                    lesson_source_archive, inspect_source_archive)
from notebook_ink_playback import validate_playback


def circle():
    return dict(v=1,mode='lesson',intent='Draw a circle',scene={'family':'drawing'},
        steps=[dict(caption='Here is a circle.',draw=[dict(op='circle',center=[300,180],radius=100)])],
        claims=[],takeaway='A circle is a closed round curve.')


class ShortDrawingTests(unittest.TestCase):
    def test_one_circle_uses_same_native_pipeline_and_limits(self):
        spec=circle(); before=copy.deepcopy(spec)
        bundle=native_semantic_bundle(json.dumps(spec),playback=True,pen_equations=True)
        self.assertEqual(spec,before)
        self.assertEqual([b['kind'] for b in bundle['blocks']],['text','text','ink','text'])
        ink=bundle['blocks'][2]
        self.assertEqual(ink['stroke_count'],1)
        self.assertEqual(ink['stage_count'],1)
        self.assertLessEqual(ink['point_count'],3000)
        playback=validate_playback(ink,bundle['sources'][0]['data'])
        self.assertEqual(playback['velocity'],600)
        self.assertLess(playback['duration_ms'],30000)

    def test_two_shapes_are_not_padded_with_extra_commands(self):
        spec=circle()
        spec['steps'].append(dict(caption='Add a small square.',draw=[dict(op='rect',origin=[20,20],size=[50,50])]))
        self.assertEqual(len(compile_semantic(spec)['stages']),2)

    def test_short_drawings_pass_complete_native_archive_pipeline(self):
        for count in (1,2):
            spec=circle()
            if count==2:
                spec['steps'].append(dict(caption='Add a square.',draw=[dict(op='rect',origin=[20,20],size=[50,50])]))
            bundle=native_semantic_bundle(json.dumps(spec),playback=True)
            parent=str(uuid.uuid4());template={'cPages':{},'fileType':'notebook'}
            source_document_files(bundle,template,parent)
            doc,data=lesson_source_archive(bundle,template,parent)
            inks=[b for b in bundle['blocks'] if b['kind']=='ink']
            for source,block in zip(bundle['sources'],inks):
                self.assertEqual(inspect_source_archive(data,doc,parent,source['source_page'],block['stroke_count']),
                                 hashlib.sha256(source['data']).hexdigest())
            broken=copy.deepcopy(bundle);broken['sources'].pop()
            with self.assertRaises(ValueError):source_document_files(broken,template,parent)
            teaching=copy.deepcopy(bundle);teaching['plan'].pop('semantic')
            with self.assertRaises(ValueError):source_document_files(teaching,template,parent)

    def test_empty_overlong_unsafe_or_false_claims_still_hold(self):
        for case in ('empty','seven','radius','outside','unknown','claim'):
            spec=circle()
            if case=='empty':spec['steps']=[]
            if case=='seven':spec['steps']*=7
            if case=='radius':spec['steps'][0]['draw'][0]['radius']=1000
            if case=='outside':spec['steps'][0]['draw'][0]['center']=[0,0]
            if case=='unknown':spec['steps'][0]['draw'][0]['url']='https://example.com'
            if case=='claim':spec['claims']=[dict(predicate='true')]
            with self.subTest(case=case),self.assertRaises(SemanticError):compile_semantic(spec)

    def test_legacy_lessons_keep_three_step_minimum(self):
        spec=circle()
        with self.assertRaisesRegex(ValueError,'3..6'):
            compile_lesson(spec['steps'],spec['takeaway'])
