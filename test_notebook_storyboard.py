import math
import unittest
from notebook_storyboard import integral_storyboard, gravity_storyboard, odd_squares_storyboard


class StoryboardTest(unittest.TestCase):
    def test_odd_square_growth_includes_the_general_counting_argument(self):
        from notebook_drawing import compile_storyboard
        plan = odd_squares_storyboard()
        compile_storyboard(plan)
        self.assertEqual([s['added_units'] for s in plan['stages']], [1, 3, 5, 7])
        self.assertEqual([s['total_units'] for s in plan['stages']], [1, 4, 9, 16])
        self.assertIn('k - 1', plan['stages'][-1]['text'])
        self.assertIn('first n odd numbers', plan['stages'][-1]['text'])
        self.assertEqual(plan['stages'][-1]['equation'], r'1+3+5+7=4^2=16')
        for stage in plan['stages']:
            self.assertLessEqual(stage['estimated_pen_seconds'], 30)
            for path in stage['paths']:
                self.assertTrue(all(0 <= x <= plan['width'] and 0 <= y <= plan['height'] for x, y in path))
                self.assertTrue(all(math.dist(a, b) <= 2.001 for a, b in zip(path, path[1:])))

    def test_apple_accelerates_over_equal_intervals_and_remains_a_single_apple(self):
        from notebook_drawing import compile_storyboard
        plan = gravity_storyboard()
        compiled = compile_storyboard(plan)
        p0, p1, p2 = plan['positions']
        self.assertAlmostEqual(p2[1]-p1[1], 3*(p1[1]-p0[1]))
        self.assertAlmostEqual(p2[1]-p0[1], 4*(p1[1]-p0[1]))
        self.assertIn('one apple, not three', plan['stages'][2]['text'])
        self.assertIn('not to scale', plan['stages'][-1]['text'])
        self.assertIn('air resistance omitted', plan['stages'][-1]['text'])
        self.assertFalse(plan['live_insertion_supported'])
        self.assertIn('stroke', compiled['required_operations'])
        for width, height in ((320, 300), (900, 500)):
            compile_storyboard(gravity_storyboard(width, height))
        for width, height in ((True, 400), (600, 299), (901, 400)):
            with self.assertRaises(ValueError):
                gravity_storyboard(width, height)

    def test_four_additive_stages_keep_caption_and_equation_out_of_ink(self):
        plan = integral_storyboard()
        self.assertEqual(plan['left_sum'], '7/32')
        self.assertEqual(plan['exact_area'], '1/3')
        self.assertFalse(plan['live_insertion_supported'])
        self.assertEqual([s['id'] for s in plan['stages']], ['see', 'measure', 'notice', 'conclude'])
        self.assertIn('11/96', plan['stages'][-1]['text'])
        for stage in plan['stages']:
            self.assertTrue(stage['text'])
            self.assertLessEqual(stage['estimated_pen_seconds'], 30)
            for path in stage['paths']:
                self.assertTrue(all(0 <= x <= plan['width'] and 0 <= y <= plan['height'] for x, y in path))
                self.assertTrue(all(math.dist(a, b) <= 2.001 for a, b in zip(path, path[1:])))
        self.assertEqual(plan['stages'][-1]['paths'], [])
        self.assertIn('\\frac{1}{3}', plan['stages'][-1]['equation'])

    def test_more_rectangles_improve_the_left_estimate(self):
        from fractions import Fraction
        self.assertLess(Fraction(integral_storyboard(4)['left_sum']), Fraction(integral_storyboard(8)['left_sum']))
        self.assertLess(Fraction(integral_storyboard(8)['left_sum']), Fraction(1, 3))

    def test_parameters_are_bounded_not_an_expression_interpreter(self):
        for value in (True, 0, 13, '4', float('nan')):
            with self.assertRaises(ValueError):
                integral_storyboard(value)
        for width, height in ((200, 300), (901, 300), (600, 501), (600, float('inf'))):
            with self.assertRaises(ValueError):
                integral_storyboard(width=width, height=height)


if __name__ == '__main__':
    unittest.main()
