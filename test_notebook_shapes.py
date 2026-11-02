import math
import unittest

from notebook_shapes import arrow, square_growth_layer


class ShapesTest(unittest.TestCase):
    def test_successive_odd_layers_tile_a_square_without_redrawing_edges(self):
        seen_edges, seen_cells = set(), set()
        for n in range(1, 7):
            layer = square_growth_layer(n, origin=(60, 400))
            self.assertEqual(layer['added_units'], 2*n-1)
            self.assertEqual(layer['total_units'], n*n)
            self.assertFalse(seen_edges.intersection(layer['edges']))
            self.assertFalse(seen_cells.intersection(layer['new_cells']))
            seen_edges.update(layer['edges'])
            seen_cells.update(layer['new_cells'])
            self.assertEqual(len(seen_cells), n*n)
            self.assertEqual(len(seen_edges), 2*n*(n+1))
            self.assertEqual(layer['anchors']['top_right'], (60+45*n, 400-45*n))
            # Each hatch stays strictly inside its own newly added unit cell.
            for (i, j), hatch in zip(layer['new_cells'], layer['paths'][len(layer['edges']):]):
                for x, y in hatch:
                    self.assertTrue(60+45*i < x < 60+45*(i+1))
                    self.assertTrue(400-45*(j+1) < y < 400-45*j)

    def test_motifs_are_deterministic_and_reject_invalid_geometry(self):
        self.assertEqual(square_growth_layer(3), square_growth_layer(3))
        for value in (True, 0, 7, '3', float('nan')):
            with self.assertRaises(ValueError):
                square_growth_layer(value)
        for kwargs in ({'cell': 0}, {'cell': True}, {'origin': (0, 1)},
                       {'origin': (-1, 400)}, {'origin': (0, float('inf'))}):
            with self.assertRaises(ValueError):
                square_growth_layer(3, **kwargs)

    def test_arrow_has_a_shared_tip_and_bounded_finite_head(self):
        stem, head = arrow((0, 0), (100, 50))
        self.assertEqual(stem[-1], head[1])
        self.assertLessEqual(math.dist(head[0], head[1]), 12)
        for end in ((0, 0), (float('inf'), 0), (float('nan'), 0)):
            with self.assertRaises(ValueError):
                arrow((0, 0), end)


if __name__ == '__main__':
    unittest.main()
