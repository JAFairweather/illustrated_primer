import copy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from notebook_drawing import compile_storyboard
from notebook_lesson import compile_lesson, format_lesson
from notebook_lesson_eval import check_draft, render, compare
from notebook_lesson_native import native_semantic_bundle
from notebook_pen_budget import NativePenBudgetError, budget_feedback
from notebook_plotter_font import original_glyphs
from notebook_storyboard import _dense


def crowded_labels():
    return [dict(caption='Name the two regions.',draw=[
        dict(op='rect',id='left',origin=[20,180],size=[100,50]),
        dict(op='rect',id='right',origin=[400,180],size=[100,50]),
        *[dict(op='label',at=[20,30+row*30],text='H'*20,size=12) for row in range(4)]]),
        dict(caption='Add one relation.',draw=[dict(op='arrow',**{'from':[130,205],'to':[390,205]})]),
        dict(caption='Mark the result.',draw=[dict(op='circle',center=[450,280],radius=10)])]


def semantic(steps):
    return json.dumps(dict(v=1,mode='lesson',intent='A resource test',scene=dict(family='drawing'),
                           steps=steps,claims=[],takeaway='A resource test, not an accepted explanation.'))


class PenBudgetFeedbackTest(unittest.TestCase):
    def test_dense_preserves_paths_and_reports_exact_strokes(self):
        paths=[[(10,10),(11,10)]]*64
        self.assertEqual(_dense(paths),paths)
        with self.assertRaises(NativePenBudgetError) as caught:
            _dense(paths+[[(20,20),(21,20)]],stage=2,label_strokes=60)
        failure=budget_feedback(caught.exception)['attempts'][0]['failure']
        self.assertEqual(failure,dict(resource='strokes',observed=65,limit=64,exact=True,
            scope='stage',stage=2,strokes=65,
            stroke_breakdown=dict(labels=60,geometry=5,complete=True)))
        self.assertEqual(str(caught.exception),'storyboard stage exceeds the native pen budget')

    def test_dense_points_are_a_lower_bound_without_scanning_the_remainder(self):
        paths=[[(0,0),(5998,0)]]
        self.assertEqual(sum(map(len,_dense(paths))),3000)
        with self.assertRaises(NativePenBudgetError) as caught:
            # The later None must not be read after the first excessive segment.
            _dense([[(0,0),(6000,0),None]],stage=3,label_strokes=0)
        failure=budget_feedback(caught.exception)['attempts'][0]['failure']
        self.assertEqual((failure['resource'],failure['observed'],failure['limit'],failure['exact']),
                         ('points',3001,3000,False))
        self.assertEqual(failure['stroke_breakdown'],dict(labels=0,geometry=1,complete=True))
        with self.assertRaisesRegex(ValueError,'at least two points'):
            _dense([[(0,0)]])

    def test_both_fonts_report_label_cost_before_any_native_encoding(self):
        steps=crowded_labels(); original=copy.deepcopy(steps)
        with patch('notebook_lesson_native.storyboard_assets') as encoder:
            with self.assertRaises(ValueError) as caught:
                native_semantic_bundle(semantic(steps))
            encoder.assert_not_called()
        self.assertEqual(steps,original)
        feedback=budget_feedback(caught.exception)
        self.assertEqual([a['font'] for a in feedback['attempts']],['continuous','original'])
        for attempt,strokes,labels in zip(feedback['attempts'],(82,242),(80,240)):
            failure=attempt['failure']
            self.assertEqual((failure['stage'],failure['observed'],failure['limit'],failure['exact']),
                             (1,strokes,64,True))
            self.assertEqual(failure['stroke_breakdown'],dict(labels=labels,geometry=2,complete=True))
        # Consumers cannot alter compiler exception context through the report.
        feedback['attempts'][0]['failure']['limit']=10000
        self.assertEqual(budget_feedback(caught.exception)['attempts'][0]['failure']['limit'],64)

    def test_unexpanded_anchors_and_connections_report_only_lower_bounds(self):
        for deferred in [dict(op='label',target='left',text='Later'),
                         dict(op='connect',**{'from':'left','to':'right'})]:
            with self.subTest(deferred=deferred):
                steps=crowded_labels();steps[0]['draw'].append(deferred)
                with self.assertRaises(ValueError) as caught:
                    native_semantic_bundle(semantic(steps))
                failure=budget_feedback(caught.exception)['attempts'][0]['failure']
                self.assertEqual(failure['observed'],82)
                self.assertFalse(failure['exact'])
                self.assertFalse(failure['stroke_breakdown']['complete'])

    def test_partial_command_prefix_never_claims_a_complete_stage_count(self):
        steps=crowded_labels()
        for command in steps[0]['draw']:
            command.pop('id',None)
        steps[0]['draw'].append(dict(op='line',**{'from':[10,300],'to':[20,300]}))
        with self.assertRaises(ValueError) as caught:
            compile_lesson(steps,'Keep the remainder unmeasured.')
        failure=budget_feedback(caught.exception)['attempts'][0]['failure']
        self.assertEqual((failure['observed'],failure['command']),(82,6))
        self.assertFalse(failure['exact'])
        self.assertFalse(failure['stroke_breakdown']['complete'])

    def test_estimated_time_failure_is_not_a_device_timing(self):
        steps=crowded_labels()
        steps[0]['draw']=[dict(op='line',**{'from':[20,20+4*i],'to':[114,20+4*i]}) for i in range(60)]
        with self.assertRaises(ValueError) as caught:
            compile_lesson(steps,'Time budget fixture.',procedural=True)
        failure=budget_feedback(caught.exception)['attempts'][0]['failure']
        self.assertEqual((failure['resource'],failure['limit'],failure['strokes'],failure['points']),
                         ('estimated_seconds',30,60,2973))  # hand-drawn lines run a little longer
        self.assertAlmostEqual(failure['observed'],30.957)
        self.assertTrue(failure['exact'])

    def test_whole_lesson_point_budget_reports_prefix_scope(self):
        plan=dict(kind='native-pen-storyboard-plan',scene='budget',width=600,height=360,
            stages=[dict(id=f'step-{i}',title='Test',text='Test',paths=[[(10,10)]*2401],annotations=[])
                    for i in range(1,6)])
        with self.assertRaises(NativePenBudgetError) as caught:
            compile_storyboard(plan)
        failure=budget_feedback(caught.exception)['attempts'][0]['failure']
        self.assertEqual(failure,dict(resource='points',observed=12005,limit=12000,
                                     scope='lesson',exact=False,stage=5,stage_id='step-5'))

    def test_no_feedback_invented_from_prose_and_cause_traversal_is_bounded(self):
        for error in (ValueError('native budget exceeded'),NativePenBudgetError('legacy')):
            self.assertIsNone(budget_feedback(error))
        loop=ValueError('loop');loop.__cause__=loop
        self.assertIsNone(budget_feedback(loop))
        detail=dict(resource='strokes',observed=65,limit=64,exact=True)
        original=NativePenBudgetError('limit',details=detail)
        detail['limit']=999
        wrapped=ValueError('wrapper');wrapped.__cause__=original
        self.assertEqual(budget_feedback(wrapped)['attempts'][0]['failure']['limit'],64)
        with original_glyphs():
            with self.assertRaises(ValueError) as caught:
                native_semantic_bundle(semantic(crowded_labels()))
        self.assertEqual(len(budget_feedback(caught.exception)['attempts']),1)

    def test_offline_check_and_comparison_expose_feedback_but_no_rejected_ink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'draft.txt'
            source.write_text(format_lesson(crowded_labels(),'Resource test.'))
            result=check_draft(source,root/'checked')
            self.assertFalse(result['valid'])
            self.assertFalse(result['compiler_valid'])
            self.assertEqual(result['stages'],[])
            self.assertIn('resource_feedback',result)
            self.assertEqual(list((root/'checked').glob('*.rm')),[])
            self.assertEqual(list((root/'checked').glob('*.svg')),[])
            packet=dict(version=1,response_format='semantic-v1',questions=[
                dict(id='dense',question='Explain visually.',prompt='Fixed test.',prompt_sha256='fixed')])
            answers=dict(model='fixed-test-not-model-eval',answers=[
                dict(id='dense',response=semantic(crowded_labels()),prompt_sha256='fixed')])
            (root/'packet.json').write_text(json.dumps(packet))
            (root/'answers.json').write_text(json.dumps(answers))
            result=render(root/'packet.json',root/'answers.json',root/'rendered')
            self.assertFalse(result['rows'][0]['valid'])
            self.assertEqual(result['rows'][0]['stages'],[])
            self.assertIn('resource_feedback',result['rows'][0])
            self.assertEqual(list((root/'rendered').glob('*.rm')),[])
            compare(root/'rendered',None,root/'comparison.html')
            html=(root/'comparison.html').read_text()
            self.assertIn('Measured resource failure (not a repaired lesson)',html)
            self.assertIn('&quot;observed&quot;: 82',html)
            self.assertIn('&quot;limit&quot;: 64',html)

    def test_semantic_draft_check_preserves_raw_answer_and_uses_native_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'draft.json'
            raw=semantic(crowded_labels())
            source.write_text(raw)
            result=check_draft(source,root/'held',semantic=True)
            self.assertFalse(result['valid'])
            self.assertFalse(result['visual_lesson'])
            self.assertEqual(result['response_format'],'semantic-v1')
            self.assertEqual(result['resource_feedback']['attempts'][0]['failure']['observed'],82)
            self.assertEqual((root/'held/draft.txt').read_text(),raw)
            self.assertEqual(list((root/'held').glob('*.rm')),[])
            self.assertEqual(list((root/'held').glob('*.svg')),[])
            steps=[dict(caption='Start with a line.',draw=[dict(op='line',**{'from':[20,20],'to':[40,20]})]),
                   dict(caption='Add a circle.',draw=[dict(op='circle',center=[100,100],radius=20)]),
                   dict(caption='Add a region.',draw=[dict(op='rect',origin=[200,200],size=[50,50])])]
            source.write_text(semantic(steps))
            result=check_draft(source,root/'valid',semantic=True)
            self.assertTrue(result['valid'])
            self.assertTrue(result['visual_lesson'])
            self.assertEqual(result['mode'],'lesson')
            self.assertEqual(result['quality_status'],'unreviewed')
            self.assertEqual(len(result['stages']),3)
            self.assertEqual(list((root/'valid').glob('*.rm')),[])

    def test_semantic_check_distinguishes_plain_answers_and_clarification_from_lessons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'draft.json'
            for mode in ('answer','clarify'):
                source.write_text(json.dumps(dict(v=1,mode=mode,text='Please explain the context.')))
                result=check_draft(source,root/mode,semantic=True)
                self.assertTrue(result['valid'])
                self.assertTrue(result['compiler_valid'])
                self.assertFalse(result['visual_lesson'])
                self.assertFalse(result['tablet_proven'])
                self.assertEqual(result['mode'],mode)
                self.assertEqual(result['stages'],[])
                self.assertEqual(list((root/mode).glob('*.png')),[])

    def test_semantic_check_cli_and_size_policy(self):
        from notebook_semantic import MAX_BYTES
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'draft.json'
            source.write_text(semantic(crowded_labels()))
            script=Path(__file__).with_name('notebook_lesson_eval.py')
            run=subprocess.run([sys.executable,str(script),'check',str(source),str(root/'held'),'--semantic'],
                               text=True,capture_output=True,check=False)
            self.assertEqual(run.returncode,2,run.stderr)
            self.assertEqual(json.loads(run.stdout)['resource_feedback']['attempts'][0]['failure']['limit'],64)
            source.write_bytes(b'x'*(MAX_BYTES+1))
            with self.assertRaisesRegex(ValueError,'bounded'):
                check_draft(source,root/'large',semantic=True)
            self.assertFalse((root/'large').exists())
            with self.assertRaisesRegex(ValueError,'explicit semantic'):
                check_draft(source,root/'bad-option',semantic=1)
            self.assertFalse((root/'bad-option').exists())


if __name__=='__main__':
    unittest.main()
