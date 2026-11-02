"""Mathematical notation remains actual bounded ink, not text replacement."""
import unittest

from ink import strokes
from notebook_lesson import compile_lesson
from notebook_plotter_font import GLYPHS, label_paths, original_glyphs
from notebook_stroke_asset import storyboard_assets


SYMBOLS = '∝≈∞±÷·→←↔↑↓'


class MathGlyphTests(unittest.TestCase):
    def test_relations_are_distinct_bounded_static_paths_at_all_label_sizes(self):
        for size in (12, 18, 28):
            rendered = []
            for symbol in SYMBOLS:
                paths, advance = label_paths(symbol, size)
                self.assertTrue(paths)
                self.assertAlmostEqual(advance, size*.9)
                self.assertTrue(all(0 <= x <= size*4/6 and 0 <= y <= size
                                    for path in paths for x,y in path))
                self.assertTrue(all(len(path) >= 2 for path in paths))
                self.assertNotEqual(paths, label_paths('=',size)[0])
                rendered.append(repr(paths))
            self.assertEqual(len(set(rendered)),len(SYMBOLS))

    def test_proportionality_is_open_on_right_but_infinity_is_closed(self):
        with original_glyphs():
            proportional,_ = label_paths('∝',18)
            infinity,_ = label_paths('∞',18)
        self.assertEqual(len(proportional),1)
        self.assertEqual(proportional[0][0][0], proportional[0][-1][0])
        self.assertNotEqual(proportional[0][0][1], proportional[0][-1][1])
        self.assertEqual(infinity[0][0],infinity[0][-1])

    def test_math_notation_encodes_as_real_native_strokes_with_unchanged_limits(self):
        texts = ('a ∝ b²', 'u ≈ v ± 1', 'x → y · 2 ÷ 3')
        plan = compile_lesson([dict(caption='Add the mathematical relation.',draw=[
            dict(op='label',at=[150,80+index*80],text=text,size=18)])
            for index,text in enumerate(texts)],'The symbols retain their meanings.')
        assets=storyboard_assets(plan)
        for stage,asset in zip(plan['stages'],assets):
            self.assertLessEqual(asset['stroke_count'],64)
            self.assertLessEqual(asset['point_count'],3000)
            self.assertLessEqual(stage['estimated_pen_seconds'],30)
            decoded=strokes(asset['data'])
            self.assertEqual(len(decoded),len(stage['paths']))
            for (_,points,_),expected in zip(decoded,stage['paths']):
                self.assertEqual(len(points),len(expected))
                for point,target in zip(points,expected):
                    self.assertAlmostEqual(point[0],target[0],places=3)
                    self.assertAlmostEqual(point[1],target[1],places=3)

    def test_unknown_symbols_still_fail_instead_of_being_erased(self):
        for text in ('x ∂ y','unknown ℵ','newline\ntext'):
            with self.assertRaisesRegex(ValueError,'unsupported'):
                label_paths(text)


if __name__ == '__main__':
    unittest.main()
