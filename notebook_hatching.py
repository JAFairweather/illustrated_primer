"""Procedural diagonal ink clipped to validated polygon edges.

No model-selected hatch density, stroke timing, code or device operations.
The caller owns coordinate validation; lesson compilation owns ink budgets.
"""
import math


def _at_offset(points, offset):
    intersections = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]+points[:1]):
        t1, t2 = x1+y1, x2+y2
        # Half-open edges count a shared vertex once, including local extrema.
        if (t1 <= offset < t2) or (t2 <= offset < t1):
            fraction = (offset-t1)/(t2-t1)
            intersections.append(x1+(x2-x1)*fraction)
    intersections.sort()
    if len(intersections) % 2:
        raise ValueError('sampled area has an inconsistent boundary')
    return [[[left, offset-left], [right, offset-right]]
            for left, right in zip(intersections[::2], intersections[1::2])
            if (right-left)*math.sqrt(2) >= 1]


def hatch_paths(points):
    """Even-odd fill, preserving separate lobes at sampled-area crossings.

    Sparse page-aligned lattice shared with rectangular hatching. Only
    decorative fill is clipped; mathematical geometry is never changed.
    Fragments shorter than one display unit are omitted, never enlarged.
    """
    spacing = 32*math.sqrt(2)
    offsets = [x+y for x, y in points]
    return [path for i in range(math.ceil(min(offsets)/spacing),
                               math.floor(max(offsets)/spacing)+1)
            for path in _at_offset(points, i*spacing)]


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _intersects(a, b, c, d):
    signs = [_cross(a,b,c), _cross(a,b,d), _cross(c,d,a), _cross(c,d,b)]
    if signs[0]*signs[1] < 0 and signs[2]*signs[3] < 0:
        return True
    for cross, start, end, point in (
            (signs[0],a,b,c), (signs[1],a,b,d),
            (signs[2],c,d,a), (signs[3],c,d,b)):
        if (abs(cross) <= 1e-9 and
                min(start[0],end[0])-1e-9 <= point[0] <= max(start[0],end[0])+1e-9 and
                min(start[1],end[1])-1e-9 <= point[1] <= max(start[1],end[1])+1e-9):
            return True
    return False


def shade_paths(points):
    """One simple polygon, implicitly closed; hatch only, no duplicate outline.

    Explicitly repeating the first vertex is accepted. Crossed/touching edges
    and degenerate rings are rejected rather than guessed into a region.
    """
    points = list(points)
    if points[-1] == points[0]:
        points = points[:-1]
    if len(points) < 3 or len(set(map(tuple, points))) != len(points):
        raise ValueError('shade requires distinct polygon vertices')
    edges = list(zip(points, points[1:]+points[:1]))
    for i, (a, b) in enumerate(edges):
        if math.dist(a, b) < 1e-9:
            raise ValueError('shade has a degenerate edge')
        c = points[(i+2) % len(points)]
        if (abs(_cross(a,b,c)) <= 1e-9 and
                (b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1]) < 0):
            raise ValueError('shade boundary doubles back')
        for j in range(i+1, len(edges)):
            if j == i+1 or (i == 0 and j == len(edges)-1):
                continue
            if _intersects(a, b, *edges[j]):
                raise ValueError('shade requires a simple non-self-intersecting polygon')
    if abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in edges)) <= 1e-9:
        raise ValueError('shade requires nonzero area')
    paths = hatch_paths(points)
    if not paths:
        # Small regions between lattice lines still get a clipped cue. Never
        # enlarge their geometry or bridge a concavity to manufacture ink.
        offsets = [x+y for x,y in points]
        paths = _at_offset(points, (min(offsets)+max(offsets))/2)
    if not paths:
        raise ValueError('shade region is too thin for visible ink')
    return paths
