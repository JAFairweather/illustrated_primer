"""A handwritten note as a small picture to text: James's own new ink from the page, or words in the reader's hand.

No device writes and no sending: this only makes the PNG that a confirmed iMessage or SMS carries.
"""
import io

import numpy as np
from PIL import Image, ImageDraw

from notebook_handwriting import handwriting_paths
from tablet_live import notebook_pixels

LINE_GAP = 5  # blank rows that separate two handwritten lines (ruled lines are 52 rows apart; a gap ran 11 on 10-31)
DOT = 20  # a band shorter than this is an i's dot or an accent: it belongs to the line below it
MARGIN = 28
SIZE, LEADING, WIDTH = 44, 96, 1000  # the reader's hand: cap height, line spacing, line width in pixels


def _png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def ink_lines(mask):
    """(top, bottom) row bands of the handwritten lines in a boolean ink mask, top to bottom."""
    rows = np.flatnonzero(mask.any(axis=1))
    if not len(rows):
        return []
    bands, top = [], rows[0]
    for before, after in zip(rows, rows[1:]):
        if after-before > LINE_GAP and before+1-top >= DOT:
            bands.append((int(top), int(before)+1))
            top = after
    return bands+[(int(top), int(rows[-1])+1)]


def note_png(frame, baseline, keep='above'):
    """PNG of the ink written since baseline, minus the instruction line: keep 'above' drops the last line (the note
    came first), 'below' drops the first, 'all' drops none. None when nothing of the note is left."""
    pixels = notebook_pixels(frame)
    new = pixels < 110
    if baseline is not None:
        new &= notebook_pixels(baseline) > 160
    bands = ink_lines(new)
    bands = {'above': bands[:-1], 'below': bands[1:], 'all': bands}[keep]
    if not bands:
        return None
    rows = np.zeros(new.shape[0], bool)
    for top, bottom in bands:
        rows[top:bottom] = True
    new &= rows[:, None]
    # The pen's grey edges lie just outside the dark core: keep the frame's own pixels two rows and columns around it.
    near = new.copy()
    for dy in (-2, -1, 1, 2):
        near |= np.roll(new, dy, axis=0)
    for dx in (-2, -1, 1, 2):
        near |= np.roll(near, dx, axis=1)
    ys, xs = np.nonzero(new)
    top, bottom = max(0, ys.min()-MARGIN), min(new.shape[0], ys.max()+MARGIN+1)
    left, right = max(0, xs.min()-MARGIN), min(new.shape[1], xs.max()+MARGIN+1)
    out = np.where(near, pixels, 255).astype(np.uint8)[top:bottom, left:right]
    return _png(Image.fromarray(out, 'L'))


def written_png(text):
    """PNG of text written out in the reader's hand, wrapped to a phone-friendly width."""
    lines, line = [], ''
    for word in text.split():
        trial = f'{line} {word}'.strip()
        if line and handwriting_paths(trial, SIZE, hand='reader')[1] > WIDTH:
            lines.append(line)
            line = word
        else:
            line = trial
    lines += [line] if line else []
    if not lines:
        raise ValueError('nothing to write')
    width = max(handwriting_paths(l, SIZE, hand='reader')[1] for l in lines)
    image = Image.new('L', (int(width)+2*MARGIN, LEADING*(len(lines)-1)+SIZE*2+2*MARGIN), 255)
    draw = ImageDraw.Draw(image)
    for n, l in enumerate(lines):
        for path in handwriting_paths(l, SIZE, hand='reader')[0]:
            points = [(x+MARGIN, y+MARGIN+n*LEADING) for x, y in path]
            draw.line(points if len(points) > 1 else points*2, fill=0, width=4, joint='curve')
    return _png(image)
