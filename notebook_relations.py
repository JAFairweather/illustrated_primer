"""Lower ID-based schematic connections into the existing bounded ink grammar.

No topic names, layout repair, or device calls. Entities keep their coordinates;
the renderer owns contour attachment and routing against the final scene.
"""
from notebook_lesson import _fields, _primitive, _text
from notebook_anchored_labels import _identity
from notebook_storyboard import _dense
from notebook_pen_budget import NativePenBudgetError


def _plan_routes(pending, boxes, ports, route):
    """Try the established order first, then bounded alternative allocations.

    Planning order is not reveal order. Earlier locally valid paths can leave
    no route for a later relation. Reconsider only those route choices, never
    object coordinates, endpoint identities, labels or stage ordering. Every
    candidate still passes the existing shaft/head/obstacle clearance gates.
    """
    from notebook_procedural import RoutePlacementError
    indices=tuple(range(len(pending)))
    orders=[]
    for direction in (indices, indices[::-1]):
        for offset in range(len(direction)):
            order=direction[offset:]+direction[:offset]
            if order not in orders:
                orders.append(order)
    calls=0; first_error=None
    for order in orders:
        selected={}; previous=[]
        try:
            for index in order:
                if calls >= 48:
                    raise first_error
                _,_,_,source,target=pending[index]
                calls+=1
                commands,points=route(source,target,boxes,ports,previous)
                selected[index]=(commands,points)
                previous.append(points)
            return selected
        except RoutePlacementError as error:
            if first_error is None:
                first_error=error
            if calls >= 48:
                break
    if first_error is not None:
        raise first_error
    return {}  # No connections; ordinary drawing interpretation is unchanged.


def resolve_connections(steps):
    active = False
    for step in steps:
        _fields(step, {'caption', 'draw'})
        if not isinstance(step['draw'], list) or not 1 <= len(step['draw']) <= 32:
            raise ValueError('use 1..32 primitives per step')
        active |= any(isinstance(c, dict) and c.get('op') == 'connect' for c in step['draw'])
    if not active:
        return steps, []  # Preserve established plans and hashes.

    from notebook_procedural import _route
    boxes, ports, identities, available = {}, {}, set(), set()
    pending, total_points = [], 0
    for si, step in enumerate(steps):
        _text(step['caption'], 280)
        paths = []; label_strokes = 0; stage_complete = True
        for ci, original in enumerate(step['draw']):
            if not isinstance(original, dict):
                raise ValueError('drawing commands must be objects')
            command = dict(original)
            identity = _identity(command.pop('id')) if 'id' in command else None
            if identity is not None:
                if identity in identities or command.get('op') == 'label':
                    raise ValueError('drawing IDs must be unique and belong to non-label primitives')
                identities.add(identity)
            if command.get('op') == 'connect':
                _fields(command, {'op', 'from', 'to'})
                source, target = _identity(command['from']), _identity(command['to'])
                if source == target or source not in available or target not in available:
                    raise ValueError('connection needs distinct previously drawn circle or rect IDs')
                pending.append((si, ci, identity, source, target))
                if len(pending) > 12:
                    raise ValueError('use at most twelve schematic connections per lesson')
                stage_complete = False
                continue
            if command.get('op') == 'label' and 'target' in command:
                _fields(command, {'op', 'target', 'text'})
                _identity(command['target']); _text(command['text'], 24)
                stage_complete = False
                continue  # Existing resolver checks order and places after routing.
            expanded = _primitive(command)
            paths.extend(expanded)
            if command['op']=='label':
                label_strokes+=len(expanded)
            points = [point for path in expanded for point in path]
            if any(not (0 <= x <= 600 and 0 <= y <= 360) for x, y in points):
                raise ValueError('geometry outside drawing region')
            xs, ys = zip(*points)
            box = min(xs), min(ys), max(xs), max(ys)
            key = identity if identity is not None else (si, ci)
            boxes[key] = box  # Includes later geometry and entire fixed-label boxes.
            if identity is not None and command['op'] in ('circle', 'rect'):
                left, top, right, bottom = box
                x, y = (left + right) / 2, (top + bottom) / 2
                ports[identity] = dict(left=(left, y), right=(right, y),
                                       top=(x, top), bottom=(x, bottom))
                available.add(identity)
        if paths:
            dense = _dense(paths,stage=si+1,label_strokes=label_strokes,stage_complete=stage_complete)
            count = sum(map(len, dense))
            if count * .009 + len(dense) * .070 > 30:
                raise NativePenBudgetError('stage exceeds 30 seconds estimated pen time',details=dict(
                    resource='estimated_seconds',observed=count*.009+len(dense)*.070,limit=30,
                    exact=stage_complete,scope='stage',stage=si+1,strokes=len(dense),points=count,
                    stroke_breakdown=dict(labels=label_strokes,geometry=len(dense)-label_strokes,
                                          complete=stage_complete)))
            total_points += count
            if total_points > 12000:
                raise NativePenBudgetError('lesson geometry exceeds whole-plan point budget',details=dict(
                    resource='points',observed=total_points,limit=12000,exact=False,scope='lesson',stage=si+1))

    planned = _plan_routes(pending, boxes, ports, _route)
    replacements, provenance = {}, []
    for index, (si, ci, identity, source, target) in enumerate(pending):
        commands, points = planned[index]
        if identity is not None:
            commands[0]['id'] = identity  # Existing anchored labels can name this edge.
        replacements[si, ci] = commands
        provenance.append(dict(step=si + 1, command=ci + 1, source=source, target=target,
                               start=list(points[0]), end=list(points[-1]),
                               semantics='schematic-directed-relation'))
    result = []
    for si, step in enumerate(steps):
        commands = [c for ci, original in enumerate(step['draw'])
                    for c in replacements.get((si, ci), [dict(original)])]
        if len(commands) > 32:
            raise ValueError('expanded connections exceed 32 primitives per step')
        result.append(dict(caption=step['caption'], draw=commands))
    return result, provenance
