"""Compile a whole validated lesson to bounded paced native motion, offline.

This is the bridge between procedural scene geometry and a future protected
native adapter. It never opens input, calls the tablet, or grants a page lock.
"""
import hashlib
import json
import math

from notebook_drawing import compile_storyboard
from notebook_pen_motion import sample_motion_path,motion_chunks


def compile_motion_program(plan,pixels_per_second=240):
    """Preserve lesson order and geometry; derive motion duration from length.

    Coordinates remain local to the validated diagram region. The eventual
    adapter must validate its scene-to-display mapping before any emission.
    Very short paths have a 0.1s minimum for the diagnostic helper. Time budget
    is a planning bound, not a promise about transport or telemetry latency.
    """
    if (type(pixels_per_second) not in (int,float) or
            not math.isfinite(pixels_per_second) or not 50<=pixels_per_second<=1000):
        raise ValueError('pen speed must be within 50..1000 local units per second')
    source=compile_storyboard(plan)  # Entire lesson must pass before expansion.
    operations=[];budgets={};total=0
    for op in source['operations']:
        stage=budgets.setdefault(op['stage'],dict(points=0,contacts=0,motion_seconds=0))
        if op['kind']!='stroke':
            operations.append(op)
            continue
        path=sample_motion_path(op['path'])
        length=sum(math.dist(a,b) for a,b in zip(path,path[1:]))
        duration=max(.1,length/pixels_per_second)
        contacts=motion_chunks(path,duration)
        # Count actual emitted contact points, including shared joint copies.
        points=sum(len(contact['points']) for contact in contacts)
        stage['points']+=points;stage['contacts']+=len(contacts)
        stage['motion_seconds']+=duration;total+=points
        cost=max(stage['points']*.009,stage['motion_seconds'])+stage['contacts']*.070
        if stage['points']>3000 or stage['contacts']>64 or total>12000 or cost>30:
            raise ValueError('expanded motion exceeds lesson point/stroke/time budget')
        stage['estimated_pen_seconds']=cost
        operations.append(dict(kind='motion_stroke',stage=op['stage'],stroke=op['stroke'],
                               length=length,motion_seconds=duration,contacts=contacts))
    result=dict(kind='native-pen-motion-program',scene=source['scene'],width=source['width'],
                height=source['height'],source_digest=source['digest'],
                coordinate_space='local-diagram',pixels_per_second=pixels_per_second,
                short_stroke_min_seconds=.1,operations=operations,stage_budgets=budgets,
                points=total,live_insertion_supported=False)
    result['digest']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    return result
