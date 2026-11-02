import unittest
import itertools
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw

import tablet_acceptance as acceptance


class SafeInputTest(unittest.TestCase):
    def test_respond_helper_never_taps_pending_or_failed_request(self):
        for state in ('waiting', 'ready', 'writing', 'failed', 'no answer'):
            with self.subTest(state=state), \
                 patch.object(acceptance, 'notebook_status', return_value={'request': 'held', 'state': state}), \
                 patch.object(acceptance, 'tap') as tap, patch.object(acceptance, 'capture') as capture:
                with self.assertRaisesRegex(ValueError, 'observe/recover'):
                    acceptance.observe_reply('11111111-1111-1111-1111-111111111111',
                         '22222222-2222-2222-2222-222222222222', 'blocked')
                tap.assert_not_called(); capture.assert_not_called()

    def test_passive_watch_never_taps_or_draws_and_keeps_manual_review_gate(self):
        old = {'request': 'old', 'state': 'written'}
        waiting = {'request': 'new', 'state': 'waiting', 'respond_elapsed_ms': 2000}
        written = {'request': 'new', 'state': 'written', 'respond_elapsed_ms': 2700}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(acceptance, 'Path', return_value=Path(directory)), \
                patch.object(acceptance, 'notebook_status', side_effect=[old, old, waiting, written]), \
                patch.object(acceptance, 'capture', return_value=Image.new('L', (10, 10), 255)), \
                patch.object(acceptance.time, 'monotonic', side_effect=itertools.count(0, .01)), \
                patch.object(acceptance.time, 'sleep'), \
                patch.object(acceptance, 'tap') as tap, patch.object(acceptance, 'draw_paths') as draw:
            result = acceptance.watch_reply('11111111-1111-1111-1111-111111111111',
                       '22222222-2222-2222-2222-222222222222', 'passive', seconds=1)
            self.assertEqual(result['outcome'], 'observed_terminal')
            self.assertEqual(result['request'], 'new')
            self.assertIsNone(result['visual_pass'])
            self.assertEqual(result['samples'][0]['status']['respond_elapsed_ms'], 2700)
            tap.assert_not_called(); draw.assert_not_called()

    def test_passive_watch_timeout_does_not_count_old_written_reply_or_resend(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(acceptance, 'Path', return_value=Path(directory)), \
                patch.object(acceptance, 'notebook_status', return_value={'request': 'old', 'state': 'written'}), \
                patch.object(acceptance, 'capture') as capture, \
                patch.object(acceptance.time, 'monotonic', side_effect=itertools.count(0, .1)), \
                patch.object(acceptance.time, 'sleep'), \
                patch.object(acceptance, 'tap') as tap:
            result = acceptance.watch_reply('11111111-1111-1111-1111-111111111111',
                       '22222222-2222-2222-2222-222222222222', 'timeout', seconds=1)
            self.assertEqual(result['outcome'], 'observation_timeout')
            self.assertEqual(result['samples'], [])
            self.assertIsNone(result['request'])
            capture.assert_not_called(); tap.assert_not_called()

    def test_passive_watch_superseded_during_capture_does_not_mix_requests(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(acceptance, 'Path', return_value=Path(directory)), \
                patch.object(acceptance, 'notebook_status', side_effect=[
                    {'request': 'old', 'state': 'written'},
                    {'request': 'new', 'state': 'writing'},
                    {'request': 'different', 'state': 'waiting'}]), \
                patch.object(acceptance, 'capture', return_value=Image.new('L', (10, 10), 255)), \
                patch.object(acceptance.time, 'monotonic', side_effect=itertools.count(0, .01)), \
                patch.object(acceptance, 'tap') as tap:
            result = acceptance.watch_reply('11111111-1111-1111-1111-111111111111',
                       '22222222-2222-2222-2222-222222222222', 'superseded', seconds=1)
            self.assertEqual(result['outcome'], 'superseded')
            self.assertEqual(result['request'], 'new')
            self.assertIsNone(result['visual_pass'])
            tap.assert_not_called()

    def test_lower_left_replay_is_allowed_but_respond_overlap_is_not(self):
        def sample():
            image = Image.new('L', (300, 90), 255)
            ImageDraw.Draw(image).line((5, 5, 295, 85), fill=0, width=2)
            return image
        with patch.object(acceptance.Image, 'open', side_effect=lambda _: sample()), \
                patch.object(acceptance, 'require_blank_area') as blank, \
                patch.object(acceptance, 'draw_paths') as draw:
            acceptance.replay_handwriting('reviewed.png', 240, 1650)
            blank.assert_called_once()
            draw.assert_called_once()
        with patch.object(acceptance.Image, 'open', side_effect=lambda _: sample()), \
                patch.object(acceptance, 'draw_paths') as draw:
            with self.assertRaisesRegex(ValueError, 'native controls'):
                acceptance.replay_handwriting('reviewed.png', 600, 1650)
            draw.assert_not_called()

    def test_line_art_refuses_content_before_any_native_input(self):
        sample = Image.new('L', (160, 100), 255)
        ImageDraw.Draw(sample).line((10, 10, 145, 85), fill=0, width=3)
        with patch.object(acceptance.Image, 'open', return_value=sample), \
                patch.object(acceptance, 'require_blank_area', side_effect=ValueError('existing content')), \
                patch.object(acceptance, 'draw_paths') as draw:
            with self.assertRaisesRegex(ValueError, 'existing content'):
                acceptance.draw_line_art('line-art.png', 240, 1400)
            draw.assert_not_called()

    def test_line_art_refuses_controls_before_reading_source(self):
        with patch.object(acceptance.Image, 'open') as source:
            with self.assertRaises(ValueError):
                acceptance.draw_line_art('line-art.png', 240, 1600)
            source.assert_not_called()

    def test_gray_rules_are_not_existing_ink(self):
        image = Image.new('L', (1404, 1872), 255)
        ImageDraw.Draw(image).line((130, 1450, 1304, 1450), fill=180)
        with patch.object(acceptance, 'capture', return_value=image):
            acceptance.require_blank_area(225, 1440, 890, 1645)

    def test_dog_refuses_existing_text_before_any_stroke(self):
        image = Image.new('L', (1404, 1872), 255)
        ImageDraw.Draw(image).rectangle((250, 1510, 320, 1530), fill=0)
        with patch.object(acceptance, 'capture', return_value=image), \
                patch.object(acceptance, 'draw_paths') as draw, \
                patch.object(acceptance, 'write_note') as note:
            with self.assertRaisesRegex(ValueError, 'existing content'):
                acceptance.draw_test_dog(1440)
            draw.assert_not_called()
            note.assert_not_called()

    def test_note_refuses_existing_ink_before_any_stroke(self):
        image = Image.new('L', (1404, 1872), 255)
        ImageDraw.Draw(image).line((250, 1450, 330, 1450), fill=0, width=3)
        with patch.object(acceptance, 'capture', return_value=image), \
                patch.object(acceptance, 'draw_paths') as draw:
            with self.assertRaisesRegex(ValueError, 'existing content'):
                acceptance.write_note('Hi', 240, 1450)
            draw.assert_not_called()

    def test_replay_preserves_source_and_translates_geometry(self):
        sample = Image.new('L', (50, 30), 255)
        ImageDraw.Draw(sample).line((5, 5, 35, 20), fill=0, width=2)
        original = sample.tobytes()
        with patch.object(acceptance.Image, 'open', return_value=sample), \
                patch.object(acceptance, 'require_blank_area') as blank, \
                patch.object(acceptance, 'draw_paths') as draw:
            result = acceptance.replay_handwriting('reviewed.png', 240, 1450)
            self.assertEqual(original, sample.tobytes())
            self.assertEqual(result['kind'], 'replayed human handwriting')
            blank.assert_called_once()
            self.assertTrue(all(240 <= x < 280 and 1450 <= y < 1480
                                for path in draw.call_args.args[0] for x, y in path))

    def test_replay_refuses_existing_content(self):
        sample = Image.new('L', (50, 30), 255)
        ImageDraw.Draw(sample).line((5, 5, 35, 20), fill=0, width=2)
        with patch.object(acceptance.Image, 'open', return_value=sample), \
                patch.object(acceptance, 'require_blank_area', side_effect=ValueError('existing content')), \
                patch.object(acceptance, 'draw_paths') as draw:
            with self.assertRaisesRegex(ValueError, 'existing content'):
                acceptance.replay_handwriting('reviewed.png', 240, 1450)
            draw.assert_not_called()


if __name__ == '__main__':
    unittest.main()
