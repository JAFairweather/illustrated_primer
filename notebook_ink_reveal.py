"""Ordered native chunk assets, not an evdev or continuous-stroke adapter.

Put each consecutive group in a disjoint row of one immutable source page.
The native client can select/clone a row while keeping destination input locked.
No user page, model geometry, extra journal or device I/O belongs here.
"""
import hashlib
import math
import uuid

from ink import append, strokes
from notebook_stroke_asset import _foundation, storyboard_assets


def _bounds(paths):
    points = [p for path in paths for p in path]
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def _partition(paths, count):
    """Cut the ordered polyline stream by distance, retaining every corner.

    Only boundary points are duplicated, never a nonzero edge. Zero-length
    strokes remain intact (plotter dots are permitted by the source format).
    """
    length = sum(math.dist(a, b) for p in paths for a, b in zip(p, p[1:]))
    if not length or count == 1:
        return [paths]
    groups = [[]]; travelled = 0.; boundary = length/count
    for path in paths:
        current = [path[0]]
        for a, b in zip(path, path[1:]):
            edge = math.dist(a, b)
            end = travelled + edge
            while edge and len(groups) < count and boundary <= end:
                t = (boundary-travelled)/edge
                joint = tuple(a[k]+(b[k]-a[k])*t for k in (0, 1))
                if joint != current[-1]: current.append(joint)
                if len(current) >= 2: groups[-1].append(current)
                groups.append([]); current = [joint]
                boundary = length*len(groups)/count
            if b != current[-1]: current.append(b)
            travelled = end
        if len(current) >= 2:
            groups[-1].append(current)
        elif all(p == path[0] for p in path):
            groups[-1].append(path)
    return [g for g in groups if g]


def reveal_assets(plan, author=None, chunks=4):
    """Validate the entire lesson, then encode at most four rows per stage.

    Extra joint points/strokes count against the original caps. This explicit
    opt-in may reject a near-limit plan; it never coarsens or silently falls back.
    """
    if type(chunks) is not int or not 1 <= chunks <= 4:
        raise ValueError('native reveal requires 1..4 chunks')
    from notebook_pen_budget import NativePenBudgetError
    assets = storyboard_assets(plan, author)  # full validation before any split
    foundation = _foundation(uuid.UUID(str(author)) if author else uuid.uuid4())
    total = 0; result = []
    for asset in assets:
        paths = [[(x, y) for x, y, _ in p] for _, p, _ in strokes(asset['data'])]
        groups = _partition(paths, chunks)
        count = sum(len(g) for g in groups)
        points = sum(len(p) for g in groups for p in g)
        total += points
        if count > 64 or points > 3000 or total > 12000 or points*.009+count*.070 > 30:
            raise NativePenBudgetError('native reveal exceeds existing point/stroke/time budget')
        rows = []; encoded = []
        for index, group in enumerate(groups):
            dy = index*(asset['height']+40)
            rows.append(dict(offset=[0, dy], rect=[-10, dy-10, asset['width']+20, asset['height']+20],
                             bounds=_bounds(group), stroke_count=len(group),
                             point_count=sum(map(len, group))))
            encoded.extend([[(x, y+dy, 2) for x, y in path] for path in group])
        raw = append(foundation, encoded, start=((0, 11), (1, 14)))
        item = dict(asset, data=raw, sha256=hashlib.sha256(raw).hexdigest(),
                    stroke_count=count, point_count=points, reveal=rows)
        reveal_source_paths(item, raw)  # independent decode/descriptor check
        result.append(item)
    return result


def reveal_source_paths(block, data):
    """Validate atlas rows and return intended destination-local saved shapes.

    Both preflight and final persistence proof use this same mapping. A hash
    authenticates source bytes; it does not by itself validate row translations.
    """
    if hashlib.sha256(data).hexdigest() != block['sha256']:
        raise ValueError('native reveal source integrity changed')
    paths = [p for _, p, _ in strokes(data)]
    if (type(block['stroke_count']) is not int or not 1 <= block['stroke_count'] <= 64 or
            type(block['point_count']) is not int or not 2 <= block['point_count'] <= 3000 or
            block['point_count']*.009+block['stroke_count']*.070 > 30):
        raise ValueError('native reveal exceeds existing point/stroke/time budget')
    if len(paths) != block['stroke_count'] or sum(map(len, paths)) != block['point_count']:
        raise ValueError('native reveal source count changed')
    rows = block.get('reveal')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4:
        raise ValueError('bounded native reveal rows required')
    out = []; start = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {'offset','rect','bounds','stroke_count','point_count'}:
            raise ValueError('invalid native reveal row')
        dy = index*(block['height']+40)
        if row['offset'] != [0, dy] or row['rect'] != [-10, dy-10, block['width']+20, block['height']+20]:
            raise ValueError('native reveal row transform changed')
        n = row['stroke_count']
        if type(n) is not int or not 1 <= n <= 64 or start+n > len(paths):
            raise ValueError('native reveal row stroke count changed')
        group = [[(x, y-dy, w) for x,y,w in p] for p in paths[start:start+n]]
        if type(row['point_count']) is not int or row['point_count'] != sum(map(len, group)):
            raise ValueError('native reveal row point count changed')
        box = row['bounds']
        actual = _bounds(group)
        if (not isinstance(box, list) or len(box) != 4 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in box) or
                any(abs(a-b) > .001 for a,b in zip(box, actual)) or
                not (0 <= actual[0] <= actual[2] <= block['width'] and
                     0 <= actual[1] <= actual[3] <= block['height'])):
            raise ValueError('native reveal geometry or bounds changed')
        out.extend(group); start += n
    if start != len(paths):
        raise ValueError('native reveal leaves unselected source strokes')
    return out
