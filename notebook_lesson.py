"""Non-executing board-step JSON -> additive, bounded native stroke plan.

Every step adds to the same 600 x 360 picture. No arbitrary filenames, URLs,
expressions, styling code or device operations. Validate the whole response
before returning any stage. Native insertion still uses the existing guards.
"""
import hashlib
import json
import math
import re

from notebook_drawing import compile_storyboard
from notebook_plotter_font import label_paths, font_budget_fallback
from notebook_handwriting import handwriting_paths
from notebook_pen_budget import NativePenBudgetError
from notebook_shapes import arrow
from notebook_storyboard import _dense
from notebook_hatching import shade_paths
from notebook_organic import organic


WIDTH, HEIGHT = 600, 360
CAPTION = 400  # characters in a step's caption: a story episode is one or two sentences, some long (James's raven model)
MAX_RESPONSE = 48000
# Diagram labels in the plotter letters or one of the hands; the server sets it from the operator's
# label_hand in .notebook-lessons.json each time it reads that file.
LABEL_HANDS = ('plotter', 'primer', 'reader', 'letter')
label_hand = 'plotter'
STEP =re.compile(r'```board-step[ \t]*\n(.*?)\n```', re.S)
FIELDS = {
    'line': {'from', 'to'}, 'arrow': {'from', 'to'},
    'circle': {'center', 'radius'}, 'rect': {'origin', 'size'},
    'polyline': {'points'}, 'plot': {'points'},
    'brace': {'from', 'to', 'side'}, 'label': {'at', 'text'},
    'shade': {'points'},
    'dashed': {'from', 'to'}, 'dimension': {'from', 'to'},
    'ellipse': {'center', 'radii'}, 'dot': {'center'}, 'trace': {'points'},
}
OPTIONAL = {'label': {'size'}, 'ellipse': {'angle'}}


class LessonLayoutError(ValueError):
    """Rejected layout with bounded geometry for OFFLINE diagnostic previews.

    This remains a compilation failure, never an accepted native lesson. Only
    the offline evaluator consumes diagnostic_plan; no insertion caller does.
    """
    def __init__(self, message, plan, collisions=()):
        super().__init__(message)
        self.diagnostic_plan = plan
        self.collisions = list(collisions)


class _LabelCollision(ValueError):
    def __init__(self, message, collisions):
        super().__init__(message)
        self.collisions = collisions


def _fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError('missing or unknown drawing fields: an object is required')
    missing, unknown = sorted(required-value.keys()), sorted(map(str, value.keys()-required-set(optional)))
    if missing or unknown:
        # Named, so the one repair attempt can say what to fix; unknown keys are the model's own, so kept short.
        raise ValueError('missing or unknown drawing fields: ' + '; '.join(
            ([f"missing {', '.join(missing)}"] if missing else []) +
            ([f"unknown {', '.join(k[:24] for k in unknown[:3])}"] if unknown else [])) +
            f" (allowed: {', '.join(sorted(required|set(optional)))})")


def _number(value, lower, upper):
    if type(value) not in (int, float) or not lower <= value <= upper or not math.isfinite(value):
        raise ValueError('drawing coordinate or size outside finite bounds')
    return value


def _point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('point must be [x,y]')
    return (_number(value[0], 0, WIDTH), _number(value[1], 0, HEIGHT))


def _text(value, limit, *, equation=False):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('missing or excessive lesson text')
    if any((ord(c) < 32 and not (equation and c in '\r\n\t')) or ord(c) == 127 for c in value):
        raise ValueError('lesson text must be one line')
    if equation:
        # Match the equation renderer's ordinary whitespace semantics. A spaced
        # division operator is not a file path; absolute/tilde/drive paths still
        # fail, and this text is only ever parsed as bounded math, never opened.
        value = re.sub(r'\s+', ' ', value).strip()
    path = r'(?:^|\s)(?:/(?!\s)|~/|[A-Za-z]:\\)' if equation else r'(?:^|\s)(?:/|~/|[A-Za-z]:\\)'
    if (equation and value.startswith('/')) or re.search(path, value) or re.search(r'://|www\.|```|\[\[|<[^>]*>|\b(?:eval|exec|__import__)\s*\(', value):
        raise ValueError('paths, URLs, code and control markup are not lesson text')
    if not equation and re.search(r'`|\*\*|__|^\s*#{1,6}\s|\[[^\]]+\]\(|\\(?:frac|sqrt|int|sum|begin)\b', value):
        raise ValueError('lesson captions and labels must be plain text, not raw formatting markup')
    return value.strip()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('non-finite JSON number')


def _primitive(command):
    if (not isinstance(command, dict) or not isinstance(command.get('op'), str)
            or command['op'] not in FIELDS):
        raise ValueError('unknown drawing operation')
    op = command['op']
    _fields(command, FIELDS[op] | {'op'}, OPTIONAL.get(op, ()))
    if op in ('dashed', 'dimension'):
        a, b = _point(command['from']), _point(command['to'])
        length = math.dist(a, b)
        if length < 12:
            raise ValueError(f'{op} needs at least 12 pixels')
        if op == 'dashed':
            # Hidden or projected edges: at most 12 dashes, 3:2 dash to gap, ending on both points.
            n = max(2, min(12, round(length/16)))
            unit = length/(5*n-2)
            at = lambda d: (a[0]+(b[0]-a[0])*d/length, a[1]+(b[1]-a[1])*d/length)
            return [[at(5*i*unit), at((5*i+3)*unit)] for i in range(n)]
        # A measured length: arrowheads both ways between short end bars.
        nx, ny = (a[1]-b[1])/length*7, (b[0]-a[0])/length*7
        return (arrow(a, b, 7) + arrow(b, a, 7)[1:]
                + [[(p[0]-nx, p[1]-ny), (p[0]+nx, p[1]+ny)] for p in (a, b)])
    if op in ('line', 'arrow', 'brace'):
        a, b = _point(command['from']), _point(command['to'])
        length = math.dist(a, b)
        if length < 1:
            raise ValueError('nonzero drawing segment required')
        if op == 'line':
            return [[a, b]]
        if op == 'arrow':
            return arrow(a, b)
        side = command['side']
        if type(side) is not int or side not in (-1, 1):
            raise ValueError('brace side must be -1 or 1')
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        depth = min(10, length/8)*side
        # A shallow continuous brace; side chooses which local normal it faces.
        profile = ((0,0),(.05,.7),(.1,1),(.4,1),(.46,1.3),(.5,2),
                   (.54,1.3),(.6,1),(.9,1),(.95,.7),(1,0))
        return [[(a[0]+t*length*ux-d*depth*uy, a[1]+t*length*uy+d*depth*ux)
                 for t,d in profile]]
    if op == 'circle':
        x, y = _point(command['center'])
        radius = _number(command['radius'], 2, 180)
        if not (radius <= x <= WIDTH-radius and radius <= y <= HEIGHT-radius):
            raise ValueError('circle outside drawing region')
        return [[(x+radius*math.cos(i*math.tau/64), y+radius*math.sin(i*math.tau/64)) for i in range(65)]]
    if op == 'ellipse':
        x, y = _point(command['center'])
        radii = command['radii']
        if not isinstance(radii, list) or len(radii) != 2:
            raise ValueError('radii must be [rx,ry]')
        rx, ry = _number(radii[0], 2, 280), _number(radii[1], 2, 180)
        turn = math.radians(_number(command.get('angle', 0), -180, 180))
        c, s = math.cos(turn), math.sin(turn)
        path = [(x+rx*math.cos(t)*c-ry*math.sin(t)*s, y+rx*math.cos(t)*s+ry*math.sin(t)*c)
                for t in (i*math.tau/64 for i in range(65))]
        if any(not (0 <= px <= WIDTH and 0 <= py <= HEIGHT) for px, py in path):
            raise ValueError('ellipse outside drawing region')
        return [path]
    if op == 'dot':
        x, y = _point(command['center'])
        if not (5 <= x <= WIDTH-5 and 5 <= y <= HEIGHT-5):
            raise ValueError('dot outside drawing region')
        # A filled node, particle or terminal: one tight spiral the pen fills in.
        return [[(x+4.5*i/48*math.cos(i*math.tau/12), y+4.5*i/48*math.sin(i*math.tau/12))
                 for i in range(49)]]
    if op == 'trace':
        points = command['points']
        if not isinstance(points, list) or not 2 <= len(points) <= 12:
            raise ValueError('trace requires 2..12 points')
        path = [_point(point) for point in points]
        (x0, y0), (x1, y1) = path[0], path[-1]
        if not (4 <= x0 <= WIDTH-4 and 4 <= y0 <= HEIGHT-4 and 4 <= x1 <= WIDTH-4 and 4 <= y1 <= HEIGHT-4):
            raise ValueError('trace terminals outside drawing region')
        # A circuit trace: a small ring where it leaves, a square pad where it lands.
        ring = [(x0+3*math.cos(i*math.tau/16), y0+3*math.sin(i*math.tau/16)) for i in range(17)]
        pad = [(x1-3,y1-3),(x1+3,y1-3),(x1+3,y1+3),(x1-3,y1+3),(x1-3,y1-3)]
        return [path, ring, pad]
    if op == 'rect':
        x, y = _point(command['origin'])
        w, h = _point(command['size'])
        if w < 1 or h < 1 or x+w > WIDTH or y+h > HEIGHT:
            raise ValueError('rectangle outside drawing region')
        return [[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]]
    if op in ('polyline', 'plot'):
        points = command['points']
        if not isinstance(points, list) or not 2 <= len(points) <= 160:
            raise ValueError('use 2..160 sampled points, never an expression')
        return [[_point(point) for point in points]]
    if op == 'shade':
        points = command['points']
        if not isinstance(points, list) or not 3 <= len(points) <= 160:
            raise ValueError('shade requires 3..160 polygon vertices')
        return shade_paths([_point(point) for point in points])
    text = _text(command['text'], 32)
    x, baseline = _point(command['at'])
    size = _number(command.get('size', 20), 12, 28)
    paths, _ = label_paths(text, size) if label_hand == 'plotter' else handwriting_paths(text, size, hand=label_hand)
    paths = [[(x+px, baseline-size+py) for px, py in path] for path in paths]
    # The agent cannot measure its text, so a label that runs off an edge slides back inside;
    # the clearance check still sees where it lands. Only one too big for the region is refused.
    xs, ys = [p[0] for path in paths for p in path], [p[1] for path in paths for p in path]
    dx = (WIDTH-1-max(xs) if max(xs) > WIDTH-1 else 0) + (1-min(xs) if min(xs) < 1 else 0)
    dy = (HEIGHT-1-max(ys) if max(ys) > HEIGHT-1 else 0) + (1-min(ys) if min(ys) < 1 else 0)
    return [[(px+dx, py+dy) for px, py in path] for path in paths]


def _segment_hits_box(a, b, box):
    """Segment/rectangle clipping; a diagonal's bounding box is insufficient."""
    low, high = 0.0, 1.0
    for start, delta, lower, upper in (
            (a[0], b[0]-a[0], box[0], box[2]),
            (a[1], b[1]-a[1], box[1], box[3])):
        if abs(delta) < 1e-12:
            if not lower <= start <= upper:
                return False
        else:
            enter, leave = sorted(((lower-start)/delta, (upper-start)/delta))
            low, high = max(low, enter), min(high, leave)
            if low > high:
                return False
    return True


def _check_label_clearance(objects):
    """Check the FINAL picture, including later marks over earlier labels.

    Two pixels around actual glyph bounds catch collisions, not the larger
    aspirational spacing box in the prompt. This is a compilation constraint,
    not automatic relocation or a claim that the explanation is correct.
    """
    labels = []
    for obj in objects:
        if obj['op'] == 'label':
            points = [point for path in obj['paths'] for point in path]
            xs, ys = zip(*points)
            labels.append((obj, (min(xs)-2, min(ys)-2, max(xs)+2, max(ys)+2)))
    conflicts, details, seen = [], [], set()
    for label, box in labels:
        for obj in objects:
            if obj is label:
                continue
            pair = tuple(sorted((label['location'], obj['location'])))
            if pair in seen:
                continue
            crossing = next(((a, b) for path in obj['paths']
                             for a, b in zip(path, path[1:])
                             if _segment_hits_box(a, b, box)), None)
            if crossing is not None:
                seen.add(pair)
                conflicts.append(f"{label['location']} label {label['text']!r} overlaps "
                                 f"{obj['location']} {obj['op']}")
                # Report observed geometry, never a suggested relocation. The
                # first intersecting segment includes arrowheads and is more
                # useful than a diagonal's potentially misleading bounding box.
                points = [point for path in obj['paths'] for point in path]
                xs, ys = zip(*points)
                details.append(dict(label=label['location'], text=label['text'],
                                    clearance_box=list(box), clearance_pixels=2,
                                    other=obj['location'], other_op=obj['op'],
                                    other_bounds=[min(xs),min(ys),max(xs),max(ys)],
                                    crossing_segment=[list(p) for p in crossing]))
                if len(conflicts) == 8:
                    break
        if len(conflicts) == 8:
            break
    if conflicts:
        raise _LabelCollision('lesson label collision: '+ '; '.join(conflicts)+
                              '. Revise the layout of the whole lesson before insertion.', details)


def _reanchor(steps, objects, colliding):
    """steps with each colliding placed label turned into an anchored label on the nearest earlier shape, so the
    label placer can find it room beside what it names; None when no label could be turned. A label that still
    finds no room is then left out as before. (The 13:59 Riemann lesson lost all six of its placed labels.)"""
    steps = [dict(step, draw=[dict(c) if isinstance(c, dict) else c for c in step['draw']]) for step in steps]
    shapes, turned = [], 0
    for obj in objects:
        s, c = (int(n)-1 for n in re.findall(r'\d+', obj['location']))
        command = steps[s]['draw'][c]
        if obj['op'] != 'label':
            xs, ys = zip(*(p for path in obj['paths'] for p in path))
            shapes.append((s, c, (min(xs), min(ys), max(xs), max(ys))))
            continue
        if obj['location'] not in colliding or 'at' not in command or len(command.get('text', '')) > 24:
            continue
        x, y = command['at']
        def gap(box):
            return math.hypot(max(box[0]-x, 0, x-box[2]), max(box[1]-y, 0, y-box[3]))
        near = min(shapes, key=lambda shape: gap(shape[2]), default=None)
        if near is None:
            continue
        target = steps[near[0]]['draw'][near[1]]
        target.setdefault('id', f'shape-{near[0]+1}-{near[1]+1}')
        steps[s]['draw'][c] = {'op': 'label', 'target': target['id'], 'text': command['text']}
        turned += 1
    return steps if turned else None


@font_budget_fallback
def compile_lesson(steps, takeaway, equation=None, *, allow_short=False, procedural=False,
                   drop_colliding_labels=False, _resolved=None, _anchored=0):
    """All input and expanded font geometry is counted before any asset is made."""
    if type(allow_short) is not bool:
        raise ValueError('explicit short drawing policy required')
    if type(procedural) is not bool:
        raise ValueError('explicit procedural expansion policy required')
    command_limit = 64 if procedural else 32
    minimum = 1 if allow_short else 3
    if not isinstance(steps, list) or not minimum <= len(steps) <= 6:
        raise ValueError(f'a board lesson needs {minimum}..6 drawing steps')
    takeaway = _text(takeaway, 500)
    if equation is not None:
        equation = _text(equation, 400, equation=True)
        # Parse and render offline now, so a bad equation cannot fail after ink.
        from notebook_media import render_equation
        render_equation(equation)
    from notebook_anchored_labels import resolve_labels
    from notebook_relations import resolve_connections
    # Procedural components already own label positions and never emit anchor
    # references. The agent-facing resolver retains its 32-command contract.
    if _resolved is not None:
        connections,label_layout=_resolved
    else:
        steps,connections=(steps,[]) if procedural else resolve_connections(steps)
        unplaced=[] if drop_colliding_labels else None
        steps,label_layout=(steps,[]) if procedural else resolve_labels(steps,unplaced)
    stages, objects = [], []
    for index, step in enumerate(steps):
        _fields(step, {'caption', 'draw'})
        caption = _text(step['caption'], CAPTION)
        commands = step['draw']
        if not isinstance(commands, list) or not 1 <= len(commands) <= command_limit:
            raise ValueError(f'use 1..{command_limit} primitives per step')
        paths = []; label_strokes = 0
        for command_index, command in enumerate(commands, 1):
            expanded = _primitive(command)
            objects.append(dict(op=command['op'], text=command.get('text'), paths=expanded,
                                location=f'step {index+1} command {command_index}'))
            # Shapes are drawn by hand; labels keep their letterforms.
            paths.extend(expanded if command['op']=='label' else [organic(path) for path in expanded])
            if command['op']=='label':
                label_strokes+=len(expanded)
            if len(paths) > 64:
                raise NativePenBudgetError('stage exceeds 64 strokes including labels',details=dict(
                    resource='strokes',observed=len(paths),limit=64,scope='stage',stage=index+1,
                    command=command_index,exact=command_index==len(commands),strokes=len(paths),
                    stroke_breakdown=dict(labels=label_strokes,geometry=len(paths)-label_strokes,
                                          complete=command_index==len(commands))))
        paths = _dense(paths,stage=index+1,label_strokes=label_strokes)
        count = sum(map(len, paths))
        seconds = count*.009 + len(paths)*.070
        if seconds > 30:
            raise NativePenBudgetError('stage exceeds 30 seconds estimated pen time',details=dict(
                resource='estimated_seconds',observed=seconds,limit=30,exact=True,scope='stage',
                stage=index+1,strokes=len(paths),points=count,
                stroke_breakdown=dict(labels=label_strokes,geometry=len(paths)-label_strokes,complete=True)))
        stages.append(dict(id=f'step-{index+1}', title=f'Step {index+1}', text=caption,
                           paths=paths, annotations=[], points=count,
                           estimated_pen_seconds=round(seconds, 3)))
    canonical = json.dumps(dict(steps=steps, takeaway=takeaway, equation=equation),
                           sort_keys=True, ensure_ascii=False, allow_nan=False)
    plan = dict(kind='native-pen-storyboard-plan', scene='lesson-'+hashlib.sha256(canonical.encode()).hexdigest()[:24],
                width=WIDTH, height=HEIGHT, stages=stages, takeaway=takeaway,
                lesson_version=1)
    if equation is not None:
        plan['equation'] = equation
    if label_layout:
        plan['anchored_labels']=label_layout
    if connections:
        plan['connections']=connections
    compile_storyboard(plan)
    try:
        _check_label_clearance(objects)
    except _LabelCollision as exc:
        if drop_colliding_labels and _resolved is None and not procedural and _anchored < 4:  # the check reports 8 collisions a pass
            anchored = _reanchor(steps, objects, {d['label'] for d in exc.collisions})
            if anchored:
                plan = compile_lesson(anchored, takeaway, equation, allow_short=allow_short,
                                      drop_colliding_labels=True, _anchored=_anchored+1)
                plan['dropped_labels'] = unplaced + plan.get('dropped_labels', [])
                return plan
        dropped = {d['label'] for d in exc.collisions}
        kept = [dict(step, draw=[command for number, command in enumerate(step['draw'], 1)
                                 if f'step {index+1} command {number}' not in dropped])
                for index, step in enumerate(steps)]
        if not drop_colliding_labels or not all(step['draw'] for step in kept):
            # All syntax, text, geometry and resource limits have already passed.
            # Preserve the failure; expose only enough for an offline SVG preview.
            raise LessonLayoutError(str(exc), plan, exc.collisions) from exc
        # A label that cannot be placed must not cost the drawing: leave that label out and draw the
        # rest. Each pass removes at least one label, so this ends.
        plan = compile_lesson(kept, takeaway, equation, allow_short=allow_short, procedural=procedural,
                              drop_colliding_labels=True, _resolved=(connections, label_layout))
        plan['dropped_labels'] = sorted({(d['label'], d['text']) for d in exc.collisions}) + plan.get('dropped_labels', [])
    if _resolved is None and unplaced:
        plan['dropped_labels'] = unplaced + plan.get('dropped_labels', [])
    return plan


def parse_lesson(response):
    """Strict full-response framing: steps, optional math, then Takeaway: text."""
    if not isinstance(response, str) or len(response.encode('utf-8')) > MAX_RESPONSE:
        raise ValueError('lesson response exceeds its byte budget')
    response = response.replace('\r\n', '\n')
    steps, end = [], 0
    try:
        for match in STEP.finditer(response):
            if response[end:match.start()].strip():
                raise ValueError('only board-step blocks may precede the equation and takeaway')
            steps.append(json.loads(match[1], object_pairs_hook=_pairs, parse_constant=_constant))
            if len(steps) > 6:
                raise ValueError('at most six board steps')
            end = match.end()
    except (RecursionError, json.JSONDecodeError) as exc:
        raise ValueError('invalid bounded board-step JSON') from exc
    tail = response[end:].strip()
    equation = None
    if tail.startswith('```math\n'):
        match = re.match(r'```math\n([^`]+)\n```\s*', tail)
        if not match:
            raise ValueError('one complete math block required')
        equation, tail = match[1].strip(), tail[match.end():]
    if not tail.startswith('Takeaway: '):
        raise ValueError('lesson must end with Takeaway: followed by one short paragraph')
    return compile_lesson(steps, tail[len('Takeaway: '):].strip(), equation)


def format_lesson(steps, takeaway, equation=None):
    """Author/eval convenience; produces exactly the agent-facing wire format."""
    blocks = ['```board-step\n'+json.dumps(s, ensure_ascii=False, separators=(',', ':'))+'\n```' for s in steps]
    if equation:
        blocks.append('```math\n'+equation+'\n```')
    return '\n\n'.join(blocks+['Takeaway: '+takeaway])
