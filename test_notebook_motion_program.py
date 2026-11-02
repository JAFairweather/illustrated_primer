import copy
import unittest
from unittest.mock import patch

from notebook_motion_program import compile_motion_program
from notebook_drawing import compile_storyboard
from notebook_storyboard import _dense
from notebook_semantic import compile_semantic
from notebook_semantic_examples import examples


def plan(paths):
    return dict(kind='native-pen-storyboard-plan',scene='motion-test',width=600,height=360,
                stages=[dict(id='first',title='First',text='Explain the lines.',paths=_dense(paths),annotations=[])])


class MotionProgramTests(unittest.TestCase):
    def test_lengths_control_duration_and_order(self):
        p=plan([[(10,10),(250,10)],[(10,50),(490,50)],[(10,90),(12,90)]])
        original=copy.deepcopy(p)
        r=compile_motion_program(p)
        strokes=[op for op in r['operations'] if op['kind']=='motion_stroke']
        self.assertEqual([round(s['motion_seconds'],5) for s in strokes],[1,2,.1])
        self.assertEqual(r['operations'][0]['kind'],'caption')
        self.assertEqual([s['stroke'] for s in strokes],[0,1,2])
        self.assertEqual(p,original)
        self.assertEqual(r,compile_motion_program(p))
        self.assertFalse(r['live_insertion_supported'])
        for op,source in zip(strokes,p['stages'][0]['paths']):
            self.assertEqual(op['contacts'][0]['points'][0],tuple(source[0]))
            self.assertEqual(op['contacts'][-1]['points'][-1],tuple(source[-1]))

    def test_validate_later_stage_before_sampling_anything(self):
        p=plan([[(0,0),(100,0)]])
        p['stages'].append(dict(id='bad',title='Bad',text='Invalid.',paths=[[(0,0),(999,0)]]))
        with patch('notebook_motion_program.sample_motion_path') as sampler:
            with self.assertRaises(ValueError):compile_motion_program(p)
            sampler.assert_not_called()

    def test_interleaved_payloads_and_stage_order_are_preserved(self):
        p=plan([[(10,10),(100,10)]])
        p['stages'][0].update(annotations=[dict(text='Start',point=(10,20))],
                              equation='1+1=2')
        second=copy.deepcopy(p['stages'][0])
        second.update(id='second',title='Second',text='Now connect the idea.',
                      annotations=[dict(text='Finish',point=(100,20))],equation='2+1=3')
        p['stages'].append(second)
        source=compile_storyboard(p)['operations']
        actual=compile_motion_program(p)['operations']
        self.assertEqual([(op['kind'],op['stage']) for op in actual],
                         [(kind,stage) for stage in ('first','second')
                          for kind in ('caption','motion_stroke','annotation','equation')])
        self.assertEqual([op for op in actual if op['kind']!='motion_stroke'],
                         [op for op in source if op['kind']!='stroke'])

    def test_aggregate_lesson_expansion_budget(self):
        p=plan([[(10,i*20),(590,i*20)] for i in range(1,6)])
        # Each expanded stage fits; five together exceed 12,000 points.
        one=compile_motion_program(p)
        self.assertLessEqual(one['points'],3000)
        self.assertGreater(one['points']*5,12000)
        p['stages']=[dict(copy.deepcopy(p['stages'][0]),id=f'stage-{i}') for i in range(5)]
        self.assertLessEqual(compile_storyboard(p)['points'],12000)
        with self.assertRaisesRegex(ValueError,'expanded motion.*budget'):
            compile_motion_program(p)

    def test_slow_speed_crosses_aggregate_stage_time_limit(self):
        p=plan([[(10,i*20),(470,i*20)] for i in range(1,4)])
        faster=compile_motion_program(p,60)['stage_budgets']['first']
        self.assertLess(faster['estimated_pen_seconds'],30)
        # At speed 50: 27.6s motion + 45 contacts * .070s = 30.75s.
        # Both point and contact caps still fit, and each stroke is <30s.
        with self.assertRaisesRegex(ValueError,'expanded motion.*budget'):
            compile_motion_program(p,50)

    def test_expansion_cannot_evade_stage_budget(self):
        p=plan([[(10,i*20),(590,i*20)] for i in range(1,10)])
        with self.assertRaisesRegex(ValueError,'budget'):compile_motion_program(p)

    def test_contact_expansion_cannot_evade_stroke_budget(self):
        # At contact 66: 33*.68 + 66*.07 = 27.06s, so the stroke cap
        # rather than the 30s time cap is the first failing constraint.
        p=plan([[(10,i*4),(44,i*4)] for i in range(64)])
        with self.assertRaisesRegex(ValueError,'budget'):compile_motion_program(p,50)

    def test_speed_validation(self):
        p=plan([[(0,0),(100,0)]])
        for value in (True,0,49,1001,float('nan'),float('inf'),'240'):
            with self.assertRaises(ValueError):compile_motion_program(p,value)

    def test_semantic_fixtures_compile_without_model_coordinates(self):
        for name,spec in examples().items():
            with self.subTest(name=name):
                r=compile_motion_program(compile_semantic(spec))
                self.assertGreater(r['points'],0)
                for budget in r['stage_budgets'].values():
                    self.assertLessEqual(budget['points'],3000)
                    self.assertLessEqual(budget['contacts'],64)
                    self.assertLessEqual(budget.get('estimated_pen_seconds',0),30)


if __name__=='__main__':unittest.main()
