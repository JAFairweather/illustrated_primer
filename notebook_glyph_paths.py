"""Continuous pen walks for the built-in plotter alphabet, not arbitrary ink.

Only existing glyph segments may be traversed. Exact rational intersections
preserve the visible geometry; disconnected components (such as dots) retain
separate pen lifts. The caller keeps the original paths unless the candidate
has fewer lifts and no greater estimated native drawing cost at its size.
"""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
import heapq
from itertools import combinations
import math


def _cross(a, b):
    return a[0]*b[1]-a[1]*b[0]


def _sub(a, b):
    return a[0]-b[0], a[1]-b[1]


def _contains(a, b, p):
    return _cross(_sub(b,a),_sub(p,a)) == 0 and all(
        min(a[k],b[k]) <= p[k] <= max(a[k],b[k]) for k in (0,1))


def _graph(encoded):
    # This is developer-authored font data, never a model drawing command.
    if not isinstance(encoded,str) or not 1 <= len(encoded) <= 512:
        raise ValueError('bounded static glyph required')
    paths = [[tuple(map(Fraction, p.split(','))) for p in s.split()]
             for s in encoded.split(';')]
    if any(len(path)<2 or any(len(p)!=2 for p in path) for path in paths):
        raise ValueError('glyph needs two-dimensional pen paths')
    segments = [(a,b) for path in paths for a,b in zip(path,path[1:]) if a != b]
    if not 1 <= len(segments) <= 64:
        raise ValueError('bounded static glyph segments required')
    splits = [set((a,b)) for a,b in segments]
    for i,(a,b) in enumerate(segments):
        for j,(c,d) in enumerate(segments[:i]):
            for p in (a,b,c,d):
                if _contains(a,b,p) and _contains(c,d,p):
                    splits[i].add(p); splits[j].add(p)
            r,s = _sub(b,a),_sub(d,c)
            denominator = _cross(r,s)
            if denominator:
                t,u = _cross(_sub(c,a),s)/denominator,_cross(_sub(c,a),r)/denominator
                if 0 <= t <= 1 and 0 <= u <= 1:
                    p = a[0]+t*r[0],a[1]+t*r[1]
                    splits[i].add(p); splits[j].add(p)
    edges = set()
    for (a,b),points in zip(segments,splits):
        points = sorted(points,key=lambda p: sum((p[k]-a[k])*(b[k]-a[k]) for k in (0,1)))
        edges.update(tuple(sorted((c,d))) for c,d in zip(points,points[1:]))
    adjacent = {}
    for a,b in sorted(edges):
        adjacent.setdefault(a,set()).add(b); adjacent.setdefault(b,set()).add(a)
    return paths,edges,adjacent


@lru_cache(maxsize=128)
def glyph_paths(encoded):
    """Return immutable original/candidate paths in unscaled font coordinates.

    Pair odd-degree junctions by shortest existing paths, leaving two ends for
    an open pen walk. At most eight odd vertices are allowed per component;
    current glyphs have at most six. No connecting bridge is ever invented.
    """
    original,edges,adjacent = _graph(encoded)
    remaining = set(adjacent); result = []
    while remaining:
        # Keep disconnected parts in authored order, e.g. stem before its dot.
        seed = next(p for path in original for p in path if p in remaining)
        component = set(); todo = [seed]
        while todo:
            vertex = todo.pop()
            if vertex in component: continue
            component.add(vertex); todo.extend(adjacent[vertex]-component)
        remaining -= component
        odds = tuple(sorted(v for v in component if len(adjacent[v]) % 2))
        if len(odds) > 8:
            raise ValueError('static glyph has too many branch endpoints')
        routes = {}
        for start in odds:
            queue = [(0,start,())]; reached = set()
            while queue:
                distance,v,path = heapq.heappop(queue)
                if v in reached: continue
                reached.add(v); routes[start,v] = distance,path+(v,)
                for n in sorted(adjacent[v]-reached):
                    heapq.heappush(queue,(distance+math.dist(v,n),n,path+(v,)))

        @lru_cache(None)
        def pair(vertices):
            if not vertices: return 0,()
            a = vertices[0]; options = []
            for b in vertices[1:]:
                rest = tuple(v for v in vertices if v not in (a,b))
                cost,pairs = pair(rest)
                options.append((cost+routes[a,b][0],((a,b),)+pairs))
            return min(options)

        if odds:
            _,_,pairs,ends = min((pair(tuple(v for v in odds if v not in ends))[0],
                                 seed not in ends,
                                 pair(tuple(v for v in odds if v not in ends))[1],ends)
                                for ends in combinations(odds,2))
            start = seed if seed in ends else ends[0]
        else:
            pairs = (); start = seed
        counts = Counter({edge:1 for edge in edges if edge[0] in component})
        for a,b in pairs:
            path = routes[a,b][1]
            counts.update(tuple(sorted((x,y))) for x,y in zip(path,path[1:]))
        stack = [start]; trail = []
        while stack:
            v = stack[-1]
            choices = [n for n in sorted(adjacent[v]) if counts[tuple(sorted((v,n)))]]
            if choices:
                n = choices[0]; counts[tuple(sorted((v,n)))] -= 1; stack.append(n)
            else: trail.append(stack.pop())
        result.append(list(reversed(trail)))
    def freeze(paths):
        return tuple(tuple((float(x),float(y)) for x,y in p) for p in paths)
    return freeze(original),freeze(result)


def select_paths(encoded, scale):
    original,candidate = glyph_paths(encoded)
    def cost(paths):
        points = sum(1+sum(max(1,math.ceil(math.dist(a,b)*scale/2))
                          for a,b in zip(p,p[1:])) for p in paths)
        return points*9+len(paths)*70
    if len(candidate)<len(original) and cost(candidate)<=cost(original):
        return candidate
    return original
