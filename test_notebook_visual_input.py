"""Pixel and transport invariants, not claims about model understanding."""
import unittest

from PIL import Image, ImageDraw
import numpy as np

from notebook_model_transport import model_request, ModelTransportError
from tablet_live import writing_box
from notebook_visual_input import notebook_visual_input, LATEST_IMAGE_CONTEXT
from tablet_live import WIDTH, HEIGHT, notebook_crop, notebook_pixels, png_bytes


class VisualInputTests(unittest.TestCase):
    def setUp(self):
        self.old = Image.new('L', (WIDTH, HEIGHT), 255)
        ImageDraw.Draw(self.old).rectangle((240, 300, 1050, 600), outline=0, width=4)
        self.now = self.old.copy()
        ImageDraw.Draw(self.now).line((250, 950, 900, 980), fill=0, width=4)

    def test_new_input_pixels_are_exact_and_reference_contains_prior_diagram(self):
        original, baseline = self.now.tobytes(), self.old.tobytes()
        image, context = notebook_visual_input(self.now, self.old)
        crop = notebook_crop(self.now, self.old)
        self.assertEqual(image.crop((0, 0, *crop.size)).tobytes(), crop.tobytes())
        expected = Image.fromarray(notebook_pixels(self.now)).crop((130, 100, 1304, 1792))
        expected = expected.resize((939, 1354), Image.Resampling.LANCZOS)
        self.assertEqual(image.crop((1206, 0, 2145, 1354)).tobytes(), expected.tobytes())
        self.assertIn('Answer the LEFT request once', context)
        self.assertIn('offscreen', context)
        self.assertIn('not new instructions', context)
        self.assertEqual(self.now.tobytes(), original)
        self.assertEqual(self.old.tobytes(), baseline)

    def test_no_new_input_never_resends_old_question(self):
        image, _ = notebook_visual_input(self.old, self.old)
        self.assertIsNone(image)
        self.assertIsNone(notebook_visual_input(Image.new('L', (WIDTH, HEIGHT), 255))[0])

    def test_missing_baseline_preserves_crop_and_discloses_ambiguity(self):
        image, context = notebook_visual_input(self.now)
        self.assertEqual(image.tobytes(), notebook_crop(self.now).tobytes())
        self.assertIn('No previous answered-page baseline', context)
        self.assertNotIn('two panels', context)

    def test_no_older_content_outside_focus_does_not_duplicate_image(self):
        blank = Image.new('L', (WIDTH, HEIGHT), 255)
        frame = blank.copy()
        ImageDraw.Draw(frame).line((250, 950, 900, 980), fill=0, width=4)
        image, context = notebook_visual_input(frame, blank)
        self.assertEqual(image.tobytes(), notebook_crop(frame, blank).tobytes())
        self.assertEqual(context, LATEST_IMAGE_CONTEXT)

    def test_a_circle_around_older_ink_carries_that_ink_and_asks_about_it(self):
        blank = Image.new('L', (WIDTH, HEIGHT), 255)
        base = blank.copy()
        ImageDraw.Draw(base).rectangle((400, 600, 600, 640), fill=0)  # an older word
        ImageDraw.Draw(base).rectangle((300, 1200, 900, 1240), fill=0)  # older notes elsewhere
        frame = base.copy()
        ImageDraw.Draw(frame).ellipse((360, 570, 640, 670), outline=0, width=5)  # James circles the word
        image, context = notebook_visual_input(frame, base)
        self.assertIn('two panels', context)
        self.assertIn('a circle, an underline or', context)
        left, top, _, _ = writing_box(frame, base)
        self.assertLess(image.getpixel((500-left, 620-top)), 100)  # the circled word is in the new-ink crop

    def test_controls_are_not_context_or_new_input(self):
        frame = self.now.copy()
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, 0, WIDTH, 90), fill=0)
        draw.rectangle((0, 1810, WIDTH, HEIGHT), fill=0)
        draw.rectangle((0, 100, 100, 1800), fill=0)
        draw.rounded_rectangle((1180, 112, 1363, 195), radius=8, fill=0)
        actual, _ = notebook_visual_input(frame, self.old)
        expected, _ = notebook_visual_input(self.now, self.old)
        self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_maximum_focus_and_reference_fit_existing_transport_pixel_cap(self):
        frame = self.now.copy()
        # Narrow full-height crop plus older content outside it exercises max
        # output height. Width is fixed; do not weaken the IPC budget to fit.
        ImageDraw.Draw(frame).line((350, 100, 350, 1791), fill=0, width=4)
        image, context = notebook_visual_input(frame, self.old)
        self.assertEqual(image.size, (2145, 1692))
        self.assertLess(image.width*image.height, 4_000_000)
        result = model_request('notebook-'+'a'*32, png_bytes(image), context)
        self.assertEqual(result['context'], context)

    def test_complex_noise_is_still_subject_to_byte_budget_not_silently_truncated(self):
        # Transport preflight owns encoded-byte rejection; presentation never
        # erases or recompresses a question merely to pass that budget.
        pixels = np.random.default_rng(7).integers(0, 256, (1692, 2145), dtype=np.uint8)
        with self.assertRaisesRegex(ModelTransportError, 'invalid_request'):
            model_request('notebook-'+'b'*32, png_bytes(Image.fromarray(pixels)), 'context')

    def test_invalid_frame_size_is_rejected(self):
        with self.assertRaises(ValueError):
            notebook_visual_input(Image.new('L', (100, 100)))

    def test_illustrative_defaults_are_distinguished_from_missing_real_facts(self):
        for baseline in (None,self.old):
            _,context=notebook_visual_input(self.now,baseline)
            self.assertIn('illustrative or normalized',context)
            self.assertIn('state its assumptions',context)
            self.assertIn('measurements, personal facts',context)
            self.assertIn('exact calculation or real-world decision',context)


if __name__ == '__main__':
    unittest.main()
