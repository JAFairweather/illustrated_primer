import struct
import unittest
from unittest import mock

import notebook_tablet_input as t


def events(blob):
    return [struct.unpack('<IIHHi', blob[i:i+16])[2:] for i in range(0, len(blob), 16)]


class PenTest(unittest.TestCase):
    def test_a_stroke_touches_in_its_first_write_and_lifts_in_its_last_with_no_sleeps(self):
        with mock.patch.object(t, '_run') as run:
            t.pen([[(100, 300), (400, 300)], [(100, 400), (100, 600)]])
        lines = run.call_args[0][0]
        self.assertEqual({kind for kind, _ in lines}, {'event1'})
        writes = [events(blob) for _, blob in lines]
        self.assertTrue(all(sum(e == (0, 0, 0) for e in w) <= t.BURST+1 for w in writes))
        flat = [e for w in writes for e in w]
        self.assertEqual(flat.count((1, 0x14a, 1)), 2)
        self.assertEqual(flat.count((1, 0x14a, 0)), 2)
        self.assertEqual(writes[0][0], (1, 0x140, 1))
        self.assertEqual(writes[-1][-2:], [(1, 0x140, 0), (0, 0, 0)])
        downs = [i for i, e in enumerate(flat) if e == (1, 0x14a, 1)]
        ups = [i for i, e in enumerate(flat) if e == (1, 0x14a, 0)]
        self.assertTrue(downs[0] < ups[0] < downs[1] < ups[1])
