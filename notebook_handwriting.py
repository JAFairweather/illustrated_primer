"""Handwriting for notebook ink: a procedural single-line pen font with three hands.

  primer  the agent's own hand: a slanted, joined script with looped ascenders and flourished capitals.
  reader  a plain, very legible casual print, standing in for the person's writing (test input).
  letter  the agent's lettering for young readers: upright ball-and-stick print, as in a picture book.

Each glyph is a skeleton of control points on a cap height of 10 units (y down: ascenders at 0, baseline 10,
descenders to about 14.6). `;` separates strokes; a point ending in `!` is a sharp corner, every other point is
passed through by a smooth curve (centripetal Catmull-Rom). In a joining hand the first stroke of a letter is its
body: it starts with a lead-in from the baseline and ends with an exit, and consecutive joining letters are written
as one stroke. Later strokes (dots, crossbars) are drawn after the body.

Each time a text is written it gets a slight, seeded variation (size, baseline, tilt, wobble), so the writing looks
hand-made and the same text in the same hand always draws the same way, which keeps replays and scene hashes stable.
Characters a hand lacks come from the reader's hand, then from the plotter alphabet.
"""
import hashlib
import math
import random
import string

CAP = 10.0


def _dot(x, y, r=.45):
    return f'{x:g},{y-r:g} {x-r:g},{y:g} {x:g},{y+r:g} {x+r:g},{y:g} {x:g},{y-r*1.1:g}'


READER = {
    # Capitals: casual print.
    'A': ('0,10 3,0! 6,10;1.2,6.6 4.8,6.6', 6),
    'B': ('0,10 0,0! 3,0 4.5,0.9 4.7,2.5 3.7,4.4 0.2,4.8;0.2,4.8 3.8,5 5,6.5 4.9,8.6 3.4,10 0,10', 5.2),
    'C': ('6,1.6 4.6,0.2 3,0 1.2,1 0.1,3.5 0.1,6.5 1.2,9 3,10 4.6,9.8 6,8.4', 6.2),
    'D': ('0,0 0,10;0,0 2.6,0 4.8,1.4 5.8,4 5.8,6 4.8,8.6 2.6,10 0,10', 6),
    'E': ('5,0 0,0! 0,10! 5,10;0,5 4,5', 5),
    'F': ('5,0 0,0! 0,10;0,5 4,5', 5),
    'G': ('6,1.8 4.6,0.2 3,0 1.2,1 0.1,3.5 0.1,6.5 1.2,9 3,10 4.8,9.6 6,8 6,5.6! 3.6,5.6', 6.3),
    'H': ('0,0 0,10;5.4,0 5.4,10;0,5 5.4,5', 5.4),
    'I': ('1.5,0 1.5,10;0,0 3,0;0,10 3,10', 3),
    'J': ('1.5,0 5,0;3.6,0 3.6,7.5 2.8,9.5 1.6,10 0.4,9.3 0,8', 5),
    'K': ('0,0 0,10;5,0 0.2,6;1.8,4.6 5.2,10', 5.2),
    'L': ('0,0 0,10! 4.6,10', 4.8),
    'M': ('0,10 0.4,0! 3.4,6.5! 6.4,0! 6.8,10', 6.8),
    'N': ('0,10 0,0! 5.4,10! 5.4,0', 5.4),
    'O': ('3,0 1.1,1 0,3.6 0,6.4 1.1,9 3,10 4.9,9 6,6.4 6,3.6 4.9,1 2.7,0.1', 6),
    'P': ('0,10 0,0! 3.2,0 4.8,1.1 5,2.8 4.4,4.4 3,5.2 0,5.2', 5),
    'Q': ('3,0 1.1,1 0,3.6 0,6.4 1.1,9 3,10 4.9,9 6,6.4 6,3.6 4.9,1 2.7,0.1;3.6,7.4 6.2,10.4', 6.2),
    'R': ('0,10 0,0! 3.2,0 4.8,1.1 5,2.8 4.4,4.4 3,5.2 0,5.2;2.4,5.2 5.2,10', 5.2),
    'S': ('5,1.4 3.8,0.1 2.4,0 0.8,0.6 0.3,2.2 1.2,3.9 3.8,5.3 5,7 4.8,8.9 3.2,10 1.6,10 0,8.8', 5.2),
    'T': ('0,0 6,0;3,0 3,10', 6),
    'U': ('0,0 0,6.8 0.8,9.2 2.8,10 4.6,9.2 5.4,6.8 5.4,0', 5.4),
    'V': ('0,0 3,10! 6,0', 6),
    'W': ('0,0 1.8,10! 4,2.8! 6.2,10! 8,0', 8),
    'X': ('0,0 5.4,10;5.4,0 0,10', 5.4),
    'Y': ('0,0 2.8,5! 5.6,0;2.8,5 2.8,10', 5.6),
    'Z': ('0,0 5.4,0! 0,10! 5.6,10', 5.6),
    # Lower case.
    'a': ('4.4,5.4 3.4,4.2 2,4 0.7,4.8 0,6.8 0.4,9.2 1.8,10 3.2,9.6 4.4,8;4.4,4 4.4,10', 4.6),
    'b': ('0,0 0,10;0,6.6 1,4.6 2.4,4 3.8,4.6 4.6,6.8 4.2,9.2 2.6,10 1.2,9.6 0,8.2', 4.6),
    'c': ('4.2,5 3,4.1 1.6,4.1 0.4,5.4 0,7.2 0.6,9.2 2,10 3.4,9.8 4.4,9', 4.4),
    'd': ('4.6,0 4.6,10;4.6,6.6 3.6,4.6 2.2,4 0.8,4.6 0,6.8 0.4,9.2 2,10 3.4,9.6 4.6,8.2', 4.6),
    'e': ('0.2,7.2 4.4,7.2! 4.2,5.4 3,4.1 1.6,4.1 0.4,5.4 0,7.2 0.6,9.2 2,10 3.4,9.8 4.4,9', 4.4),
    'f': ('3.8,0.6 2.8,0 1.8,0.4 1.4,1.8 1.4,10;0,4.2 3.4,4.2', 3.6),
    'g': ('4.4,5.4 3.4,4.2 2,4 0.7,4.8 0,6.6 0.4,8.6 1.8,9.4 3.2,9 4.4,7.6;4.4,4 4.4,12 3.6,13.4 2,13.6 0.6,12.8', 4.6),
    'h': ('0,0 0,10;0,6.4 1,4.6 2.4,4 3.8,4.6 4.4,6.4 4.4,10', 4.4),
    'i': (f'0.4,4 0.4,10;{_dot(.4, 2)}', 0.8),
    'j': (f'1.6,4 1.6,12.2 1,13.4 0,13.6;{_dot(1.6, 2)}', 2),
    'k': ('0,0 0,10;3.8,4 0.2,7.6;1.4,6.6 4,10', 4),
    'l': ('0.6,0 0.6,9 1,10 1.6,10', 1.6),
    'm': ('0,4 0,10;0,6 0.8,4.4 1.8,4 2.8,4.6 3.2,6 3.2,10;3.2,6 4,4.4 5,4 6,4.6 6.4,6 6.4,10', 6.4),
    'n': ('0,4 0,10;0,6.2 1,4.5 2.2,4 3.6,4.6 4.2,6.2 4.2,10', 4.2),
    'o': ('2.2,4 0.7,4.7 0,7 0.7,9.3 2.2,10 3.7,9.3 4.4,7 3.7,4.7 2,4.05', 4.4),
    'p': ('0,4 0,13.6;0,6.6 1,4.6 2.4,4 3.8,4.6 4.6,6.8 4.2,9.2 2.6,10 1.2,9.6 0,8.2', 4.6),
    'q': ('4.6,4 4.6,13.6 5.4,13;4.6,6.6 3.6,4.6 2.2,4 0.8,4.6 0,6.8 0.4,9.2 2,10 3.4,9.6 4.6,8.2', 5),
    'r': ('0,4 0,10;0,6.6 0.8,4.8 2,4 3.4,4.2', 3.4),
    's': ('3.8,4.8 2.8,4 1.4,4 0.4,4.8 0.6,6.2 2,7 3.4,7.6 3.9,8.8 3.2,9.8 1.8,10.1 0.4,9.6 0,9', 4),
    't': ('1.4,1.2 1.4,9 2,10 3,10 3.6,9.6;0,4.2 3.2,4.2', 3.6),
    'u': ('0,4 0,8.2 0.8,9.6 2,10 3.2,9.6 4.2,8;4.2,4 4.2,10', 4.2),
    'v': ('0,4 2.2,10! 4.4,4', 4.4),
    'w': ('0,4 1.5,10! 3,5.6! 4.5,10! 6,4', 6),
    'x': ('0,4 4.2,10;4.2,4 0,10', 4.2),
    'y': ('0,4 2.2,9.6;4.4,4 2,11.6 1.2,13 0,13.6', 4.4),
    'z': ('0,4 4.2,4! 0,10! 4.4,10', 4.4),
    # Figures.
    '0': ('2.6,0 0.8,1.2 0,4 0,6 0.8,8.8 2.6,10 4.4,8.8 5.2,6 5.2,4 4.4,1.2 2.3,0.1', 5.2),
    '1': ('1.5,1.4 2.6,0! 2.6,10', 3.2),
    '2': ('0.2,2.2 1.2,0.5 2.8,0 4.2,0.6 4.8,2.2 4.4,4 0,10! 5,10', 5),
    '3': ('0.4,1 1.8,0 3.4,0 4.6,1 4.6,2.8 3.4,4.4 1.8,4.8! 3.6,5.2 4.9,6.6 4.9,8.4 3.8,9.7 2.2,10 0.8,9.6 0,8.6', 5),
    '4': ('3.8,10 3.8,0! 0,6.8! 5.2,6.8', 5.2),
    '5': ('4.6,0 0.8,0! 0.4,4.4! 1.8,3.8 3.4,3.9 4.6,5 5,7 4.4,9.2 2.6,10 1,9.7 0,8.8', 5),
    '6': ('4.4,0.6 3,0 1.6,0.6 0.4,2.8 0,5.6 0.4,8.4 1.6,9.7 2.8,10 4.2,9.4 5,7.8 4.8,6 3.6,5 2.2,5 0.8,5.8 0.1,7', 5),
    '7': ('0,0 5,0! 1.6,10', 5),
    '8': ('2.5,4.8 0.8,3.8 0.4,2.2 1,0.6 2.5,0 4,0.6 4.6,2.2 4.2,3.8 2.5,4.8 0.6,6 0,7.8 0.8,9.5 2.5,10 4.2,9.5 '
          '5,7.8 4.4,6 2.5,4.8', 5),
    '9': ('4.8,3.2 4,4.6 2.6,5.2 1.2,4.8 0.2,3.4 0.4,1.4 1.6,0.2 2.8,0 4.2,0.6 4.9,2.6 4.8,5.6 4.2,8.4 3,9.7 '
          '1.6,10 0.4,9.4', 5),
    # Punctuation and the common operators.
    '.': (_dot(.5, 9.5), 1),
    ',': ('0.7,9.2 0.9,9.8 0.7,10.6 0.1,11.6', 1.1),
    '?': (f'0.2,2 1.2,0.4 2.6,0 4,0.6 4.4,2 3.8,3.4 2.2,4.6 2.2,7;{_dot(2.2, 9.5)}', 4.4),
    '!': (f'0.7,0 0.7,7;{_dot(.7, 9.5)}', 1.4),
    ':': (f'{_dot(.5, 4.8)};{_dot(.5, 9.5)}', 1),
    ';': (f'{_dot(.6, 4.8)};0.7,9.2 0.9,9.8 0.7,10.6 0.1,11.6', 1.1),
    '-': ('0,6.4 3,6.4', 3),
    '−': ('0,6.4 4.4,6.4', 4.4),
    '+': ('2.4,3.8 2.4,8.6;0,6.2 4.8,6.2', 4.8),
    '=': ('0,4.8 4.4,4.8;0,7.6 4.4,7.6', 4.4),
    '×': ('0.4,4.2 4.2,8.4;4.2,4.2 0.4,8.4', 4.6),
    '/': ('3.6,0 0,10.6', 3.6),
    '(': ('2,0 0.6,2.4 0,5 0.6,7.6 2,10.4', 2),
    ')': ('0,0 1.4,2.4 2,5 1.4,7.6 0,10.4', 2),
    "'": ('0.4,0 0.3,2.4', 0.8),
    '"': ('0.4,0 0.3,2.4;1.6,0 1.5,2.4', 2),
}

# The Primer's script. Lower case: x-height from 5.6 to the baseline; every letter starts at (0,10) with a lead-in
# upstroke and ends with an exit near the baseline (o, v, w leave from the top, as a bridge).
ASCENDER_LOOP = '0,10 1.4,6.6 2.4,3 2.4,0.8 1.8,0.1 1.2,1 1.0,4'
BOWL = '3.4,5.6! 2.2,5.5 1,6.4 0.7,8.4 1.4,9.9 2.6,9.6 3.6,7.6'
PRIMER = {
    'a': (f'0,10 1.6,7.2 {BOWL} 3.6,5.6! 3.5,9.2 4.1,10 5,9.6', 5),
    'b': (f'{ASCENDER_LOOP} 1.0,8.8 1.6,9.9 2.8,9.8 3.8,8.4 4,6.6 3.6,5.6 3.2,6.2 4.2,6.2 5.2,5.6', 5.2),
    'c': ('0,10 1.6,7.2 3.2,5.8 3.9,6! 3,5.6 1.8,5.9 0.9,7 0.8,8.6 1.6,9.9 3,9.9 4.4,9.2', 4.4),
    'd': (f'0,10 1.6,7.2 {BOWL} 4.2,0! 3.8,9.2 4.4,10 5.2,9.5', 5.2),
    'e': ('0,10 1.4,8.6 3,7.4 3.6,6.4 3.2,5.6 2.2,5.7 1.2,6.8 0.9,8.6 1.6,9.9 3,9.9 4.2,9.2', 4.2),
    'f': (f'{ASCENDER_LOOP} 1.0,10 1.0,13 0.6,14.4 0.2,13.6 0.8,11.4 2,10.2 3.2,9.4', 3.4),
    'g': (f'0,10 1.6,7.2 {BOWL} 3.6,5.6! 3.6,12.4 3,14.4 2,14.6 1.4,13.8 2.2,12 3.8,10.2 4.8,9.4', 4.8),
    'h': (f'{ASCENDER_LOOP} 1.0,10! 1.4,7.4 2.4,5.8 3.2,5.6 3.8,6.4 3.8,9.2 4.4,10 5.2,9.5', 5.2),
    'i': (f'0,10 1.4,7.4 2,5.6! 1.8,9.2 2.4,10 3.2,9.5;{_dot(2.1, 3.9, .4)}', 3.2),
    'j': (f'0,10 1.4,7.4 2,5.6! 2,12.6 1.6,14.4 0.8,14.6 0.4,13.8 1.2,12 2.6,10.4 3.6,9.5;{_dot(2.1, 3.9, .4)}', 3.6),
    'k': (f'{ASCENDER_LOOP} 1.0,10! 1.6,7.4 2.8,5.6 3.8,5.8 3.6,7 2.2,7.8 1.6,7.8! 2.8,8.2 3.4,9.4 4.2,10 5,9.5', 5),
    'l': (f'{ASCENDER_LOOP} 1.0,8.8 1.6,9.9 2.6,9.8 3.4,9.2', 3.4),
    'm': ('0,10 0.6,8 1.2,5.6! 1,10! 1.6,7.2 2.4,5.8 3.1,5.6 3.6,6.4 3.6,10! 4.2,7.2 5,5.8 5.7,5.6 6.2,6.4 '
          '6.2,9.2 6.8,10 7.6,9.5', 7.6),
    'n': ('0,10 0.6,8 1.2,5.6! 1,10! 1.6,7.2 2.4,5.8 3.1,5.6 3.6,6.4 3.6,9.2 4.2,10 5,9.5', 5),
    'o': ('0,10 1.6,7.2 3,5.6 1.8,5.7 0.9,6.8 0.8,8.8 1.6,9.9 2.8,9.8 3.6,8.4 3.6,6.6 3,5.6 3.4,6.2 4.4,6 5,5.6', 5),
    'p': ('0,10 1,7.6 1.6,5.6! 1.2,14.6! 1.3,10 1.6,7.4 2.6,5.8 3.6,5.7 4.1,7 3.8,8.8 2.8,9.8 1.6,9.6 2.8,9.8 '
          '4.2,9.4 5,9', 5),
    'q': (f'0,10 1.6,7.2 {BOWL} 3.6,5.6! 3.4,14.6! 3.8,11.8 4.4,10.4 5,9.6', 5),
    'r': ('0,10 1,7.6 1.6,5.4 2.4,5.8 2.6,6.4! 3.2,6.2 3.6,6.6 3.6,9.2 4.2,10 5,9.5', 5),
    's': ('0,10 1.4,7.6 2.4,5.4 3.2,7.4 3.4,8.8 2.6,9.9 1.4,9.8 1.0,9.2 1.8,9.6 3,9.8 4,9.4', 4),
    't': ('0,10 1.4,6.6 2.4,3.2! 1.8,9 2.4,10 3.2,9.5;0.6,5.4 3.6,5.2', 3.4),
    'u': ('0,10 0.6,8 1.2,5.6! 0.9,8.6 1.6,9.9 2.6,9.6 3.6,7.6 3.6,5.6! 3.6,9.2 4.2,10 5,9.5', 5),
    'v': ('0,10 0.8,7.4 1.6,5.6 1.8,6.6 2,9.8! 3,8.4 3.8,6.2 3.6,5.6 3.4,6.2 4.2,6 4.8,5.6', 4.8),
    'w': ('0,10 0.6,8 1.2,5.6! 0.9,8.6 1.6,9.9 2.6,9.6 3.4,7.6 3.4,6! 3.6,9 4.4,9.9 5.4,9.2 5.8,7.2 5.6,5.6 '
          '5.4,6.2 6.2,6 6.8,5.6', 6.8),
    'x': ('0,10 1.4,7.4 2.4,5.6 3.2,6 3.6,8 3.8,9.6 4.4,10 5,9.5;4.6,5.6 1.6,10', 5),
    'y': ('0,10 0.6,8 1.2,5.6! 0.9,8.6 1.6,9.9 2.6,9.6 3.6,7.6 3.6,5.6! 3.6,12.4 3,14.4 2,14.6 1.4,13.8 2.2,12 '
          '3.8,10.2 4.8,9.4', 4.8),
    'z': ('0,10 1.2,7.6 2,5.8 3.6,5.6 4,6.2 2.4,8! 3.6,8.4 4,10 3.6,12.6 2.8,14.4 2,14.4 2.2,13 3.6,11 4.8,9.6', 4.8),
    # Capitals with swashes; they stand apart from the letter after them.
    'A': ('0.6,9.2 1.6,9.9 2.6,9.2 4,5.6 5.6,0! 5.8,7 6,9.4 6.8,10 7.6,9.3;2.6,6 4.4,5.4 6.6,5.6', 7.6),
    'B': ('1.6,1.4 2.6,0.4 3.8,0.4 3.6,5 3,9.6 1.8,10 0.6,9.4 1,8.6;3.8,0.6 5.4,0 6.6,0.6 6.8,2.2 5.8,3.8 3.6,4.8! '
          '6,5.2 7,6.8 6.4,8.8 4.8,9.9 3,9.8', 7),
    'C': ('5.4,1.8 6.2,2 6.4,1 5.2,0 3.2,0.4 1.4,2 0.4,4.6 0.4,7.4 1.6,9.4 3.4,10 5.4,9.6 6.8,8.4', 6.8),
    'D': ('3.4,0.6 3,5 2.4,9.4 1.4,10 0.4,9.4 0.8,8.6 2,9.2 3.4,9.9 5,9.6 6.6,8 7.2,5.4 6.8,2.6 5.4,0.8 3.6,0 '
          '1.8,0.4 1,1.4 1.6,2.2', 7.2),
    'E': ('6,1.2 5.4,0.2 4,0 2.6,0.6 2.4,2.2 3.6,4.2 4.6,4.6! 2.6,5 1.2,6.4 1.2,8.6 2.6,9.9 4.4,10 6,9.4 6.6,8.4', 6.6),
    'F': ('1,1.2 2.4,0.2 4.6,0.6 6.4,0.2 7.4,0;4.4,0.6 4,5 3.4,9.2 2.4,10 1.2,9.8 0.6,9 1.2,8.4;2.6,5 5.4,4.8', 7.4),
    'G': ('5.8,1.8 6.4,1.4 5.4,0 3.4,0.2 1.4,1.8 0.4,4.6 0.6,7.6 2,9.6 3.8,10 5.4,9.2 6.2,7.4 6.2,5! 6,9.8 5.2,13 '
          '4,14.4 3,14.2 3.2,12.6 5,10.6 7,9.4', 7),
    'H': ('0.6,1.6 1.6,0.2 2.8,0.6 2.4,5 1.8,9.6 1,10 0.4,9.4;6.4,0 5.8,5 5.4,9.4 6,10 6.8,9.4;1.6,5.4 4,4.8 6.6,5',
          7),
    'I': ('0.8,1.4 2,0.2 4,0.2 5.6,0 6.4,0.4;4.4,0.2 3.8,5 3.2,9.2 2.2,10 0.8,9.6 0.6,8.8 1.4,8.6', 6.4),
    'J': ('0.8,1.4 2,0.2 4,0.2 5.6,0 6.4,0.4;4.6,0.2 4.2,6 3.6,11 2.6,13.6 1.4,14.2 0.6,13.4 1.2,11.8 2.8,10.4', 6.4),
    'K': ('0.6,1.6 1.6,0.2 2.8,0.6 2.4,5 1.8,9.6 1,10 0.4,9.4;6.8,0.4 6,0.2 4.6,1.6 2.4,4.8! 3.8,5.2 4.4,7.4 4.8,9.4 '
          '5.6,10 6.6,9.4', 7),
    'L': ('2.6,4 2.2,2 3,0.2 4.4,0 5,0.8 4.2,3 2.8,6 1.6,8.6 0.6,9.6 0.4,9 1.6,8.6 3.4,9.4 5,10 6.4,9.6 7,8.8', 7),
    'M': ('0.2,9.4 1,10 1.6,9.2 2.4,5 3,0.4! 3.6,6 4.2,9.6! 5.8,4 7.2,0.2! 6.8,5 6.6,9.2 7.2,10 8,9.4', 8),
    'N': ('0.2,9.4 1,10 1.6,9.2 2.4,5 3,0.2! 5.4,9.8! 6.2,5 6.8,1.2 7.6,0 8.2,0.6', 8.2),
    'O': ('4,0.2 2.2,0.6 0.8,2.6 0.4,5.4 1,8.4 2.8,9.9 4.6,9.8 6.2,8.4 6.8,5.6 6.4,2.6 5,0.6 3.4,0.2 2.4,1.2 2.8,2',
          6.8),
    'P': ('3.4,0.6 3,5 2.4,9.4 1.4,10 0.4,9.4 0.8,8.6;1.2,2 2.6,0.4 4.6,0 6.4,0.6 6.8,2.4 5.8,4.4 3.8,5.2 2.8,5', 6.8),
    'Q': ('4,0.2 2.2,0.6 0.8,2.6 0.4,5.4 1,8.4 2.8,9.9 4.6,9.8 6.2,8.4 6.8,5.6 6.4,2.6 5,0.6 3.4,0.2 2.4,1.2 2.8,2;'
          '3.6,7.8 5,9.6 6.6,10.6 8,10.4', 8),
    'R': ('3.4,0.6 3,5 2.4,9.4 1.4,10 0.4,9.4 0.8,8.6;1.2,2 2.6,0.4 4.6,0 6.4,0.6 6.8,2.4 5.8,4.4 3.8,5.2 2.8,5! '
          '4.4,5.8 5,8 5.4,9.6 6.2,10 7,9.4', 7),
    'S': ('1.2,8.4 0.6,9.4 1.6,10 3.4,9.8 5,8.6 5.2,6.6 3.6,5 2.2,3.6 2.2,1.6 3.6,0.2 5.4,0 6.4,0.8 6,1.8', 6.4),
    'T': ('0.6,1.8 1.4,0.4 3.2,0.4 5.4,0 7.4,0.2;4.6,0.2 4.2,5 3.6,9.2 2.6,10 1.2,9.8 0.6,9 1.2,8.4', 7.4),
    'U': ('0.6,1.6 1.6,0.2 2.6,0.8 2.2,4 1.6,7.6 2,9.6 3.4,10 5,9.2 6,6.4 6.6,0.2! 6,6 5.8,9.2 6.4,10 7.2,9.4', 7.2),
    'V': ('0.6,1.6 1.6,0.2 2.6,0.8 3,5 3.4,9.8! 5.6,5 6.6,2 7.4,0.4 8,0.4', 8),
    'W': ('0.6,1.6 1.6,0.2 2.4,0.8 2.4,5 2.6,9.8! 4.6,4 5,9.8! 7,4 7.8,1.2 8.6,0.2 9.2,0.6', 9.2),
    'X': ('0.6,1.4 1.6,0.2 2.8,0.6 4,4 5.2,8.6 6.2,10 7.2,9.4;7,0.6 5,3 2.2,7.4 0.6,9.6 0.2,9', 7.2),
    'Y': ('0.6,1.6 1.6,0.2 2.6,0.8 2.2,4 2,6 2.8,7.2 4.4,6.4 5.6,3 6.4,0! 5.6,6 5,11 4,13.8 2.8,14.4 2.4,13.4 '
          '3.6,11.6 5.6,10', 6.4),
    'Z': ('0.8,1.6 1.8,0.4 4,0.6 6.6,0! 0.4,10! 2,9.2 3.8,10 5.6,9.6 6.6,8.8', 6.6),
}

# The Primer's lettering for young readers: upright ball-and-stick print with closed round bowls, as in a picture book.
# Each letter is written the way a child is taught to print it, mostly without lifting the pen: the circle, then up and
# down the stem (a, d, g, q), or down the stem and back up into the bowl or arch (b, h, m, n, p, r). Letters it does not
# restate come from the reader's print.
BALL = '4.4,5.6 3.6,4.5 2.2,4 0.8,4.6 0,7 0.8,9.4 2.2,10 3.6,9.5 4.4,8.2!'
BOWL_RIGHT = '0,7.4 0.6,5 2.6,4 4.1,4.7 4.8,7 4.1,9.3 2.6,10 1,9.6 0,8.4'
LETTER = {
    'a': (f'{BALL} 4.4,4! 4.4,10', 4.4),
    'b': (f'0,0 0,10! {BOWL_RIGHT}', 4.8),
    'd': (f'{BALL} 4.4,0! 4.4,10', 4.4),
    'e': ('0.1,7 4.4,7! 4,5.1 2.2,4 0.7,4.7 0,7 0.7,9.3 2.2,10 3.6,9.7 4.3,8.9', 4.4),
    'g': (f'{BALL} 4.4,4! 4.4,12.2 3.8,13.4 2.2,13.8 0.6,13.2', 4.4),
    'h': ('0,0 0,10! 0,6.6 1,4.6 2.4,4 3.8,4.6 4.4,6.4 4.4,10', 4.4),
    'k': ('0,0 0,10;3.8,4 0.4,7.4! 4,10', 4),
    'm': ('0,4 0,10! 0,6 0.8,4.4 1.8,4 2.8,4.6 3.2,6 3.2,10! 3.2,6 4,4.4 5,4 6,4.6 6.4,6 6.4,10', 6.4),
    'n': ('0,4 0,10! 0,6.2 1,4.5 2.2,4 3.6,4.6 4.2,6.2 4.2,10', 4.2),
    'p': (f'0,4 0,13.8! {BOWL_RIGHT}', 4.8),
    'q': (f'{BALL} 4.4,4! 4.4,13.8', 4.4),
    'r': ('0,4 0,10! 0,6.6 0.8,4.8 2,4 3.4,4.2', 3.4),
    'u': ('0,4 0,8.2 0.8,9.6 2,10 3.2,9.6 4.2,8.2! 4.2,4! 4.2,10', 4.2),
    'y': ('0,4 2.2,9.6;4.4,4 1.6,13.8', 4.4),
}

HANDS = {
    'primer': dict(glyphs=PRIMER, joins=frozenset(string.ascii_lowercase), slant=.32, gap=.9, space=3.4, jitter=.05, wide=1.25),
    'reader': dict(glyphs=READER, joins=frozenset(), slant=.10, gap=1.5, space=5.5, jitter=.12, wide=1),
    'letter': dict(glyphs=LETTER, joins=frozenset(), slant=0, gap=1.6, space=5, jitter=.07, wide=1),
}
SUPERSCRIPTS = dict(zip('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789'))
SUBSCRIPTS = dict(zip('₀₁₂₃₄₅₆₇₈₉', '0123456789'))


def _parse(encoded):
    """Strokes as lists of runs; a run is a smooth piece between sharp corners."""
    strokes = []
    for stroke in encoded.split(';'):
        runs, run = [], []
        for token in stroke.split():
            sharp = token.endswith('!')
            x, y = map(float, token.rstrip('!').split(','))
            run.append((x, y))
            if sharp:
                runs.append(run)
                run = [(x, y)]
        runs.append(run)
        strokes.append([r for r in runs if len(r) > 1])
    return strokes


def _catmull(points, step):
    """Centripetal Catmull-Rom through points, sampled about every `step` units."""
    if len(points) == 2:
        (ax, ay), (bx, by) = points
        n = max(1, math.ceil(math.dist(points[0], points[1]) / step))
        return [(ax + (bx-ax)*k/n, ay + (by-ay)*k/n) for k in range(n+1)]
    p = [(2*points[0][0]-points[1][0], 2*points[0][1]-points[1][1])] + list(points) + \
        [(2*points[-1][0]-points[-2][0], 2*points[-1][1]-points[-2][1])]
    out = [points[0]]
    for i in range(1, len(p)-2):
        p0, p1, p2, p3 = p[i-1], p[i], p[i+1], p[i+2]
        t1 = math.dist(p0, p1)**.5 or 1e-6
        t2 = t1 + (math.dist(p1, p2)**.5 or 1e-6)
        t3 = t2 + (math.dist(p2, p3)**.5 or 1e-6)
        n = max(1, math.ceil(math.dist(p1, p2) / step))
        for k in range(1, n+1):
            t = t1 + (t2-t1)*k/n

            def lerp(a, b, ta, tb):
                return tuple(a[j]*(tb-t)/(tb-ta) + b[j]*(t-ta)/(tb-ta) for j in (0, 1))
            a1, a2, a3 = lerp(p0, p1, 0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            b1, b2 = lerp(a1, a2, 0, t2), lerp(a2, a3, t1, t3)
            out.append(lerp(b1, b2, t1, t2))
    return out


def _simplify(points, tolerance):
    """Ramer-Douglas-Peucker: drop points within tolerance of the line through their neighbours."""
    if len(points) < 3:
        return points
    (ax, ay), (bx, by) = points[0], points[-1]
    length = math.hypot(bx-ax, by-ay)
    far, index = 0.0, 0
    for i in range(1, len(points)-1):
        px, py = points[i]
        d = abs((bx-ax)*(ay-py) - (ax-px)*(by-ay))/length if length else math.hypot(px-ax, py-ay)
        if d > far:
            far, index = d, i
    if far <= tolerance:
        return [points[0], points[-1]]
    return _simplify(points[:index+1], tolerance)[:-1] + _simplify(points[index:], tolerance)


def _glyph(char, glyphs):
    if char in glyphs:
        return glyphs[char]
    if char in READER:
        return READER[char]
    from notebook_plotter_font import GLYPHS as PLOTTER
    if char not in PLOTTER:
        raise ValueError('unsupported handwriting glyph')
    # A plotter glyph (cap height 6) restated on this font's cap height.
    k = CAP/6
    return ';'.join(' '.join(f'{float(x)*k:g},{float(y)*k:g}!' for x, y in (p.split(',') for p in s.split()))
                    for s in PLOTTER[char].split(';')), 4*k


def handwriting_paths(text, size=24, *, hand='primer', seed=None):
    """Pen paths for text in a hand, and the advance. size is the cap height in pixels; the origin is the top-left of a
    capital, like notebook_plotter_font.label_paths. The same text, size and hand draw the same way."""
    if hand not in HANDS:
        raise ValueError('unknown hand')
    if not isinstance(text, str) or not 1 <= len(text) <= 400:
        raise ValueError('bounded handwriting text required')
    if type(size) not in (int, float) or not math.isfinite(size) or not 8 <= size <= 120:
        raise ValueError('handwriting size must be 8..120')
    h = HANDS[hand]
    rng = random.Random(seed if seed is not None else hashlib.sha256(f'{hand}:{size}:{text}'.encode()).hexdigest())
    strokes = []  # each a list of runs of page-space control points
    advance, drift, body = 0.0, 0.0, None  # body: the open joined stroke a following letter continues
    for char in text:
        if char == ' ':
            advance += size/CAP * h['space'] * rng.uniform(.9, 1.1)
            body = None
            continue
        raised, lowered = char in SUPERSCRIPTS, char in SUBSCRIPTS
        glyph = SUPERSCRIPTS.get(char, SUBSCRIPTS.get(char, char))
        encoded, width = _glyph(glyph, h['glyphs'])
        joins = glyph in h['joins'] and not (raised or lowered)
        wide = h['wide'] if joins else 1
        width *= wide
        scale = size/CAP * (.62 if raised or lowered else 1) * rng.uniform(.97, 1.03)
        dy = -size*.30 if raised else size*.55 if lowered else 0
        drift = max(-.5, min(.5, drift + rng.uniform(-.2, .2)))  # baseline wander, in cap units
        tilt = rng.uniform(-.02, .02)

        def place(x, y):
            x, y = x*wide + rng.uniform(-h['jitter'], h['jitter']), y + rng.uniform(-h['jitter'], h['jitter'])
            x, y = x + h['slant']*(CAP-y), y + drift + tilt*(x - width/2)
            return advance + x*scale, dy + y*scale
        parsed = _parse(encoded)
        if joins and body is None:
            # A word's first letter has no lead-in: a short upstroke ending in a corner is left out entirely, a longer
            # one loses its touchdown on the baseline.
            runs = parsed[0]
            if len(runs) > 1 and len(runs[0]) <= 4:
                runs.pop(0)
            elif len(runs[0]) > 2:
                runs[0].pop(0)
        glyph_strokes = [[[place(x, y) for x, y in run] for run in runs] for runs in parsed]
        if joins and body is not None:
            first = glyph_strokes.pop(0)
            body[-1].extend(first[0][1:])  # the exit flows into this letter's upstroke, as one curve
            body.extend(first[1:])
        elif joins:
            body = glyph_strokes[0]
        else:
            body = None
        strokes.extend(glyph_strokes)
        advance += (width if joins else width + h['gap']*rng.uniform(.85, 1.15)) * scale
    step = max(.1, CAP/size)  # sampled about every pixel, then thinned to within .35 px of the curve
    paths = []
    for runs in strokes:
        points = []
        for run in runs:
            sampled = _catmull(run, step)
            points.extend(sampled[1:] if points else sampled)
        paths.append([(round(x, 2), round(y, 2)) for x, y in _simplify(points, .35)])
    return paths, advance
