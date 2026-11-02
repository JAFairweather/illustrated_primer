"""Small data tables -> a shared-scale, additive pen chart (no device I/O).

The author supplies quantities, not canvas coordinates. Straight links are
explicit interpolation guides, never an inferred function or smoothed curve.
Input truth and scientific interpretation still require model/user review.
"""
from fractions import Fraction
import math

from notebook_lesson import _fields, _number, _text
from notebook_procedural import _label, _line


def sampled_chart(obj):
    _fields(obj, {'id', 'component', 'x', 'y', 'x_label', 'y_label'}, {'label', 'reference'})
    xs, ys = obj['x'], obj['y']
    if (not isinstance(xs, list) or not isinstance(ys, list) or
            not 2 <= len(xs) <= 8 or len(xs) != len(ys)):
        raise ValueError('sampled chart requires 2..8 paired quantities')
    xs = [Fraction(str(_number(v, -1000000, 1000000))) for v in xs]
    ys = [Fraction(str(_number(v, -1000000, 1000000))) for v in ys]
    reference = obj.get('reference')
    reference_ys = []
    if 'reference' in obj:
        _fields(reference, {'label', 'y'})
        primary_label = _text(obj.get('label'), 12)
        reference_label = _text(reference['label'], 12)
        if primary_label == reference_label:
            raise ValueError('comparison series need distinct labels')
        if not isinstance(reference['y'], list) or len(reference['y']) != len(xs):
            raise ValueError('reference series must use the same x samples')
        reference_ys = [Fraction(str(_number(v, -1000000, 1000000))) for v in reference['y']]
    elif 'label' in obj:
        raise ValueError('series labels accompany a reference comparison')
    if any(b <= a for a, b in zip(xs, xs[1:])):
        raise ValueError('sampled chart x quantities must strictly increase')
    x_label, y_label = (_text(obj[k], 16) for k in ('x_label', 'y_label'))
    # Include zero; a small change in a large quantity must not look enormous.
    low, high = min(Fraction(0), *ys, *reference_ys), max(Fraction(0), *ys, *reference_ys)
    if low == high:  # all-zero series still has a defined, honest scale
        low, high = Fraction(-1), Fraction(1)
    project = lambda x, y: (110 + 400 * float((x-xs[0])/(xs[-1]-xs[0])),
                            265 - 200 * float((y-low)/(high-low)))
    points = [project(x, y) for x, y in zip(xs, ys)]
    reference_points = [project(x, y) for x, y in zip(xs, reference_ys)]
    for series in (points, reference_points):
        if any(math.dist(a, b) < 12 for a, b in zip(series, series[1:])):
            raise ValueError('sampled chart points are too close to distinguish')

    def number(value):
        # Plain compact numbers, no obscure exponent notation or rounded
        # endpoints that silently change the represented scale.
        text = format(float(value), '.6f').rstrip('0').rstrip('.') if value else '0'
        if len(text) > 9 or Fraction(text) != value:
            raise ValueError('sampled chart axis values need exact short decimal labels')
        return text

    frame = [_line((110, 55), (110, 275)), _line((100, 265), (520, 265)),
             _label(y_label, 310, 26), _label(x_label, 310, 345)]
    scales = []
    for value, x in ((xs[0], 110), (xs[-1], 510)):
        scales += [_line((x, 261), (x, 269)), _label(number(value), x, 300, 16)]
    for value in sorted({low, high, Fraction(0)}):
        _, y = project(xs[0], value)
        scales += [_line((106, y), (114, y)), _label(number(value), 54, y+5, 14)]
    samples = [{'op': 'circle', 'center': list(p), 'radius': 3} for p in points]
    links = []
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        # Stop at each marker boundary instead of painting through the dots.
        direction = [(b[k]-a[k])/length for k in (0, 1)]
        links.append(_line([a[k]+3*direction[k] for k in (0, 1)],
                           [b[k]-3*direction[k] for k in (0, 1)]))
    increasing = all(b > a for a, b in zip(ys, ys[1:]))
    decreasing = all(b < a for a, b in zip(ys, ys[1:]))
    constant = len(set(ys)) == 1
    result = dict(parts={'axes': frame, 'scale': scales, 'samples': samples, 'links': links},
                dependencies={'scale': {'axes'}, 'samples': {'scale'}, 'links': {'samples'}},
                facts={'increasing': increasing, 'decreasing': decreasing, 'constant': constant,
                       'mixed': not (increasing or decreasing or constant)},
                required_claims=[['increasing', 'decreasing', 'constant', 'mixed']],
                equation=None,
                metrics={'x': list(map(str, xs)), 'y': list(map(str, ys)),
                         'y_range': [str(low), str(high)], 'points': [list(p) for p in points],
                         'interpolation': 'straight guides between supplied samples',
                         'input_values_verified': False})
    if reference_ys:
        samples += [_line((115,46),(133,46)), {'op':'circle','center':[140,46],'radius':3},
                    _label(primary_label,225,51,14)]
        reference_samples = [_line((382,43),(388,49)), _line((382,49),(388,43)),
                             _label(reference_label,455,51,14)]
        for x,y in reference_points:
            reference_samples += [_line((x-2,y-2),(x+2,y+2)), _line((x-2,y+2),(x+2,y-2))]
        # Keep the existing solid curve intact. Identical segments are shared,
        # not painted over. Noncoincident reference segments use dashed guides.
        reference_links = [_line((355,46),(366,46)), _line((371,46),(377,46))]
        shared_segments = []
        for i,(a,b) in enumerate(zip(reference_points,reference_points[1:])):
            if reference_ys[i:i+2] == ys[i:i+2]:
                shared_segments.append(i)
                continue
            length = math.dist(a,b)
            direction = [(b[k]-a[k])/length for k in (0,1)]
            start = 3.0
            while start < length-3:
                end = min(start+16,length-3)
                if end-start >= 1:
                    reference_links.append(_line([a[k]+start*direction[k] for k in (0,1)],
                                                 [a[k]+end*direction[k] for k in (0,1)]))
                start += 28
        gap = ys[-1]-reference_ys[-1]
        result['parts'].update(reference_samples=reference_samples, reference_links=reference_links,
                               difference=[_label('Final gap = '+number(gap),310,311,14)])
        result['dependencies'].update(reference_samples={'scale'}, reference_links={'reference_samples'},
                                      difference={'links','reference_links'})
        result['facts'].update(final_above=gap>0, final_below=gap<0, final_equal=gap==0)
        result['required_claims'].append(['final_above','final_below','final_equal'])
        result['metrics']['reference'] = dict(label=reference_label,y=list(map(str,reference_ys)),
            points=[list(p) for p in reference_points],shared_segments=shared_segments,
            final_gap=str(gap),gap_convention='primary minus reference')
        result['metrics']['label'] = primary_label
    return result
