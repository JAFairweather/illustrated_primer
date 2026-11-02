"""Offline LessonSpec v1 subset: meaning in, validated native geometry out.

No model, filesystem, network, or device calls. Only implemented components are
advertised. All parts are compiled before any native delivery is possible.
Typed predicates verify supported quantities; arbitrary prose is NOT verified.
"""
from fractions import Fraction
import json
import math

from notebook_lesson import compile_lesson, FIELDS, _fields, _number, _text, _pairs, _constant
from notebook_procedural import compile_board, _lever, _label, _line, _poly, _id
from notebook_sampled_chart import sampled_chart
from notebook_count_grid import count_grid
from notebook_right_triangle import right_triangle


MAX_BYTES = 24000
CAPABILITIES = {
    'v': 1,
    'modes': ['lesson'],
    'drawing': {'region':[600,360], 'commands':sorted(set(FIELDS) | {'connect'}),
                'connections':{'endpoints':'previous circle or rect IDs', 'max_connections':12,
                               'meaning':'schematic directed relation, not a physical trajectory'},
                'commands_per_step':[1,32], 'steps':[1,6],
                'strokes_per_step':64, 'points_per_step':3000, 'total_points':12000,
                'anchored_labels':{'target':'previous non-label primitive id','max_labels':12,
                                   'max_text':24,'size':18}},
    'mechanism': {'lever': ['body', 'forces', 'arms']},
    'quantitative': {'riemann_area': ['axes', 'curve', 'coarse', 'refinement', 'exact_value'],
                     'odd_square_growth': ['layer1', 'layer2', 'layer3', 'layer4', 'layer5', 'layer6'],
                     'fraction_comparison': ['wholes','partitions','first','second'],
                     'sampled_chart': ['axes','scale','samples','links'],
                     'count_grid': ['frame','columns','row1','row2','totals','selection'],
                     'right_triangle': ['triangle','a_square','b_square','c_square','areas']},
    'sampled_chart_reference': {'optional_fields':['label','reference'],
                               'extra_parts':['reference_samples','reference_links','difference'],
                               'required_claims':[['final_above','final_below','final_equal']]},
    'causal': {'objects': ['circle','box','person','sun','cloud','water'],
               'relationship_types': ['process']},
    'required_claims': {'lever':[['balanced','left_greater','right_greater']],
                        'riemann_area':[['increasing'],['refinement_improves'],['exact_integral']],
                        'odd_square_growth':[['odd_border_growth'],['final_area']],
                        'fraction_comparison':[['equal','first_greater','second_greater']],
                        'sampled_chart':[['increasing','decreasing','constant','mixed']],
                        'count_grid':[['selected_fraction']],
                        'right_triangle':[['hypotenuse_squared']]},
}


def _math_fraction(value):
    return str(value.numerator) if value.denominator==1 else r'\frac{'+str(value.numerator)+'}{'+str(value.denominator)+'}'


class SemanticError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def parse_semantic(raw):
    if not isinstance(raw,str) or len(raw.encode('utf-8'))>MAX_BYTES:
        raise SemanticError('invalid_schema','bounded JSON lesson required')
    try:
        spec=json.loads(raw,object_pairs_hook=_pairs,parse_constant=_constant)
    except (ValueError,RecursionError) as exc:
        raise SemanticError('invalid_schema','invalid or duplicate-field lesson JSON') from exc
    return compile_semantic(spec)


def _numeric_pair(obj, key, unit):
    field=obj[key]
    _fields(field,{'values','unit'})
    if field['unit']!=unit or not isinstance(field['values'],list) or len(field['values'])!=2:
        raise SemanticError('invalid_quantity',f'{key} requires two values in {unit}')
    return [_number(x,.1,10000) for x in field['values']]


def _lever_component(obj):
    _fields(obj,{'id','component','arms','forces'})
    arms=_numeric_pair(obj,'arms','m')
    forces=_numeric_pair(obj,'forces','N')
    stages,layout=_lever({'kind':'lever','arms':arms,'forces':forces,
                          'captions':['Setup','Forces','Distances'],'takeaway':'Turning effects.'})
    # Exact decimal arithmetic makes predicates independent of display rounding.
    moments=[Fraction(str(a))*Fraction(str(f)) for a,f in zip(arms,forces)]
    facts={'balanced':moments[0]==moments[1], 'left_greater':moments[0]>moments[1],
           'right_greater':moments[1]>moments[0]}
    eq=f'{forces[0]:g} × {arms[0]:g} '+('=' if facts['balanced'] else '>' if facts['left_greater'] else '<')+f' {forces[1]:g} × {arms[1]:g}'
    return dict(parts=dict(zip(('body','forces','arms'),[s['draw'] for s in stages])),
                dependencies={'forces':{'body'},'arms':{'body','forces'}},facts=facts,
                required_claims=CAPABILITIES['required_claims']['lever'],equation=eq,metrics=layout[0])


def _difference(interval, occupied):
    fragments=[interval]
    for lower,upper in sorted(occupied):
        next_fragments=[]
        for a,b in fragments:
            if upper<=a or lower>=b:
                next_fragments.append((a,b))
            else:
                if a<lower:next_fragments.append((a,lower))
                if b>upper:next_fragments.append((upper,b))
        fragments=next_fragments
    return fragments


def _riemann_component(obj):
    _fields(obj,{'id','component','polynomial_coefficients_ascending','interval','partitions','sampling'})
    coefficients=obj['polynomial_coefficients_ascending']
    interval=obj['interval']; counts=obj['partitions']
    if not isinstance(coefficients,list) or not 2<=len(coefficients)<=5:
        raise SemanticError('invalid_quantity','use a degree 1..4 nonnegative polynomial')
    c=[Fraction(str(_number(x,0,1000))) for x in coefficients]
    if not any(c[1:]):
        raise SemanticError('invalid_quantity','this component requires an increasing polynomial')
    if not isinstance(interval,list) or len(interval)!=2:
        raise SemanticError('invalid_quantity','use two interval endpoints')
    a,b=[Fraction(str(_number(x,0,1000))) for x in interval]
    if not a<b or b-a<Fraction(1,1000):
        raise SemanticError('invalid_quantity','use an increasing interval of width at least 0.001')
    if (not isinstance(counts,list) or len(counts)!=2 or
            any(type(n) is not int for n in counts) or not 2<=counts[0]<=6 or
            counts[1]!=2*counts[0] or obj['sampling']!='left'):
        raise SemanticError('invalid_quantity','use two nested left partitions n,2n with n in 2..6')
    f=lambda x:sum(v*x**i for i,v in enumerate(c))
    peak=f(b)
    point=lambda x,y:(90+420*float((x-a)/(b-a)),240-180*float(y/peak))
    def rects(n):
        dx=(b-a)/n
        return [(a+i*dx,a+(i+1)*dx,f(a+i*dx)) for i in range(n)]
    # Track mathematical intervals before scaling; never redraw an old edge.
    occupied={('h',Fraction(0)):[(a,b)],('v',a):[(Fraction(0),peak)]}
    emitted=[]
    def edges(n):
        result=[]
        for left,right,height in rects(n):
            if height==0:continue
            for axis,fixed,lo,hi in [('h',height,left,right),('v',left,Fraction(0),height),('v',right,Fraction(0),height)]:
                key=(axis,fixed)
                for start,end in _difference((lo,hi),occupied.get(key,())):
                    p,q=((start,fixed),(end,fixed)) if axis=='h' else ((fixed,start),(fixed,end))
                    # Very small fragments need not become impossible subpixel ink.
                    # They remain in the computed geometry/area; do not distort scale.
                    if math.dist(point(*p),point(*q))>=1:
                        result.append(_line(point(*p),point(*q)))
                        emitted.append([axis,str(fixed),str(start),str(end)])
                occupied.setdefault(key,[]).append((lo,hi))
        return result
    sums=[sum((r-l)*h for l,r,h in rects(n)) for n in counts]
    exact=sum(v*(b**(i+1)-a**(i+1))/(i+1) for i,v in enumerate(c))
    terms=[];label_terms=[]
    superscripts={2:'²',3:'³',4:'⁴'}
    for degree,value in reversed(list(enumerate(c))):
        if not value:continue
        coefficient='' if value==1 and degree else str(value)
        math_coefficient='' if value==1 and degree else _math_fraction(value)
        if degree and value.denominator!=1:
            coefficient='('+str(value)+')'
        terms.append(math_coefficient+('x' if degree==1 else f'x^{degree}' if degree else ''))
        label_terms.append(coefficient+('x'+superscripts.get(degree,'') if degree else ''))
    parts={
        'axes':[_poly([(90,40),(90,240),(530,240)]),
                _label(f'{float(a):g}',90,270),_label(f'{float(b):g}',510,270),
                _label('x',550,246),_label('y',65,30),
                _line((86,60),(94,60)),_label(f'{float(peak):g}',60,66)],
        'curve':[{'op':'plot','points':[list(point(a+(b-a)*i/64,f(a+(b-a)*i/64))) for i in range(65)]},
                 _label('y = '+'+'.join(label_terms),300,45)],
        'coarse':edges(counts[0]),'refinement':edges(counts[1]),
        'exact_value':[_label('Area = '+str(exact),300,320)],
    }
    if any(not parts[name] for name in ('coarse','refinement')):
        raise SemanticError('layout_overflow','area additions are too small to explain legibly')
    equation=r'\int_{'+_math_fraction(a)+'}^{'+_math_fraction(b)+'} ('+'+'.join(terms)+r')\,dx='+_math_fraction(exact)
    return dict(parts=parts, dependencies={'curve':{'axes'},'coarse':{'axes','curve'},
                'refinement':{'coarse'},'exact_value':{'refinement'}},
                facts={'increasing':True,'nonnegative':True,'left_underestimate':sums[0]<exact,
                       'refinement_improves':sums[0]<sums[1]<exact,'exact_integral':exact},
                required_claims=CAPABILITIES['required_claims']['riemann_area'],
                equation=equation,metrics={'left_sums':list(map(str,sums)),
                    'exact_integral':str(exact),'new_edges':emitted,
                    'interval':list(map(str,interval)),'partitions':counts[:]})


def _coalesced_grid_edges(edges):
    """Join only touching collinear edges added in this same reveal step."""
    groups={}
    for a,b in edges:
        axis=0 if a[1]==b[1] else 1
        fixed=a[1-axis]
        groups.setdefault((axis,fixed),[]).append(sorted((a[axis],b[axis])))
    result=[]
    for (axis,fixed),intervals in sorted(groups.items()):
        merged=[]
        for start,end in sorted(intervals):
            if merged and merged[-1][1]==start:merged[-1][1]=end
            else:merged.append([start,end])
        for start,end in merged:
            result.append([(start,fixed),(end,fixed)] if axis==0
                          else [(fixed,start),(fixed,end)])
    return result


def _odd_square_component(obj):
    """One growing lattice; shared edges appear once, not once per cell.

    Counts and alternating border hatches come from the existing tested motif.
    The agent chooses a bounded layer count, never grid coordinates or labels.
    """
    from notebook_shapes import square_growth_layer
    _fields(obj,{'id','component','layers'})
    count=obj['layers']
    if type(count) is not int or not 3<=count<=6:
        raise SemanticError('invalid_quantity','odd-square growth requires 3..6 integer layers')
    cell=min(60,240//count)
    parts={};compact_parts={};dependencies={};layers=[]
    for n in range(1,count+1):
        motif=square_growth_layer(n,origin=(180,300),cell=cell)
        name='layer'+str(n)
        target=motif['anchors']['label_target']
        # Keep unit divisions but avoid lifting the pen at every collinear
        # outer-edge join. Hatches remain separate, inside their own tiles.
        grid=_coalesced_grid_edges(motif['edges'])
        paths=grid+motif['paths'][len(motif['edges']):]
        legend=[
            _label('1' if n==1 else '+'+str(2*n-1),95,target[1]+6),
            _line((125,target[1]),(170,target[1]))]
        parts[name]=[_poly(path) for path in paths]+legend
        # Grouped borders can exceed the native stroke budget if every new
        # tile is hatched. Grid edges already show every unit cell; decorative
        # hatches may be omitted, never labels, quantities or unit divisions.
        compact_parts[name]=[_poly(path) for path in grid]+legend
        if n>1:dependencies[name]={'layer'+str(n-1)}
        layers.append({'layer':n,'added_units':motif['added_units'],
                       'total_units':motif['total_units'],'new_cells':motif['new_cells'],
                       'new_edges':motif['edges'],'drawn_grid_edges':grid})
    equation='+'.join(str(2*n-1) for n in range(1,count+1))+f'={count}^2={count*count}'
    return dict(parts=parts,compact_parts=compact_parts,dependencies=dependencies,
                facts={'odd_border_growth':all(layer['added_units']==2*layer['layer']-1 for layer in layers),
                       'final_area':Fraction(count*count)},
                required_claims=CAPABILITIES['required_claims']['odd_square_growth'],
                equation=equation,metrics={'layers':layers,'cell_size':cell,'final_area':count*count})


def _fraction_component(obj):
    """Two equal wholes, different partitions, exact quantity-driven shading.

    Partition lines are added once; interior hatches never redraw borders.
    The supplied comparison is verified with rational arithmetic, not captions.
    """
    _fields(obj,{'id','component','fractions'},{'split_partitions'})
    split = obj.get('split_partitions', False)
    if type(split) is not bool:
        raise SemanticError('invalid_quantity','split_partitions must be boolean')
    quantities=obj['fractions']
    if not isinstance(quantities,list) or len(quantities)!=2:
        raise SemanticError('invalid_quantity','compare exactly two proper fractions')
    values=[]
    for q in quantities:
        _fields(q,{'numerator','denominator'})
        n,d=q['numerator'],q['denominator']
        if type(n) is not int or type(d) is not int or not 2<=d<=12 or not 1<=n<d:
            raise SemanticError('invalid_quantity','use integer proper fractions with denominators 2..12')
        values.append(Fraction(n,d))
    parts={'wholes':[_label('Same whole',280,40)],'partitions':[],'first':[],'second':[]}
    if split:
        del parts['partitions']
        parts.update(upper_partitions=[], lower_partitions=[])
    metrics=[]
    for index,(q,y) in enumerate(zip(quantities,(75,205))):
        n,d=q['numerator'],q['denominator'];x=100;width=360;height=58
        unit=Fraction(width,d)
        parts['wholes'].append({'op':'rect','origin':[x,y],'size':[width,height]})
        partition = ('upper_partitions' if index == 0 else 'lower_partitions') if split else 'partitions'
        parts[partition].extend(_line((x+float(unit*i),y),(x+float(unit*i),y+height)) for i in range(1,d))
        hatches=[]
        # One shared 45-degree hatch pattern, independent of denominators:
        # equal amounts must not look darker merely because they have more
        # pieces. Clip to the selected prefix, leaving original borders clear.
        fill_width=float(unit*n)-8;fill_height=height-8
        for diagonal in range(16,math.ceil(fill_width+fill_height),16):
            begin=max(0,diagonal-fill_height);end=min(fill_width,diagonal)
            if end-begin>=1:
                hatches.append([[x+4+begin,y+4+diagonal-begin],
                                [x+4+end,y+4+diagonal-end]])
        parts['first' if index==0 else 'second']=[_line(*line) for line in hatches]+[_label(f'{n}/{d}',520,y+36)]
        metrics.append({'numerator':n,'denominator':d,'value':str(values[index]),
                        'whole_bounds':[x,y,x+width,y+height],
                        'selected_bounds':[x,y,x+float(unit*n),y+height],
                        'cell_width':float(unit),'selected_cells':n,'hatches':hatches})
    first,second=values
    sign='=' if first==second else '>' if first>second else '<'
    equation=sign.join(r'\frac{'+str(q['numerator'])+'}{'+str(q['denominator'])+'}' for q in quantities)
    dependencies = ({'upper_partitions':{'wholes'},'lower_partitions':{'upper_partitions'},
                     'first':{'lower_partitions'},'second':{'first'}} if split else
                    {'partitions':{'wholes'},'first':{'partitions'},'second':{'first'}})
    return dict(parts=parts,dependencies=dependencies,
                facts={'equal':first==second,'first_greater':first>second,'second_greater':first<second},
                required_claims=CAPABILITIES['required_claims']['fraction_comparison'],equation=equation,
                metrics={'fractions':metrics,'comparison':sign,'equal_whole_sizes':True})


def _claims(claims, objects):
    if not isinstance(claims,list) or len(claims)>8:
        raise SemanticError('invalid_schema','use at most eight typed claims')
    checked=[];seen=set()
    for claim in claims:
        _fields(claim,{'object','predicate'},{'value'})
        obj=_id(claim['object']);predicate=claim['predicate']
        if obj not in objects or not isinstance(predicate,str) or predicate not in objects[obj]['facts']:
            raise SemanticError('unsupported_claim','unknown object or component predicate')
        if (obj,predicate) in seen:
            raise SemanticError('invalid_schema','duplicate component claim')
        seen.add((obj,predicate))
        actual=objects[obj]['facts'][predicate]
        if type(actual) is bool:
            if 'value' in claim or not actual:
                raise SemanticError('contradictory_claim','component quantities contradict the claimed relationship')
        else:
            value=claim.get('value')
            _fields(value,{'numerator','denominator'})
            if (any(type(v) is not int or abs(v)>10**18 for v in value.values()) or
                    value['denominator']<=0 or Fraction(value['numerator'],value['denominator'])!=actual):
                raise SemanticError('contradictory_claim','claimed exact value differs from the computed quantity')
        checked.append(dict(claim))
    for identity,component in objects.items():
        for alternatives in component['required_claims']:
            if not any((identity,predicate) in seen for predicate in alternatives):
                raise SemanticError('missing_claim','component conclusion requires an explicit verified predicate')
    return checked


def _reveal(steps, object_id, component):
    if not isinstance(steps,list) or not 3<=len(steps)<=6:
        raise SemanticError('invalid_schema','use 3..6 reveal steps')
    result=[];seen=set()
    for step in steps:
        _fields(step,{'reveal','caption'})
        ids=step['reveal']
        if not isinstance(ids,list) or not 1<=len(ids)<=8:
            raise SemanticError('invalid_schema','bounded reveal IDs required')
        names=[]
        for name in ids:
            if not isinstance(name,str) or not name.startswith(object_id+'.'):
                raise SemanticError('invalid_schema','reveal must name this component part')
            part=name[len(object_id)+1:]
            if part not in component['parts'] or part in seen or part in names:
                raise SemanticError('invalid_schema','unknown or duplicate component part')
            names.append(part)
        for name in names:
            if not component['dependencies'].get(name,set())<=seen:
                raise SemanticError('invalid_schema','reveal dependencies before their dependent part, including within a step')
            seen.add(name)
        commands=[c for n in names for c in component['parts'][n]]
        if len(commands)>32 and len(names)>1 and 'compact_parts' in component:
            commands=[c for n in names for c in component['compact_parts'][n]]
        result.append({'caption':step['caption'],'draw':commands})
    if seen!=component['parts'].keys():
        raise SemanticError('invalid_schema','reveal every component part exactly once')
    return result


def _reveals(nodes, links, steps):
    ends={l['id']:{l['from'],l['to']} for l in links}
    declared,seen=[n['id'] for n in nodes]+list(ends),set()
    for step in steps:
        added=step['add']
        if len(set(added))!=len(added) or any(i not in declared or i in seen for i in added):
            raise ValueError('each object or connection must be revealed exactly once')
        seen.update(added)
        if any(not ends.get(i,set())<=seen for i in added):
            raise ValueError('reveal endpoints before or with their connector')
    if seen!=set(declared):
        raise ValueError('every declared object/connection must appear in a step')


def _rows(nodes, links, steps):
    """Boxes in one or two rows with straight arrows between them, revealed step by step."""
    # Two staggered rows: three boxes make a triangle, so every arrow runs between neighbours.
    count=len(nodes); top=math.ceil(count/2) if count>1 else 1
    width,height=600/max(top,1)-60,64
    boxes={}
    for i,node in enumerate(nodes):
        row,col=(0,i) if i<top else (1,i-top)
        across=top if row==0 else count-top
        cell=600/across
        boxes[node['id']]=(round(col*cell+(cell-width)/2,1),40 if row==0 or count==1 else 256,width,height)
    def label(text,box):
        # Measured with the pen that will write it: the longest run of whole words that fits inside the box.
        from notebook_lesson import _primitive
        x,y,w,h=box
        def span(t):
            xs=[p[0] for path in _primitive({'op':'label','at':[0,40],'text':t,'size':16}) for p in path]
            return max(xs)-min(xs)
        words,out=str(text).split(),''
        for word in words:
            longer=(out+' '+word).strip()
            if len(longer)>32 or span(longer)>w-24:break
            out=longer
        while not out and words:
            out=words[0][:32]
            while len(out)>1 and span(out)>w-24:out=out[:-1]
        out=out.rstrip(',;:') or out
        return {'op':'label','at':[round(x+(w-span(out))/2,1),round(y+h/2+6,1)],'text':out,'size':16}
    def arrow(link):
        ax,ay,aw,ah=boxes[link['from']]; bx,by,bw,bh=boxes[link['to']]
        a=(ax+aw/2,ay+ah/2); b=(bx+bw/2,by+bh/2)
        def edge(c,o,box):
            x,y,w,h=box; dx,dy=o[0]-c[0],o[1]-c[1]
            t=min((w/2+6)/abs(dx) if dx else 1e9,(h/2+6)/abs(dy) if dy else 1e9)
            return [round(c[0]+dx*t,1),round(c[1]+dy*t,1)]
        return {'op':'arrow','from':edge(a,b,boxes[link['from']]),'to':edge(b,a,boxes[link['to']])}
    named={n['id']:n for n in nodes}; joined={l['id']:l for l in links}; shown=set(); out=[]
    for step in steps:
        draw=[]
        for key in step['add'] if isinstance(step['add'],list) else [step['add']]:
            if key in named and key not in shown:
                x,y,w,h=boxes[key]; draw+=[{'op':'rect','origin':[x,y],'size':[w,h]},label(named[key]['label'],boxes[key])]
            elif key in joined and key not in shown and joined[key]['from']!=joined[key]['to']:
                draw.append(arrow(joined[key]))
            shown.add(key)
        if draw:out.append({'caption':step['caption'],'draw':draw})
        elif out:out[-1]['caption']=(out[-1]['caption']+' '+step['caption'])[:280]
    if not out:raise ValueError('nothing in the network to draw')
    return out


def compile_semantic(spec):
    """Compile components or the existing bounded drawing grammar, never raw ink."""
    try:
        encoded=json.dumps(spec,allow_nan=False)
        if len(encoded.encode())>MAX_BYTES:
            raise SemanticError('invalid_schema','semantic lesson exceeds byte budget')
        spec=json.loads(encoded)  # detached, JSON-only input; never mutate caller
        drawing = (isinstance(spec,dict) and isinstance(spec.get('scene'),dict)
                   and spec['scene'].get('family')=='drawing')
        _fields(spec,{'v','mode','intent','scene','steps','claims','takeaway'},
                {'equation'} if drawing else ())
        if type(spec['v']) is not int or spec['v']!=1 or spec['mode']!='lesson':
            raise SemanticError('unsupported_component','only v1 lesson mode is implemented')
        _text(spec['intent'],280)
        if drawing:
            _fields(spec['scene'],{'family'})
            if spec['claims'] != []:
                raise SemanticError('unsupported_claim','drawing geometry does not verify mathematical or scientific claims')
            plan=compile_lesson(spec['steps'],spec['takeaway'],spec.get('equation'),allow_short=True,drop_colliding_labels=True)
            plan['semantic']={'v':1,'family':'drawing','intent':spec['intent'],
                              'verified_claims':[],'prose_verified':False,
                              'metrics':{'geometry_source':'bounded-primitives',
                                         'mathematics_verified':False}}
            return plan
        scene=spec['scene'];_fields(scene,{'family','objects'},{'relations'})
        objects=scene['objects']
        if not isinstance(objects,list) or not 1<=len(objects)<=6:
            raise ValueError('use 1..6 semantic objects')
        if scene['family']=='causal':
            nodes=[]
            for obj in objects:
                _fields(obj,{'id','component','label'})
                if obj['component'] not in CAPABILITIES['causal']['objects']:
                    raise SemanticError('unsupported_component','unsupported causal object')
                nodes.append({'id':obj['id'],'shape':obj['component'],'label':obj['label']})
            relations=scene.get('relations',[])
            if not isinstance(relations,list) or len(relations)>8:
                raise ValueError('use at most eight process relations')
            links=[]
            for r in relations:
                _fields(r,{'id','from','to','type','label'})
                if r['type']!='process':
                    raise SemanticError('unsupported_component','causal routing supports explanatory processes, not physical paths')
                links.append({k:v for k,v in r.items() if k!='type'})
            if not isinstance(spec['steps'],list):raise ValueError('steps must be a list')
            steps=[]
            for step in spec['steps']:
                _fields(step,{'reveal','caption'})
                steps.append({'add':step['reveal'],'caption':step['caption']})
            checked=_claims(spec['claims'],{})
            board={'kind':'network','objects':nodes,'links':links,'steps':steps,'takeaway':spec['takeaway']}
            _reveals(nodes,links,steps)  # a broken reveal is refused; only a scene that will not route falls back
            try:
                plan=compile_board(board)
                metrics=plan['procedural']['layout']
            except (ValueError,TypeError,KeyError) as exc:
                # A network the router cannot fit (IRIS reply, 2026-10-30: four refusals) is drawn as fixed rows
                # of boxes instead, so the answer still reaches the page; the captions carry the explanation.
                plan=compile_lesson(_rows(nodes,links,steps),spec['takeaway'],allow_short=True,
                                    drop_colliding_labels=True)
                metrics={'layout':'rows','refused':str(exc)[:200]}
        else:
            if len(objects)!=1 or 'relations' in scene:
                raise SemanticError('unsupported_component','quantitative components currently occupy one scene')
            obj=objects[0]
            if not isinstance(obj,dict):raise ValueError('component must be an object')
            identity=_id(obj.get('id'))
            pair=(scene['family'],obj.get('component'))
            if pair==('mechanism','lever'):component=_lever_component(obj)
            elif pair==('quantitative','riemann_area'):component=_riemann_component(obj)
            elif pair==('quantitative','odd_square_growth'):component=_odd_square_component(obj)
            elif pair==('quantitative','fraction_comparison'):component=_fraction_component(obj)
            elif pair==('quantitative','sampled_chart'):component=sampled_chart(obj)
            elif pair==('quantitative','count_grid'):component=count_grid(obj)
            elif pair==('quantitative','right_triangle'):component=right_triangle(obj)
            else:raise SemanticError('unsupported_component','unknown family or component')
            checked=_claims(spec['claims'],{identity:component})
            expanded=_reveal(spec['steps'],identity,component)
            # A few semantic parts can expand into more than 32 commands.
            # This allowance belongs to trusted component geometry, not the
            # agent's raw drawing grammar; all native budgets still apply.
            procedural_expansion=(pair in {('quantitative','odd_square_growth'),
                                           ('quantitative','fraction_comparison')} and
                                  any(len(step['draw'])>32 for step in expanded))
            plan=compile_lesson(expanded,spec['takeaway'],component['equation'],procedural=procedural_expansion,drop_colliding_labels=True)
            metrics={identity:component['metrics']}
        plan['semantic']={'v':1,'family':scene['family'],'intent':spec['intent'],
                          'verified_claims':checked,'prose_verified':False,'metrics':metrics}
        return plan
    except SemanticError:
        raise
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:
        message=str(exc)
        code='native_budget_exceeded' if 'budget' in message or 'strokes' in message or 'pen time' in message else 'invalid_schema'
        if 'label location' in message or 'label placement' in message or 'connector route' in message or 'collision' in message:
            code='layout_overflow'
        raise SemanticError(code,message) from exc
