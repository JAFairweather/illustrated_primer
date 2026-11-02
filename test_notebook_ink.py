import math
import unittest
from PIL import Image, ImageDraw
from notebook_ink import line_art_paths, place_paths


class NotebookInkTest(unittest.TestCase):
    def sample(self):
        image = Image.new('L', (160, 100), 255)
        pen = ImageDraw.Draw(image)
        pen.line([(15, 15), (15, 85), (145, 85)], fill=0, width=3)
        pen.line([(20, 80), (50, 72), (80, 56), (110, 35), (140, 17)], fill=0, width=3)
        return image

    def test_native_plan_preserves_source_bounds_and_dense_sampling(self):
        image = self.sample()
        before = image.tobytes()
        plan = line_art_paths(image, 300, 180)
        self.assertEqual(before, image.tobytes())
        self.assertEqual(plan['kind'], 'native-pen-plan')
        self.assertLessEqual(plan['estimated_pen_seconds'], 15)
        for path in plan['paths']:
            self.assertTrue(all(0 <= x < 300 and 0 <= y < 180 for x, y in path))
            self.assertTrue(all(math.dist(a, b) <= 2.001 for a, b in zip(path, path[1:])))
        placed = place_paths(plan, 240, 1400)
        self.assertTrue(all(x >= 240 and y >= 1400 for path in placed for x, y in path))
        self.assertEqual(plan, line_art_paths(image, 300, 180))

    def test_transparency_is_white_paper(self):
        image = self.sample().convert('RGBA')
        image.putalpha(self.sample().point(lambda v: 255-v))
        plan = line_art_paths(image, 300, 180)
        self.assertTrue(plan['paths'])
        with self.assertRaisesRegex(ValueError, 'no usable'):
            line_art_paths(Image.new('RGBA', (100, 100), (0, 0, 0, 0)))

    def test_refuses_dense_unbounded_or_slow_art(self):
        for image in (Image.new('L', (100, 100), 0), Image.new('L', (1100, 1100), 255)):
            with self.assertRaises(ValueError):
                line_art_paths(image)
        with self.assertRaisesRegex(ValueError, 'pen budget'):
            line_art_paths(self.sample(), max_seconds=.01)
        with self.assertRaises(ValueError):
            line_art_paths(self.sample(), width=1200)
        with self.assertRaises(ValueError):
            place_paths({'paths': []}, float('nan'), 0)


if __name__ == '__main__':
    unittest.main()
