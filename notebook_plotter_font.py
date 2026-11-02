"""Original single-line plotter alphabet for small notebook diagram labels.

Glyphs are open pen paths, not font outlines or skeletonized bitmaps. Coordinates
use a six-unit cap height. Unsupported characters fail explicitly; no fallback
font can silently insert a replacement box. Captions remain native text.
"""
import math
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from notebook_glyph_paths import select_paths
from notebook_pen_budget import NativePenBudgetError, native_budget_failure


_continuous = ContextVar('notebook_continuous_glyphs', default=True)
_compilation_depth = ContextVar('notebook_font_compilation_depth', default=0)


@contextmanager
def original_glyphs():
    """A local compilation choice, isolated from concurrent requests."""
    token = _continuous.set(False)
    try:
        yield
    finally:
        _continuous.reset(token)


def font_budget_fallback(compile_function):
    """One same-input, original-font compilation after a typed budget failure.

    Retrying never changes text, geometry, constraints or model output. This
    is pure offline compilation: decorate no function that writes to a device.
    Invalid schema, collisions and provider failures are not retryable here.
    """
    @wraps(compile_function)
    def compile_with_fallback(*args, **kwargs):
        depth = _compilation_depth.get()
        token = _compilation_depth.set(depth+1)
        try:
            try:
                return compile_function(*args, **kwargs)
            except ValueError as error:
                if depth or not _continuous.get():
                    raise
                cause = error
                for _ in range(8):
                    if isinstance(cause, NativePenBudgetError):
                        break
                    cause = getattr(cause, '__cause__', None)
                else:
                    raise
                first_failure = native_budget_failure(error)
            with original_glyphs():
                try:
                    return compile_function(*args, **kwargs)
                except ValueError as error:
                    final_failure = native_budget_failure(error)
                    if first_failure is not None and final_failure is not None:
                        # Preserve both existing compilation attempts, not just
                        # the larger count from the original-font fallback.
                        error.budget_attempts = [dict(font='continuous',failure=first_failure),
                                                 dict(font='original',failure=final_failure)]
                    raise
        finally:
            _compilation_depth.reset(token)
    return compile_with_fallback


GLYPHS = {
    'A': '0,6 2,0 4,6;1,3 3,3',
    'B': '0,6 0,0 2.5,0 4,1 4,2 2.5,3 0,3;2.5,3 4,4 4,5 2.5,6 0,6',
    'C': '4,1 3,0 1,0 0,1 0,5 1,6 3,6 4,5',
    'D': '0,6 0,0 2,0 4,2 4,4 2,6 0,6',
    'E': '4,0 0,0 0,6 4,6;0,3 3,3',
    'F': '4,0 0,0 0,6;0,3 3,3',
    'G': '4,1 3,0 1,0 0,1 0,5 1,6 3,6 4,5 4,3 2,3',
    'H': '0,0 0,6;4,0 4,6;0,3 4,3',
    'I': '0,0 4,0;2,0 2,6;0,6 4,6',
    'J': '0,0 4,0 4,5 3,6 1,6 0,5',
    'K': '0,0 0,6;4,0 0,3 4,6',
    'L': '0,0 0,6 4,6',
    'M': '0,6 0,0 2,3 4,0 4,6',
    'N': '0,6 0,0 4,6 4,0',
    'O': '1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0',
    'P': '0,6 0,0 3,0 4,1 4,2 3,3 0,3',
    'Q': '1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0;2,4 4,6',
    'R': '0,6 0,0 3,0 4,1 4,2 3,3 0,3;2,3 4,6',
    'S': '4,1 3,0 1,0 0,1 0,2 1,3 3,3 4,4 4,5 3,6 1,6 0,5',
    'T': '0,0 4,0;2,0 2,6',
    'U': '0,0 0,5 1,6 3,6 4,5 4,0',
    'V': '0,0 2,6 4,0',
    'W': '0,0 1,6 2,3 3,6 4,0',
    'X': '0,0 4,6;4,0 0,6',
    'Y': '0,0 2,3 4,0;2,3 2,6',
    'Z': '0,0 4,0 0,6 4,6',
    'a': '4,3 3,2 1,2 0,3 0,5 1,6 3,6 4,5;4,2 4,6',
    'b': '0,0 0,6;0,3 1,2 3,2 4,3 4,5 3,6 1,6 0,5',
    'c': '4,3 3,2 1,2 0,3 0,5 1,6 3,6 4,5',
    'd': '4,0 4,6;4,3 3,2 1,2 0,3 0,5 1,6 3,6 4,5',
    'e': '0,4 4,4 4,3 3,2 1,2 0,3 0,5 1,6 3,6 4,5',
    'f': '1,6 1,1 2,0 3,0;0,2 3,2',
    'g': '4,3 3,2 1,2 0,3 0,5 1,6 3,6 4,5;4,2 4,7 3,8 1,8',
    'h': '0,0 0,6;0,3 1,2 3,2 4,3 4,6',
    'i': '2,2 2,6;2,0 2.1,0',
    'j': '3,2 3,7 2,8 1,8;3,0 3.1,0',
    'k': '0,0 0,6;4,2 0,4 4,6',
    'l': '1,0 1,5 2,6 3,6',
    'm': '0,6 0,2;0,3 1,2 2,3 2,6;2,3 3,2 4,3 4,6',
    'n': '0,6 0,2;0,3 1,2 3,2 4,3 4,6',
    'o': '1,2 3,2 4,3 4,5 3,6 1,6 0,5 0,3 1,2',
    'p': '0,8 0,2;0,3 1,2 3,2 4,3 4,5 3,6 1,6 0,5',
    'q': '4,8 4,2;4,3 3,2 1,2 0,3 0,5 1,6 3,6 4,5',
    'r': '0,6 0,2;0,3 1,2 3,2 4,3',
    's': '4,3 3,2 1,2 0,3 1,4 3,4 4,5 3,6 1,6 0,5',
    't': '2,0 2,5 3,6 4,6;0,2 4,2',
    'u': '0,2 0,5 1,6 3,6 4,5;4,2 4,6',
    'v': '0,2 2,6 4,2',
    'w': '0,2 1,6 2,4 3,6 4,2',
    'x': '0,2 4,6;4,2 0,6',
    'y': '0,2 2,6;4,2 1,8 0,8',
    'z': '0,2 4,2 0,6 4,6',
    '0': '1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0',
    '1': '0,1 2,0 2,6;0,6 4,6',
    '2': '0,1 1,0 3,0 4,1 4,2 0,6 4,6',
    '3': '0,0 4,0 2,3 4,4 4,5 3,6 0,6',
    '4': '3,6 3,0 0,4 4,4',
    '5': '4,0 0,0 0,3 3,3 4,4 4,5 3,6 0,6',
    '6': '4,0 1,0 0,1 0,5 1,6 3,6 4,5 4,4 3,3 0,3',
    '7': '0,0 4,0 1,6',
    '8': '1,0 3,0 4,1 4,2 3,3 1,3 0,4 0,5 1,6 3,6 4,5 4,4 3,3 1,3 0,2 0,1 1,0',
    '9': '4,3 1,3 0,2 0,1 1,0 3,0 4,1 4,5 3,6 0,6',
    '+': '0,3 4,3;2,1 2,5', '-': '0,3 4,3',
    '=': '0,2 4,2;0,4 4,4', '/': '0,6 4,0',
    '*': '0,1 4,5;0,5 4,1;2,0 2,6',
    '^': '0,2 2,0 4,2', '_': '0,6 4,6',
    '.': '2,5.9 2.1,6', ',': '2,5.5 1.5,7',
    ':': '2,2 2.1,2;2,5 2.1,5', ';': '2,2 2.1,2;2,5 1.5,6.5',
    '(': '3,0 1,2 1,4 3,6', ')': '1,0 3,2 3,4 1,6',
    '[': '3,0 1,0 1,6 3,6', ']': '1,0 3,0 3,6 1,6',
    '<': '4,0 0,3 4,6', '>': '0,0 4,3 0,6',
    '−': '0,3 4,3',
    '≤': '4,0 0,2 4,4;0,6 4,6',
    '≥': '0,0 4,2 0,4;0,6 4,6',
    '≠': '0,2 4,2;0,4 4,4;0,5 4,1',
    '!': '2,0 2,4;2,5.9 2.1,6',
    '?': '0,1 1,0 3,0 4,1 4,2 2,3 2,4;2,5.9 2.1,6',
    "'": '2,0 1.5,1.5', '"': '1,0 1,1.5;3,0 3,1.5',
    '%': '0,6 4,0;0,0 1,0 1,1 0,1 0,0;3,5 4,5 4,6 3,6 3,5',
    '$': '4,1 3,0 1,0 0,1 0,2 1,3 3,3 4,4 4,5 3,6 1,6 0,5;2,-1 2,7',
    '|': '2,0 2,6', '×': '0,1 4,5;4,1 0,5',
    'Δ': '0,6 2,0 4,6 0,6', 'π': '0,2 4,2;1,2 1,6;3,2 3,6',
    'Σ': '4,0 0,0 2,3 0,6 4,6', '√': '0,3 1,4 2,0 4,0',
    '∫': '4,0 3,0 2,1 2,5 1,6 0,6',
    # Ordinary mathematical relations remain pen paths, not substitutions
    # such as turning proportionality into equality or a missing-font box.
    '∝': '4,1 3.4,1 2.8,1.6 2,3 1.2,4.4 0.6,4.6 0,4 0,2 0.6,1.4 1.2,1.6 2,3 2.8,4.4 3.4,5 4,5',
    '≈': '0,2 0.75,1.5 1.5,1.5 2.5,2.5 3.25,2.5 4,2;0,4 0.75,3.5 1.5,3.5 2.5,4.5 3.25,4.5 4,4',
    '∞': '0,3 0.5,1.8 1.2,1.8 2,3 2.8,4.2 3.5,4.2 4,3 3.5,1.8 2.8,1.8 2,3 1.2,4.2 0.5,4.2 0,3',
    '±': '0,2 4,2;2,0 2,4;0,6 4,6',
    '÷': '0,3 4,3;2,0.5 2.1,0.5;2,5.5 2.1,5.5',
    '·': '2,3 2.1,3',
    '→': '0,3 4,3;2,1 4,3 2,5',
    '←': '4,3 0,3;2,1 0,3 2,5',
    '↔': '0,3 4,3;2,1 4,3 2,5;2,1 0,3 2,5',
    '↑': '2,6 2,0;0,2 2,0 4,2',
    '↓': '2,0 2,6;0,4 2,6 4,4',
    # Greek as science and mathematics use it; lowercase sits on the x-height like the Latin.
    'α': '4,2 3.5,4 3,5 2.5,6 1,6 0,5 0,3 1,2 2.2,2 3,3 3.5,4 4,6',
    'β': '0,8 0,1 1,0 3,0 4,1 4,2 3,3 1,3;3,3 4,4 4,5 3,6 1,6 0,5',
    'γ': '0,2 1,2 2,6 3,2;2,6 2,8',
    'δ': '3,0 1,0 1,1 3,2 4,3 4,5 3,6 1,6 0,5 0,3 1,2 3,2',
    'ε': '4,2 1,2 0,3 1,4 3,4;1,4 0,5 1,6 4,6',
    'ζ': '1,0 4,0 0,4 0,6 1,6 3,6 3,7 2,8',
    'η': '0,2 0,6;0,3 1,2 3,2 4,3 4,8',
    'θ': '1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0;0,3 4,3',
    'λ': '0,0 1,0 4,6;2,2 0,6',
    'μ': '0,8 0,2;0,5 1,6 3,6 4,5;4,2 4,6',
    'ν': '0,2 1,2 2,6 4,3 4,2',
    'ξ': '1,0 4,0;3,0 1,1 1,2 3,3 1,3 0,4 0,5 1,6 3,6 3,7 2,8',
    'ρ': '0,8 0,3 1,2 3,2 4,3 4,5 3,6 1,6 0,5',
    'σ': '4,2 1,2 0,3 0,5 1,6 3,6 4,5 4,4 3,2',
    'τ': '0,2 4,2;2,2 2,5 3,6',
    'φ': '2,0 2,8;1,2 0,3 0,5 1,6 3,6 4,5 4,3 3,2 1,2',
    'χ': '0,2 2,5 4,8;4,2 2,5 0,8',
    'ψ': '2,0 2,8;0,2 0,4 1,6 3,6 4,4 4,2',
    'ω': '1,2 0,4 0,5 1,6 2,5 2,4;2,5 3,6 4,5 4,4 3,2',
    'Γ': '4,0 0,0 0,6',
    'Θ': '1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0;1,3 3,3',
    'Λ': '0,6 2,0 4,6',
    'Π': '0,6 0,0 4,0 4,6',
    'Φ': '2,0 2,6;1,1 0,2 0,4 1,5 3,5 4,4 4,2 3,1 1,1',
    'Ψ': '2,0 2,6;0,1 0,3 1,4 3,4 4,3 4,1',
    'Ω': '0,6 1.5,6 1.5,5 0,4 0,1 1,0 3,0 4,1 4,4 2.5,5 2.5,6 4,6',
}
SUPERSCRIPTS = dict(zip('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789'))
SUBSCRIPTS = dict(zip('₀₁₂₃₄₅₆₇₈₉', '0123456789'))


def label_paths(text, size=24):
    """Return sparse paths and advance; origin is the ordinary glyph's top-left."""
    if not isinstance(text, str) or not 1 <= len(text) <= 48:
        raise ValueError('bounded diagram label required')
    if type(size) not in (int, float) or not math.isfinite(size) or not 12 <= size <= 28:
        raise ValueError('label size must be 12..28')
    paths, advance = [], 0.0
    for char in text:
        if char == ' ':
            advance += size*.4
            continue
        raised = char in SUPERSCRIPTS
        lowered = char in SUBSCRIPTS
        glyph = SUPERSCRIPTS.get(char, SUBSCRIPTS.get(char, char))
        if glyph not in GLYPHS:
            raise ValueError('unsupported diagram-label glyph')
        scale = size/6 * (.67 if raised or lowered else 1)
        dy = -size*.32 if raised else size*.55 if lowered else 0
        chosen = select_paths(GLYPHS[glyph], scale) if _continuous.get() else (
            [tuple(map(float, p.split(','))) for p in stroke.split()]
            for stroke in GLYPHS[glyph].split(';'))
        for points in chosen:
            paths.append([(advance+x*scale, dy+y*scale) for x, y in points])
        advance += 5.4*scale
    return paths, advance
