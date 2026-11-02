"""Offline typed data-space panels with immutable historical picture reuse.

The model names frames, mathematical values and label relationships. This
module owns display coordinates. It returns no device operations or authority.
"""
from copy import deepcopy
import math

from notebook_story_plan import validate_story, _id, _bounded_copy
from notebook_lesson import _fields, _number, _text, _primitive, compile_lesson, _check_label_clearance
from notebook_drawing import compile_storyboard
from notebook_procedural import (_place_labels, _route_label_candidates,
                                 _label_lines, _label_group, _group_label_bounds)
from notebook_panel_objects import lower_symbolic
from notebook_pen_budget import NativePenBudgetError
from notebook_plotter_font import label_paths
from notebook_label_candidates import edge_slides, corner_callouts
from notebook_contract_feedback import exact_fields, item_fields
from notebook_label_attachment import region_attachment, contour_attachment
from notebook_hatching import hatch_paths


_CONTOUR_CALLOUT_TYPES = frozenset((
    'dot', 'circle', 'line', 'arrow', 'brace', 'shade', 'vline', 'hline', 'polyline', 'plot', 'connect'))


def _span(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('data range requires two numbers')
    a, b = [_number(v, -1e6, 1e6) for v in value]
    if b-a < 1e-9:
        raise ValueError('data range must increase with finite nonzero span')
    return [a, b]


def _frame(item, labels=()):
    item_fields(item)
    if type(item.get('visible', True)) is not bool:
        raise ValueError('axes visible must be a boolean')
    if not item.get('visible', True) and labels:
        raise ValueError('labels must attach to visible geometry, not a hidden coordinate frame')
    x, y = _span(item['x']), _span(item['y'])
    if item['aspect'] not in ('equal', 'independent'):
        raise ValueError('axes aspect must be equal or independent')
    def lettering_width(value):
        paths, _ = label_paths(str(value), 18)
        xs = [p[0] for path in paths for p in path]
        return max(xs)-min(xs)
    # Reserve actual endpoint lettering BEFORE mapping data to display units.
    # Later panels inherit this frame; new labels never rescale old geometry.
    left_margin = max(80, max(map(lettering_width,y))+40, lettering_width(x[0])/2+12)
    right_margin = max(80, lettering_width(x[1])/2+12)
    margins = dict(left=left_margin, right=right_margin, top=50, bottom=70)
    # Titles belong to the layout, not the model's data coordinates. Measure
    # all same-panel axis titles before mapping any geometry. Later snapshots
    # inherit the finished frame and never move already drawn ink.
    for label in labels:
        text = _text(label['text'], 24)
        side = label['side']
        if side not in ('auto', 'top', 'bottom', 'left', 'right'):
            raise ValueError('unknown label side')
        side = 'top' if side == 'auto' else side
        box = _group_label_bounds(_label_group(_label_lines(text)[0], 0, 0))
        extent = box[2]-box[0] if side in ('left','right') else box[3]-box[1]
        margins[side] = max(margins[side], extent+36)
    width, height = 600-margins['left']-margins['right'], 360-margins['top']-margins['bottom']
    if min(width, height) < 80:
        raise ValueError('axis labels leave no readable data region')
    available_width, available_height = width, height
    if item['aspect'] == 'equal':
        scale = min(width/(x[1]-x[0]), height/(y[1]-y[0]))
        width, height = scale*(x[1]-x[0]), scale*(y[1]-y[0])
        if min(width, height) < 24:
            raise ValueError('equal-scale axes would be unreadably thin')
    left = margins['left']+(available_width-width)/2
    top = margins['top']+(available_height-height)/2
    return dict(x=x, y=y, aspect=item['aspect'], box=[left, top, left+width, top+height])


def _point(frame, value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('data point requires two coordinates')
    x = _number(value[0], *frame['x']); y = _number(value[1], *frame['y'])
    left, top, right, bottom = frame['box']
    return [left+(x-frame['x'][0])/(frame['x'][1]-frame['x'][0])*(right-left),
            bottom-(y-frame['y'][0])/(frame['y'][1]-frame['y'][0])*(bottom-top)]


def _line(a, b, op='line'):
    return dict(op=op, **{'from':a, 'to':b})


def _bounds(commands):
    points = [point for command in commands for path in _primitive(command) for point in path]
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def _candidates(bounds, side, *, callouts=False):
    def candidates(local_box):
        left, top, right, bottom = bounds
        cx, cy = (left+right)/2, (top+bottom)/2
        half_width = (local_box[2]-local_box[0])/2
        center_y = (local_box[1]+local_box[3])/2
        preferred = ('top', 'right', 'bottom', 'left', 'top-left', 'top-right',
                     'bottom-right', 'bottom-left') if side=='auto' else (side,)
        alternatives = tuple(s for s in ('top','right','bottom','left',
                            'top-left','top-right','bottom-right','bottom-left')
                             if s not in preferred)
        # Keep every old preferred candidate first. side is a placement hint,
        # not an instruction to fail an otherwise legible attached label.
        for order, gap in [(preferred,g) for g in (12,24)] + [(alternatives,g) for g in (12,24)]:
            positions = {
                'top': (cx, top-gap-local_box[3]),
                'bottom': (cx, bottom+gap-local_box[1]),
                'left': (left-gap-half_width, cy-center_y),
                'right': (right+gap+half_width, cy-center_y),
                'top-left': (left-gap-half_width, top-gap-local_box[3]),
                'top-right': (right+gap+half_width, top-gap-local_box[3]),
                'bottom-right': (right+gap+half_width, bottom+gap-local_box[1]),
                'bottom-left': (left-gap-half_width, bottom+gap-local_box[1]),
            }
            for selected in order:
                yield positions[selected]
        yield from edge_slides(bounds, local_box, along_edge=True)
        # An empty enclosed region can carry its own label. The existing
        # ink/collision checks still reject hatching or lines through text.
        yield (cx, cy-center_y)
    # The existing joint placement search tries wrapping variants too.
    result = lambda box: list(candidates(box))
    if callouts:
        result.fallback = lambda box: corner_callouts(bounds, box)
    return result


def _hatch_region(left, top, right, bottom):
    """Sparse 45-degree fill, distinct from horizontal/vertical boundaries.

    A page-aligned lattice keeps adjacent/subdivided regions consistent. Only
    the decorative fill is clipped to its validated rectangle; mathematical
    objects and data ranges are never clipped or adjusted.
    """
    spacing = 32 * math.sqrt(2)  # 32 display units measured perpendicular to ink.
    first = math.ceil((left + top) / spacing)
    last = math.floor((right + bottom) / spacing)
    commands = []
    for index in range(first, last + 1):
        offset = index * spacing
        x1, x2 = max(left, offset-bottom), min(right, offset-top)
        if x2-x1 > 1e-9:
            commands.append(_line([x1, offset-x1], [x2, offset-x2]))
    # A tiny valid region between grid lines still needs a visible fill cue.
    if not commands:
        offset = (left+right+top+bottom)/2
        x1, x2 = max(left, offset-bottom), min(right, offset-top)
        commands.append(_line([x1, offset-x1], [x2, offset-x2]))
    return commands


def _axis_title_candidates(bounds, side):
    """An axis title stays on its named edge, not a different axis's margin."""
    side = 'top' if side == 'auto' else side
    candidates = _candidates(bounds, side)
    left,top,right,bottom = bounds
    def same_edge(local_box):
        result = []
        for x,y in candidates(local_box):
            x0,y0,x1,y1 = (x+local_box[0],y+local_box[1],
                            x+local_box[2],y+local_box[3])
            if ((side == 'top' and y1 <= top and left <= (x0+x1)/2 <= right) or
                (side == 'bottom' and y0 >= bottom and left <= (x0+x1)/2 <= right) or
                (side == 'left' and x1 <= left and top <= (y0+y1)/2 <= bottom) or
                (side == 'right' and x0 >= right and top <= (y0+y1)/2 <= bottom)):
                result.append((x,y))
        return result
    return same_edge


def _hatch_polygon(points):
    """Sparse diagonal even-odd fill of an already validated sampled boundary.

    Intersections are calculated against the same segments that will be drawn,
    not a bounding rectangle. Half-open edges count shared vertices once;
    even-odd pairs keep separate lobes separate when the baseline is crossed.
    Sub-pixel decorative hatch fragments are omitted, never enlarged.
    """
    return [_line(a,b) for a,b in hatch_paths(points)]


def _polynomial(item):
    coefficients = item['coefficients']
    if not isinstance(coefficients, list) or not 1 <= len(coefficients) <= 5:
        raise ValueError('plot uses degree 0..4 polynomial coefficients, never code')
    coefficients = [_number(c, -1e6, 1e6) for c in coefficients]
    a, b = _span(item['domain'])
    return coefficients, a, b


def _sample_curve(item):
    if 'function' in item:
        from notebook_function_plot import function_points
        return function_points(item['function'],item['domain'])
    coefficients, a, b = _polynomial(item)
    values = []
    # An affine polynomial is exactly one segment, including a coefficient
    # list padded with zero higher powers. Retain sampling for every genuinely
    # curved polynomial; never flatten a small but nonzero coefficient.
    intervals = 1 if all(c == 0 for c in coefficients[2:]) else 64
    for i in range(intervals+1):
        x = a if i == 0 else b if i == intervals else a+(b-a)*i/intervals
        values.append([x,sum(c*x**power for power,c in enumerate(coefficients))])
    return values


def _area(item, point):
    values = _sample_curve(item)
    baseline = _number(item['baseline'], -1e6, 1e6)
    fill = item['fill']
    if fill not in ('none', 'hatch'):
        raise ValueError('area fill must be none or hatch')
    # Validate every curve/baseline vertex before generating decorative fill.
    points = [point(p) for p in values+[[values[-1][0],baseline],[values[0][0],baseline]]]
    commands = [dict(op='polyline', points=points+[points[0]])]
    if fill == 'hatch':
        commands.extend(_hatch_polygon(points))
    return commands


def _riemann(item, point):
    """Sample equal data intervals procedurally, preserving signed heights.

    A zero-height sample is its baseline segment, not an invalid rectangle or
    an invented positive area. Nonzero bars retain exact heights, even when
    subpixel; no clipping, rounding, or minimum visual area changes the math.
    The ordinary stage compiler still enforces stroke/point/time budgets.
    """
    coefficients, a, b = _polynomial(item)
    baseline = _number(item['baseline'], -1e6, 1e6)
    count = item['count']
    if type(count) is not int or not 1 <= count <= 16:
        raise ValueError('Riemann subdivision count must be an integer from 1 to 16')
    sample = item['sample']
    if not isinstance(sample, str) or sample not in ('left', 'midpoint', 'right'):
        raise ValueError('Riemann sample must be left, midpoint or right')
    offset = {'left': 0, 'midpoint': .5, 'right': 1}[sample]
    edges = [a+(b-a)*index/count for index in range(count+1)]
    edges[0], edges[-1] = a, b
    commands = []
    for left, right in zip(edges, edges[1:]):
        x = left if offset == 0 else right if offset == 1 else left+(right-left)/2
        height = sum(c*x**power for power,c in enumerate(coefficients))
        points = [[left, baseline], [left, height], [right, height],
                  [right, baseline], [left, baseline]]
        if height == baseline:
            points = [[left, baseline], [right, baseline]]
        commands.append(dict(op='polyline', points=[point(p) for p in points]))
    return commands


def _lower(item, frames):
    """Data values -> existing bounded primitives; no expression execution."""
    kind = item.get('type')
    item_fields(item)
    if kind not in ('line','arrow','brace','shade','vline','hline','dot','rect','region','circle','polyline','plot','riemann','area'):
        raise ValueError('unsupported typed panel shape')
    frame_id = _id(item['in'])
    if frame_id not in frames:
        raise ValueError('shape requires an earlier axes ID in its picture')
    frame = frames[frame_id]
    point = lambda p: _point(frame, p)
    if kind == 'riemann':
        return _riemann(item, point)
    if kind == 'area':
        return _area(item, point)
    if kind in ('line', 'arrow'):
        return [_line(point(item['from']), point(item['to']), kind)]
    if kind == 'brace':
        if type(item['side']) is not int or item['side'] not in (-1, 1):
            raise ValueError('brace side must be -1 or 1')
        # Positive is the LEFT normal of the directed segment in mathematical
        # coordinates. Display y runs down, so reverse the primitive's normal.
        return [dict(_line(point(item['from']), point(item['to']), 'brace'), side=-item['side'])]
    if kind == 'shade':
        values = item['points']
        if not isinstance(values, list) or not 3 <= len(values) <= 160:
            raise ValueError('shade requires 3..160 data vertices')
        return [dict(op='shade', points=[point(p) for p in values])]
    if kind == 'vline':
        return [_line(point([item['value'], frame['y'][0]]), point([item['value'], frame['y'][1]]))]
    if kind == 'hline':
        return [_line(point([frame['x'][0], item['value']]), point([frame['x'][1], item['value']]))]
    if kind == 'dot':
        return [dict(op='circle', center=point(item['at']), radius=3)]
    if kind in ('rect', 'region'):
        x, y = _span(item['x']), _span(item['y'])
        left, bottom = point([x[0], y[0]]); right, top = point([x[1], y[1]])
        commands = [dict(op='rect', origin=[left, top], size=[right-left, bottom-top])]
        fill = item.get('fill', 'none')
        if fill not in ('none', 'hatch'):
            raise ValueError('rectangular fill must be none or hatch')
        if fill == 'hatch':
            commands.extend(_hatch_region(left, top, right, bottom))
        return commands
    if kind == 'circle':
        if frame['aspect'] != 'equal':
            raise ValueError('a mathematical circle needs equal axis scale')
        center = item['center']; radius = _number(item['radius'], 1e-9, 1e6)
        mapped = point(center)
        for dx, dy in ((radius,0),(-radius,0),(0,radius),(0,-radius)):
            point([center[0]+dx, center[1]+dy])
        pixels = radius*(frame['box'][2]-frame['box'][0])/(frame['x'][1]-frame['x'][0])
        return [dict(op='circle', center=mapped, radius=pixels)]
    if kind == 'polyline' or 'points' in item:
        values = item['points']
        if not isinstance(values, list) or not 2 <= len(values) <= 160:
            raise ValueError('sampled curve needs 2..160 data points')
    else:
        values = _sample_curve(item)
    return [dict(op='polyline', points=[point(p) for p in values])]


def compile_panel_shapes(story, drafts):
    """Resolve every panel before returning any accepted picture.

    Resolve geometry for the complete story, then place labels against all
    planned geometry in each shared picture. Only that final layout is frozen;
    provisional offline prefixes are not already-written notebook content.
    Each returned panel preserves its base paths exactly. Native multi-region
    placement is NOT supplied.
    The 12,000-point story cap conservatively counts all materialized snapshots,
    since separate-panel delivery may need to draw inherited ink again.
    """
    story = validate_story(story)
    drafts = _bounded_copy(drafts)
    expected = {p['id'] for p in story['panels']}
    if not isinstance(drafts, dict) or set(drafts) != expected:
        raise ValueError('provide exactly one typed-shape draft for every story panel')
    families, assemblies, geometry_by_family, labels_by_family = {}, {}, {}, {}
    # Preflight the whole draft collection before accessing future titles.
    for panel in story['panels']:
        identity = panel['id']; draft = drafts[identity]
        exact_fields(draft, {'v','mode','panel','items'})
        if type(draft['v']) is not int or draft['v'] != 1 or draft['mode'] != 'panel-shapes' or draft['panel'] != identity:
            raise ValueError('version 1 panel-shapes identity mismatch')
        if not isinstance(draft['items'], list) or not 1 <= len(draft['items']) <= 24:
            raise ValueError('use 1..24 new typed items per panel')
        for item_index, item in enumerate(draft['items']):
            item_fields(item, path=f'/items/{item_index}')
        families[identity] = families[panel['base']] if panel['base'] else identity
    for panel in story['panels']:
        identity = panel['id']; draft = drafts[identity]; family = families[identity]
        base = assemblies.get(panel['base'])
        frames = deepcopy(base['frames']) if base else {}
        items = deepcopy(base['items']) if base else {}
        groups = deepcopy(base['groups']) if base else {}
        origins = deepcopy(base['origins']) if base else {}
        pending, fresh = [], []
        for item in draft['items']:
            if not isinstance(item, dict): raise ValueError('typed panel item required')
            item_id = _id(item.get('id'))
            if item_id in items: raise ValueError('cannot redefine an inherited or duplicate item ID')
            fresh.append(item_id)
            kind = item.get('type')
            if kind == 'axes':
                if frames: raise ValueError('this panel layout supports one axes frame per picture')
                if any(old['type']=='object' for old in items.values()):
                    raise ValueError('symbolic objects and mathematical axes need separate pictures')
                titles = [candidate for other in story['panels'] if families[other['id']] == family
                          for candidate in drafts[other['id']]['items']
                          if isinstance(candidate, dict) and candidate.get('type') == 'label'
                          and candidate.get('to') == item_id]
                frame = _frame(item, titles); frames[item_id] = frame
                left, top, right, bottom = frame['box']
                visible = item.get('visible', True)
                commands = ([_line([left,top],[left,bottom]), _line([left,bottom],[right,bottom])]
                            if visible else [])
                endpoints = (
                        ('xmin',frame['x'][0],[left,bottom],'bottom'),
                        ('xmax',frame['x'][1],[right,bottom],'bottom'),
                        ('ymin',frame['y'][0],[left,bottom],'left'),
                        ('ymax',frame['y'][1],[left,top],'left'))
                for suffix, val, at, side in (endpoints if visible else ()):
                    tick_id = '__'+item_id+'-'+suffix
                    pending.append((tick_id, str(val), _candidates([*at,*at],side)))
                    fresh.append(tick_id)
                    groups[tick_id] = []
            elif kind == 'label':
                _fields(item, {'id','type','to','text','side'})
                target = _id(item['to'])
                if target not in items or items[target]['type'] == 'label':
                    raise ValueError('label requires an earlier geometric item in its picture')
                if item['side'] not in ('auto','top','bottom','left','right'):
                    raise ValueError('unknown label side')
                text = _text(item['text'], 24)
                candidates = _candidates(_bounds(groups[target]),item['side'],
                    callouts=items[target]['type'] in ('rect','region','object'))
                if items[target]['type']=='axes':
                    candidates = _axis_title_candidates(_bounds(groups[target]),item['side'])
                elif items[target]['type']=='connect':
                    points = groups[target][0]['points']
                    # A side preference cannot detach a label from its actual
                    # connector and make it appear to name another arrow.
                    candidates = lambda box,points=points: _route_label_candidates(
                        points,box,gaps=(12,24,36,48))
                elif items[target]['type'] in ('line','arrow','brace','vline','hline','polyline','plot','area'):
                    command = groups[target][0]
                    points = _primitive(command)[0]
                    preferred = candidates
                    # The actual curve/line is the owner, not an empty corner
                    # of its bounding box. Try arc-local positions first.
                    candidates = lambda box,points=points,preferred=preferred: (
                        _route_label_candidates(points,box)+preferred(box))
                if items[target]['type'] in _CONTOUR_CALLOUT_TYPES:
                    bounds = _bounds(groups[target])
                    point = items[target]['type']=='dot'
                    candidates.fallback = lambda box,bounds=bounds,point=point: corner_callouts(
                        bounds,box,diagonal=point)
                pending.append((item_id,text,candidates))
                commands = []
            elif kind in ('object','connect'):
                commands = lower_symbolic(item,items,groups,frames)
            else:
                commands = _lower(item, frames)
            # Validate dimensions/geometry now, before any joint label search.
            for command in commands: _primitive(command)
            groups[item_id] = commands
            items[item_id] = deepcopy(item)
        for item_id in fresh:
            origins[item_id] = identity+':'+item_id
        geometry_by_family.setdefault(family, []).extend(
            command for item_id in fresh for command in groups[item_id])
        labels_by_family.setdefault(family, []).extend(
            (origins[item_id], text, candidates) for item_id,text,candidates in pending)
        assemblies[identity] = dict(frames=frames,items=items,groups=groups,
            origins=origins,fresh=fresh,pending=[item_id for item_id,_,_ in pending])
    # Reject impossible stages before spending the bounded joint-layout search.
    # Word wrapping changes positions, not glyph stroke count. Leader pointers
    # can only add strokes, so this is a lower bound, never final acceptance.
    label_text = {origin: text for rows in labels_by_family.values()
                  for origin, text, _ in rows}
    for stage_index, panel in enumerate(story['panels'], 1):
        assembly = assemblies[panel['id']]
        geometry_strokes = sum(len(_primitive(command))
            for item_id in assembly['fresh'] for command in assembly['groups'][item_id])
        label_strokes = sum(len(label_paths(label_text[assembly['origins'][item_id]], 18)[0])
            for item_id in assembly['pending'])
        minimum = geometry_strokes + label_strokes
        if minimum > 64:
            raise NativePenBudgetError('panel requires more than 64 strokes before label placement',
                details=dict(resource='strokes', observed=minimum, limit=64,
                    exact=False, scope='stage', stage=stage_index, panel=panel['id'],
                    strokes=minimum, phase='before-label-placement',
                    stroke_breakdown=dict(labels=label_strokes, geometry=geometry_strokes,
                                          complete=False)))
    # Shared ancestors have one placement, even when later panels branch.
    # Geometry from alternative branches is conservatively treated as an
    # obstacle too. No previous snapshot's text is moved during playback.
    placements_by_origin, groups_by_origin = {}, {}
    for family, geometry in geometry_by_family.items():
        attachments = {}
        fallback_attachments = {}
        for identity, assembly in assemblies.items():
            if families[identity] != family:
                continue
            for item_id in assembly['pending']:
                item = assembly['items'].get(item_id)
                if item is None:  # Implicit numeric axis endpoint label.
                    continue
                target = assembly['items'][item['to']]
                if (target['type'] in ('rect', 'region') or
                        (target['type']=='object' and target['shape']=='box')):
                    attachments[assembly['origins'][item_id]] = region_attachment(
                        _bounds(assembly['groups'][item['to']]), geometry)
                elif target['type'] in ('object','shade','dot'):
                    # Point annotations are not axis ticks. Even a nearby
                    # label needs an explicit attachment to its actual dot;
                    # scene clearance prevents a pointer crossing an axis or
                    # a different curve to reach a misleading margin.
                    attachments[assembly['origins'][item_id]] = contour_attachment(
                        assembly['groups'][item['to']], geometry)
                elif target['type'] in _CONTOUR_CALLOUT_TYPES:
                    fallback_attachments[assembly['origins'][item_id]] = contour_attachment(
                        assembly['groups'][item['to']], geometry)
        placed, placements = _place_labels(labels_by_family[family], geometry,
                                            attachments=attachments,
                                            fallback_attachments=fallback_attachments)
        groups_by_origin.update(placed)
        placements_by_origin.update((row['id'],row) for row in placements)
    resolved, total_points = {}, 0
    for panel in story['panels']:
        identity = panel['id']; draft = drafts[identity]; assembly = assemblies[identity]
        frames, items, groups = assembly['frames'], assembly['items'], assembly['groups']
        fresh = assembly['fresh']; base = resolved.get(panel['base'])
        for item_id, origin in assembly['origins'].items():
            if origin in groups_by_origin:
                groups[item_id] = deepcopy(groups_by_origin[origin])
        placements = [dict(deepcopy(placements_by_origin[assembly['origins'][item_id]]), id=item_id)
                      for item_id in assembly['pending']]
        commands = [command for group in groups.values() for command in group]
        _check_label_clearance([dict(op=c['op'], text=c.get('text'), paths=_primitive(c), location=f'item-{i}')
                                for i,c in enumerate(commands)])
        additions = [command for item_id in fresh for command in groups[item_id]]
        delta = compile_lesson([dict(caption=panel['caption'],draw=additions)],
                               story['takeaway'], allow_short=True, procedural=True)
        stage = delta['stages'][0]; stage['id'] = identity; stage['title'] = panel['title']
        plan = deepcopy(delta)
        plan['scene'] = 'panel-'+identity
        plan['stages'] = (deepcopy(base['plan']['stages']) if base else []) + [stage]
        program = compile_storyboard(plan)
        total_points += program['points']
        if total_points > 12000:
            raise NativePenBudgetError('materialized panel snapshots exceed whole-story point budget',
                details=dict(resource='points', observed=total_points, limit=12000,
                             exact=False, scope='story-snapshots', panel=identity))
        resolved[identity] = dict(plan=plan, frames=frames, items=items, groups=groups,
                                  # A coordinate-only frame has no ink bounds.
                                  # Its mapping box remains available in frames.
                                  item_bounds={key:_bounds(groups[key]) if groups[key] else None
                                               for key in items},
                                  new_item_ids=[i['id'] for i in draft['items']],
                                  label_layout=placements, snapshot_points=program['points'],
                                  added_points=stage['points'])
    equation = None
    if 'equation' in story:
        from notebook_equation_ink import equation_plan
        equation = equation_plan(story['equation'])
        total_points += compile_storyboard(equation)['points']
        if total_points > 12000:
            raise NativePenBudgetError('story snapshots and equation exceed whole-story point budget',
                details=dict(resource='points', observed=total_points, limit=12000,
                             exact=True, scope='story-snapshots-and-equation'))
    return dict(kind='offline-panel-story', panels=resolved, snapshot_points=total_points,
                equation_plan=equation,
                geometry_validated=True, native_delivery_supported=False,
                tablet_proven=False, quality_status='unreviewed')
