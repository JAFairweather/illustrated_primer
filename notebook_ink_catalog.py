"""Trusted immutable native source-page catalog, not model-supplied geometry.

Agent markers select an authored scene/stage. They cannot name files, UUIDs,
coordinates, scripts or URLs. The runtime still must verify source bytes and
obtain a real request/page/layout/input lease before any foreground insertion.
"""
import copy
import json
import math
from pathlib import Path
import re
import uuid

from notebook_drawing import compile_storyboard
from notebook_storyboard import integral_storyboard, gravity_storyboard, odd_squares_storyboard


FACTORIES = {'unit-square-integral': integral_storyboard, 'falling-apple': gravity_storyboard,
             'odd-squares': odd_squares_storyboard}


class InkCatalog:
    def __init__(self, manifest):
        if (not isinstance(manifest, dict) or set(manifest) != {'version', 'scenes'} or
                type(manifest['version']) is not int or manifest['version'] != 1 or
                not isinstance(manifest['scenes'], dict) or not 1 <= len(manifest['scenes']) <= 4):
            raise ValueError('bounded native ink source manifest required')
        self.scenes = {}
        for scene, data in manifest['scenes'].items():
            if scene not in FACTORIES or not isinstance(data, dict) or set(data) != {'digest', 'stages'}:
                raise ValueError('unknown authored native scene')
            plan = FACTORIES[scene]()
            program = compile_storyboard(plan)
            stages = {stage['id'] for stage in plan['stages'] if stage['paths'] or stage.get('annotations')}
            if data['digest'] != program['digest'] or not isinstance(data['stages'], dict) or set(data['stages']) != stages:
                raise ValueError('native source manifest does not match its authored program')
            checked = {}
            for stage, asset in data['stages'].items():
                fields = {'source_doc', 'source_page', 'sha256', 'stroke_count', 'point_count', 'bounds', 'labels'}
                if not isinstance(asset, dict) or set(asset) != fields:
                    raise ValueError('invalid native source descriptor')
                for key in ('source_doc', 'source_page'):
                    if not isinstance(asset[key], str) or str(uuid.UUID(asset[key])) != asset[key]:
                        raise ValueError('source descriptor requires canonical UUIDs')
                if not isinstance(asset['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', asset['sha256']):
                    raise ValueError('native source digest required')
                if (type(asset['stroke_count']) is not int or not 1 <= asset['stroke_count'] <= 64 or
                        type(asset['point_count']) is not int or not 2 <= asset['point_count'] <= 3000 or
                        asset['labels'] != 'ink-labels'):
                    raise ValueError('native source counts or explicit label policy invalid')
                box = asset['bounds']
                if (not isinstance(box, list) or len(box) != 4 or
                        any(type(n) not in (int, float) or not math.isfinite(n) for n in box) or
                        not (0 <= box[0] <= box[2] <= plan['width'] and 0 <= box[1] <= box[3] <= plan['height'])):
                    raise ValueError('native source bounds exceed authored geometry')
                checked[stage] = copy.deepcopy(asset)
            self.scenes[scene] = dict(digest=data['digest'], stages=checked,
                                      width=plan['width'], height=plan['height'],
                                      order=[stage['id'] for stage in plan['stages'] if stage['id'] in stages])

    def get(self, scene, stage):
        try:
            data = self.scenes[scene]
            asset = data['stages'][stage]
        except (KeyError, TypeError):
            raise ValueError('native ink scene/stage is not registered') from None
        return dict(copy.deepcopy(asset), scene=scene, stage=stage, digest=data['digest'],
                    width=data['width'], height=data['height'],
                    stage_index=data['order'].index(stage), stage_count=len(data['order']))


def load_catalog(path):
    """Configuration is bounded; absent catalog is unavailable, never a fallback."""
    with Path(path).open('rb') as stream:
        data = stream.read(16385)
    if len(data) > 16384:
        raise ValueError('native source catalog is too large')
    return InkCatalog(json.loads(data))
