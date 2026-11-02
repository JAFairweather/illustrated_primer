"""Resolve explicitly requested object labels before the ordinary ink compiler.

This is opt-in composition, never repair of an explicit `at` label. No shape,
caption, explicit label, stage order or safety limit is changed.
"""
import re

from notebook_lesson import _fields, _primitive, _text
from notebook_storyboard import _dense
from notebook_pen_budget import NativePenBudgetError
from notebook_label_candidates import edge_slides


def _identity(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,23}',value):
        raise ValueError('drawing IDs must be short local lowercase names')
    return value


def resolve_labels(steps, dropped=None):
    """Place anchored labels. With a dropped list, a label that has no clear location is left out (and appended to
    the list as (location, text)) instead of holding the whole lesson; otherwise LabelPlacementError."""
    tagged=False
    for step in steps:
        _fields(step,{'caption','draw'})
        commands=step['draw']
        if not isinstance(commands,list) or not 1<=len(commands)<=32:
            raise ValueError('use 1..32 primitives per step')
        tagged |= any(isinstance(c,dict) and ('id' in c or 'target' in c) for c in commands)
    if not tagged:
        return steps,[]  # Byte-for-byte established interpretation and hashes.

    from notebook_procedural import _place_labels, _route_label_candidates
    resolved=[];targets={};pending=[];geometry=[];reserved=[];total_points=0
    for step_index,step in enumerate(steps):
        commands=[];stage_paths=[];label_strokes=0
        for command_index,original in enumerate(step['draw']):
            if not isinstance(original,dict):
                raise ValueError('drawing commands must be objects')
            command=dict(original)
            if command.get('op')=='label' and 'target' in command:
                _fields(command,{'op','target','text'})
                target=_identity(command['target'])
                if target not in targets:
                    raise ValueError('label target must be a previously drawn non-label primitive')
                if dropped is not None and isinstance(command['text'],str) and len(command['text'])>24:
                    # Too long to anchor: leave it out like a label with no clear location.
                    dropped.append((f'step {step_index+1} command {command_index+1}',command['text']))
                    commands.append([])
                    continue
                text=_text(command['text'],24)
                if len(pending)==12 and dropped is not None:
                    # Keep the first twelve: a retry for a thirteenth cost James's 2026-11-01 replies 20-35 s each.
                    dropped.append((f'step {step_index+1} command {command_index+1}',text))
                    commands.append([])
                    continue
                pending.append((step_index,command_index,target,text,targets[target]))
                if len(pending)>12:
                    raise ValueError('use at most twelve anchored labels per lesson')
                commands.append(None)
                continue
            identity=command.pop('id',None)
            if 'id' in original:
                identity=_identity(identity)
                if command.get('op')=='label' or identity in targets:
                    raise ValueError('drawing IDs must be unique and belong to non-label primitives')
            paths=_primitive(command)  # Strict original grammar after ID removal.
            stage_paths.extend(paths)
            if command['op']=='label':
                label_strokes+=len(paths)
            geometry.append(command)
            points=[p for path in paths for p in path]
            xs,ys=zip(*points)
            bounds=(min(xs),min(ys),max(xs),max(ys))
            if identity is not None:
                closed=command['op'] in ('circle','rect') or (
                    command['op']=='polyline' and paths[0][0]==paths[0][-1])
                targets[identity]=(bounds,closed,paths[0])
            if command['op']=='label':
                # Reserve the whole fixed-label box, not just its glyph ink;
                # another word must not be placed into gaps between letters.
                reserved.append(tuple(v+delta for v,delta in zip(bounds,(-2,-2,2,2))))
            commands.append(command)
        # Reject excessive geometry before running the finite placement search.
        # The full geometry-plus-label budget is checked again by compile_lesson.
        if stage_paths:
            total_points+=sum(map(len,_dense(stage_paths,stage=step_index+1,label_strokes=label_strokes,
                                            stage_complete=all(c is not None for c in commands))))
            if total_points>12000:
                raise NativePenBudgetError('lesson geometry exceeds whole-plan point budget',details=dict(
                    resource='points',observed=total_points,limit=12000,exact=False,
                    scope='lesson',stage=step_index+1))
        resolved.append({'caption':step['caption'],'draw':commands})

    items=[]
    for step_index,command_index,target,text,(bounds,closed,path) in pending:
        identity=f'label-{step_index}-{command_index}'
        def candidates(local_box,bounds=bounds,closed=closed,path=path):
            positions=[] if closed else _route_label_candidates(path,local_box)
            # A label names the whole target, not a tessellation segment.
            # Normals on a winding open path can all point back into other
            # parts of that path. Also search outside its complete bounds.
            # Short straight paths may also have no clear normal candidate
            # when a wider label meets a neighbouring shape. Preserve normal
            # preference, then try the same bounded whole-target perimeter.
            left,top,right,bottom=bounds
            cx,cy=(left+right)/2,(top+bottom)/2
            half_width=(local_box[2]-local_box[0])/2
            local_cy=(local_box[1]+local_box[3])/2
            if closed:
                positions.append((cx,cy-local_cy))
            for gap in (12,24,36):
                positions.extend(((cx,top-gap-local_box[3]),
                                  (cx,bottom+gap-local_box[1]),
                                  (right+gap+half_width,cy-local_cy),
                                  (left-gap-half_width,cy-local_cy)))
            positions.extend(edge_slides(bounds,local_box))
            return positions
        items.append((identity,text,candidates))
    from notebook_procedural import LabelPlacementError
    while True:
        try:
            placed,layout=_place_labels(items,geometry,reserved) if items else ({},[])
            break
        except LabelPlacementError as error:
            if dropped is None:
                raise
            # Leave out the label with no clear location, or the last one when no joint placement exists.
            index=next((k for k,item in enumerate(items) if item[0]==error.identity),len(items)-1)
            step_index,command_index,_,text,_=pending.pop(index)
            items.pop(index)
            resolved[step_index]['draw'][command_index]=[]
            if not any(c for c in resolved[step_index]['draw']):
                raise
            dropped.append((f'step {step_index+1} command {command_index+1}',text))
    provenance=[]
    for (step_index,command_index,target,text,_),record in zip(pending,layout):
        labels=placed[record['id']]
        resolved[step_index]['draw'][command_index]=labels
        provenance.append(dict(target=target,step=step_index+1,command=command_index+1,
                               text=text,lines=record['lines'],label_box=record['label_box'],size=18))
    for step in resolved:
        # Wrapping may yield two labels. Never silently exceed the original
        # per-step command budget; the caller validates the expanded list.
        step['draw']=[c for item in step['draw'] for c in (item if isinstance(item,list) else [item])]
    return resolved,provenance
