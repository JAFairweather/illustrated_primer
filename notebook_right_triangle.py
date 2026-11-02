"""Lengths, not guessed corners, produce a right triangle and outward squares.

This construction verifies numerical areas, not a proof of Pythagoras or the
meaning of the question. It has no model, device, filesystem or network I/O.
"""
from fractions import Fraction
import math

from notebook_lesson import _fields, _number
from notebook_procedural import _label, _label_bounds, _poly


def right_triangle(obj):
    _fields(obj, {'id', 'component', 'legs'})
    legs = obj['legs']
    if not isinstance(legs, list) or len(legs) != 2:
        raise ValueError('right triangle requires two positive leg lengths')
    a, b = [Fraction(str(_number(v, .1, 10000))) for v in legs]
    if max(a, b) / min(a, b) > 5:
        raise ValueError('right triangle leg ratio exceeds readable 5:1 layout')
    af, bf = float(a), float(b)
    vertices = [(0., 0.), (af, 0.), (0., -bf)]
    # Screen coordinates: positive y points down. All squares are OUTSIDE.
    squares = [
        [vertices[0], vertices[1], (af, af), (0., af)],
        [vertices[2], vertices[0], (-bf, 0.), (-bf, -bf)],
        [vertices[1], vertices[2], (bf, -bf-af), (af+bf, -af)],
    ]
    scale = min(420 / (af+2*bf), 280 / (2*af+bf))
    offset = (300 - af*scale/2, 175 + bf*scale/2)
    def point(p):
        return [offset[0]+scale*p[0], offset[1]+scale*p[1]]
    triangle = [point(p) for p in vertices]
    mapped = [[point(p) for p in square] for square in squares]
    marker = min(12., min(af, bf)*scale*.18)
    x,y = triangle[0]
    parts = {'triangle': [_poly(triangle+[triangle[0]]),
                           _poly([[x+marker,y],[x+marker,y-marker],[x,y-marker]])]}
    names = ('a_square', 'b_square', 'c_square')
    for name, square in zip(names, mapped):
        # The shared edge is already in the triangle. Add only the other 3.
        parts[name] = [_poly(square[1:]+[square[0]])]
    labels = []
    for index, (text, square) in enumerate(zip(('a²', 'b²', 'c²'), mapped)):
        center = [sum(p[k] for p in square)/4 for k in (0,1)]
        # Use actual glyph extents, including the raised 2. The rotated
        # hypotenuse square needs the label's diagonal inside its side length.
        size = min(18., (math.dist(square[0],square[1])-6)/(1.35 if index<2 else 1.9))
        if size<12:
            raise ValueError('right triangle area labels do not fit readable layout')
        label = _label(text, center[0], center[1], size=size)
        _,top,_,bottom = _label_bounds(label)
        label['at'][1] += center[1]-(top+bottom)/2
        labels.append(label)
    parts['areas'] = labels
    c2 = a*a+b*b
    def number(value):
        return str(value.numerator) if value.denominator == 1 else (
            r'\frac{'+str(value.numerator)+'}{'+str(value.denominator)+'}')
    root_n, root_d = math.isqrt(c2.numerator), math.isqrt(c2.denominator)
    exact = root_n**2 == c2.numerator and root_d**2 == c2.denominator
    hypotenuse = number(Fraction(root_n,root_d)) if exact else r'\sqrt{'+number(c2)+'}'
    equation = number(a*a)+'+'+number(b*b)+'='+number(c2)+r',\quad c='+hypotenuse
    return dict(parts=parts,
        dependencies={**{name:{'triangle'} for name in names}, 'areas':set(names)},
        facts={'hypotenuse_squared':c2}, required_claims=[['hypotenuse_squared']],
        equation=equation,
        metrics={'legs':[str(a),str(b)], 'triangle':triangle, 'squares':mapped,
                 'area_values':[str(a*a),str(b*b),str(c2)],
                 'hypotenuse_exact':str(Fraction(root_n,root_d)) if exact else None,
                 'uniform_scale':scale, 'shared_edges_drawn_once':True,
                 'general_proof_verified':False, 'source_interpretation_verified':False})
