"""Line-art frames to a staged native pen picture: clean, diff, vectorize, order, budget.

Each frame is the whole picture so far (a base drawing, then each edit applied to the one before). Every stage of
the plan holds only the ink that its frame added, so the picture builds up on the page one step at a time. Frames
are untrusted pixels; only the resulting pen paths, bounded by the native stage budgets, leave this module.
"""
import hashlib
import io
import math

import numpy as np
from PIL import Image

from ink import thin, trace, rdp
from notebook_drawing import compile_storyboard
from notebook_storyboard import sparse, SPARSE_STEP

WIDTH, HEIGHT, MARGIN = 1100, 480, 10  # most of the 1140 x 500 a native region may take: detail reads at page scale
STAGE_POINTS, STAGE_STROKES, PICTURE_POINTS = 3000, 64, 12000
TOLERANCE = 3  # px an edit may redraw an old line by before it counts as new ink
SPILL = 3  # native blocks one frame may draw across: each holds 64 strokes, so a rich base frame needs several
BLOCKS = 6  # drawing blocks a lesson may hold (notebook_stroke_asset.validate_native_ink_budget)
FRAME_STROKES = 48  # a frame keeps its longest lines: an explainer doodle reads from its outlines, not its details
VELOCITY = 1800  # local units/second a picture plays back at: a rich base frame still draws within 30 s
SOLID = 5  # px ink must stay inked when shrunk by to count as a filled shape (a black raven), not a line
HATCH = 5  # px between the hatch lines that shade a filled shape
SHADE_STROKES = 16  # zigzags one frame's filled shapes may take


def _grey(png):
    im = Image.open(io.BytesIO(png))
    im.load()
    if im.width*im.height > 4096*4096:
        raise ValueError('frame too large')
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        flat = Image.new('RGBA', im.size, 'white')
        flat.alpha_composite(im)
        im = flat
    return np.asarray(im.convert('L'), dtype=np.float32)


def _otsu(a):
    hist = np.bincount(a.astype(np.uint8).ravel(), minlength=256).astype(float)
    p = hist/hist.sum()
    omega, mu = np.cumsum(p), np.cumsum(p*np.arange(256))
    with np.errstate(divide='ignore', invalid='ignore'):
        between = (mu[-1]*omega-mu)**2/(omega*(1-omega))
    return float(np.nanargmax(between))


def components(mask):
    """The 8-connected ink groups of mask, each a list of (y, x)."""
    seen = np.zeros_like(mask)
    h, w = mask.shape
    groups = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        group, stack = [], [(y, x)]
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            group.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy+dy, cx+dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        groups.append(group)
    return groups


def despeck(mask, minimum):
    """mask without the 8-connected specks smaller than minimum pixels."""
    out = mask.copy()
    for group in components(mask):
        if len(group) < minimum:
            ys, xs = zip(*group)
            out[list(ys), list(xs)] = False
    return out


def dilate(mask, r):
    out = mask.copy()
    padded = np.pad(mask, r)
    h, w = mask.shape
    for dy in range(-r, r+1):
        for dx in range(-r, r+1):
            out |= padded[r+dy:r+dy+h, r+dx:r+dx+w]
    return out


def clean(frames, width=WIDTH, height=HEIGHT, margin=MARGIN, fit=False):
    """Each frame as a boolean ink mask of width x height, all cropped and scaled alike to fit inside the margins;
    with fit, also the map from a frame's 0..1000 box to the masks' pixels."""
    greys = [_grey(f) for f in frames]
    if len({g.shape for g in greys}) != 1:
        raise ValueError('frames must share one size')
    cut = _otsu(greys[-1])
    inked = [g <= min(cut, 200) for g in greys]
    union = np.logical_or.reduce(inked)
    if not union.any():
        raise ValueError('no ink in the frames')
    ys, xs = np.nonzero(union)
    y0, y1, x0, x1 = ys.min(), ys.max()+1, xs.min(), xs.max()+1
    scale = min((width-2*margin)/(x1-x0), (height-2*margin)/(y1-y0))
    w, h = max(1, round((x1-x0)*scale)), max(1, round((y1-y0)*scale))
    ox, oy = (width-w)//2, (height-h)//2
    masks = []
    for ink in inked:
        # Shrink the full-size ink, not the grey, and keep pixels a quarter covered, so fine lines survive.
        cover = Image.fromarray((ink[y0:y1, x0:x1]*255).astype(np.uint8)).resize((w, h), Image.BOX)
        m = np.zeros((height, width), bool)
        m[oy:oy+h, ox:ox+w] = np.asarray(cover) >= 64
        masks.append(despeck(m, 6))
    if fit:
        fh, fw = greys[0].shape
        def box(b):
            ymin, xmin, ymax, xmax = b
            return ((xmin*fw/1000-x0)*scale+ox, (ymin*fh/1000-y0)*scale+oy,
                    (xmax*fw/1000-x0)*scale+ox, (ymax*fh/1000-y0)*scale+oy)
        return masks, box
    return masks


def lost_share(previous, current):
    """The share of previous frame's ink that current no longer has: a large one means current redrew the picture."""
    before, after = clean([previous, current])
    return float((before & ~dilate(after, TOLERANCE)).sum())/max(1, int(before.sum()))


def new_ink(previous, current, tolerance=TOLERANCE):
    """The ink current adds to previous; lines an edit merely redrew nearby stay old."""
    return despeck(current & ~dilate(previous, tolerance), 8)


def solids(mask, r=SOLID):
    """The filled shapes of mask: the ink that survives shrinking by r, grown back out to its own edges."""
    return dilate(~dilate(~mask, r), r) & mask


def hatch(solid, step=HATCH):
    """Diagonal hatching inside solid, a line every step px, joined into zigzags wherever the turn stays inside, so
    a black shape reads dark in a few strokes. The longest zigzags first."""
    h, w = solid.shape
    inner = ~dilate(~solid, 1)  # the hatch stops short of the outline that is drawn around the shape
    if not inner.any():
        return []
    d, n = np.array([1.0, -1.0])/math.sqrt(2), np.array([1.0, 1.0])/math.sqrt(2)
    reach = math.hypot(w, h)

    def inside(points, region=inner):
        xs, ys = np.round(points[:, 0]).astype(int), np.round(points[:, 1]).astype(int)
        ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        out = np.zeros(len(points), bool)
        out[ok] = region[ys[ok], xs[ok]]
        return out

    t = np.arange(-reach, reach)
    lines = []
    for k in np.arange(0, reach, step):
        points = k*n+t[:, None]*d
        hit = inside(points)
        edges = np.flatnonzero(np.diff(np.concatenate([[0], hit.astype(int), [0]])))
        lines.append([(points[a], points[b-1]) for a, b in zip(edges[::2], edges[1::2]) if b-a >= 3])
    done, open_ = [], []  # open_: zigzags still growing, each [points, end, direction]
    for runs in lines:
        grown = []
        for a, b in runs:
            best = None
            for z in open_:
                start, stop = (b, a) if z[2] > 0 else (a, b)  # each line runs the other way along the zigzag
                gap = z[1]-start
                # The turn may graze the outline (it is drawn over anyway), but not cross white.
                if math.hypot(*gap) <= 3*step and inside(np.linspace(z[1], start, 8), solid).all():
                    best = (z, start, stop)
                    break
            if best:
                z, start, stop = best
                open_.remove(z)
                z[0] += [tuple(start), tuple(stop)]
                z[1], z[2] = stop, -z[2]
                grown.append(z)
            else:
                grown.append([[tuple(a), tuple(b)], b, 1])
        done += [z[0] for z in open_]
        open_ = grown
    done += [z[0] for z in open_]
    paths = [[(float(x), float(y)) for x, y in p] for p in done]
    return sorted((p for p in paths if _length(p) >= 3*step), key=_length, reverse=True)  # a stub reads as a speck


def _length(path):
    return sum(math.dist(a, b) for a, b in zip(path, path[1:]))


def _points(path):
    """Points this path costs once sampled for the pen (see notebook_storyboard.sparse)."""
    return len(sparse([path])[0])


def linemerge(paths, tolerance=3.0):
    """Join paths whose ends meet, so the pen lifts less."""
    paths = [list(p) for p in paths]
    if not paths:
        return []
    heads = np.array([p[0] for p in paths], float)
    tails = np.array([p[-1] for p in paths], float)
    alive = np.ones(len(paths), bool)
    out = []
    for i in range(len(paths)):
        if not alive[i]:
            continue
        alive[i] = False
        current = paths[i]
        for _ in range(2):  # grow the tail, then turn round and grow the other end
            while alive.any():
                end = np.array(current[-1], float)
                to_head = np.where(alive, np.hypot(*(heads-end).T), np.inf)
                to_tail = np.where(alive, np.hypot(*(tails-end).T), np.inf)
                j, k = int(to_head.argmin()), int(to_tail.argmin())
                if min(to_head[j], to_tail[k]) > tolerance:
                    break
                if to_head[j] <= to_tail[k]:
                    current = current+paths[j][1:]
                else:
                    j = k
                    current = current+paths[j][::-1][1:]
                alive[j] = False
            current.reverse()
        out.append(current)
    return out


def order(paths, start=(0.0, 0.0)):
    """Greedy nearest-end order, reversing a path when its far end is closer, so the pen travels little."""
    left, out, at = [list(p) for p in paths], [], start
    while left:
        best = min(range(len(left)), key=lambda i: min(math.dist(at, left[i][0]), math.dist(at, left[i][-1])))
        path = left.pop(best)
        if math.dist(at, path[-1]) < math.dist(at, path[0]):
            path.reverse()
        out.append(path)
        at = path[-1]
    return out


def smooth(path, window=5):
    """A moving average along the path, ends pinned, so a traced edge loses its pixel staircase."""
    if len(path) <= 2:
        return path
    a = np.array(path, float)
    closed = math.dist(path[0], path[-1]) <= 1.5
    k = window//2
    padded = np.concatenate([a[-k-1:-1], a, a[1:k+1]]) if closed else np.pad(a, ((k, k), (0, 0)), mode='edge')
    out = np.stack([np.convolve(padded[:, i], np.ones(window)/window, mode='valid') for i in (0, 1)], 1)
    if not closed:
        out[0], out[-1] = a[0], a[-1]
    return [(float(x), float(y)) for x, y in out]


def vectorize(mask, eps=1.5, shortest=16.0):
    """Skeleton polylines of mask, thinned by Ramer-Douglas-Peucker; paths shorter than shortest are dropped."""
    mask, dots = mask.copy(), []
    for group in components(mask):
        ys, xs = zip(*group)
        h, w = max(ys)-min(ys)+1, max(xs)-min(xs)+1
        # A solid dot, an eye or a pupil: thinning would leave a scrawl. A disc fills ~78% of its box; a sliver an edit
        # left by redrawing a line is long or half empty, and stays a line.
        if max(h, w) <= 24 and max(h, w) <= 2*min(h, w) and len(group) >= .65*h*w:
            mask[list(ys), list(xs)] = False
            cx, cy = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
            rx, ry = max(1.5, w/2-.5), max(1.5, h/2-.5)
            # A spiral in to the centre, one turn per unit of radius, so the dot reads as solid ink, not a ring.
            n = 12*math.ceil(max(rx, ry))
            dots.append([(float(cx+rx*(1-k/n)*math.cos(k*math.pi/6)), float(cy+ry*(1-k/n)*math.sin(k*math.pi/6)))
                         for k in range(n)])
    # A filled shape is drawn as its outline, the edges of any white detail inside it included; thinning it would
    # leave a scrawl down its middle. raster_plan hatches its inside.
    solid = solids(mask)
    edge = solid & dilate(~solid, 1)
    lines = (mask & ~dilate(solid, 1)) | edge
    paths = [rdp(smooth([(float(x), float(y)) for x, y in p]), eps) for p in trace(thin(lines))]
    paths = linemerge(paths)
    return [p for p in paths if len(p) >= 2 and _length(p) >= shortest]+dots


def budget(paths, points=STAGE_POINTS, strokes=STAGE_STROKES):
    """The longest paths that fit one stage's point, stroke and 30 s pen-time budgets, in their original order.

    Pen time is checked both ways the stage is judged: the compiler's per-point estimate and the playback length."""
    keep, used, seconds = set(), 0, 0.0
    for i in sorted(range(len(paths)), key=lambda i: -_length(paths[i])):
        cost, time = _points(paths[i]), max(.025, _length(paths[i])/VELOCITY)
        n = len(keep)+1
        if n > strokes or used+cost > points or (used+cost)*.009+n*.070 > 29 or seconds+time+n*.070 > 29:
            continue
        keep.add(i)
        used += cost
        seconds += time
    return [p for i, p in enumerate(paths) if i in keep]


LABEL_SIZE, LABEL_GAP = 20, 12  # lettered label height and its clearance from ink, in plan units


def _label_rect(x, y, w):
    return (x, y, x+w, y+LABEL_SIZE)


def _free(rect, ink, taken, width, height):
    x0, y0, x1, y1 = rect
    if x0 < 2 or y0 < 2 or x1 > width-2 or y1 > height-2:
        return False
    if any(not (x1 < a or a1 < x0 or y1 < b or b1 < y0) for a, b, a1, b1 in taken):
        return False
    g = LABEL_GAP//2
    return not ink[max(0, int(y0)-g):int(y1)+g, max(0, int(x0)-g):int(x1)+g].any()


def place_labels(names, boxes, ink, width=WIDTH, height=HEIGHT, taken=None):
    """Pen paths lettering each name in clear space beside its box, with a short line pointing at the box, and the
    rects they take. ink is the finished picture's mask; taken, the rects earlier labels hold. A name with no box, or
    no clear space within reach, is left out."""
    from notebook_plotter_font import label_paths
    taken, paths, placed = list(taken or []), [], []
    for name in names:
        if name not in boxes:
            continue
        bx0, by0, bx1, by1 = boxes[name]
        glyphs, w = label_paths(name, LABEL_SIZE)
        cx, cy = (bx0+bx1)/2, (by0+by1)/2
        spot = None
        for reach in (LABEL_GAP, 40, 80, 130):
            for x, y in ((bx1+reach, cy-LABEL_SIZE/2), (bx0-reach-w, cy-LABEL_SIZE/2), (cx-w/2, by0-reach-LABEL_SIZE),
                         (cx-w/2, by1+reach), (bx1+reach, by0-reach-LABEL_SIZE), (bx0-reach-w, by0-reach-LABEL_SIZE),
                         (bx1+reach, by1+reach), (bx0-reach-w, by1+reach)):
                if _free(_label_rect(x, y, w), ink, taken, width, height):
                    spot = (x, y)
                    break
            if spot:
                break
        if not spot:
            continue
        x, y = spot
        rect = _label_rect(x, y, w)
        # The pointer runs from the label's nearest edge to the nearest ink inside the box, stopping short of both.
        lx, ly = min(max(cx, rect[0]), rect[2]), min(max(cy, rect[1]), rect[3])
        tx, ty = _nearest_ink(ink, boxes[name], (lx, ly))
        gap = math.dist((lx, ly), (tx, ty))
        pointer = None
        if gap > 2*LABEL_GAP:
            ux, uy = (tx-lx)/gap, (ty-ly)/gap
            pointer = [(lx+ux*5, ly+uy*5), (tx-ux*6, ty-uy*6)]
            if any(_crosses(pointer, r) for r in taken):
                continue
        taken.append(rect)
        placed.append(name)
        paths += [[(x+px, y+py) for px, py in glyph] for glyph in glyphs]
        if pointer:
            paths.append(pointer)
    return paths, taken, placed


def _nearest_ink(ink, box, point):
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    ys, xs = np.nonzero(ink[max(0, y0):max(0, y1)+1, max(0, x0):max(0, x1)+1])
    if not len(xs):
        return min(max(point[0], x0), x1), min(max(point[1], y0), y1)
    i = int(np.argmin((xs+max(0, x0)-point[0])**2+(ys+max(0, y0)-point[1])**2))
    return float(xs[i]+max(0, x0)), float(ys[i]+max(0, y0))


def _crosses(segment, rect):
    (ax, ay), (bx, by) = segment
    x0, y0, x1, y1 = rect
    return any(x0 <= ax+(bx-ax)*k/20 <= x1 and y0 <= ay+(by-ay)*k/20 <= y1 for k in range(21))


def _overlap(a, b):
    w = min(a[2], b[2])-max(a[0], b[0])
    h = min(a[3], b[3])-max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w*h/min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))


def raster_plan(frames, captions, width=WIDTH, height=HEIGHT, total=PICTURE_POINTS, blocks=BLOCKS, labels=None,
                scenes=False):
    """A storyboard plan drawing each frame's added ink in one to SPILL stages, each stage marked with its frame and
    whether it continues the one before, within total points and blocks native blocks. labels, one list of
    (name, 0..1000 box) per frame, are lettered beside what they name in the stage that draws it. With scenes, each
    frame is a whole picture of its own, cropped to itself and drawn entire in a scene of its own, so the tablet puts
    it below the text written before it. Returns (plan, report)."""
    if not 1 <= len(frames) == len(captions) <= blocks:
        raise ValueError('one caption per frame, 1..6 frames')
    if scenes:
        cleaned = [clean([f], width, height, fit=True) for f in frames]
        masks, fits = [m[0] for m, _ in cleaned], [fit for _, fit in cleaned]
    else:
        masks, fit = clean(frames, width, height, fit=True)
        fits = [fit]*len(masks)
    labels, taken, claimed = list(labels or [])[:len(masks)], [], []
    drawn_ink = np.logical_or.reduce(masks)  # the pen cannot erase, so labels clear everything any frame draws
    stages, report, at = [], [], (0.0, 0.0)
    previous = np.zeros_like(masks[0])
    for index, (mask, caption) in enumerate(zip(masks, captions)):
        if scenes:  # nothing drawn before it shares its paper
            previous, drawn_ink, taken, claimed = np.zeros_like(mask), mask, [], []
        added = new_ink(previous, mask) if index and not scenes else mask
        found = vectorize(added)
        longest = set(sorted(range(len(found)), key=lambda i: -_length(found[i]))[:FRAME_STROKES])
        found = [p for i, p in enumerate(found) if i in longest]
        found += hatch(solids(added))[:SHADE_STROKES]
        share = (total-sum(r['points'] for r in report))//(len(masks)-index)
        # The longest lines first, so each frame's outlines are drawn before its details; a frame with more lines than
        # one block holds continues in up to SPILL blocks, the later ones uncaptioned.
        left, chunks = list(found), []
        while left and len(chunks) < SPILL and len(stages)+len(chunks) < blocks-(len(masks)-index-1):
            chunk = budget(left, min(STAGE_POINTS, share-sum(map(_points, sum(chunks, [])))))
            if not chunk:
                break
            chunks.append(chunk)
            drawn = {id(p) for p in chunk}
            left = [p for p in left if id(p) not in drawn]
        named, lettered, placed, merge = (labels[index] if index < len(labels) else []), [], [], False
        # Two names the vision model located on the same thing (both arms on the whole plank) would point at nothing
        # in particular, so only the first keeps it.
        named = [(n, fits[index](b)) for n, b in named]
        named = [(n, b) for i, (n, b) in enumerate(named) if not any(_overlap(b, c) > .8 for _, c in claimed+named[:i])]
        claimed += named
        if named:
            lettered, held, placed = place_labels([n for n, _ in named], dict(named), drawn_ink,
                                                  width, height, taken)
            # Labels ride in the frame's last block when they fit its stroke budget, else in one more block.
            merge = bool(chunks) and len(chunks[-1])+len(lettered) <= STAGE_STROKES
            if lettered and not merge:
                if len(stages)+len(chunks) < blocks-(len(masks)-index-1):
                    chunks.append([])
                else:
                    lettered, placed = [], []
            if lettered:
                taken = held
        kept_paths = []
        for part, chunk in enumerate(chunks):
            chunk = order(chunk, at) if chunk else []
            if part == len(chunks)-1:
                chunk = chunk+lettered
            at = chunk[-1][-1]
            paths = sparse([[(float(min(max(x, 0), width)), float(min(max(y, 0), height))) for x, y in p] for p in chunk])
            stages.append(dict(id=f'step-{index+1}' + (f'-{part+1}' if part else ''), title=caption[:160], text=caption,
                               paths=paths, annotations=[], frame=index, continued=bool(part),
                               **({'scene': 'lesson-'+hashlib.sha256(b'%d' % index+frames[index]).hexdigest()[:24]}
                                  if scenes else {})))
            kept_paths += chunk[:len(chunk)-len(lettered)] if part == len(chunks)-1 else chunk
        # Ink the frame took away: pen ink cannot be erased, so a large share means the model redrew the picture.
        lost = previous & ~dilate(mask, TOLERANCE)
        report.append(dict(stage=index, found=len(found), kept=len(kept_paths), blocks=len(chunks),
                           **({'labels': len(named), 'lettered': len(placed)} if named else {}),
                           points=sum(len(p) for st in stages if st['frame'] == index for p in st['paths']),
                           removed=round(float(lost.sum())/max(1, int(previous.sum())), 3),
                           dropped_length=round(sum(map(_length, found))-sum(map(_length, kept_paths)))))
        previous = mask
    digest = hashlib.sha256(b''.join(hashlib.sha256(f).digest() for f in frames)).hexdigest()[:24]
    plan = dict(kind='native-pen-storyboard-plan', scene='lesson-'+digest, width=width, height=height,
                max_step=SPARSE_STEP, velocity=VELOCITY, stages=stages)
    compile_storyboard(plan)
    return plan, report
