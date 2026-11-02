"""Pure, bounded procedural storyboard plans; this module never touches a tablet.

The first supported scene is deliberately specific: integral of x² on [0, 1].
Captions/equations stay separate from drawing paths so they can remain native
notebook text. Stages add ink rather than replacing an earlier raster poster.
Live insertion still requires the caller's request/page/layout safety gates.
"""
import math
from fractions import Fraction
from notebook_pen_budget import NativePenBudgetError

SPARSE_STEP, SPARSE_TOLERANCE = 8, .25  # see notebook_drawing.compile_storyboard's max_step


def _rdp(pts, eps):
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    length = math.hypot(bx-ax, by-ay)
    far, worst = 0, -1.0
    for i in range(1, len(pts)-1):
        # A closed loop has no chord, so it splits at the point farthest from where it starts.
        d = (abs((bx-ax)*(ay-pts[i][1])-(by-ay)*(ax-pts[i][0]))/length if length
             else math.hypot(pts[i][0]-ax, pts[i][1]-ay))
        if d > worst:
            far, worst = i, d
    if worst <= eps:
        return [pts[0], pts[-1]]
    return _rdp(pts[:far+1], eps)[:-1]+_rdp(pts[far:], eps)


def sparse(paths, step=SPARSE_STEP, tolerance=SPARSE_TOLERANCE):
    """paths with as few points as keep each curve within tolerance of the original, and no gap wider than step."""
    out = []
    for path in paths:
        fine = [tuple(path[0])]
        for a, b in zip(path, path[1:]):
            n = max(1, math.ceil(math.dist(a, b)))
            fine.extend((a[0]+(b[0]-a[0])*k/n, a[1]+(b[1]-a[1])*k/n) for k in range(1, n+1))
        kept, sampled = _rdp(fine, tolerance), []
        for a, b in zip(kept, kept[1:]):
            n = max(1, math.ceil(math.dist(a, b)/step))
            sampled.extend((float(a[0]+(b[0]-a[0])*k/n), float(a[1]+(b[1]-a[1])*k/n)) for k in range(n))
        out.append(sampled+[(float(kept[-1][0]), float(kept[-1][1]))])
    return out


def _dense(paths, *, stage=None, label_strokes=None, stage_complete=True):
    result = []
    total = 0
    def exceeded(resource, observed, limit, exact):
        details = dict(resource=resource, observed=observed, limit=limit, exact=exact and stage_complete,
                       scope='stage', strokes=len(paths))
        if stage is not None:
            details['stage'] = stage
        if label_strokes is not None:
            details['stroke_breakdown'] = dict(labels=label_strokes,
                geometry=len(paths)-label_strokes, complete=stage_complete)
        return NativePenBudgetError('storyboard stage exceeds the native pen budget', details=details)
    if len(paths) > 64:
        raise exceeded('strokes',len(paths),64,True)
    for path in paths:
        if len(path) < 2:
            raise ValueError('stroke needs at least two points')
        points = []
        for a, b in zip(path, path[1:]):
            count = max(1, math.ceil(math.dist(a, b) / 2))
            if total + len(points) + count + 1 > 3000:
                # Stop at the same segment as before. This is a lower bound,
                # not a fabricated count for the unvisited rest of the stage.
                raise exceeded('points',total+len(points)+count+1,3000,False)
            points.extend((a[0]+(b[0]-a[0])*i/count, a[1]+(b[1]-a[1])*i/count)
                          for i in range(count))
        points.append(path[-1])
        result.append(points)
        total += len(points)
    if sum(map(len, result)) > 3000 or len(result) > 64:
        raise exceeded('points',sum(map(len,result)),3000,True)
    return result


def integral_storyboard(rectangles=4, width=600, height=300):
    """Return four authored stages, not an arbitrary-expression evaluator.

    Geometry is local to a reserved drawing region. Annotation positions are
    metadata, not rasterized captions or a claim of supported live text APIs.
    """
    if type(rectangles) is not int or not 2 <= rectangles <= 12:
        raise ValueError('use 2..12 rectangles')
    if type(width) is not int or type(height) is not int or not (320 <= width <= 900 and 200 <= height <= 500):
        raise ValueError('storyboard must fit a bounded notebook region')
    left, base, span, rise = 45, height-45, width-100, height-95
    point = lambda x, y: (left+x*span, base-y*rise)
    axes = [[point(0, 1.08), point(0, 0), point(1.08, 0)]]
    curve = [[point(i/64, (i/64)**2) for i in range(65)]]
    bars = []
    for i in range(rectangles):
        a, b, y = i/rectangles, (i+1)/rectangles, (i/rectangles)**2
        if i:  # the first left rectangle has zero height
            bars.append([point(a, 0), point(a, y), point(b, y), point(b, 0)])
    gaps = []
    for x in (.84, .90, .96):
        floor = (int(x*rectangles)/rectangles)**2
        gaps.append([point(x, floor), point(x, x*x)])
    estimate = sum(Fraction(i, rectangles)**2 for i in range(rectangles))/rectangles
    exact = Fraction(1, 3)
    stages = [
        {'id': 'see', 'title': 'See the area',
         'text': 'The integral measures the area under y = x², from x = 0 to x = 1.',
         'paths': _dense(axes+curve),
         'annotations': [{'text': '0', 'point': point(-.025, -.08)},
                         {'text': '1', 'point': point(1, -.08)},
                         {'text': '1', 'point': point(-.05, 1)},
                         {'text': 'y = x²', 'point': point(.55, .8)}]},
        {'id': 'measure', 'title': 'Measure with rectangles',
         'text': f'Use {rectangles} equal slices and the height at each left edge. '
                 f'These rectangles lie below the curve; their total area is {estimate}.',
         'paths': _dense(bars), 'annotations': []},
        {'id': 'notice', 'title': 'Notice what is missing',
         'text': 'The marked gaps are area we missed. Finer slices reduce this underestimate; '
                 'the integral is the limit, not the area of these few rectangles.',
         'paths': _dense(gaps), 'annotations': []},
        {'id': 'conclude', 'title': 'Compute the exact area',
         'text': f'The exact area is {exact}. Our finite rectangle estimate was short by {exact-estimate}.',
         'equation': r'\int_0^1 x^2\,dx=\frac{1}{3}', 'paths': [], 'annotations': []}
    ]
    for stage in stages:
        stage['points'] = sum(map(len, stage['paths']))
        stage['estimated_pen_seconds'] = round(stage['points']*.009 + len(stage['paths'])*.070, 3)
        if stage['estimated_pen_seconds'] > 30:
            raise ValueError('storyboard stage exceeds its drawing-time budget')
    return {'kind': 'native-pen-storyboard-plan', 'scene': 'unit-square-integral',
            'width': width, 'height': height, 'stages': stages,
            'left_sum': str(estimate), 'exact_area': str(exact),
            'live_insertion_supported': False}


def gravity_storyboard(width=600, height=400):
    """An apple's equal-time snapshots: displacement grows as t², not t.

    The diagram is illustrative, not a measured/scale-calibrated trajectory.
    Captions explain that the three positions depict ONE apple over time.
    """
    if type(width) is not int or type(height) is not int or not (320 <= width <= 900 and 300 <= height <= 500):
        raise ValueError('gravity scene must fit a bounded notebook region')
    cx, cy, step, radius = width*.65, height*.20, round(height*.12), 13
    positions = [(cx, cy+step*t*t) for t in (0, 1, 2)]

    def apple(x, y):
        outline = [(x+radius*math.cos(i*math.tau/48)*(1-.1*math.sin(i*math.tau/48)),
                    y+radius*math.sin(i*math.tau/48)) for i in range(49)]
        return [outline, [(x, y-radius), (x+2, y-radius-7)]]

    trunk = width*.18
    tree = [[(trunk-8, height*.9), (trunk-4, height*.45), (trunk, cy-radius-15),
             (cx-50, cy-radius-15), (cx, cy-radius-20), (cx+2, cy-radius-7)],
            [(trunk+8, height*.9), (trunk+10, height*.45)]]
    # Sparse branch leaves, not an expensive filled canopy or raster silhouette.
    for x in (width*.30, width*.43, width*.54):
        y = cy-radius-15
        tree.append([(x, y), (x-10, y-16), (x+6, y-11), (x, y)])
    arrow_x = cx+70
    arrows = [[(arrow_x, cy+5), (arrow_x, cy+70)],
              [(arrow_x-8, cy+59), (arrow_x, cy+70), (arrow_x+8, cy+59)]]
    stages = [
        {'id': 'release', 'title': 'Let go of the apple',
         'text': 'The branch supported the apple. Once it lets go, Earth’s gravity pulls it downward.',
         'paths': _dense(tree+apple(*positions[0])),
         'annotations': [{'text': 't = 0', 'point': (cx+22, cy+5)}]},
        {'id': 'accelerate', 'title': 'Gravity changes its speed',
         'text': 'Ignoring air resistance, the downward acceleration is about 9.8 m/s². '
                 'It gains speed; gravity does not merely give it a constant falling speed.',
         'paths': _dense(arrows),
         'annotations': [{'text': 'gravity', 'point': (arrow_x-40, cy+95)}]},
        {'id': 'compare', 'title': 'Compare equal time intervals',
         'text': 'These are successive snapshots of one apple, not three apples. '
                 'In the second equal time interval it travels three times as far as in the first.',
         'paths': _dense(apple(*positions[1])+apple(*positions[2])),
         'annotations': [{'text': 't = 1', 'point': (cx+22, positions[1][1]+5)},
                         {'text': 't = 2', 'point': (cx+22, positions[2][1]+5)}]},
        {'id': 'conclude', 'title': 'Distance grows as time squared',
         'text': 'From rest, doubling the fall time gives four times the distance in this ideal model. '
                 'The sketch is illustrative, not to scale; gravity is treated as uniform and air resistance omitted.',
         'equation': r's=\frac{1}{2}gt^2', 'paths': [], 'annotations': []}
    ]
    for stage in stages:
        stage['points'] = sum(map(len, stage['paths']))
        stage['estimated_pen_seconds'] = round(stage['points']*.009+len(stage['paths'])*.070, 3)
        if stage['estimated_pen_seconds'] > 30:
            raise ValueError('gravity scene exceeds its drawing-time budget')
    return {'kind': 'native-pen-storyboard-plan', 'scene': 'falling-apple',
            'width': width, 'height': height, 'stages': stages,
            'positions': positions, 'time_units': 'equal illustrative ticks, not measured seconds',
            'live_insertion_supported': False}


def odd_squares_storyboard():
    """A constructive visual proof: odd L borders build successive squares.

    A finite picture illustrates the invariant; the final caption supplies the
    general counting argument, rather than pretending four examples prove it.
    """
    from notebook_shapes import square_growth_layer
    names = ('one','three','five','seven')
    texts = (
        'Start with one unit square: its area is 1.',
        'Add an L of three units. The result is a 2 by 2 square, so 1 + 3 = 4.',
        'The next L has five units. Now the square is 3 by 3: 1 + 3 + 5 = 9.',
        'Seven more units complete 4 by 4. In general, growing to k by k adds '
        'k units along one side and k - 1 along the other: 2k - 1 units. '
        'Thus the first n odd numbers fill an n by n square, with area n².')
    stages = []
    for n,(identity,text) in enumerate(zip(names,texts),1):
        motif = square_growth_layer(n)
        target = motif['anchors']['label_target']
        paths = _dense(motif['paths']+[[(45,target[1]),target]])
        stage = dict(id=identity,title=('One unit','An L of three','An L of five','An L of seven')[n-1],
                     text=text,paths=paths,annotations=[dict(text='1' if n == 1 else '+'+str(2*n-1),
                         point=(10,target[1]+4))],
                     added_units=motif['added_units'],total_units=motif['total_units'],
                     points=sum(map(len,paths)))
        stage['estimated_pen_seconds'] = round(stage['points']*.009+len(paths)*.070,3)
        stages.append(stage)
    stages[-1]['equation'] = r'1+3+5+7=4^2=16'
    return dict(kind='native-pen-storyboard-plan',scene='odd-squares',width=600,height=280,
                stages=stages,layers=[1,3,5,7],exact_area=16,
                general_rule='sum of the first n odd numbers = n²',live_insertion_supported=False)
