"""Worked drawing-language lessons used verbatim in the agent prompt and eval."""
from notebook_lesson import format_lesson


def integral_example():
    return format_lesson([
        {'caption': 'The integral measures the area beneath y = x² between zero and one.',
         'draw': [
             {'op':'polyline','points':[[80,70],[80,290],[500,290]]},
             {'op':'plot','points':[[80+50*i,290-200*(i/8)**2] for i in range(9)]},
             {'op':'label','at':[370,65],'text':'y = x²'},
             {'op':'label','at':[72,322],'text':'0'},
             {'op':'label','at':[475,322],'text':'1'}]},
        {'caption': 'Four equal slices, using the left-edge heights, give rectangles that underestimate the area.',
         'draw': [
             {'op':'rect','origin':[180,277.5],'size':[100,12.5]},
             {'op':'rect','origin':[280,240],'size':[100,50]},
             {'op':'rect','origin':[380,177.5],'size':[100,112.5]}]},
        {'caption': 'The marked gaps shrink as the slices become finer, so the limiting sum gives the exact area.',
         'draw': [
             {'op':'line','from':[420,177.5],'to':[420,145.5]},
             {'op':'line','from':[440,177.5],'to':[440,128]},
             {'op':'line','from':[460,177.5],'to':[460,109.5]},
             {'op':'arrow','from':[540,115],'to':[462,142]},
             {'op':'label','at':[500,95],'text':'gaps'}]},
    ], 'The area is 1/3; the finite rectangles illustrate the limit, not the exact area.',
       r'\int_0^1 x^2\,dx=\frac{1}{3}')


def odd_squares_example():
    steps = []
    captions = ['One unit square starts the picture.',
                'An L-shaped border adds three units to make a two-by-two square.',
                'The next L adds five units to make a three-by-three square.',
                'Adding seven completes a four-by-four square, showing how each odd border grows the square.']
    # Explicit geometry in the emitted example; the agent need not write code.
    seen = set()
    for n, caption in enumerate(captions, 1):
        edges = set()
        for row in range(n):
            for col in range(n):
                x, y = 150+45*col, 285-45*row
                corners = [(x,y),(x+45,y),(x+45,y-45),(x,y-45)]
                edges.update(tuple(sorted((corners[i], corners[(i+1)%4]))) for i in range(4))
        commands = [{'op':'line','from':list(a),'to':list(b)} for a,b in sorted(edges-seen)]
        commands.append({'op':'label','at':[350,150+35*(n-1)],'text':str(2*n-1) if n == 1 else '+'+str(2*n-1)})
        steps.append({'caption':caption,'draw':commands})
        seen = edges
    return format_lesson(steps,
        'Every new border has k + (k - 1) = 2k - 1 units, so the first n odd numbers fill an n-by-n square.',
        r'1+3+5+7=4^2=16')


EXAMPLES = {'integral': integral_example, 'odd-squares': odd_squares_example}
