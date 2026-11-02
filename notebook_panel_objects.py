"""Bounded symbolic object/relationship panels, without mathematical axes.

Reuse the established procedural contours and connector routing. Position
names describe composition, never pen coordinates. Existing groups are read
only: additions cannot move old shapes, lettering or connector paths.
"""
from notebook_contract_feedback import item_fields
from notebook_story_plan import _id
from notebook_procedural import _object, _object_ports, _bounds, _hits, _route


SHAPES = ('circle', 'box', 'person', 'sun', 'cloud', 'water')
POSITIONS = {row+'-'+column: (100+200*x,85+170*y)
             for y,row in enumerate(('top','bottom'))
             for x,column in enumerate(('left','center','right'))}


def lower_symbolic(item, items, groups, frames):
    """Lower one new object or connection; no mutation or model-side sampling."""
    if frames:
        raise ValueError('symbolic objects and mathematical axes need separate pictures')
    kind = item.get('type')
    item_fields(item)
    if kind == 'object':
        shape, position = item['shape'], item['position']
        if not isinstance(shape,str) or shape not in SHAPES:
            raise ValueError('unsupported symbolic object shape')
        if not isinstance(position,str) or position not in POSITIONS:
            raise ValueError('symbolic object needs a named grid position')
        if any(old['type']=='object' and old['position']==position for old in items.values()):
            raise ValueError('symbolic object position is already occupied')
        commands = _object(shape, *POSITIONS[position])
        left,top,right,bottom = _bounds(commands)
        reserve = (left-5,top-5,right+5,bottom+5)
        # Existing connector/label ink belongs to its old meaning. A new
        # object cannot enclose it, even when its own contour misses the ink.
        if any(_hits(group,reserve) for group in groups.values() if group):
            raise ValueError('new object would cover existing ink; use another position or picture')
        return commands
    if kind != 'connect':
        raise ValueError('symbolic item must be object or connect')
    source, target = _id(item['from']), _id(item['to'])
    objects = {key:value for key,value in items.items() if value['type']=='object'}
    if source == target or source not in objects or target not in objects:
        raise ValueError('connection needs two distinct earlier symbolic objects')
    connections = [key for key,value in items.items() if value['type']=='connect']
    if len(connections)>=8:
        raise ValueError('use at most eight symbolic connections per picture')
    boxes = {key:_bounds(groups[key]) for key in objects}
    ports = {key:_object_ports(value['shape'],*POSITIONS[value['position']]) for key,value in objects.items()}
    # Freeze prior labels as routing obstacles. Pending labels in the current
    # addition are placed by the caller after all its geometry is available.
    for key, group in groups.items():
        if group and all(command['op']=='label' for command in group):
            boxes['__label-'+key] = _bounds(group)
    previous = [groups[key][0]['points'] for key in connections]
    commands,_ = _route(source,target,boxes,ports,previous,allow_detours=True)
    return commands
