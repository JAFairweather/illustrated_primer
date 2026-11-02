"""Generate isolated v6 ink assets from validated procedural geometry.

No user-page template, text, images, disk writes or device operations. The
asset's sole layer is unanchored; foreground notebook content is never copied.
The format primitives are shared with our existing ink writer. A generated
file is not proof that a running native SceneView accepts or can clone it.
"""
import hashlib
import copy
import math
import struct
import uuid
import re

from ink import append, cid, i4, sub, tag, vu
from notebook_drawing import compile_storyboard, HAND_STROKES
from notebook_plotter_font import label_paths
from notebook_organic import pen_profile
from notebook_pen_budget import NativePenBudgetError
from notebook_hand_ink import WIDTH as HAND_WIDTH


def _validate_story_blocks(inks):
    """Validate renderer-owned panel/run order, not a model-provided shortcut.

    Up to twelve panels may branch from earlier exact snapshots. At worst
    1+2+...+12 source-stage instances are needed, still under the SAME 12,000
    actual-delivery point budget. Each source asset keeps its stage caps.
    Legacy six-step lessons do not opt into this contract implicitly.
    """
    from notebook_story_plan import MAX_PANELS
    fields = {'version','id','panels','panel','part','parts'}
    if not 1 <= len(inks) <= MAX_PANELS*(MAX_PANELS+1)//2:
        raise ValueError('bounded story stage instances required')
    first = inks[0].get('story')
    if (not isinstance(first,dict) or set(first) != fields or
            type(first['version']) is not int or first['version'] != 1 or
            not isinstance(first['id'],str) or not re.fullmatch(r'[0-9a-f]{64}',first['id']) or
            type(first['panels']) is not int or not 1 <= first['panels'] <= MAX_PANELS):
        raise ValueError('invalid native story descriptor')
    panel, part, parts, scenes, active_scene = 0, 0, None, {}, None
    for b in inks:
        s = b.get('story')
        if (not isinstance(s,dict) or set(s) != fields or
                any(s[k] != first[k] or type(s[k]) is not type(first[k]) for k in ('version','id','panels')) or
                any(type(s[k]) is not int for k in ('panel','part','parts')) or
                s['panel'] != panel or s['part'] != part or
                not 1 <= s['parts'] <= panel+1 or b.get('role') is not None):
            raise ValueError('native story panel/part order changed')
        if part == 0: parts = s['parts']
        if parts != s['parts']:
            raise ValueError('native story part count changed')
        scene = b.get('scene')
        if not isinstance(scene,str) or not re.fullmatch('lesson-story-'+first['id'][:24]+r'-[0-9]{1,2}',scene):
            raise ValueError('native story picture identity mismatch')
        if (type(b.get('stage_index')) is not int or type(b.get('stage_count')) is not int or
                not 1 <= b['stage_count'] <= MAX_PANELS):
            raise ValueError('invalid native story stage order')
        if scene != active_scene:
            if scene in scenes or part != 0:
                raise ValueError('native story cannot reenter an earlier picture')
            if active_scene is not None and scenes[active_scene][0] != scenes[active_scene][1]:
                raise ValueError('native story picture is incomplete')
            scenes[scene] = [0,b['stage_count'],b.get('digest'),set()]
            active_scene = scene
        progress = scenes[scene]
        if (b['stage_index'] != progress[0] or b['stage_count'] != progress[1] or
                b.get('digest') != progress[2] or not isinstance(b.get('stage'),str) or
                b['stage'] in progress[3]):
            raise ValueError('native story stages are missing, duplicated or reordered')
        progress[0] += 1; progress[3].add(b['stage'])
        part += 1
        if part == parts: panel += 1; part = 0
    if panel != first['panels'] or part or any(s[0] != s[1] for s in scenes.values()):
        raise ValueError('native story is incomplete')


HAND_REGIONS, HAND_POINTS = 20, 36000  # handwritten words: a six-step story, its opening and takeaway in the letter hand


def validate_native_ink_budget(blocks):
    """Six drawing steps plus one renderer-owned final equation, never seven steps.

    Math shares the whole-lesson point budget and per-stage limits. Models do
    not supply these resolved blocks or their role/source/digest metadata.
    """
    inks=[b for b in blocks if b.get('kind') == 'ink']
    # Handwritten captions and takeaway, each a one-stage renderer-owned region of its own, with their own budget.
    written=[b for b in inks if b.get('role') == 'hand']
    if written and (len(written) > HAND_REGIONS or len({b.get('scene') for b in written}) != len(written) or any(
            b.get('stage') != 'hand' or b.get('stage_index') != 0 or b.get('stage_count') != 1 or
            not re.fullmatch(r'hand-[0-9a-f]{24}',b.get('scene','')) or b.get('width') != HAND_WIDTH or
            type(b.get('height')) is not int or not 200 <= b['height'] <= 500 for b in written)):
        raise ValueError('handwriting must be separate renderer-owned ink regions')
    totals=inks
    inks=[b for b in inks if b.get('role') != 'hand']
    equations=[b for b in inks if b.get('role') == 'equation']
    story = any('story' in b for b in inks)
    if story:
        if len(equations) > 1 or any('story' in b for b in equations):
            raise ValueError('a story permits one separate final equation')
        _validate_story_blocks([b for b in inks if b.get('role') != 'equation'])
    elif (inks or not written) and (not 1 <= len(inks)-len(equations) <= 6 or len(equations) > 1):  # a story's head is handwriting alone
        raise ValueError('use at most six drawing steps and one final equation')
    if any(b.get('role') not in (None,'equation') for b in inks):
        raise ValueError('unknown native ink role')
    if equations:
        e=equations[0]
        if (e is not inks[-1] or e.get('stage') != 'equation' or e.get('stage_index') != 0 or
                e.get('stage_count') != 1 or not re.fullmatch(r'equation-[0-9a-f]{24}',e.get('scene','')) or
                (e.get('width'),e.get('height')) != (600,200)):
            raise ValueError('equation must be the final renderer-owned ink region')
    total=hand=0
    for b in totals:
        n,p=b.get('stroke_count'),b.get('point_count')
        if type(n) is not int or type(p) is not int:
            raise ValueError('native stage exceeds stroke, point or pen-time budget')
        written=b.get('role') == 'hand'  # handwriting is held to its timed playback, checked when it was made
        if not 1<=n<=(HAND_STROKES if written else 64) or not 2<=p<=3000 or (not written and p*.009+n*.070>30):
            raise NativePenBudgetError('native stage exceeds stroke, point or pen-time budget')
        if b.get('role') == 'hand':
            hand+=p
        else:
            total+=p
    if hand>HAND_POINTS:
        raise NativePenBudgetError('handwritten words exceed their point budget')
    if total>12000:
        raise NativePenBudgetError('diagram and equation exceed the whole-lesson point budget')
    return totals


def _block(kind, body, minimum=1, version=1):
    return struct.pack('<IBBBB', len(body), 0, minimum, version, kind)+body


def _boolean(index, value):
    return tag(index, 1)+bytes([int(value)])


def _string(index, value):
    encoded = value.encode('utf-8')
    return sub(index, vu(len(encoded))+b'\x01'+encoded)


def _lww(index, timestamp, value):
    return sub(index, cid(1, *timestamp)+value)


def _foundation(author):
    """One new root/layer, with no text container or inherited scene items."""
    header = b'reMarkable .lines file, version=6'.ljust(43, b' ')
    authors = _block(9, vu(1)+sub(0, vu(16)+author.bytes_le+struct.pack('<H', 1)))
    migration = _block(0, cid(1, 1, 1)+_boolean(2, True)+_boolean(3, False))
    page = _block(10, b''.join(i4(i, value) for i, value in enumerate((1, 0, 0, 0, 0), 1)), 0)
    tree = _block(1, cid(1, 0, 11)+cid(2, 0, 0)+_boolean(3, True)+sub(4, cid(1, 0, 1)))
    root = _block(2, cid(1, 0, 1)+_lww(2, (0, 0), _string(2, ''))+
                  _lww(3, (0, 0), _boolean(2, True)), 1, 2)
    layer = _block(2, cid(1, 0, 11)+_lww(2, (0, 12), _string(2, 'Layer 1'))+
                   _lww(3, (0, 0), _boolean(2, True)), 1, 2)
    link = _block(4, cid(1, 0, 1)+cid(2, 0, 13)+cid(3, 0, 0)+cid(4, 0, 0)+
                  i4(5, 0)+sub(6, b'\x02'+cid(2, 0, 11)))
    return header+authors+migration+page+tree+root+layer+link


def storyboard_assets(plan, author=None, ink_labels=False):
    """Additive stage assets; captions and annotations remain separate metadata.

    Callers must allocate fresh immutable notebook/page UUIDs. Never rewrite a
    cached source page or write an asset over the foreground notebook's file.
    """
    program = compile_storyboard(plan)  # validate even the LAST operation first
    if type(ink_labels) is not bool:
        raise ValueError('explicit boolean ink-label policy required')
    if ink_labels:
        expanded = copy.deepcopy(plan)
        for stage in expanded['stages']:
            for annotation in stage.get('annotations', []):
                text = annotation['text']
                x, y = annotation['point']
                paths, width = label_paths(text)
                if width > plan['width']-x:
                    raise ValueError('diagram label would wrap or overflow its reserved region')
                for path in paths:
                    dense = []
                    for p, q in zip(path, path[1:]):
                        count = max(1, math.ceil(math.dist(p, q)/2))
                        dense.extend((float(x+p[0]+(q[0]-p[0])*i/count), float(y-24+p[1]+(q[1]-p[1])*i/count))
                                     for i in range(count))
                    dense.append((float(x+path[-1][0]), float(y-24+path[-1][1])))
                    stage['paths'].append(dense)
            stage['annotations'] = []
        # Labels become native ink ONLY under this explicit policy; prose and
        # captions are never sent through this font/tracing path.
        geometry = compile_storyboard(expanded)
    else:
        geometry = program
    author = uuid.UUID(str(author)) if author is not None else uuid.uuid4()
    foundation = _foundation(author)
    assets = []
    for stage in plan['stages']:
        paths = [op['path'] for op in geometry['operations']
                 if op['kind'] == 'stroke' and op['stage'] == stage['id']]
        if not paths:
            continue
        # Asset-local coordinates; native clone/paste determines destination.
        raw = append(foundation, [[(x, y, w, d) for (x, y), (w, d) in zip(path, pen_profile(path))]
                                  for path in paths],
                     start=((0, 11), (1, 14)))
        points = [point for path in paths for point in path]
        bounds = [min(p[0] for p in points), min(p[1] for p in points),
                  max(p[0] for p in points), max(p[1] for p in points)]
        assets.append({'stage': stage['id'], 'data': raw,
                       'sha256': hashlib.sha256(raw).hexdigest(),
                       'stroke_count': len(paths), 'point_count': sum(map(len, paths)),
                       'width': program['width'], 'height': program['height'],
                       'program_digest': program['digest'], 'bounds': bounds,
                       'annotations_rendered_as': 'ink-labels' if ink_labels else 'separate-metadata'})
    return assets
