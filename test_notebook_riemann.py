"""General sampled-area geometry, not a tuned answer or a model-result repair."""
from copy import deepcopy
import unittest

from notebook_panel_shapes import _frame, _lower, _point, compile_panel_shapes
from notebook_panel_examples import graph_reuse_example
from notebook_story_native import native_story_bundle
from notebook_contract_feedback import item_fields
from notebook_lesson import _primitive


def item(**changes):
    return dict(dict(id='bars', type='riemann', **{'in': 'ax'},
        coefficients=[0, 0, 1], domain=[0, 1], baseline=0, count=6,
        sample='left'), **changes)


def frame(x=None, y=None):
    return _frame(dict(id='ax', type='axes', x=x or [0, 1],
                       y=y or [0, 1], aspect='independent'))


class RiemannTests(unittest.TestCase):
    def test_zero_sample_is_exact_baseline_without_fake_area(self):
        f = frame(); source = item(); before = deepcopy(source)
        commands = _lower(source, {'ax': f})
        self.assertEqual(len(commands), 6)
        self.assertEqual(commands[0]['points'], [_point(f, [0, 0]), _point(f, [1/6, 0])])
        self.assertEqual(source, before)
        for i, command in enumerate(commands[1:], 1):
            self.assertEqual(command['points'][1], _point(f, [i/6, (i/6)**2]))
            _primitive(command)

    def test_sampling_rules_and_signed_baselines_are_data_driven(self):
        f = frame([-2, 2], [-10, 10])
        for sample, offset in (('left', 0), ('midpoint', .5), ('right', 1)):
            source = item(coefficients=[-1, 2], domain=[-2, 2], baseline=3,
                          count=4, sample=sample)
            commands = _lower(source, {'ax': f})
            for i, command in enumerate(commands):
                left, right = i-2, i-1
                height = -1+2*(left+offset)
                expected = ([_point(f, [left, 3]), _point(f, [right, 3])]
                            if height == 3 else [_point(f, p) for p in
                            [[left,3],[left,height],[right,height],[right,3],[left,3]]])
                self.assertEqual(command['points'], expected)

    def test_subpixel_heights_are_not_inflated_or_dropped(self):
        f = frame(); height = 1e-8
        commands = _lower(item(coefficients=[height], count=2), {'ax': f})
        self.assertEqual(len(commands[0]['points']), 5)
        self.assertEqual(commands[0]['points'][1], _point(f, [0, height]))
        self.assertNotEqual(commands[0]['points'][0], commands[0]['points'][1])
        _primitive(commands[0])

    def test_bounds_types_and_unknown_fields_fail_without_clipping(self):
        for change in ({'count':True}, {'count':0}, {'count':17}, {'count':2.5},
                       {'sample':'random'}, {'sample':[]}, {'baseline':float('nan')},
                       {'baseline':2}, {'domain':[-1,1]}, {'domain':[0,0]},
                       {'coefficients':[2]}, {'coefficients':['x']},
                       {'coefficients':[0]*6}, {'path':'/tmp/example'}, {'fill':'hatch'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                _lower(item(**change), {'ax':frame()})

    def test_full_story_native_delivery_and_branch_preserve_base(self):
        story, drafts = graph_reuse_example()
        story['panels'] = story['panels'][:3]; story['acts'] = story['acts'][:1]
        drafts = {k: drafts[k] for k in ('axes', 'curve', 'mark')}
        drafts['mark']['items'] = [item()]
        before = deepcopy(drafts)
        compiled = compile_panel_shapes(story, drafts)
        self.assertEqual(compiled['panels']['curve']['plan']['stages'],
                         compiled['panels']['mark']['plan']['stages'][:2])
        bundle = native_story_bundle(story, drafts)
        self.assertEqual(bundle['mode'], 'story')
        self.assertLessEqual(bundle['delivery_points'], 12000)
        self.assertEqual(drafts, before)
        # Refinement branches from the curve, so it does not erase or overlap
        # the original bars in the same picture run.
        branch = deepcopy(story['panels'][-1]); branch.update(id='refined', base='curve')
        story['panels'].append(branch)
        drafts['refined'] = dict(v=1, mode='panel-shapes', panel='refined',
                                 items=[item(count=8, sample='midpoint')])
        branched = native_story_bundle(story, drafts)
        self.assertEqual(len(branched['plans']), 2)

    def test_existing_rectangle_validation_is_not_weakened(self):
        with self.assertRaises(ValueError):
            _lower(dict(id='bad', type='rect', **{'in':'ax'}, x=[0,1], y=[0,0]),
                   {'ax':frame()})
        item_fields(item())

    def test_many_high_level_items_cannot_bypass_native_budget(self):
        story, drafts = graph_reuse_example()
        story['panels'] = story['panels'][:2]; story['acts'] = story['acts'][:1]
        drafts = {k: drafts[k] for k in ('axes', 'curve')}
        drafts['curve']['items'] = [item(id='bars-'+str(i), count=16) for i in range(8)]
        with self.assertRaises(ValueError):
            native_story_bundle(story, drafts)


if __name__ == '__main__': unittest.main()
