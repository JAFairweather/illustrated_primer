"""Renderer-owned pointers from external labels to their actual geometry.

No object, word or label size is changed. Geometry is already final before
these finite candidates are tested; the joint solver handles other labels.
Pointers are ordinary ink commands and consume the ordinary native budget.
"""
import math

from notebook_lesson import _primitive
from notebook_procedural import _segment_distance


def _region_clearance(owner_bounds, geometry):
    """A region label cannot sit inside another, non-ancestor rectangle.

    Stroke clearance alone misses a label in a later empty strip: no line
    crosses the text, yet the strip appears to own it. Whole-picture geometry
    supplies future regions too. Containers of the actual owner are harmless;
    children, siblings and partially overlapping regions are competing owners.
    This does not move geometry, erase labels, or interpret their wording.
    """
    left, top, right, bottom = owner_bounds
    competitors = []
    for command in geometry:
        if command['op'] != 'rect':
            continue
        x, y = command['origin']
        width, height = command['size']
        bounds = (x, y, x+width, y+height)
        if x <= left and y <= top and x+width >= right and y+height >= bottom:
            continue  # Owner itself, coincident boundary, or containing region.
        competitors.append(bounds)

    def clear(box):
        return not any(box[0] < r and box[2] > l and box[1] < b and box[3] > t
                       for l,t,r,b in competitors)
    return clear


def _pointer_clear(start, end, segments):
    length = math.dist(start,end)
    if length < 4:
        return False
    # Keep two units of clearance along the shaft, except the final three
    # units approaching its owner. Only the exact endpoint may meet scene ink.
    trimmed = [end[k]+(start[k]-end[k])*3/length for k in (0,1)]
    for a,b in segments:
        if (max(start[0],end[0])+2 < min(a[0],b[0]) or
            max(a[0],b[0])+2 < min(start[0],end[0]) or
            max(start[1],end[1])+2 < min(a[1],b[1]) or
            max(a[1],b[1])+2 < min(start[1],end[1])):
            continue
        if (_segment_distance(start,end,a,b) < 1e-8 and
                _segment_distance(end,end,a,b) >= 1e-8):
            return False
        if _segment_distance(start,trimmed,a,b) < 2:
            return False
    return True


def contour_attachment(owner, geometry):
    """Attach to a native contour, never an empty corner of its bounding box.

    Project toward real segments from the text-box centre. Rank candidates by
    pointer length and try at most 32 distinct endpoints. The complete scene
    and joint label solver enforce the same clearance as rectangular pointers.
    A label inside a closed contour needs no pointer; collision checks still
    reject any stroke crossing its padded box.
    """
    paths = [path for command in owner for path in _primitive(command)]
    owner_segments = [(a,b) for path in paths for a,b in zip(path,path[1:]) if a!=b]
    if not owner_segments:
        raise ValueError('label owner needs a nonempty native contour')
    points = [p for path in paths for p in path]
    clear_region = _region_clearance((min(p[0] for p in points), min(p[1] for p in points),
                                     max(p[0] for p in points), max(p[1] for p in points)), geometry)
    segments = [(a,b) for command in geometry for path in _primitive(command)
                for a,b in zip(path,path[1:])]

    def inside(point, path):
        x,y=point;result=False
        for a,b in zip(path,path[1:]):
            if (a[1]>y)!=(b[1]>y):
                crossing=a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
                if x<crossing:result=not result
        return result

    def attach(box):
        if not clear_region(box):
            return None
        x0,y0,x1,y1=box
        corners=((x0,y0),(x1,y0),(x1,y1),(x0,y1))
        if any(math.dist(path[0],path[-1])<1e-8 and
               all(inside(p,path) for p in corners) for path in paths):
            return []
        cx,cy=(x0+x1)/2,(y0+y1)/2
        choices=[];seen=set()
        for a,b in owner_segments:
            dx,dy=b[0]-a[0],b[1]-a[1]
            t=min(1,max(0,((cx-a[0])*dx+(cy-a[1])*dy)/(dx*dx+dy*dy)))
            for end in ((a[0]+t*dx,a[1]+t*dy),a,b):
                end=tuple(end)
                if end in seen:continue
                seen.add(end)
                start=(min(x1,max(x0,end[0])),min(y1,max(y0,end[1])))
                choices.append((math.dist(start,end),start,end))
        for _,start,end in sorted(choices,key=lambda item:item[0])[:32]:
            if _pointer_clear(start,end,segments):
                return [dict(op='line',**{'from':list(start),'to':list(end)})]
        return None
    return attach


def region_attachment(bounds, geometry):
    """Return a candidate validator/decorator for one immutable rectangle.

    box is the padded text box. A label fully within its region needs no
    pointer (ordinary ink collision checks still apply). Every external label
    gets a straight, unheaded pointer to the facing region edge. Prefer its
    midpoint; try bounded interior anchors when a divider blocks that point.
    A pointer may meet that edge but cannot run across other scene ink.
    """
    left, top, right, bottom = bounds
    clear_region = _region_clearance(bounds, geometry)
    cx, cy = (left+right)/2, (top+bottom)/2
    segments = [(a,b) for command in geometry for path in _primitive(command)
                for a,b in zip(path,path[1:])]

    def attach(box):
        if not clear_region(box):
            return None
        x0,y0,x1,y1 = box
        if left <= x0 and x1 <= right and top <= y0 and y1 <= bottom:
            return []
        clamp = lambda value,a,b: min(max(value,a),b)
        if not (y1 <= top or y0 >= bottom or x1 <= left or x0 >= right):
            return None  # A label straddling the boundary has unclear ownership.
        for fraction in (.5, .25, .75, .125, .875):
            ex, ey = left+(right-left)*fraction, top+(bottom-top)*fraction
            if y1 <= top:
                start, end = [clamp(ex,x0,x1),y1], [ex,top]
                gap = top-y1
            elif y0 >= bottom:
                start, end = [clamp(ex,x0,x1),y0], [ex,bottom]
                gap = y0-bottom
            elif x1 <= left:
                start, end = [x1,clamp(ey,y0,y1)], [left,ey]
                gap = left-x1
            else:
                start, end = [x0,clamp(ey,y0,y1)], [right,ey]
                gap = x0-right
            if gap < 4:
                return None
            if _pointer_clear(start,end,segments):
                return [dict(op='line', **{'from':start,'to':end})]
        return None
    return attach
