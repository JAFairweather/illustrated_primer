import copy
import hashlib
import struct
import unittest

from ink import blocks, last_item, strokes
from notebook_stroke_asset import storyboard_assets, label_paths
from notebook_storyboard import gravity_storyboard, integral_storyboard, odd_squares_storyboard


AUTHOR = '4b4acc76-62ce-428b-8602-a7ad7ac9e330'


class StrokeAssetTest(unittest.TestCase):
    def test_superscript_label_is_an_actual_raised_digit_not_a_missing_glyph_box(self):
        ordinary, width = label_paths('2')
        raised, small_width = label_paths('²')
        self.assertLess(small_width,width)
        self.assertLess(max(y for line in raised for _,y in line), max(y for line in ordinary for _,y in line))
        self.assertNotEqual(ordinary,raised)
        for invalid in ('unhandled ∂', 'wrapped\nlabel', 'tab\tlabel'):
            with self.assertRaisesRegex(ValueError,'unsupported'):
                label_paths(invalid)

    def test_only_structure_and_authored_strokes_never_text_or_images(self):
        plan = integral_storyboard()
        assets = storyboard_assets(plan, AUTHOR)
        self.assertEqual([a['stage'] for a in assets], ['see', 'measure', 'notice'])
        for asset in assets:
            raw = asset['data']
            self.assertEqual(set(k for k, r in blocks(raw)), {0, 1, 2, 4, 5, 9, 10})
            self.assertEqual(len(raw), 43+sum(len(r) for k, r in blocks(raw)))
            self.assertEqual(asset['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertNotIn(b'The integral', raw)
            decoded = strokes(raw)
            expected = next(s['paths'] for s in plan['stages'] if s['id'] == asset['stage'])
            self.assertEqual(len(decoded), asset['stroke_count'])
            self.assertEqual(sum(len(p) for _, p, _ in decoded), asset['point_count'])
            for (tool, points, ours), path in zip(decoded, expected):
                self.assertEqual(tool, 17)
                self.assertTrue(ours)
                for (x, y, width), (px, py) in zip(points, path):
                    self.assertAlmostEqual(x, px, places=3)
                    self.assertAlmostEqual(y, py, places=3)
                    self.assertTrue(1.0 <= width <= 2.6)  # the hand-drawn pen's pressure swell around 2

    def test_fresh_author_by_default_and_reproducible_explicit_author(self):
        plan = gravity_storyboard()
        self.assertEqual(storyboard_assets(plan, AUTHOR), storyboard_assets(plan, AUTHOR))
        self.assertNotEqual(storyboard_assets(plan)[0]['sha256'], storyboard_assets(plan)[0]['sha256'])
        self.assertEqual([a['stage'] for a in storyboard_assets(plan)], ['release', 'accelerate', 'compare'])

    def test_all_lines_share_isolated_layer_and_have_unique_ordered_ids(self):
        asset = storyboard_assets(integral_storyboard(), AUTHOR)[1]
        lines = [r for k, r in blocks(asset['data']) if k == 5]
        self.assertEqual([last_item(r) for r in lines],
                         [((0, 11), (1, n)) for n in range(15, 15+len(lines))])
        page = next(r for k, r in blocks(asset['data']) if k == 10)
        self.assertEqual(struct.unpack_from('<I', page, 19)[0], 0)  # text char count

    def test_rejects_invalid_late_geometry_without_returning_partial_assets(self):
        plan = integral_storyboard()
        original = copy.deepcopy(plan)
        storyboard_assets(plan, AUTHOR)
        self.assertEqual(plan, original)
        plan['stages'][-1]['paths'] = [[(0, 0), (float('nan'), 1)]]
        with self.assertRaises(ValueError):
            storyboard_assets(plan)

    def test_explicit_short_ink_labels_keep_prose_out_and_respect_point_budgets(self):
        for plan in (integral_storyboard(), gravity_storyboard(), odd_squares_storyboard()):
            original = copy.deepcopy(plan)
            plain = storyboard_assets(plan, AUTHOR)
            labelled = storyboard_assets(plan, AUTHOR, ink_labels=True)
            self.assertEqual(plan, original)
            self.assertGreater(labelled[0]['stroke_count'], plain[0]['stroke_count'])
            for asset in labelled:
                self.assertEqual(asset['annotations_rendered_as'], 'ink-labels')
                self.assertLessEqual(asset['point_count'], 3000)
                self.assertLessEqual(asset['stroke_count'], 64)
                self.assertNotIn(7, [kind for kind, raw in blocks(asset['data'])])
                x0, y0, x1, y1 = asset['bounds']
                self.assertTrue(0 <= x0 <= x1 <= plan['width'])
                self.assertTrue(0 <= y0 <= y1 <= plan['height'])
            self.assertEqual(labelled[0]['program_digest'], plain[0]['program_digest'])
        plan = integral_storyboard()
        plan['stages'][0]['annotations'][0]['text'] = 'too long '*20
        with self.assertRaises(ValueError):
            storyboard_assets(plan, ink_labels=True)


if __name__ == '__main__':
    unittest.main()
