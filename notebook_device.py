"""Bounded native-view telemetry, not a drawing lease or a control API.

Only geometry/identity/revision counters are retained in memory, never notebook
text. A fresh snapshot alone does not make raw pen injection navigation-safe.
"""
import copy
import math
import re
import threading
import time
import uuid
from notebook_drawing import compile_storyboard


def _vector(value, length):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError('native geometry has invalid dimensions')
    if any(type(x) not in (float, int) or not math.isfinite(x) or abs(x) > 10_000_000 for x in value):
        raise ValueError('native geometry must be bounded and finite')
    return list(value)


class DeviceContext:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.latest = None
        self.sequences = {}
        self.awake = None

    def keep_awake(self, body):
        """Explicit local maintenance lease; never a drawing/input permission.

        Refresh at most every two minutes during work. A disconnected helper or
        stopped server cannot leave a permanent tablet power setting behind.
        """
        if not isinstance(body, dict) or set(body) != {'doc', 'seconds'}:
            raise ValueError('keep-awake requires doc and seconds')
        doc, seconds = body['doc'], body['seconds']
        if not isinstance(doc, str) or str(uuid.UUID(doc)) != doc:
            raise ValueError('keep-awake requires a canonical document UUID')
        if type(seconds) is not int or not 0 <= seconds <= 180:
            raise ValueError('keep-awake duration must be 0..180 seconds')
        with self.lock:
            if seconds:
                if (not self.latest or self.clock()-self.latest[0] > 1.5 or
                        not self.latest[1]['active'] or self.latest[1]['doc'] != doc):
                    raise ValueError('keep-awake requires the fresh active document')
                self.awake = (self.clock()+seconds, doc)
            else:
                if self.awake and self.awake[1] == doc:
                    self.awake = None
        return {'keep_awake_seconds': seconds, 'doc': doc, 'control_lease': False}

    def awake_seconds(self, doc):
        with self.lock:
            if not self.awake or self.awake[1] != doc:
                return 0
            return max(0, math.ceil(self.awake[0]-self.clock()))

    def update(self, body):
        required = {'doc', 'page', 'surface', 'sequence', 'active', 'view',
                    'size', 'text_bounds', 'content_revision', 'ink_revision'}
        if not isinstance(body, dict) or set(body) != required:
            raise ValueError('invalid native context fields')
        body = copy.deepcopy(body)
        for key in ('doc', 'page'):
            if not isinstance(body[key], str) or str(uuid.UUID(body[key])) != body[key]:
                raise ValueError('native context requires canonical UUIDs')
        if not isinstance(body['surface'], str) or not re.fullmatch(r'[0-9]{10,16}-[0-9]{1,10}', body['surface']):
            raise ValueError('native surface identity required')
        for key in ('sequence', 'content_revision', 'ink_revision'):
            if type(body[key]) is not int or not 0 <= body[key] <= 2**31-1:
                raise ValueError('invalid native revision counter')
        if type(body['active']) is not bool:
            raise ValueError('native activity must be boolean')
        matrix = body['view'] = _vector(body['view'], 6)
        determinant = matrix[0]*matrix[3] - matrix[1]*matrix[2]
        if not .0001 <= abs(determinant) <= 100:
            raise ValueError('native view transform is singular or unsupported')
        size = body['size'] = _vector(body['size'], 2)
        if not all(100 <= n <= 3000 for n in size):
            raise ValueError('native viewport size unsupported')
        bounds = body['text_bounds'] = _vector(body['text_bounds'], 4)
        if bounds[2] < 0 or bounds[3] < 0:
            raise ValueError('negative native text dimensions')
        with self.lock:
            surface = body['surface']
            if body['sequence'] <= self.sequences.get(surface, -1):
                return {'accepted': False, 'reason': 'out-of-order context'}
            # Bounded memory; old surface counters are diagnostic, not leases.
            if surface not in self.sequences and len(self.sequences) >= 32:
                self.sequences.pop(next(iter(self.sequences)))
            self.sequences[surface] = body['sequence']
            self.latest = (self.clock(), body)
        return {'accepted': True}

    def snapshot(self):
        with self.lock:
            if self.latest is None:
                return {'available': False, 'fresh': False}
            received, body = self.latest
            age = max(0, self.clock()-received)
            return dict(copy.deepcopy(body), available=True, age_ms=round(age*1000),
                        fresh=age <= 1.5 and body['active'], control_lease=False)


def _region_projection(width, height, context, scene_origin):
    """Shared reservation geometry for authored and compiled agent lessons."""
    if type(width) is not int or type(height) is not int or not (320 <= width <= 1140 and 200 <= height <= 500):
        raise ValueError('diagram region exceeds notebook bounds')
    if not isinstance(context, dict) or not isinstance(scene_origin, (list, tuple)):
        raise ValueError('native geometry and a scene origin are required')
    if not context.get('available') or not context.get('fresh') or not context.get('active'):
        raise ValueError('fresh active native geometry required for projection')
    if context.get('size') != [1404, 1872]:
        raise ValueError('unsupported native display orientation or dimensions')
    a, b, c, d, tx, ty = _vector(context.get('view'), 6)
    determinant = a*d-b*c
    if not .0001 <= abs(determinant) <= 100:
        raise ValueError('native view transform is singular or unsupported')
    ox, oy = _vector(list(scene_origin), 2)
    def display(x, y):
        x, y = ox+x-tx, oy+y-ty
        return ((d*x-c*y)/determinant, (-b*x+a*y)/determinant)
    corners = [display(x, y) for x, y in ((0, 0), (width, 0), (0, height), (width, height))]
    box = [min(p[0] for p in corners), min(p[1] for p in corners),
           max(p[0] for p in corners), max(p[1] for p in corners)]
    if box[0] < 130 or box[1] < 210 or box[2] > 1304 or box[3] > 1792:
        raise ValueError('whole diagram must fit safe paper; scroll/reposition before drawing')
    return box, display


def project_region(width, height, context, scene_origin):
    """Project a registered region; this is not permission to write into it."""
    return _region_projection(width, height, context, scene_origin)[0]


def project_storyboard(plan, context, scene_origin, stage=None):
    """Project validated geometry, refusing diagrams partly outside safe paper.

    The caller must still reserve the native UI, check blank space and bind the
    request. Fresh telemetry alone never grants permission to inject input.
    """
    program = compile_storyboard(plan)
    box, display = _region_projection(program['width'], program['height'], context, scene_origin)
    stages = {op['stage'] for op in program['operations']}
    if stage is not None and stage not in stages:
        raise ValueError('unknown storyboard stage')
    paths, count = [], 0
    for op in program['operations']:
        if op['kind'] != 'stroke' or (stage is not None and op['stage'] != stage):
            continue
        mapped = [display(x, y) for x, y in op['path']]
        dense = []
        for p, q in zip(mapped, mapped[1:]):
            steps = max(1, math.ceil(math.dist(p, q)/2))
            dense.extend((p[0]+(q[0]-p[0])*i/steps, p[1]+(q[1]-p[1])*i/steps)
                         for i in range(steps))
        dense.append(mapped[-1])
        count += len(dense)
        if count > 12000:
            raise ValueError('projected drawing exceeds the native point budget')
        paths.append(dense)
    return {'kind': 'projected-native-pen-plan', 'paths': paths, 'points': count,
            'bounds': box, 'scene': program['scene'], 'digest': program['digest'],
            'stage': stage, 'control_lease': False}
