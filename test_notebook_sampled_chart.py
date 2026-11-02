import copy
from fractions import Fraction
import unittest
from unittest.mock import patch

from notebook_semantic import compile_semantic, SemanticError
from notebook_semantic_examples import examples
from notebook_sampled_chart import sampled_chart
from notebook_stroke_asset import storyboard_assets
from notebook_motion_program import compile_motion_program


class SampledChartTests(unittest.TestCase):
    def spec(self, xs, ys, predicate):
        spec = examples()['sampled-growth']
        spec['scene']['objects'][0].update(x=xs, y=ys)
        spec['claims'][0]['predicate'] = predicate
        return spec

    def test_native_and_motion_paths_share_scaled_quantities(self):
        for xs, ys, predicate in [
                ([0,1,2,3,4], [100,110,121,133.1,146.41], 'increasing'),
                ([0,1,2,3], [0,5,20,45], 'increasing'),
                ([-2,-1,0,2], [12,6,3,1], 'decreasing'),
                ([0,1,2], [-20,5,-10], 'mixed'),
                ([0,1,2], [0,0,0], 'constant'),
                ([0,1,2], [-5,-5,-5], 'constant'),
                (list(range(8)), list(range(8)), 'increasing')]:
            with self.subTest(y=ys):
                spec = self.spec(xs, ys, predicate)
                before = copy.deepcopy(spec)
                plan = compile_semantic(spec)
                self.assertEqual(spec, before)
                self.assertEqual(plan, compile_semantic(spec))
                self.assertEqual(len(storyboard_assets(plan)), 4)
                self.assertEqual(len(compile_motion_program(plan)['stage_budgets']), 4)
                metric = plan['semantic']['metrics']['growth']
                self.assertEqual(list(map(Fraction, metric['y'])), list(map(lambda y: Fraction(str(y)), ys)))
                low, high = map(Fraction, metric['y_range'])
                self.assertLessEqual(low, 0)
                self.assertGreaterEqual(high, 0)
                self.assertFalse(metric['input_values_verified'])
                for x, y, p in zip(xs, ys, metric['points']):
                    self.assertAlmostEqual(p[0], 110+400*(x-xs[0])/(xs[-1]-xs[0]))
                    self.assertAlmostEqual(p[1], 265-200*float((Fraction(str(y))-low)/(high-low)))

    def test_strokes_stop_at_sample_boundary_and_do_not_smooth(self):
        component = sampled_chart(self.spec([0,1,2], [0,1,4], 'increasing')['scene']['objects'][0])
        points = component['metrics']['points']
        import math
        for a,b,line in zip(points, points[1:], component['parts']['links']):
            self.assertAlmostEqual(math.dist(a, line['from']), 3)
            self.assertAlmostEqual(math.dist(b, line['to']), 3)
            self.assertAlmostEqual(math.dist(a,b)-6, math.dist(line['from'],line['to']))
        self.assertEqual(len(component['parts']['samples']), 3)

    def test_invalid_data_is_rejected_before_native_allocation(self):
        mutations = [dict(x=[0,0,1]), dict(x=[2,1,0]), dict(x=[0,1]),
                     dict(y=[0,True,2]), dict(y=[0,float('nan'),2]),
                     dict(y=[0,1,1000001]), dict(x=list(range(9)),y=list(range(9))),
                     dict(x=[0,0.0000001,1],y=[0,0,2]), dict(x=[0,0.0000001,0.0000002]),
                     dict(y=[0,1,1.1234567]), dict(x_label='https://example.org'),
                     dict(y_label='A'*17), dict(origin=[0,0]), dict(function='eval(x)')]
        for changes in mutations:
            with self.subTest(changes=changes):
                spec=self.spec([0,1,2],[0,1,2],'increasing')
                spec['scene']['objects'][0].update(changes)
                with patch('notebook_lesson_native.storyboard_assets') as encoder:
                    from notebook_lesson_native import native_semantic_bundle
                    import json
                    with self.assertRaises(SemanticError):native_semantic_bundle(json.dumps(spec))
                    encoder.assert_not_called()

    def test_required_trend_and_dependency_claims(self):
        for predicate in ('increasing', 'decreasing', 'constant'):
            with self.assertRaises(SemanticError):
                compile_semantic(self.spec([0,1,2],[0,1,0],predicate))
        spec=self.spec([0,1,2],[0,1,2],'increasing')
        spec['claims']=[]
        with self.assertRaises(SemanticError):compile_semantic(spec)
        spec=self.spec([0,1,2],[0,1,2],'increasing')
        spec['steps'][2],spec['steps'][3]=spec['steps'][3],spec['steps'][2]
        with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_reference_uses_same_scale_and_exact_final_comparison(self):
        for ys,reference,predicate in [([100,110,121,133.1],[100,110,120,130],'final_above'),
                                       ([1,2,3,4],[-10,0,10,20],'final_below'),
                                       ([1,2,3,4],[4,3,2,4],'final_equal'),
                                       ([1,2,3,4],[1,2,3,4],'final_equal')]:
            with self.subTest(reference=reference):
                spec=examples()['sampled-comparison']
                spec['scene']['objects'][0].update(y=ys,reference={'label':'Reference','y':reference})
                spec['claims'][-1]['predicate']=predicate
                before=copy.deepcopy(spec)
                plan=compile_semantic(spec)
                self.assertEqual(before,spec)
                self.assertEqual(len(storyboard_assets(plan)),6)
                self.assertEqual(len(compile_motion_program(plan)['stage_budgets']),6)
                metric=plan['semantic']['metrics']['growth']
                low,high=map(Fraction,metric['y_range'])
                self.assertEqual(low,min([0]+ys+reference))
                self.assertEqual(high,max(map(lambda v:Fraction(str(v)),[0]+ys+reference)))
                for value,point in zip(reference,metric['reference']['points']):
                    self.assertAlmostEqual(point[1],265-200*float((Fraction(str(value))-low)/(high-low)))
                self.assertEqual(Fraction(metric['reference']['final_gap']),Fraction(str(ys[-1]))-Fraction(str(reference[-1])))

    def test_shared_segments_are_not_painted_twice(self):
        spec=examples()['sampled-comparison']
        component=sampled_chart(spec['scene']['objects'][0])
        self.assertEqual(component['metrics']['reference']['shared_segments'],[0])
        points=component['metrics']['reference']['points']
        # Ignore the two legend dashes; the first shared data interval emits no ink.
        self.assertTrue(all(line['from'][0]>=points[1][0] for line in component['parts']['reference_links'][2:]))
        for line in component['parts']['reference_links'][2:]:
            import math
            self.assertLessEqual(math.dist(line['from'],line['to']),16.0000001)

    def test_eight_sample_comparison_fits_existing_motion_caps(self):
        spec=examples()['sampled-comparison']
        spec['scene']['objects'][0].update(x=list(range(8)),y=list(range(8)),
            reference={'label':'Reference','y':list(reversed(range(8)))})
        plan=compile_semantic(spec)
        self.assertEqual(len(storyboard_assets(plan)),6)
        self.assertEqual(len(compile_motion_program(plan)['stage_budgets']),6)
        for stage in plan['stages']:
            self.assertLessEqual(stage['points'],3000)
            self.assertLessEqual(len(stage['paths']),64)
            self.assertLessEqual(stage['estimated_pen_seconds'],30)

    def test_both_sample_sets_can_precede_links_or_reference_can_come_first(self):
        original=examples()['sampled-comparison']
        parts=sampled_chart(original['scene']['objects'][0])['parts']
        for groups in ([['axes','scale'],['samples','reference_samples'],['links','reference_links'],['difference']],
                       [['axes','scale'],['reference_samples'],['reference_links'],['samples'],['links'],['difference']]):
            spec=copy.deepcopy(original)
            spec['steps']=[{'reveal':['growth.'+name for name in group],'caption':'The next measured comparison step.'}
                           for group in groups]
            plan=compile_semantic(spec)
            self.assertEqual(len(storyboard_assets(plan)),len(groups))
            self.assertEqual(len(compile_motion_program(plan)['stage_budgets']),len(groups))
            # Every same component command is retained; only authored grouping changes.
            from notebook_lesson import compile_lesson
            expected=compile_lesson([{'caption':step['caption'],'draw':[cmd for name in group for cmd in parts[name]]}
                                     for step,group in zip(spec['steps'],groups)],spec['takeaway'])
            self.assertEqual(plan['stages'],expected['stages'])
        spec=copy.deepcopy(original)
        spec['steps'][2],spec['steps'][-1]=spec['steps'][-1],spec['steps'][2]
        with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_reference_cannot_omit_or_falsify_claims_or_escape_bounds(self):
        mutations=[lambda s:s['claims'].pop(),
                   lambda s:s['claims'][-1].update(predicate='final_below'),
                   lambda s:s['scene']['objects'][0].pop('label'),
                   lambda s:s['scene']['objects'][0].update(reference=None),
                   lambda s:s['scene']['objects'][0]['reference'].update(y=[1,2]),
                   lambda s:s['scene']['objects'][0]['reference'].update(y=[1,2,3,True]),
                   lambda s:s['scene']['objects'][0]['reference'].update(y=[1,2,3,1000001]),
                   lambda s:s['scene']['objects'][0]['reference'].update(label='Compounded'),
                   lambda s:s['scene']['objects'][0]['reference'].update(label='A'*13),
                   lambda s:s['scene']['objects'][0]['reference'].update(origin=[1,2]),
                   lambda s:s['steps'][-1].update(reveal=['growth.reference_links'])]
        for mutate in mutations:
            spec=examples()['sampled-comparison'];mutate(spec)
            with self.assertRaises(SemanticError):compile_semantic(spec)


if __name__ == '__main__':unittest.main()
