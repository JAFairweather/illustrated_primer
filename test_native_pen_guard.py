import io
import struct
import unittest
from unittest.mock import patch
from tablet_live import draw_paths


class InputBuffer(io.BytesIO):
    def close(self):
        self.saved = self.getvalue()
        super().close()


class FakeInput:
    def __init__(self):
        self.stdin = InputBuffer()
        self.stderr = io.BytesIO()
        self.returncode = 0
        self.waited = False

    def wait(self, timeout):
        self.waited = True


class NativePenGuardTest(unittest.TestCase):
    def test_timed_motion_uses_arc_length_and_monotonic_deadlines(self):
        child=FakeInput();clock=[0.0];checks=[]
        def sleep(seconds):clock[0]+=seconds
        def guard():
            checks.append(clock[0]);clock[0]+=.01
            return True
        with patch('tablet_live.subprocess.Popen',return_value=child), \
                patch('tablet_live.time.sleep',side_effect=sleep), \
                patch('tablet_live.time.monotonic',side_effect=lambda:clock[0]):
            draw_paths([[(200,300),(210,300),(300,300)]],[],{},duration=2.5,guard=guard)
        # Motion targets are 10% and 100% of the duration, not equal time
        # per vertex. Guard overhead is not accumulated into every deadline.
        self.assertAlmostEqual(checks[-1]-checks[-2],2.25)
        self.assertAlmostEqual(clock[0],2.61)

    def test_timed_motion_does_not_skip_points_when_guard_is_slow(self):
        child=FakeInput();clock=[0.0]
        def guard():clock[0]+=.2;return True
        with patch('tablet_live.subprocess.Popen',return_value=child), \
                patch('tablet_live.time.sleep',side_effect=lambda t:clock.__setitem__(0,clock[0]+t)), \
                patch('tablet_live.time.monotonic',side_effect=lambda:clock[0]):
            draw_paths([[(200,300),(210,300),(300,300)]],[],{},duration=.1,guard=guard)
        events=[(kind,code,value) for _,_,kind,code,value in struct.iter_unpack('<iiHHi',child.stdin.saved)]
        self.assertEqual(sum(kind==3 and code==0 for kind,code,_ in events),3)
        self.assertGreater(clock[0],1)

    def test_bad_duration_or_zero_length_refused_before_device_open(self):
        with patch('tablet_live.subprocess.Popen') as popen:
            for duration in (True,0,-1,11,float('nan'),float('inf'),'3'):
                with self.assertRaises(ValueError):
                    draw_paths([[(200,300),(300,300)]],[],{},duration=duration)
            with self.assertRaises(ValueError):
                draw_paths([[(200,300),(200,300)]],[],{},duration=2.5)
            popen.assert_not_called()

    def test_failed_initial_lease_never_opens_device(self):
        with patch('tablet_live.subprocess.Popen') as popen:
            for value in (False, None, 1, 'yes'):
                with self.assertRaisesRegex(RuntimeError, 'lease'):
                    draw_paths([[(200, 300), (201, 300)]], [], {}, guard=lambda: value)
            popen.assert_not_called()

    def test_mid_stroke_failure_releases_pen_and_stops_all_later_points(self):
        child = FakeInput()
        calls = []
        def guard():
            calls.append(1)
            return len(calls) < 5
        with patch('tablet_live.subprocess.Popen', return_value=child), patch('tablet_live.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'lease'):
                draw_paths([[(200, 300), (201, 300), (202, 300)],
                            [(500, 500), (501, 500)]], [], {}, guard=guard)
        records = list(struct.iter_unpack('<iiHHi', child.stdin.saved))
        events = [(kind, code, value) for _, _, kind, code, value in records]
        self.assertEqual(events[-5:], [(3, 24, 0), (3, 25, 100), (1, 330, 0), (1, 320, 0), (0, 0, 0)])
        self.assertEqual(events.count((1, 330, 1)), 1)
        self.assertTrue(child.waited)

    def test_empty_and_invalid_paths_never_open_device(self):
        with patch('tablet_live.subprocess.Popen') as popen:
            draw_paths([], [], {}, guard=lambda: True)
            for paths in ([[(200, 300), (-1, 300)]], [[(200, 300), (200, 2000)]]):
                with self.assertRaises(ValueError):
                    draw_paths(paths, [], {})
            for pace in (-1, True, float('nan'), float('inf')):
                with self.assertRaises(ValueError):
                    draw_paths([[(200, 300), (201, 300)]], [], {}, pace=pace)
            popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
