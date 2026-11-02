"""Reply words written out in a hand, as renderer-owned ink regions the tablet plays back stroke by stroke.

Each region is a separate 1140-wide scene holding as many whole lines as the native budgets allow (HAND_STROKES
strokes, 3000 points, 30 s pen time). Points are spaced by curvature rather than every 2 units, so a region holds several lines. A word too wide for a line, or a glyph neither the hand nor the plotter
letters have, is refused here, so the caller can keep the words typed instead.
"""
import hashlib
import math

from notebook_drawing import compile_storyboard, HAND_STROKES
from notebook_handwriting import handwriting_paths, HANDS
from notebook_storyboard import sparse as _sampled, SPARSE_STEP as STEP

WIDTH, MARGIN, TOP = 1140, 20, 12  # the widest native region: wider than the 936 typed column, inside safe paper
SIZE = 32  # about the cap height of the typed reply text on the page
HEIGHT = 500  # tallest native region
REGIONS = 6  # per passage; longer words stay typed
VELOCITY = 2000  # local units/second: the most the tablet plays back; a child reads the line as it lands
# A pen writes typographic punctuation as the plain marks.
PLAIN = str.maketrans({'\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2013': '-', '\u2014': ' - ',
                       '\u2026': '...'})


def _fits(paths):
    """Whether paths fit one handwritten region: HAND_STROKES strokes, 3000 points and 29 s of timed playback (the
    tablet's cap is 30 s, with a 35 ms pen lift between strokes; twice that is allowed here)."""
    sampled = _sampled(paths)
    points = sum(map(len, sampled))
    playback = sum(max(.05, sum(math.dist(a, b) for a, b in zip(p, p[1:]))/VELOCITY) for p in sampled)
    return len(sampled) <= HAND_STROKES and points <= 3000 and playback + .07*len(sampled) <= 29


def hand_lines(text, size=SIZE, hand='primer', width=WIDTH-2*MARGIN):
    """Greedy word wrap; a line must fit the margins and, on its own, one native stage."""
    def fits(line):
        strokes, advance = handwriting_paths(line, size, hand=hand)
        return advance <= width and _fits(strokes)
    lines, current = [], ''
    for word in text.translate(PLAIN).split():
        trial = f'{current} {word}' if current else word
        if fits(trial):
            current = trial
            continue
        if not current or not fits(word):
            raise ValueError('a word is too wide for a handwritten line')
        lines.append(current)
        current = word
    if not current:
        raise ValueError('handwritten text required')
    return lines + [current]


def hand_plans(text, hand='primer', size=SIZE, place=0):
    """Storyboard plans, one per region, in reading order. Raises ValueError when the words cannot be written.

    place tells passages of one reply apart, so two identical captions still get distinct scenes."""
    if hand not in HANDS:
        raise ValueError('unknown hand')
    lead = round(1.7*size)  # baseline to baseline; capitals stand one size tall, loops and tails reach past it
    groups, current = [], []
    for line in hand_lines(text, size, hand):
        strokes, _ = handwriting_paths(line, size, hand=hand)
        if (current and 2*TOP + len(current)*lead + 1.5*size <= HEIGHT and
                _fits([p for group in current + [strokes] for p in group])):
            current.append(strokes)
            continue
        if current:
            groups.append(current)
        current = [strokes]
    groups.append(current)
    if len(groups) > REGIONS:
        raise ValueError('too many words to write by hand')
    plans = []
    for index, group in enumerate(groups):
        paths = [[(MARGIN+x, TOP+row*lead+y) for x, y in path] for row, strokes in enumerate(group) for path in strokes]
        bottom = max(y for path in paths for _, y in path)
        digest = hashlib.sha256(f'{hand}:{size}:{place}:{index}:{text}'.encode()).hexdigest()[:24]
        plan = dict(kind='native-pen-storyboard-plan', scene='hand-'+digest, width=WIDTH,
                    height=max(200, math.ceil(bottom)+TOP), max_step=STEP,
                    stages=[dict(id='hand', title='Handwriting', text='Read the handwritten words.',
                                 paths=_sampled(paths), annotations=[])])
        compile_storyboard(plan)
        plans.append(plan)
    return plans


def _curl(cx, cy, radius, turns, start, sign):
    """A spiral curling inward from radius at angle start, sign 1 clockwise on the page."""
    steps = max(8, int(24*turns))
    return [(cx+radius*(1-.75*k/steps)*math.cos(start+sign*2*math.pi*turns*k/steps),
             cy+radius*(1-.75*k/steps)*math.sin(start+sign*2*math.pi*turns*k/steps)) for k in range(steps+1)]


def end_plan(hand='primer', size=44, place=0):
    """'The End' centred in the hand with a small scroll under it, as a fairy tale ends (James, 2026-10-30).
    Raises ValueError when the hand cannot write it."""
    if hand not in HANDS:
        raise ValueError('unknown hand')
    strokes, advance = handwriting_paths('The End', size, hand=hand)
    left = (WIDTH-advance)/2
    paths = [[(left+x, TOP+y) for x, y in path] for path in strokes]
    base = max(y for path in paths for _, y in path)+size*.45
    # The scroll: a gentle wave a little wider than the words, curling under at each end.
    x0, x1, amp = left-size*.6, left+advance+size*.6, size*.12
    wave = [(x0+(x1-x0)*k/40, base+amp*math.sin(math.pi*2*k/40)) for k in range(41)]
    r = size*.28
    head = list(reversed(_curl(x0, base+r, r, 1.1, -math.pi/2, -1)))
    tail = _curl(x1, base+r, r, 1.1, -math.pi/2, 1)
    paths += [head+wave+tail]
    bottom = max(y for path in paths for _, y in path)
    digest = hashlib.sha256(f'end:{hand}:{size}:{place}'.encode()).hexdigest()[:24]
    plan = dict(kind='native-pen-storyboard-plan', scene='hand-'+digest, width=WIDTH,
                height=max(200, math.ceil(bottom)+TOP), max_step=STEP,
                stages=[dict(id='hand', title='Handwriting', text='The End.', paths=_sampled(paths), annotations=[])])
    if not _fits(paths):
        raise ValueError('the ending does not fit one handwritten region')
    compile_storyboard(plan)
    return plan
