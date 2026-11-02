import unittest

from notebook_handwriting import HANDS,handwriting_paths
from notebook_plotter_font import GLYPHS as PLOTTER


class HandwritingTest(unittest.TestCase):
    def test_both_hands_write_every_plotter_glyph(self):
        for hand in HANDS:
            for char in PLOTTER:
                paths,advance=handwriting_paths(char,24,hand=hand)
                self.assertTrue(paths and all(len(p)>=2 for p in paths),(hand,char))
                self.assertGreater(advance,0)

    def test_same_text_draws_the_same_way_and_other_text_differently(self):
        self.assertEqual(handwriting_paths('Hello there',28),handwriting_paths('Hello there',28))
        self.assertNotEqual(handwriting_paths('hello',28)[0][0],handwriting_paths('hello',28,seed=1)[0][0])

    def test_primer_joins_a_word_into_one_stroke_and_reader_does_not(self):
        self.assertEqual(len(handwriting_paths('minimum',28)[0]),1+2)  # the word, then its two i dots
        self.assertEqual(len(handwriting_paths('once more',28)[0]),2)
        self.assertGreater(len(handwriting_paths('minimum',28,hand='reader')[0]),7)

    def test_letter_prints_upright_ball_and_stick_letters_mostly_in_one_stroke(self):
        for char in 'abdeghmnpqru':
            self.assertEqual(len(handwriting_paths(char,28,hand='letter')[0]),1,char)
        self.assertEqual(len(handwriting_paths('once',28,hand='letter')[0]),4)  # print: a stroke a letter
        stem=handwriting_paths('l',28,hand='letter')[0][0]
        self.assertLess(abs(stem[0][0]-stem[-1][0]),3,'upright, not slanted')
        slanted=handwriting_paths('l',28)[0][0]
        self.assertGreater(max(x for x,_ in slanted)-min(x for x,_ in slanted),5)

    def test_ink_stays_in_the_line_box(self):
        for hand in HANDS:
            paths,advance=handwriting_paths('Quickly jog, fix 7 × 8 = 56?',30,hand=hand)
            xs=[x for p in paths for x,_ in p]; ys=[y for p in paths for _,y in p]
            self.assertGreaterEqual(min(xs),-3)
            self.assertLessEqual(max(xs),advance+30)
            self.assertGreaterEqual(min(ys),-6)
            self.assertLessEqual(max(ys),30*1.6)

    def test_a_word_starts_without_a_lead_in(self):
        start=handwriting_paths('a',30)[0][0][0]
        self.assertLess(start[1],30*.62)  # the pen touches down at the bowl's top, not on the baseline

    def test_a_label_costs_no_more_pen_time_than_the_plotter_font_allows(self):
        for hand in HANDS:
            paths,_=handwriting_paths('one example: a² + b² = c²',28,hand=hand)
            self.assertLess(sum(len(p) for p in paths)*.009+len(paths)*.07,6)

    def test_bounds(self):
        for bad in ('',  'x'*401):
            with self.assertRaises(ValueError):
                handwriting_paths(bad)
        with self.assertRaises(ValueError):
            handwriting_paths('hi',4)
        with self.assertRaises(ValueError):
            handwriting_paths('hi',hand='copperplate')
        with self.assertRaises(ValueError):
            handwriting_paths('€')


if __name__=='__main__':
    unittest.main()
