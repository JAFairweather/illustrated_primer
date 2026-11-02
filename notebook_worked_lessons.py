"""Authored teaching examples, never runtime question/scene selection rules."""
import json


def _lesson(question, takeaway, steps, equation=None):
    story = dict(v=1, mode='story', audience='A high-school student',
                 template='explain_concept', question=question,
                 acts=[dict(id='learn', beat='Build the idea, then explain its meaning.')],
                 panels=[], takeaway=takeaway)
    shapes = {}
    for identity, base, caption, idea, items in steps:
        story['panels'].append(dict(id=identity, act='learn', base=base,
            title=identity.replace('-', ' ').title(), question='What does this step explain?',
            caption=caption, new_idea=idea, visual_kind='Illustrated explanation'))
        shapes[identity] = dict(v=1, mode='panel-shapes', panel=identity, items=items)
    if equation is not None: story['equation'] = equation
    return story, shapes


def _axes(x, y, aspect='independent'):
    return dict(id='ax', type='axes', x=x, y=y, aspect=aspect)


def _shape(identity, kind, **fields):
    return dict(id=identity, type=kind, **{'in':'ax'}, **fields)


def integral_example():
    return _lesson('What does the integral of x squared from zero to one mean?',
        'The integral measures the exact area; thinner rectangles approach one third.', [
        ('curve', None, 'The curve shows how the height changes across one unit.',
         'Introduce the curve y equals x squared between zero and one.',
         [_axes([0,1],[0,1]), _shape('curve','plot',coefficients=[0,0,1],domain=[0,1])]),
        ('rectangles', 'curve', 'Four thin rectangles give an estimate of the area.',
         'Add four midpoint rectangles under the curve as an approximation, not the exact answer.',
         [_shape('estimate','riemann',coefficients=[0,0,1],domain=[0,1],baseline=0,count=4,sample='midpoint')]),
        ('area', 'curve', 'As rectangles get thinner, their total approaches the shaded area.',
         'Return to the unpartitioned curve and shade its exact target region above the baseline.',
         [_shape('target','area',coefficients=[0,0,1],domain=[0,1],baseline=0,fill='hatch')]),
        ], r'\int_0^1 x^2\,dx=\frac{1}{3}')


def odd_squares_example():
    return _lesson('Why does adding consecutive odd numbers build square numbers?',
        'An n by n square gains n cells along each side plus one corner: the next odd number.', [
        ('one', None, 'Start with one cell: a one-by-one square.',
         'Show a unit square on a grid measured in cells.',
         [_axes([0,3],[0,3],'equal'),_shape('one','rect',x=[0,1],y=[0,1])]),
        ('three', 'one', 'Three new cells wrap around it to make a two-by-two square.',
         'Add the next L-shaped layer without changing the original square.',
         [_shape('right','rect',x=[1,2],y=[0,1]),_shape('top','rect',x=[0,2],y=[1,2]),
          _shape('divider','line',**{'from':[1,1],'to':[1,2]})]),
        ('five', 'three', 'Five more cells make the next square; the same wrapping pattern continues.',
         'Add a third row and column; explain that any next layer has two sides of n cells and one corner.',
         [_shape('right-more','rect',x=[2,3],y=[0,2]),_shape('top-more','rect',x=[0,3],y=[2,3]),
          _shape('cut-a','line',**{'from':[2,1],'to':[3,1]}),
          _shape('cut-b','line',**{'from':[1,2],'to':[1,3]}),
          _shape('cut-c','line',**{'from':[2,2],'to':[2,3]})]),
        ], r'(n+1)^2-n^2=2n+1')


def riemann_example():
    """Source-assisted explanation of the supplied unreviewed claim, not a proof.

    Coordinates of dots and the old boundary are illustrative, not calculated
    zeros or a numerical zero-free-region bound. Captions preserve that limit.
    """
    label = lambda identity,target,text: dict(id=identity,type='label',to=target,text=text,side='auto')
    obj = lambda identity,position: dict(id=identity,type='object',shape='box',position=position)
    connect = lambda identity,a,b: dict(id=identity,type='connect',**{'from':a,'to':b})
    story, shapes = _lesson('What does the claimed Riemann seven-eighths result mean?',
        'The unreviewed claim would exclude more possible zero locations; it would not prove RH.', [
        ('primes', None, 'Primes are building blocks: twelve is two times two times three.',
         'Show a factorization as a concrete introduction, not a theorem about zero locations.',
         [obj('factors','top-left'),obj('whole','top-right'),connect('build','factors','whole'),
          label('factor-name','factors','2 x 2 x 3'),label('whole-name','whole','12')]),
        ('count', None, 'The count jumps at each prime, making an uneven staircase.',
         'Show the exact count of primes up to ten as a staircase.',
         [_axes([0,10],[0,4]),_shape('stairs','polyline',points=[[0,0],[2,0],[2,1],[3,1],[3,2],[5,2],[5,3],[7,3],[7,4],[10,4]])]),
        ('machine', None, 'A function called zeta connects prime numbers with a different mathematical picture.',
         'Introduce zeta as a symbolic machine connecting prime information and zeros.',
         [obj('primes','top-left'),obj('zeta','top-center'),obj('zeros','top-right'),
          connect('input','primes','zeta'),connect('output','zeta','zeros'),
          label('prime-name','primes','primes'),label('function-name','zeta','zeta'),label('zero-name','zeros','zeros')]),
        ('strip', None, 'A zero is an input where zeta outputs zero; these illustrative dots mark such locations.',
         'Introduce real and imaginary coordinates as horizontal and vertical location; show a schematic central line and dots.',
         [_axes([0,1],[0,10]),_shape('middle','vline',value=.5),
          *[_shape('zero-'+str(i),'dot',at=[.5,i]) for i in (2,4,6,8)]]),
        ('why', 'machine', 'Where zeros lie controls how far prime counts stray from a smooth estimate.',
         'Return to the zeta machine and connect zeros to the size of prime-counting errors; this arrow states a relationship, not a proof.',
         [obj('error','bottom-right'),connect('relation','zeros','error'),label('error-name','error','counting error')]),
        ('known', 'strip', 'Nontrivial zeros lie inside this strip, and none lie on its right edge.',
         'Add the known zero-free right boundary; distinguish knowledge from the central-line conjecture.',
         [_shape('edge','vline',value=1),label('edge-name','edge','known edge')]),
        ('old-zone', 'known', 'Schematically, the proven safe zone narrows as height increases.',
         'Shade a schematic narrowing sliver next to the right boundary; its shape is illustrative, not a numerical bound.',
         [_shape('old-safe','shade',points=[[.8,0],[.9,5],[.95,10],[1,10],[1,0]])]),
        ('hypothesis', None, 'RH predicts every nontrivial zero has horizontal coordinate one half.',
         'Use a separate number-line comparison to explain the central-line conjecture.',
         [_axes([0,1],[0,1]),_shape('half','vline',value=.5),label('rh-name','half','RH')]),
        ('new-wall', 'known', 'An unreviewed manuscript claims no zeros strictly to the right of seven eighths.',
         'Return to the known strip, not the earlier sliver; add a fixed seven-eighths boundary and claimed safe band.',
         [_shape('wall','vline',value=.875),_shape('claimed','region',x=[.875,1],y=[0,10],fill='hatch')]),
        ('open', 'hypothesis', 'Even if verified, that leaves a gap before the one-half line predicted by RH.',
         'Return to the number line, add the claimed boundary, and mark the remaining gap without calling the claim proved.',
         [_shape('wall','vline',value=.875),_shape('gap','brace',**{'from':[.5,.55],'to':[.875,.55]},side=1),
          label('gap-name','gap','still open')]),
        ], r'\frac{1}{2}<\frac{7}{8}<1')
    story['template'] = 'explain_result'
    story['acts'] = [dict(id=identity,beat=beat) for identity,beat in (
        ('what','Introduce primes, zeta and the meaning of a zero.'),
        ('why','Connect zero locations to prime-counting errors.'),
        ('known','Separate proven boundaries from schematic illustrations.'),
        ('open','State the central-line conjecture.'),
        ('new','Explain the unreviewed claim and the remaining gap.'))]
    for panel,act in zip(story['panels'], ['what']*4+['why']+['known']*2+['open']+['new']*2):
        panel['act'] = act
    story['takeaway'] += ' The manuscript also names Dirichlet and finite-order Hecke families; independent verification is not supplied here.'
    return story, shapes


def worked_examples():
    return {'integral':integral_example(), 'odd-squares':odd_squares_example(),
            'riemann-claim':riemann_example()}


def prompt_examples(role):
    """Same validated examples, but no shape/coordinate tokens for the planner."""
    rows = []
    for name,(story,shapes) in worked_examples().items():
        value = {'example':name,'story':story}
        if role == 'drawer':
            value['answer'] = dict(v=1,mode='story-shapes',panels=shapes)
        rows.append(json.dumps(value,ensure_ascii=False,separators=(',',':')))
    return '\nWorked examples (teaching patterns, never substitute for the actual question):\n'+'\n'.join(rows)
