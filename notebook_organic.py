"""Hand-drawn ink for procedural geometry: the agent chooses the shapes, this decides how a pen draws them.

Two parts. organic() dithers a shape's path: a slow wobble and a slight bow off the true line, an end that
over- or undershoots, a closed shape whose seam overlaps or stops short. pen_profile() gives each point a
width (what pressure looks like on the page) and a pen angle: light at touchdown, firm through the stroke,
lifting at the end. Both are seeded by the path itself, so the same lesson always draws the same way.

The wobble stays within WOBBLE px of the true geometry, well inside the 8 px label clearance, so a shape
still means what the agent drew. Pressure is not varied: our strokes keep pressure 255 and speed 2, the mark
that tells our ink from James's (ink.strokes).
"""
import hashlib
import math
import random

WOBBLE = 1.6   # px: the furthest a dithered point strays from the true path
STEP = 5.98    # px between dithered points: just under 3 of the densifier's 2 px, so it adds no extra points


def _rng(path, salt):
    key = repr([(round(x, 1), round(y, 1)) for x, y in path[:4]] + [len(path), salt])
    return random.Random(hashlib.sha256(key.encode()).digest())


def _resample(path):
    out = [tuple(path[0])]
    for a, b in zip(path, path[1:]):
        n = max(1, math.ceil(math.dist(a, b) / STEP))
        out += [(a[0] + (b[0]-a[0])*i/n, a[1] + (b[1]-a[1])*i/n) for i in range(1, n+1)]
    return out


def _arc(path):
    s = [0.0]
    for a, b in zip(path, path[1:]):
        s.append(s[-1] + math.dist(a, b))
    return s


def organic(path, width=600, height=360):
    """One shape's path, dithered as a hand would draw it."""
    length = _arc(path)[-1]
    if len(path) < 2 or length < 4 or not all(0 <= x <= width and 0 <= y <= height for x, y in path):
        return [tuple(p) for p in path]   # out-of-region geometry is left for the validator to reject
    r = _rng(path, 'shape')
    closed = math.dist(path[0], path[-1]) < .5
    points = _resample(path)
    s = _arc(points)
    amp = min(WOBBLE * .7, .35 + length / 260)
    waves = [(r.uniform(28, 46), r.uniform(0, math.tau), .65), (r.uniform(9, 15), r.uniform(0, math.tau), .35)]
    bow = 0 if closed or len(path) > 2 else r.choice((-1, 1)) * min(WOBBLE - amp, length * .01)
    out = []
    for i, (x, y) in enumerate(points):
        a, b = points[max(0, i-1)], points[min(len(points)-1, i+1)]
        tx, ty = b[0]-a[0], b[1]-a[1]
        n = math.hypot(tx, ty) or 1
        t = s[i] / s[-1]
        d = amp * sum(w * math.sin(s[i] / lam + phase) for lam, phase, w in waves) + bow * math.sin(math.pi * t)
        out.append((x - d * ty / n, y + d * tx / n))
    if closed:
        # A hand rarely lands exactly on its start: carry on a little past it, or lift just short.
        if r.random() < .6:
            extra = [p for p, si in zip(out[1:], s[1:]) if si <= r.uniform(3, 7)]
            out += extra or out[1:2]
        elif len(out) > 3:
            out = out[:-1]
    elif length > 20:
        (ax, ay), (bx, by) = out[-2], out[-1]
        n = math.hypot(bx-ax, by-ay) or 1
        e = r.uniform(-.6, 1.6)   # mostly a small overshoot, sometimes stopping just short
        out[-1] = (bx + e * (bx-ax) / n, by + e * (by-ay) / n)
    # Only the dither is clamped: the true path is already inside the region.
    return [(min(max(x, 0), width), min(max(y, 0), height)) for x, y in out]


def pen_profile(path):
    """(width, direction) for each point: a pressure swell along the stroke and a hand's slowly turning angle."""
    r = _rng(path, 'pen')
    s = _arc(path)
    length = s[-1] or 1
    base = r.uniform(1.85, 2.15)
    land, lift = r.uniform(4, 9), r.uniform(6, 12)
    swell = (r.uniform(18, 34), r.uniform(0, math.tau))
    tilt, turn = r.uniform(.56, .70), (r.uniform(35, 60), r.uniform(0, math.tau))
    out = []
    for si in s:
        ramp = min(1, si / land, (length - si) / lift) if length > 12 else 1
        width = base * (.7 + .3 * max(0, ramp)) * (1 + .09 * math.sin(si / swell[0] + swell[1]))
        direction = int(255 * ((tilt + .025 * math.sin(si / turn[0] + turn[1])) % 1))
        out.append((round(width, 2), direction))
    return out
