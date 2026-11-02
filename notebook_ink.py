"""Bounded line-art-to-native-pen plans. Conversion alone never touches the tablet.

This traces line art, not photographs, and never converts the reply's prose.
The caller must reserve/check a blank destination before drawing these paths.
"""
import math
import numpy as np
from PIL import Image
from ink import thin, trace, rdp


def line_art_paths(image, width=600, height=300, max_seconds=15):
    if not isinstance(image, Image.Image):
        raise ValueError('line art must be a decoded image')
    if not (32 <= width <= 1000 and 32 <= height <= 600):
        raise ValueError('drawing must fit a bounded notebook region')
    if not (0 < max_seconds <= 30):
        raise ValueError('drawing time budget must be at most 30 seconds')
    if image.width * image.height > 1_000_000 or min(image.size) < 2:
        raise ValueError('line art input must contain at most one million pixels')
    # Transparent areas are paper, never black ink. Preserve the source image.
    rgba = image.convert('RGBA')
    paper = Image.new('RGBA', rgba.size, 'white')
    paper.alpha_composite(rgba)
    mask = np.asarray(paper.convert('L')) < 128
    ys, xs = np.nonzero(mask)
    if len(xs) < 10:
        raise ValueError('image contains no usable line art')
    mask = mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
    if np.mean(mask) > .25:
        raise ValueError('image is too densely filled; supply sparse line art, not a photo or poster')
    src_h, src_w = mask.shape
    scale = min((width-16) / max(1, src_w-1), (height-16) / max(1, src_h-1))
    paths = []
    points_used = 0
    for path in trace(thin(mask)):
        # Simplify before dense event sampling: the native input still needs
        # closely spaced coordinates, even for one long straight stroke.
        placed = [(8+x*scale, 8+y*scale) for x, y in path]
        simple = rdp(placed, .7)
        dense = []
        for a, b in zip(simple, simple[1:]):
            count = max(1, math.ceil(math.dist(a, b) / 2))
            dense.extend([(a[0]+(b[0]-a[0])*i/count, a[1]+(b[1]-a[1])*i/count)
                          for i in range(count)])
        dense.append(simple[-1])
        points_used += len(dense)
        paths.append(dense)
        # Bound event count, fragmentation and total nominal pen time. This
        # estimate excludes SSH/CPU overhead; it is not measured latency.
        estimate = points_used * .009 + len(paths) * .070
        if len(paths) > 128 or points_used > 6000 or estimate > max_seconds:
            raise ValueError('drawing exceeds pen budget; simplify the line art or reduce its size')
    return {'paths': paths, 'width': width, 'height': height,
            'estimated_pen_seconds': round(estimate, 3), 'points': points_used,
            'kind': 'native-pen-plan'}


def place_paths(plan, x, y):
    """Translate a plan only; caller must validate page identity and blank area."""
    if not all(math.isfinite(value) for value in (x, y)):
        raise ValueError('drawing origin must be finite')
    return [[(x+px, y+py) for px, py in path] for path in plan['paths']]
