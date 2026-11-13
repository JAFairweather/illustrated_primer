"""Synthetic sample reproducibility and fail-closed controls."""
import unittest

from handwriting_sample import select


def candidate(n):
    return {'page': f'p{n}', 'notebook': f'n{n % 5}', 'image_sha256': f'{n:064x}', 'eligible': True}


class HandwritingSampleTests(unittest.TestCase):
    def test_seeded_selection_is_order_independent(self):
        rows = [candidate(n) for n in range(130)]
        first = select(rows, 'B3-2026-11-12')
        second = select(list(reversed(rows)), 'B3-2026-11-12')
        self.assertEqual(first, second)
        self.assertEqual((len(first['sample']), len(first['reserves'])), (100, 20))
        self.assertEqual(len({r['page'] for r in first['sample'] + first['reserves']}), 120)

    def test_requires_real_candidate_pool_and_unique_pages(self):
        with self.assertRaisesRegex(ValueError, 'fewer than 100'):
            select([candidate(n) for n in range(99)], 'seed')
        rows = [candidate(n) for n in range(100)] + [candidate(1)]
        with self.assertRaisesRegex(ValueError, 'duplicate page'):
            select(rows, 'seed')
        duplicate = [candidate(n) for n in range(100)]
        duplicate[-1]['image_sha256'] = duplicate[0]['image_sha256']
        with self.assertRaisesRegex(ValueError, 'duplicate eligible image'):
            select(duplicate, 'seed')


if __name__ == '__main__':
    unittest.main()
