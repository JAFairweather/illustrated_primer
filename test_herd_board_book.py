import importlib.machinery
import importlib.util
import os
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.realpath(__file__))
loader = importlib.machinery.SourceFileLoader('herd_board_book', os.path.join(HERE, 'herd-board-book'))
book = importlib.util.module_from_spec(importlib.util.spec_from_loader('herd_board_book', loader))
loader.exec_module(book)


def box(top, bottom, tool=17):
    return (tool, [(-300, top, 3), (300, top, 3), (300, bottom, 3), (-300, bottom, 3), (-300, top, 3)], False)


class BookTests(unittest.TestCase):
    def test_pages_are_read_in_order_without_deleted_ones(self):
        self.assertEqual(book.order({'cPages': {'pages': [{'id': 'a'}, {'id': 'b', 'deleted': {'value': 1}},
                                                          {'id': 'c'}]}}), ['a', 'c'])
        self.assertEqual(book.order({'pages': ['x', 'y']}), ['x', 'y'])

    def test_a_tall_page_is_cut_at_a_blank_band_never_through_a_drawing(self):
        # Words near the top (one above the first screen), a drawing across the screen's edge, words far below.
        lines = [box(-20, 30), box(1500, 1600), box(1700, 2000), box(2600, 2650), box(3000, 3100, tool=6)]
        with patch.object(book, 'strokes', return_value=lines):
            sheets = book.sheets(b'page')
        self.assertEqual(len(sheets), 2)
        first, second = sheets
        self.assertEqual((first.width, first.height), (book.WIDTH, book.HEIGHT))
        self.assertLess(first.getpixel((402, 60)), 128)  # the top box, moved down onto the sheet
        self.assertLess(first.getpixel((402, 1600)), 128)
        self.assertEqual(min(first.crop((0, 1700, book.WIDTH, book.HEIGHT)).getdata()), 255)  # drawing not split
        self.assertLess(second.getextrema()[0], 128)  # the drawing whole on the next sheet

    def test_a_page_with_nothing_drawn_gives_no_sheets(self):
        with patch.object(book, 'strokes', return_value=[box(100, 200, tool=6)]):
            self.assertEqual(book.sheets(b'page'), [])


if __name__ == '__main__':
    unittest.main()
