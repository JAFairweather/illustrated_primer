"""Compile authored storyboard plans into bounded, additive native operations.

No device I/O, expression evaluation, images or generated coordinate tokens.
The adapter must supply a reserved page region and a current request/page lease.
This is an engine boundary, NOT an assertion that live insertion is supported.
"""
import copy
import hashlib
import json
import math
from xml.sax.saxutils import escape
from notebook_pen_budget import NativePenBudgetError

# A handwritten region (scene 'hand-...') may hold more strokes than a drawing stage: print lifts the pen at every
# letter, so three lines of it are about 180 strokes. Its timed playback still keeps to 3000 points and 30 seconds.
HAND_STROKES = 192


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('drawing coordinates must be finite numbers')
    return value


def _text(value, limit=1600):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('storyboard text is missing or exceeds its budget')
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('storyboard text contains control characters')
    return value


def compile_storyboard(plan):
    """Validate the ENTIRE plan before a caller can begin a native operation.

    Coordinates remain local to one reserved diagram. Captions and equations
    are distinct operations, never approximated by pen-shaped glyphs. Text
    annotations retain semantic positions; adapters must explicitly support
    them or reject the program before writing anything.
    """
    if not isinstance(plan, dict) or plan.get('kind') != 'native-pen-storyboard-plan':
        raise ValueError('authored native storyboard plan required')
    width, height = plan.get('width'), plan.get('height')
    if type(width) is not int or type(height) is not int or not (320 <= width <= 1140 and 200 <= height <= 500):
        raise ValueError('diagram region exceeds notebook bounds')
    scene = _text(plan.get('scene'), 80)
    hand = scene.startswith('hand-')
    # Drawn strokes are sampled every 2 units. Handwriting may space its points up to 8 apart where the line is
    # straight, so a region holds several written lines; curves keep their close points.
    step = plan.get('max_step', 2)
    if step not in (2, 8):
        raise ValueError('pen point spacing must be 2 or 8 units')
    stages = plan.get('stages')
    if not isinstance(stages, list) or not 1 <= len(stages) <= 12:
        raise ValueError('use 1..12 authored stages')
    operations, seen, total_points = [], set(), 0
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError('invalid storyboard stage')
        identity = _text(stage.get('id'), 80)
        if identity in seen:
            raise ValueError('duplicate storyboard stage')
        seen.add(identity)
        operations.append({'kind': 'caption', 'stage': identity,
                           'title': _text(stage.get('title'), 160),
                           'text': _text(stage.get('text'))})
        paths = stage.get('paths')
        if not isinstance(paths, list) or len(paths) > (HAND_STROKES if hand else 64):
            raise ValueError('stage exceeds its path budget')
        points = 0
        for index, path in enumerate(paths):
            if not isinstance(path, (list, tuple)) or not 2 <= len(path) <= 3000:
                raise ValueError('stroke must contain 2..3000 points')
            checked = []
            for point in path:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    raise ValueError('invalid pen point')
                x, y = map(_number, point)
                if not (0 <= x <= width and 0 <= y <= height):
                    raise ValueError('stroke outside reserved diagram region')
                if checked and math.dist(checked[-1], (x, y)) > step+.01:
                    raise ValueError('stroke is not densely sampled for native pen input')
                checked.append((x, y))
            points += len(checked)
            operations.append({'kind': 'stroke', 'stage': identity,
                               'path': checked, 'stroke': index})
        total_points += points
        if points > 3000 or total_points > 12000:
            raise NativePenBudgetError('storyboard exceeds its point budget',details=dict(
                resource='points',observed=points if points>3000 else total_points,
                limit=3000 if points>3000 else 12000,scope='stage' if points>3000 else 'lesson',
                exact=points>3000,stage=len(seen),stage_id=identity))
        if not hand and points*.009 + len(paths)*.070 > 30:  # handwriting is held to its timed playback instead
            raise NativePenBudgetError('storyboard stage exceeds its drawing-time budget',details=dict(
                resource='estimated_seconds',observed=points*.009+len(paths)*.070,limit=30,
                exact=True,scope='stage',stage=len(seen),stage_id=identity,points=points,strokes=len(paths)))
        annotations = stage.get('annotations', [])
        if not isinstance(annotations, list) or len(annotations) > 16:
            raise ValueError('stage exceeds its annotation budget')
        for annotation in annotations:
            if not isinstance(annotation, dict):
                raise ValueError('invalid diagram annotation')
            point = annotation.get('point')
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError('annotation point required')
            x, y = map(_number, point)
            if not (0 <= x <= width and 0 <= y <= height):
                raise ValueError('annotation outside reserved region')
            operations.append({'kind': 'annotation', 'stage': identity,
                               'text': _text(annotation.get('text'), 160), 'point': (x, y)})
        if 'equation' in stage:
            operations.append({'kind': 'equation', 'stage': identity,
                               'source': _text(stage['equation'], 400)})
    program = {'scene': scene, 'width': width, 'height': height,
               'operations': operations, 'points': total_points,
               'required_operations': sorted({op['kind'] for op in operations})}
    program['digest'] = hashlib.sha256(json.dumps(program, sort_keys=True).encode()).hexdigest()
    return program


class StoryboardRun:
    """One-shot adapter executor; partial output is held, never auto-replayed.

    Adapter contract: capabilities, reserve(program, identity), current_identity(),
    record(event), emit(operation), verify(program). reserve MUST establish the
    exclusive request/page/layout lease, check blank diagram space and reserve
    caption/equation layout. It must durably claim this identity/digest and refuse
    any previously attempted claim, including across process restarts. All
    caption/equation insertion must preserve the diagram's reserved geometry.
    current_identity MUST include user-input/view epochs,
    not only a UUID. emit(stroke) MUST guard that lease throughout native input,
    releasing the pen on failure. record MUST durably persist intent before emit.

    This class enforces operation boundaries; it cannot manufacture an atomic
    tablet lease or prove an adapter's guarantees. No live adapter is wired yet.
    """
    def __init__(self, plan, identity):
        self.program = compile_storyboard(plan)
        if not isinstance(identity, tuple) or len(identity) != 5 or any(v is None for v in identity):
            raise ValueError('request, document, page, view epoch and input epoch required')
        self.identity = identity
        self.state = 'new'
        self.completed = 0

    def run(self, adapter):
        if self.state != 'new':
            raise RuntimeError('storyboard already attempted; inspect rather than replay')
        if not set(self.program['required_operations']) <= set(adapter.capabilities):
            raise ValueError('adapter cannot render every required native operation')
        self.state = 'reserving'
        try:
            adapter.reserve(copy.deepcopy(self.program), self.identity)
            for index, operation in enumerate(self.program['operations']):
                if adapter.current_identity() != self.identity:
                    raise RuntimeError('storyboard page, request or input changed')
                event = {'digest': self.program['digest'], 'operation': index,
                         'identity': self.identity}
                self.state = 'writing'
                adapter.record(dict(event, state='intent'))
                # Recheck after persistence: a journal flush can be slow.
                if adapter.current_identity() != self.identity:
                    raise RuntimeError('storyboard lease changed before insertion')
                adapter.emit(copy.deepcopy(operation))
                adapter.record(dict(event, state='complete'))
                self.completed += 1
            if adapter.current_identity() != self.identity or adapter.verify(copy.deepcopy(self.program)) is not True:
                raise RuntimeError('native storyboard persistence not confirmed')
            self.state = 'verified'
        except Exception:
            self.state = 'attention'
            raise
        return {'state': self.state, 'operations': self.completed,
                'digest': self.program['digest']}


def preview_svg(plan, through_stage=None):
    """Diagnostic vector preview only. Not a notebook response or native proof.

    Captions are deliberately outside the drawing so text never becomes strokes.
    Stage previews are cumulative; execution operations remain additive.
    """
    program = compile_storyboard(plan)
    stages = [s['id'] for s in plan['stages']]
    if through_stage is not None and through_stage not in stages:
        raise ValueError('unknown preview stage')
    last = stages.index(through_stage) if through_stage is not None else len(stages)-1
    selected = set(stages[:last+1])
    w, h = program['width'], program['height']
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<rect width="100%" height="100%" fill="white"/>']
    for op in program['operations']:
        if op['stage'] not in selected:
            continue
        if op['kind'] == 'stroke':
            points = ' '.join(f'{x:.2f},{y:.2f}' for x, y in op['path'])
            parts.append(f'<polyline points="{points}" fill="none" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
        elif op['kind'] == 'annotation':
            x, y = op['point']
            parts.append(f'<text x="{x:.2f}" y="{y:.2f}" font-family="sans-serif" font-size="17">{escape(op["text"])}</text>')
    return '\n'.join(parts+['</svg>'])
