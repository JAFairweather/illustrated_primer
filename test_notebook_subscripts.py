"""Subscript digits use measured pen paths, never font replacement boxes."""
import unittest
from contextlib import nullcontext

from notebook_plotter_font import label_paths, original_glyphs
from notebook_procedural import _label_group, _group_label_bounds
from notebook_panel_examples import graph_reuse_example
from notebook_story_native import native_story_bundle


class SubscriptTests(unittest.TestCase):
    def test_all_digits_share_superscript_shape_and_scale_but_lower_baseline(self):
        for context in (nullcontext, original_glyphs):
            with context():
                for size in (12, 18, 24, 28):
                    for raised, lowered in zip('⁰¹²³⁴⁵⁶⁷⁸⁹', '₀₁₂₃₄₅₆₇₈₉'):
                        upper, upper_width = label_paths(raised, size)
                        lower, lower_width = label_paths(lowered, size)
                        self.assertEqual(upper_width, lower_width)
                        self.assertEqual([len(p) for p in upper], [len(p) for p in lower])
                        for up, down in zip(upper, lower):
                            for (ux,uy), (dx,dy) in zip(up, down):
                                self.assertEqual(ux,dx)
                                self.assertAlmostEqual(dy-uy, .87*size)

    def test_subscripts_are_measured_below_normal_baseline(self):
        normal, _ = label_paths('0', 24)
        lowered, _ = label_paths('₀', 24)
        bottom = lambda paths: max(y for path in paths for x,y in path)
        self.assertGreater(bottom(lowered), bottom(normal))
        normal_bounds = _group_label_bounds(_label_group(['x0'], 0, 0))
        sub_bounds = _group_label_bounds(_label_group(['x₀'], 0, 0))
        self.assertGreater(sub_bounds[3], normal_bounds[3])
        self.assertLess(sub_bounds[2]-sub_bounds[0], normal_bounds[2]-normal_bounds[0])

    def test_numeric_limits_encode_in_native_story_without_rewriting_text(self):
        story, drafts = graph_reuse_example()
        text = '[x³/3]₀¹ = 1/3'
        drafts['mark']['items'] = [dict(id='limits',type='label',to='square',
                                      text=text,side='right')]
        bundle = native_story_bundle(story, drafts)
        self.assertEqual(bundle['mode'], 'story')
        self.assertEqual(drafts['mark']['items'][0]['text'], text)
        self.assertLessEqual(bundle['delivery_points'], 12000)

    def test_unknown_characters_still_fail_instead_of_replacement_boxes(self):
        for label in ('x₀🙂', 'x\ufffd', 'x\u0378'):
            with self.assertRaisesRegex(ValueError, 'unsupported diagram-label glyph'):
                label_paths(label)


if __name__ == '__main__': unittest.main()
