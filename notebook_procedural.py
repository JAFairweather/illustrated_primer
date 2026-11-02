"""Semantic board descriptions -> deterministic geometry -> existing native ink.

Offline prototype. The model supplies objects, relationships and reveal order,
not pixel coordinates, font widths or shell commands. No device/network I/O.
This is deliberate procedural layout, not repair of a rejected authored plan.
"""
import math
import re

from notebook_lesson import (compile_lesson, _fields, _number, _text,
                             _primitive, _segment_hits_box)
from notebook_plotter_font import label_paths
from notebook_label_candidates import edge_slides


class LabelPlacementError(ValueError):
    """A complete bounded composition could not place all original labels. identity names the label that had no
    clear location at all, when one did."""

    def __init__(self, message, identity=None):
        super().__init__(message)
        self.identity = identity


class RoutePlacementError(ValueError):
    """Valid endpoints could not be connected in this bounded composition."""


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,23}', value):
        raise ValueError('use a short lowercase object ID')
    return value


def _line(a, b):
    return {'op': 'line', 'from': list(a), 'to': list(b)}


def _poly(points):
    return {'op': 'polyline', 'points': [list(p) for p in points]}


def _bezier(a, b, c, d, samples=24):
    """Bounded cubic sampling, owned by the renderer rather than the model."""
    return [tuple((1-t)**3*a[k]+3*(1-t)**2*t*b[k]+3*(1-t)*t*t*c[k]+t**3*d[k]
                  for k in (0,1)) for t in (i/samples for i in range(samples+1))]


def _contour(x, y, segments):
    points=[]
    for a,b,c,d in segments:
        part=_bezier(a,b,c,d,8)
        points.extend(part if not points else part[1:])
    return _poly([(x+px,y+py) for px,py in points])


def _bounds(commands):
    points = [p for c in commands for path in _primitive(c) for p in path]
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def _hits(commands, box):
    return any(_segment_hits_box(a, b, box) for c in commands
               for path in _primitive(c) for a, b in zip(path, path[1:]))


def _label(text, center, baseline, size=18):
    """Center using actual expanded glyph extents, including descenders."""
    text = _text(text, 24)
    paths, _ = label_paths(text, size)
    xs = [x for path in paths for x, _ in path]
    return {'op':'label', 'at':[center-(min(xs)+max(xs))/2,baseline],
            'text':text, 'size':size}


def _label_bounds(command):
    # Candidate positions may be outside the page. Measure before validating
    # the position so one rejected candidate cannot abort the finite search.
    paths, _ = label_paths(command['text'], command['size'])
    x,y = command['at']
    points = [(x+px,y-command['size']+py) for path in paths for px,py in path]
    xs,ys = zip(*points)
    return min(xs),min(ys),max(xs),max(ys)


def _label_lines(text):
    """Prefer balanced word breaks for wide labels; never shrink or truncate."""
    text=_text(text,24)
    splits=[]
    for match in re.finditer(r' +',text):
        lines=(text[:match.start()],text[match.end():])
        widths=[_label_bounds(_label(line,0,0))[2]-_label_bounds(_label(line,0,0))[0]
                for line in lines]
        splits.append((max(widths),abs(widths[0]-widths[1]),match.start(),lines))
    wrapped=[item[-1] for item in sorted(splits)]
    box=_label_bounds(_label(text,0,0))
    # A long one-line label placed beside a diagonal route drifts far from
    # its owner. Prefer a compact block, keeping short names on one line.
    return wrapped+[(text,)] if wrapped and box[2]-box[0]>140 else [(text,)]+wrapped


def _label_group(lines, center, baseline):
    # Baseline belongs to the bottom line, so above-object placement retains
    # the same bottom clearance regardless of whether the text wraps.
    commands=[];next_top=None
    for line in reversed(lines):
        command=_label(line,center,baseline)
        if next_top is not None:
            command['at'][1]+=next_top-6-_label_bounds(command)[3]
        next_top=_label_bounds(command)[1]
        commands.insert(0,command)
    return commands


def _group_label_bounds(commands):
    boxes=[_label_bounds(command) for command in commands]
    return min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)


def _object_label_candidates(box, center):
    """Keep established positions, then clear the entire wrapped label box.

    Wrapped labels use their full measured extents. These are finite nearby
    candidates, not permission to move shapes or disregard connector ink.
    """
    _, top, _, bottom = box
    x, _ = center
    def candidates(local_box):
        positions = [(x,top-13),(x,bottom+30),(x,top-30),(x,bottom+48)]
        for gap in (14,28):
            positions.extend([(x,top-gap-local_box[3]),
                              (x,bottom+gap-local_box[1])])
        positions.extend(edge_slides(box,local_box,(14,28)))
        return positions
    return candidates


def _route_label_candidates(points, local_box, *, gaps=(12,24)):
    """Finite nearby positions measured normal to the connector, not the page.

    Arc-length samples avoid dependence on cubic tessellation. Offsets include
    the full block's support along the normal, including wrapped line height.
    """
    segments=[(a,b,math.dist(a,b)) for a,b in zip(points,points[1:]) if a!=b]
    length=sum(segment[2] for segment in segments)
    half_width=(local_box[2]-local_box[0])/2
    half_height=(local_box[3]-local_box[1])/2
    center_y=(local_box[1]+local_box[3])/2
    candidates=[]
    for fraction in (.5,.35,.65,.2,.8):
        remaining=length*fraction
        for a,b,distance in segments:
            if remaining<=distance:
                t=remaining/distance
                x,y=(a[k]+t*(b[k]-a[k]) for k in (0,1))
                nx,ny=-(b[1]-a[1])/distance,(b[0]-a[0])/distance
                support=abs(nx)*half_width+abs(ny)*half_height
                for gap in gaps:
                    for side in (1,-1):
                        offset=side*(support+gap)
                        candidates.append((x+nx*offset,y+ny*offset-center_y))
                break
            remaining-=distance
    return candidates


def _place_labels(items, geometry, reserved=(), *, attachments=None,
                  fallback_attachments=None):
    """Place near the owner's shape/path against the ENTIRE final picture.

    Bounded deterministic candidates; no model round trip. Never changes any
    object's geometry or relationship. If no safe location exists, fail before
    returning ink. Returns provenance so fixtures can inspect placement.
    """
    options={}; fallback_options={}
    attachments = attachments or {}
    fallback_attachments = fallback_attachments or {}
    for identity, text, candidates in items:
        options[identity]=[]
        fallback_options[identity]=[]
        seen=set()
        for lines in _label_lines(text):
            local_box=_group_label_bounds(_label_group(lines,0,0))
            positions=candidates(local_box) if callable(candidates) else candidates
            fallback = getattr(candidates, 'fallback', None)
            extra = fallback(local_box) if fallback else ()
            for is_fallback, (center, baseline) in (
                    [(False, p) for p in positions]+[(True, p) for p in extra]):
                commands = _label_group(lines, center, baseline)
                box = _group_label_bounds(commands)
                # Remote callouts need extra breathing room
                # so adjacent wrapped labels do not read as one sentence.
                padding = 12 if is_fallback else 6
                box = (box[0]-padding, box[1]-padding,
                       box[2]+padding, box[3]+padding)
                if not (4 <= box[0] < box[2] <= 596 and 4 <= box[1] < box[3] <= 356):
                    continue
                if _hits(geometry, box):
                    continue
                if any(box[0]<other[2] and box[2]>other[0]
                       and box[1]<other[3] and box[3]>other[1] for other in reserved):
                    continue
                attach = (fallback_attachments.get(identity) if is_fallback else None)
                attach = attach or attachments.get(identity)
                leaders = attach(box) if attach else []
                if leaders is None or any(_hits(leaders, other) for other in reserved):
                    continue
                # Different placement routes can produce the exact same
                # annotation. Explore it once, preserving the first preference
                # and every distinct pointer; no coordinate rounding is used.
                key=(box,lines,repr(leaders))
                if key in seen:
                    continue
                seen.add(key)
                target = fallback_options if is_fallback else options
                target[identity].append((leaders+commands,box,lines,leaders))
        if not options[identity] and not fallback_options[identity]:
            raise LabelPlacementError(f'no clear label location for {identity}; simplify the scene', identity)
    def conflicts(option, other):
        _,box,_,leaders=option
        if (box[0]<other[1][2] and box[2]>other[1][0]
                and box[1]<other[1][3] and box[3]>other[1][1]):
            return True
        # Keep the complete annotation: pointers cannot cross other text or
        # other pointers, even when the text boxes themselves are disjoint.
        return (_hits(leaders, other[1]) or _hits(other[3], box)
                or any(_segment_distance(a,b,c,d)<2
                       for command in leaders for path in _primitive(command)
                       for a,b in zip(path,path[1:])
                       for old in other[3] for old_path in _primitive(old)
                       for c,d in zip(old_path,old_path[1:])))

    from notebook_label_solver import select_labels, LabelSearchBudgetExceeded
    try:
        selected = select_labels(options, conflicts, fallback_options=fallback_options)
    except LabelSearchBudgetExceeded as exc:
        raise LabelPlacementError(str(exc)) from exc
    if selected is None:
        raise LabelPlacementError('no joint clear label placement; simplify the scene')
    result,provenance={},[]
    for identity,_,_ in items:
        commands,box,lines,leaders=selected[identity]
        result[identity]=commands
        provenance.append({'id':identity,'label_box':list(box),
                           'at':commands[-1]['at'][:],'lines':list(lines),'size':18})
        if identity in attachments or leaders:
            provenance[-1]['leaders'] = leaders
    return result, provenance


def _object(shape, x, y):
    if shape == 'circle':
        return [{'op': 'circle', 'center': [x,y], 'radius': 22}]
    if shape == 'box':
        return [{'op': 'rect', 'origin': [x-35,y-22], 'size': [70,44]}]
    if shape == 'person':
        return [{'op': 'circle', 'center': [x,y-18], 'radius': 10},
                _line((x,y-8),(x,y+15)), _line((x-17,y),(x+17,y)),
                _poly([(x-14,y+32),(x,y+15),(x+14,y+32)])]
    if shape == 'sun':
        commands = [{'op': 'circle', 'center': [x,y], 'radius': 17}]
        for i in range(8):
            a = math.tau*i/8
            commands.append(_line((x+23*math.cos(a),y+23*math.sin(a)),
                                  (x+31*math.cos(a),y+31*math.sin(a))))
        return commands
    if shape == 'cloud':
        return [_contour(x,y,[
            ((-40,0),(-40,-12),(-31,-18),(-22,-15)),
            ((-22,-15),(-22,-25),(-12,-30),(0,-30)),
            ((0,-30),(12,-30),(20,-22),(20,-14)),
            ((20,-14),(31,-20),(40,-10),(40,0)),
            ((40,0),(40,11),(28,16),(18,12)),
            ((18,12),(12,15),(6,14),(0,14)),
            ((0,14),(-12,14),(-19,17),(-25,12)),
            ((-25,12),(-34,15),(-40,10),(-40,0))])]
    if shape == 'water':
        # A surface pool, not a container: a soft shore and two water ripples.
        return [_contour(x,y,[
            ((-44,0),(-44,-8),(-22,-12),(0,-12)),
            ((0,-12),(22,-12),(44,-8),(44,0)),
            ((44,0),(44,12),(22,20),(0,20)),
            ((0,20),(-22,20),(-44,12),(-44,0))]),
            _poly([(x-28+i*2,y+2*math.sin(i*math.pi/7)) for i in range(29)]),
            _poly([(x-17+i*2,y+9+1.5*math.sin(i*math.pi/5)) for i in range(18)])]
    raise ValueError('supported shapes: circle, box, person, sun, cloud, water')


def _object_ports(shape, x, y):
    """Explicit contour anchors; a bounding-box edge is not always an object."""
    offsets = {
        'circle': [(-22,0),(22,0),(0,-22),(0,22)],
        'box': [(-35,0),(35,0),(0,-22),(0,22)],
        'person': [(-17,0),(17,0),(0,-28),(14,32)],
        'sun': [(-31,0),(31,0),(0,-31),(0,31)],
        'cloud': [(-40,0),(40,0),(0,-30),(0,14)],
        'water': [(-44,0),(44,0),(0,-12),(0,20)],
    }[shape]
    return {name:(x+dx,y+dy) for name,(dx,dy) in
            zip(('left','right','top','bottom'),offsets)}


def _point_segment_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    squared=dx*dx+dy*dy
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/squared)) if squared else 0
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)


def _segment_distance(a,b,c,d):
    """Exact segment clearance, including crossings between sampled vertices."""
    def cross(p,q,r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0):
        return 0
    return min(_point_segment_distance(a,c,d),_point_segment_distance(b,c,d),
               _point_segment_distance(c,a,b),_point_segment_distance(d,a,b))


def _trim_path(points, distance=14):
    """Reserve only interior ink; shared object ports can have short approaches."""
    result=list(points)
    for _ in range(2):
        remaining=distance
        while len(result)>1:
            a,b=result[:2];length=math.dist(a,b)
            if length>remaining:
                result[0]=tuple(a[k]+(b[k]-a[k])*remaining/length for k in (0,1))
                break
            remaining-=length;result.pop(0)
        result.reverse()
    return result


def _route_commands(points):
    # Fixed-size head follows the final tangent, not a tiny sampled last segment.
    a,b=points[-2:];length=math.dist(a,b)
    back=[b[k]+(a[k]-b[k])*30/length for k in (0,1)]
    # `back` is an invisible tangent construction point, not emitted ink. It
    # may lie beyond the canvas even when the actual ten-unit head fits.
    from notebook_shapes import arrow
    head=arrow(back,b)[1:]
    commands=[_poly(points)]+[_poly(path) for path in head]
    for command in commands:
        _primitive(command)  # Every emitted shaft/head point still must fit.
    return commands


def _route_conflicts(points, commands, previous):
    interior=_trim_path(points)
    new_paths=[interior]+[path for c in commands[1:] for path in _primitive(c)]
    old_paths=[]
    for path in previous:
        old_paths.append(_trim_path(path))
        old_paths.extend(p for c in _route_commands(path)[1:] for p in _primitive(c))
    for path in new_paths:
        for a,b in zip(path,path[1:]):
            for old in old_paths:
                for c,d in zip(old,old[1:]):
                    # Cheap broad phase before exact segment clearance.
                    if (max(a[0],b[0])+6<min(c[0],d[0]) or max(c[0],d[0])+6<min(a[0],b[0])
                            or max(a[1],b[1])+6<min(c[1],d[1]) or max(c[1],d[1])+6<min(a[1],b[1])):
                        continue
                    if _segment_distance(a,b,c,d)<6:
                        return True
    return False


def _route_detours(source, target, ports):
    """Bounded outer-lane alternatives, only considered after ordinary routes.

    Endpoint stubs follow the same contour normals as the cubic candidates.
    Unlike a single cubic or same-side lane, these paths can turn around an
    occupied side of an object without changing attachment or arrow direction.
    This is geometry-only: no relationship names or lesson-specific layouts.
    """
    normals = {'left':(-1,0), 'right':(1,0), 'top':(0,-1), 'bottom':(0,1)}
    candidates = []
    for start, na in normals.items():
        for end, nb in normals.items():
            pa, pb = ports[source][start], ports[target][end]
            for reach in (24, 40):
                sa = tuple(pa[k]+na[k]*reach for k in (0,1))
                sb = tuple(pb[k]+nb[k]*reach for k in (0,1))
                for lane in (25, 85, 145, 215, 275, 335):
                    candidates.append([pa, sa, (sa[0],lane), (sb[0],lane), sb, pb])
                for lane in (25, 100, 180, 260, 340, 420, 500, 575):
                    candidates.append([pa, sa, (lane,sa[1]), (lane,sb[1]), sb, pb])
    # 4 x 4 ports x 2 reaches x 14 lanes = 448 candidates, independent of
    # model output size. The caller applies the ordinary collision/budget gates.
    for points in sorted(candidates, key=lambda ps: sum(math.dist(a,b) for a,b in zip(ps,ps[1:]))):
        points = [p for i,p in enumerate(points) if i == 0 or p != points[i-1]]
        # Some lane/port combinations double back along a stub or cross their
        # own shaft. Reject those rather than drawing a loop or retracing ink.
        if any((b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1]) < 0
               for a,b,c in zip(points,points[1:],points[2:])):
            continue
        segments = list(zip(points, points[1:]))
        if any(_segment_distance(a,b,c,d) < 6 for i,(a,b) in enumerate(segments)
               for c,d in segments[i+2:]):
            continue
        yield points


def _route(source, target, boxes, ports, previous=(), *, allow_detours=True):
    """Finite curved candidates then orthogonal lanes for process relationships.

    These arrows mean causal connection, never a physical trajectory. Neither
    control points nor routing style are model inputs. Every candidate is
    checked against the final objects and already allocated connector ink.
    """
    a,b = boxes[source],boxes[target]
    ax,ay = (a[0]+a[2])/2,(a[1]+a[3])/2
    bx,by = (b[0]+b[2])/2,(b[1]+b[3])/2
    candidates = []
    normals={'left':(-1,0),'right':(1,0),'top':(0,-1),'bottom':(0,1)}
    for start,na in normals.items():
        for end,nb in normals.items():
            pa,pb=ports[source][start],ports[target][end]
            for handle in (55,110):
                ca=tuple(pa[k]+na[k]*handle for k in (0,1))
                cb=tuple(pb[k]+nb[k]*handle for k in (0,1))
                candidates.append(_bezier(pa,ca,cb,pb))
    if abs(ay-by) < 20:
        side = 'right' if bx > ax else 'left'
        pa,pb=ports[source][side],ports[target]['left' if side=='right' else 'right']
        if abs(pa[1]-pb[1]) < 1e-9:
            candidates.append([pa,pb])
    if abs(ax-bx) < 20:
        side = 'bottom' if by > ay else 'top'
        pa,pb=ports[source][side],ports[target]['top' if side=='bottom' else 'bottom']
        if abs(pa[0]-pb[0]) < 1e-9:
            candidates.append([pa,pb])
    for lane in (180,25,335):
        pa,pb = ports[source]['bottom' if lane > ay else 'top'],ports[target]['bottom' if lane > by else 'top']
        candidates.append([pa,(pa[0],lane),(pb[0],lane),pb])
    for lane in (200,400,25,575):
        pa,pb = ports[source]['right' if lane > ax else 'left'],ports[target]['right' if lane > bx else 'left']
        candidates.append([pa,(lane,pa[1]),(lane,pb[1]),pb])
    candidates.sort(key=lambda points:sum(math.dist(a,b) for a,b in zip(points,points[1:])))
    from itertools import chain
    detours = _route_detours(source, target, ports) if allow_detours else ()
    for points in chain(candidates, detours):
        points = [p for i,p in enumerate(points) if i == 0 or p != points[i-1]]
        if any(math.dist(a,b) < 2 for a,b in zip(points,points[1:])):
            continue
        if any(not (12<=x<=588 and 12<=y<=348) for x,y in points):
            continue
        commands = _route_commands(points)
        obstacles = [box for identity,box in boxes.items() if identity not in (source,target)]
        # Do not leave/re-enter the source or pass through the target before
        # arrival. The short contour approach is exempt, not the whole object.
        interior=_trim_path(points)
        own_collision=any(_hits([_poly(interior)],boxes[i]) for i in (source,target)) if len(interior)>1 else True
        # Include BOTH arrowheads in clearance. Trim only shafts near ports.
        crosses=_route_conflicts(points,commands,previous)
        if (not own_collision and not crosses
                and not any(_hits(commands,(l-5,t-5,r+5,b+5)) for l,t,r,b in obstacles)):
            return commands, points
    raise RoutePlacementError('no clear connector route; simplify the scene')


def _network_order(objects, links):
    """Semantic direction, not object-list order or model-supplied grid slots."""
    ids=[_id(obj['id']) for obj in objects]
    if len(set(ids))!=len(ids):
        raise ValueError('duplicate object ID')
    children={i:[] for i in ids}
    incoming={i:0 for i in ids}
    for link in links:
        _fields(link, {'id','from','to','label'})
        source,target=_id(link['from']),_id(link['to'])
        if source not in children or target not in children or source==target:
            raise ValueError('connection needs distinct existing endpoints')
        children[source].append(target)
        incoming[target]+=1
    queue=sorted(i for i in ids if incoming[i]==0)
    order=[]
    while len(order)<len(ids):
        if not queue:
            queue=[min(set(ids)-set(order))]
        identity=queue.pop(0)
        if identity in order:continue
        order.append(identity)
        queue.extend(sorted(set(children[identity])-set(order)))
    return order


def _network_preflight(spec):
    """Validate the complete reveal contract before allocating any geometry.

    Missing edges must not masquerade as spatial failures and consume the
    bounded layout search. This only validates; it never completes a reveal,
    edits a caption, changes graph topology, or mutates the caller's input.
    """
    _fields(spec, {'kind','objects','links','steps','takeaway'}, {'equation'})
    objects,links = spec['objects'],spec['links']
    if not isinstance(objects,list) or not 1 <= len(objects) <= 6:
        raise ValueError('use 1..6 objects')
    if not isinstance(links,list) or len(links) > 8:
        raise ValueError('use at most eight connections')
    for obj in objects:
        _fields(obj, {'id','shape','label'})
        _text(obj['label'],24)
    order=_network_order(objects,links)
    declared=set(order);dependencies={}
    for link in links:
        identity=_id(link['id'])
        if identity in declared:
            raise ValueError('connection requires a unique ID and distinct existing objects')
        declared.add(identity)
        _text(link['label'],24)
        dependencies[identity]={link['from'],link['to']}
    _text(spec['takeaway'],500)
    if not isinstance(spec['steps'],list) or not 3 <= len(spec['steps']) <= 6:
        raise ValueError('use 3..6 reveal steps')
    seen=set()
    for step in spec['steps']:
        _fields(step, {'caption','add'})
        _text(step['caption'],280)
        added=step['add']
        if not isinstance(added,list) or not added or len(added)>14:
            raise ValueError('step needs bounded object/connection IDs')
        ids=[_id(i) for i in added]
        if len(set(ids))!=len(ids) or any(i not in declared or i in seen for i in ids):
            raise ValueError('each object or connection must be revealed exactly once')
        seen.update(ids)
        if any(not dependencies.get(i,set()) <= seen for i in ids):
            raise ValueError('reveal endpoints before or with their connector')
    if seen != declared:
        raise ValueError('every declared object/connection must appear in a step')
    return order


def _network(spec, row_gap=170, slots=None, *, allow_detours=False):
    order=_network_preflight(spec)
    objects,links=spec['objects'],spec['links']
    layouts={1:[(1,0)],2:[(0,0),(2,0)],3:[(0,0),(1,1),(2,0)],
             4:[(0,0),(1,0),(2,0),(2,1)],
             5:[(0,0),(1,0),(2,0),(2,1),(1,1)],
             6:[(0,0),(1,0),(2,0),(2,1),(1,1),(0,1)]}
    positions=dict(zip(order,layouts[len(objects)] if slots is None else slots))
    pieces,boxes,ports,labels = {},{},{},[]
    for obj in sorted(objects,key=lambda obj:order.index(obj['id'])):
        identity = _id(obj['id'])
        slot=positions[identity]
        x,y = 100+200*slot[0],85+row_gap*slot[1]
        pieces[identity] = _object(obj['shape'],x,y)
        boxes[identity] = _bounds(pieces[identity])
        ports[identity] = _object_ports(obj['shape'],x,y)
        labels.append((identity,obj['label'],_object_label_candidates(boxes[identity],(x,y))))
    routes=[]
    for link in links:
        _fields(link, {'id','from','to','label'})
        identity = _id(link['id'])
        source,target = _id(link['from']),_id(link['to'])
        if identity in pieces or source not in boxes or target not in boxes or source == target:
            raise ValueError('connection requires a unique ID and distinct existing objects')
        commands,points = _route(source,target,boxes,ports,routes,allow_detours=allow_detours)
        routes.append(points)
        pieces[identity] = commands
        labels.append((identity,link['label'],lambda box,path=points:_route_label_candidates(path,box)))
    geometry=[c for commands in pieces.values() for c in commands]
    placed,provenance=_place_labels(labels,geometry)
    for identity,commands in placed.items():
        pieces[identity].extend(commands)
    stages=[{'caption':step['caption'],'draw':[c for i in step['add'] for c in pieces[i]]}
            for step in spec['steps']]
    return stages,[{'objects':{i:{'slot':list(positions[i]),'ports':ports[i]} for i in order},
                    'row_gap':row_gap,'routes':routes}]+provenance


def _layered_network_slots(objects, links):
    """One bounded DAG arrangement derived from edges, never topic or wording.

    Called only after normal network validation/layout has run. Cycles keep
    the existing loop layouts. Longest-path ranks keep every directed edge
    moving forward; siblings share a rank and are spaced within the canvas.
    """
    order=_network_order(objects,links)
    parents={i:set() for i in order}
    children={i:set() for i in order}
    for link in links:
        parents[link['to']].add(link['from'])
        children[link['from']].add(link['to'])
    incoming={i:len(parents[i]) for i in order}
    queue=sorted(i for i in order if not incoming[i])
    ranks={i:0 for i in order}
    visited=[]
    while queue:
        identity=queue.pop(0)
        visited.append(identity)
        for child in sorted(children[identity]):
            ranks[child]=max(ranks[child],ranks[identity]+1)
            incoming[child]-=1
            if not incoming[child]:
                queue.append(child)
        queue.sort()
    if len(visited)!=len(order):
        return None
    last=max(ranks.values())
    # Do not pack outlines more tightly than the largest supported object.
    # Existing layouts remain available for a long chain or very wide rank.
    if last>4 or any(sum(r==rank for r in ranks.values())>3 for rank in range(last+1)):
        return None
    positions={}
    for rank in range(last+1):
        members=sorted(i for i in order if ranks[i]==rank)
        # Parent barycentres reduce crossings without changing relationships.
        members.sort(key=lambda i:(sum(positions[p][1] for p in sorted(parents[i]))/len(parents[i])
                                    if parents[i] else .5,i))
        for index,identity in enumerate(members):
            positions[identity]=(2*rank/last if last else 1,
                                 index/(len(members)-1) if len(members)>1 else .5)
    return [positions[i] for i in order]


def _network_attempts(spec):
    """At most ten compositions; keep every established successful layout."""
    arrangements=[None]
    if isinstance(spec.get('objects'),list) and len(spec['objects'])==4:
        arrangements.append([(0,0),(1,1),(2,0),(0,1)])
    if isinstance(spec.get('objects'),list) and len(spec['objects'])==5:
        arrangements.append([(0,0),(.75,0),(2,0),(2,1),(0,1)])
    for slots in arrangements:
        for gap in (170,140):
            yield slots,gap
    # Laziness matters: malformed input must fail in _network, not be repaired
    # or inspected by a fallback before the normal validator has seen it.
    slots=_layered_network_slots(spec['objects'],spec['links'])
    if slots is not None:
        for gap in (170,140):
            yield slots,gap
        # Orientation is a layout choice, not answer semantics. A joined DAG
        # can need more horizontal room for labels than its outgoing edge
        # allows. Keep ranks, sibling order and every endpoint, but let ranks
        # advance down the page instead. Only unsuccessful layouts reach here.
        vertical=[(2*y,x/2) for x,y in slots]
        for gap in (170,140):
            yield vertical,gap
    # A compact row-major grid reserves the right-hand column for long
    # annotations and returning edges. Unlike ranked layouts it also applies
    # to cycles. Positions depend only on validated object count/order, never
    # subject matter or words. Existing roomy arrangements remain preferred.
    count=len(spec['objects'])
    if count>=3:
        rows=(count+1)//2
        compact=[(i%2,(i//2)/(rows-1)) for i in range(count)]
        for gap in (170,140):
            yield compact,gap


def _lever(spec):
    _fields(spec, {'kind','arms','forces','captions','takeaway'}, {'equation'})
    for key in ('arms','forces'):
        if not isinstance(spec[key],list) or len(spec[key]) != 2:
            raise ValueError('lever requires two arm lengths and two force magnitudes')
        for value in spec[key]:
            _number(value,.1,10000)
    captions=spec['captions']
    if not isinstance(captions,list) or len(captions)!=3:
        raise ValueError('lever has setup, forces, and moment-arm captions')
    left,right=spec['arms'];load,effort=spec['forces']
    x0,x1,y=80,520,180
    pivot=x0+(x1-x0)*left/(left+right)
    if min(pivot-x0,x1-pivot)<40:
        raise ValueError('arm ratio too extreme for this bounded diagram')
    scale=80/max(load,effort)
    stages=[{'caption':captions[0],'draw':[
        _line((x0,y),(x1,y)),_poly([(pivot-16,y+30),(pivot,y),(pivot+16,y+30),(pivot-16,y+30)])]},
        {'caption':captions[1],'draw':[
            {'op':'arrow','from':[x0,y-load*scale],'to':[x0,y]},
            {'op':'arrow','from':[x1,y-effort*scale],'to':[x1,y]},
            _label(f'{load:g} N',x0,y-load*scale-15),_label(f'{effort:g} N',x1,y-effort*scale-15)]},
        {'caption':captions[2],'draw':[
            _line((x0,245),(pivot,245)),_line((pivot,245),(x1,245)),
            _line((x0,239),(x0,251)),_line((pivot,239),(pivot,251)),_line((x1,239),(x1,251)),
            _label(f'{left:g} m',(x0+pivot)/2,280),_label(f'{right:g} m',(pivot+x1)/2,280)]}]
    return stages,[{'pivot_x':pivot,'arm_lengths_px':[pivot-x0,x1-pivot],
                    'force_lengths_px':[load*scale,effort*scale],
                    'moments_Nm':[left*load,right*effort]}]


def compile_board(spec):
    """Validate all semantics/layout/native budgets before returning a full plan."""
    if not isinstance(spec,dict):
        raise ValueError('board description must be an object')
    kind=spec.get('kind')
    if kind == 'network':
        # Preserve successful layouts. Only typed spatial failures try another
        # arrangement; malformed input and native-budget failures still hold.
        # A complex outer detour must not steal a later clean composition.
        # Try all <=10 established arrangements before a <=10 detour pass.
        for allow_detours in (False, True):
            for slots,row_gap in _network_attempts(spec):
                try:
                    steps,layout=_network(spec,row_gap,slots,allow_detours=allow_detours)
                    break
                except (LabelPlacementError,RoutePlacementError) as error:
                    last_error=error
            else:
                continue
            break
        else:
            raise last_error
    elif kind == 'lever':
        steps,layout=_lever(spec)
    else:
        raise ValueError('supported procedural boards: network, lever')
    plan=compile_lesson(steps,spec['takeaway'],spec.get('equation'))
    plan['procedural']={'version':1,'kind':kind,'layout':layout}
    return plan
