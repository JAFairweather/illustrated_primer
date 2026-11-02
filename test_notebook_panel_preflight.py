"""Budget feedback must precede layout work, without becoming acceptance."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from notebook_panel_examples import relationship_example, graph_reuse_example
from notebook_panel_shapes import compile_panel_shapes
from notebook_pen_budget import NativePenBudgetError, budget_feedback
from notebook_plotter_font import label_paths, original_glyphs
from notebook_procedural import _label_lines, _label_group, LabelPlacementError
from notebook_lesson import _primitive


class PanelPreflightTests(unittest.TestCase):
    def crowded(self):
        story, drafts = relationship_example()
        story['panels'] = story['panels'][:1]
        items = drafts['objects']['items'][:2]
        items += [dict(id=f'name-{i}', type='label', to='input',
                       text='Unavoidably many letters', side='auto') for i in range(5)]
        drafts = {'objects': dict(v=1, mode='panel-shapes', panel='objects', items=items)}
        return story, drafts

    def test_over_budget_labels_fail_before_search_without_changing_input(self):
        story, drafts = self.crowded()
        original = deepcopy((story, drafts))
        with patch('notebook_panel_shapes._place_labels') as place:
            with self.assertRaises(NativePenBudgetError) as failure:
                compile_panel_shapes(story, drafts)
        place.assert_not_called()
        detail = budget_feedback(failure.exception)['attempts'][0]['failure']
        self.assertEqual(detail['resource'], 'strokes')
        self.assertEqual(detail['limit'], 64)
        self.assertEqual(detail['panel'], 'objects')
        self.assertEqual(detail['phase'], 'before-label-placement')
        self.assertFalse(detail['exact'])
        self.assertFalse(detail['stroke_breakdown']['complete'])
        expected = 2 + 5 * len(label_paths('Unavoidably many letters', 18)[0])
        self.assertEqual(detail['observed'], expected)
        self.assertEqual((story, drafts), original)

    def test_word_wrapping_preserves_cost_under_both_existing_font_modes(self):
        def check():
            for text in ('Air molecules', 'A  B C', 'x² + y²', 'x₁ and x₂'):
                expected = len(label_paths(text, 18)[0])
                for lines in _label_lines(text):
                    actual = sum(len(_primitive(command)) for command in _label_group(lines, 300, 180))
                    self.assertEqual(expected, actual)
        check()
        with original_glyphs():
            check()

    def test_budget_pass_does_not_skip_collision_search(self):
        story, drafts = relationship_example()
        with patch('notebook_panel_shapes._place_labels', side_effect=LabelPlacementError('held')) as place:
            with self.assertRaises(LabelPlacementError):
                compile_panel_shapes(story, drafts)
        place.assert_called_once()

    def test_inherited_geometry_is_not_charged_to_new_stage(self):
        story, drafts = relationship_example()
        story['panels'] = story['panels'][:2]
        drafts = {key: drafts[key] for key in ('objects', 'forward')}
        result = compile_panel_shapes(story, drafts)
        first = result['panels']['objects']['plan']['stages'][0]
        later = result['panels']['forward']['plan']['stages']
        self.assertEqual(later[0], first)
        self.assertEqual(len(later), 2)

    def test_implicit_axis_label_cost_is_included(self):
        story, drafts = graph_reuse_example()
        story['panels'] = story['panels'][:1]
        story['acts'] = story['acts'][:1]
        drafts = {'axes': drafts['axes']}
        drafts['axes']['items'][0].update(x=[-444444.444, 444444.444], y=[-444444.444, 444444.444])
        drafts['axes']['items'] += [dict(id=f'dot-{i}', type='dot',
            **{'in':'ax'}, at=[i * 1000, 0]) for i in range(23)]
        # Axis labels are compiler-created, not explicit model label items;
        # their lettering plus otherwise-valid geometry exceeds the cap.
        with original_glyphs(), patch('notebook_panel_shapes._place_labels') as place:
            with self.assertRaises(NativePenBudgetError) as failure:
                compile_panel_shapes(story, drafts)
        place.assert_not_called()
        self.assertGreater(failure.exception.details['stroke_breakdown']['labels'], 39)


if __name__ == '__main__':
    unittest.main()
