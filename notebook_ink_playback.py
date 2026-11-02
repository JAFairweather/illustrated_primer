"""Display-only timed strokes, paired with identical persistent native assets.

No input injection. The native client must keep its existing insertion lock,
claim once, show the progressive paths, and commit the ordinary ink asset.
The overlay is transient and must never be reported as saved ink.
"""
import hashlib
import math

from ink import strokes
from notebook_drawing import HAND_STROKES
from notebook_stroke_asset import storyboard_assets
from notebook_pen_budget import NativePenBudgetError

# Renderer-owned pace, doubled on 2026-10-30 (James: writing must be at least twice as fast).
# This is not a model field; the same geometry and 30-second cap still apply.
DEFAULT_VELOCITY = 600
# A child watches a letter land, not each lift of the pen (James, 2026-11-01: speed the writing up dramatically);
# the tablet accepts 10-35 ms and 10-25 ms.
PEN_UP_MS, MINIMUM_STROKE_MS = 12, 10


def _descriptor(data, velocity, most=64):
    if type(velocity) not in (int, float) or not math.isfinite(velocity) or not 50 <= velocity <= 2000:
        raise ValueError('playback velocity must be 50..2000 local units/second')
    paths = [[[x, y] for x, y, _ in path] for _, path, _ in strokes(data)]
    if (not 1 <= len(paths) <= most or sum(map(len, paths)) > 3000 or
            any(len(path) < 2 or any(not math.isfinite(n) for point in path for n in point)
                for path in paths)):
        raise ValueError('playback exceeds existing native geometry limits')
    # Decode the actual asset, not a separately rounded copy of model geometry.
    # A pen-up interval separates strokes; no travel line joins their endpoints.
    duration = sum(max(MINIMUM_STROKE_MS, 1000*sum(math.dist(a,b) for a,b in zip(p,p[1:]))/velocity)
                   for p in paths) + PEN_UP_MS*(len(paths)-1)
    if duration > 30000:
        raise NativePenBudgetError('playback exceeds thirty seconds per stage')
    return dict(version=1, velocity=velocity, pen_up_ms=PEN_UP_MS, minimum_stroke_ms=MINIMUM_STROKE_MS,
                duration_ms=duration, paths=paths)


def playback_assets(plan, author=None, velocity=DEFAULT_VELOCITY):
    assets = storyboard_assets(plan, author)
    for asset in assets:
        asset['playback'] = _descriptor(asset['data'], velocity, HAND_STROKES if plan['scene'].startswith('hand-') else 64)
    return assets


def validate_playback(block, data):
    """Authenticate the transient picture against bytes checked for native paste."""
    playback = block.get('playback')
    if ('reveal' in block or not isinstance(playback,dict) or
            hashlib.sha256(data).hexdigest() != block['sha256']):
        raise ValueError('playback source or insertion mode changed')
    if (type(playback.get('version')) is not int or
            type(block.get('stroke_count')) is not int or type(block.get('point_count')) is not int):
        raise ValueError('playback version/counts require integers')
    expected = _descriptor(data, playback.get('velocity'), HAND_STROKES if block.get('role') == 'hand' else 64)
    if playback != expected:
        raise ValueError('playback must exactly match the persistent native asset')
    if any(type(n) not in (int,float) for path in playback['paths'] for point in path for n in point):
        raise ValueError('playback coordinates require numbers')
    if len(expected['paths']) != block['stroke_count'] or sum(map(len,expected['paths'])) != block['point_count']:
        raise ValueError('playback source counts changed')
    return expected
