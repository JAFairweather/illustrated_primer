"""Four counts -> an additive two-way table, totals and conditional fraction.

The renderer owns layout and arithmetic, not interpretation of the source.
No model calls, arbitrary expressions, filesystem access or device operations.
"""
from fractions import Fraction

from notebook_lesson import _fields, _text
from notebook_procedural import (_label, _label_bounds, _line, _label_lines,
                                 _label_group, _group_label_bounds)


def _row_label(text, center_y):
    """Fit an unchanged name in its fixed row gutter; at most two lines.

    Keep established one-line geometry exactly. Long names may wrap only at a
    word boundary, never shrink, truncate, move the table, or consume a row.
    """
    single = _label(text,85,center_y+6)
    left,_,right,_ = _label_bounds(single)
    if left>=8 and right<=162:
        return [single]
    for lines in _label_lines(text):
        if len(lines)!=2:
            continue
        commands = _label_group(lines,85,center_y+6)
        left,top,right,bottom = _group_label_bounds(commands)
        if left<8 or right>162 or bottom-top>48:
            continue
        shift = center_y-(top+bottom)/2
        for command in commands:
            command['at'][1] += shift
        return commands
    raise ValueError('count grid row label must fit two lines in its fixed gutter')


def count_grid(obj):
    _fields(obj, {'id','component','rows','columns','counts','selected'})
    labels = {}
    for axis in ('rows','columns'):
        values = obj[axis]
        if not isinstance(values,list) or len(values)!=2:
            raise ValueError('count grid needs exactly two labels per axis')
        labels[axis] = [_text(value,24 if axis=='rows' else 10) for value in values]
        if labels[axis][0].casefold()==labels[axis][1].casefold():
            raise ValueError('count grid labels must be distinct within each axis')
        if any(value.casefold()=='total' for value in labels[axis]):
            raise ValueError('Total is reserved for computed margins')
    counts = obj['counts']
    if (not isinstance(counts,list) or len(counts)!=2 or
            any(not isinstance(row,list) or len(row)!=2 for row in counts) or
            any(type(n) is not int or not 0<=n<=999999 for row in counts for n in row)):
        raise ValueError('count grid requires a 2 by 2 array of nonnegative integers up to 999999')
    selected = obj['selected']
    _fields(selected, {'row','column','condition_on'})
    if (any(type(selected[k]) is not int or selected[k] not in (0,1) for k in ('row','column')) or
            selected['condition_on'] not in ('row','column')):
        raise ValueError('select row/column indices 0 or 1 and condition_on row or column')
    row_totals = [sum(row) for row in counts]
    column_totals = [sum(row[c] for row in counts) for c in range(2)]
    r,c = selected['row'],selected['column']
    denominator = (row_totals[r] if selected['condition_on']=='row' else column_totals[c])
    if denominator==0:
        raise ValueError('cannot condition on an empty row or column')
    numerator = counts[r][c]
    fraction = Fraction(numerator,denominator)
    xs,ys = [250,400,535],[140,210,280]
    # Each edge is drawn once; margins are separate cells, not overpainted data.
    frame = [_line((x,100),(x,310)) for x in (175,325,475,595)]
    frame += [_line((175,y),(595,y)) for y in (100,170,240,310)]
    column_labels = [_label(name,x,75) for name,x in zip(labels['columns']+['Total'],xs)]
    # Mere nonintersection is not sufficient: adjacent column words should
    # read as separate headings, not a single run-on label.
    for a,b in zip(column_labels,column_labels[1:]):
        if _label_bounds(b)[0]-_label_bounds(a)[2]<12:
            raise ValueError('count grid headings need shorter labels for readable spacing')
    row_labels = [_row_label(name,y) for name,y in zip(labels['rows'],ys)]
    data_labels = [[_label(str(n),xs[j],ys[i]+6) for j,n in enumerate(row+[row_totals[i]])]
                   for i,row in enumerate(counts)]
    totals = [_label('Total',85,286)]
    totals += [_label(str(n),x,286) for n,x in zip(column_totals+[sum(row_totals)],xs)]
    numerator_label = data_labels[r][c]
    denominator_label = data_labels[r][2] if selected['condition_on']=='row' else totals[c+1]

    def outline(label):
        left,top,right,bottom = _label_bounds(label)
        return {'op':'rect','origin':[left-8,top-8],
                'size':[right-left+16,bottom-top+16]}

    condition_labels = row_labels[r] if selected['condition_on']=='row' else [column_labels[c]]
    left,_,right,bottom = _group_label_bounds(condition_labels)
    selection = [outline(numerator_label),outline(denominator_label),
                 _line((left,bottom+8),(right,bottom+8)),
                 _label(f'{numerator} of {denominator}',310,345)]
    equation = r'\frac{'+str(numerator)+'}{'+str(denominator)+'}'
    if (numerator,denominator)!=(fraction.numerator,fraction.denominator):
        equation += '='+(str(fraction.numerator) if fraction.denominator==1 else
                         r'\frac{'+str(fraction.numerator)+'}{'+str(fraction.denominator)+'}')
    return dict(
        parts={'frame':frame,'columns':column_labels,
               'row1':row_labels[0]+data_labels[0],
               'row2':row_labels[1]+data_labels[1],
               'totals':totals,'selection':selection},
        dependencies={'columns':{'frame'},'row1':{'columns'},'row2':{'columns'},
                      'totals':{'row1','row2'},'selection':{'totals'}},
        facts={'selected_fraction':fraction}, required_claims=[['selected_fraction']],
        equation=equation,
        metrics={'counts':[row[:] for row in counts],'row_totals':row_totals,
                 'column_totals':column_totals,'total':sum(row_totals),
                 'rows':labels['rows'],'columns':labels['columns'],
                 'selected':dict(selected,numerator=numerator,denominator=denominator,
                                 fraction=str(fraction)),
                 'input_values_verified':False,'category_interpretation_verified':False})
