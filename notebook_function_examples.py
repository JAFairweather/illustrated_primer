"""Authored renderer checks, not generated answers or physical-system claims."""
import math


def function_examples():
    cases=(
        ('periodic','How does a repeating quantity change?', 'cos',1,2*math.pi,0,0,[0,2],[-1,1],.5,
         'One cycle repeats every unit; the value reaches minus one halfway through.',
         'A cosine curve makes two full cycles across this interval.'),
        ('phase-offset','How do phase and offset change a cycle?', 'sin',.5,math.pi,math.pi/2,2,[0,2],[1.5,2.5],1,
         'This cycle is centered at two, with amplitude one half and period two.',
         'The sine curve starts one quarter-cycle ahead and oscillates around two.'),
        ('decay','What does exponential decay look like?', 'exp',1,-1,0,0,[0,3],[0,1],1,
         'Each horizontal unit multiplies the value by about 0.368; it stays positive.',
         'The curve follows exp(-x), starting at one and decreasing smoothly.'),
        ('growth','What does exponential growth look like?', 'exp',1,.4,0,0,[0,2],[0,2.5],1,
         'Each horizontal unit multiplies the value by about 1.492, not a fixed addition.',
         'The curve follows exp(0.4 x), starting at one and growing smoothly.'),
    )
    result={}
    for identity,question,name,amplitude,rate,phase,offset,domain,yrange,x,caption,curve_caption in cases:
        function=dict(name=name,amplitude=amplitude,rate=rate,phase=phase,offset=offset)
        story=dict(v=1,mode='story',audience='A student learning graphs',template='explain_concept',
            question=question,acts=[dict(id='build',beat='Relate a mathematical rule to its graph.')],
            panels=[],takeaway=caption+' These are illustrative mathematical values, not measurements.')
        captions=(('axes',None,'Use the displayed scales to read inputs and outputs.'),
                  ('curve','axes',curve_caption),
                  ('point','curve',caption))
        for pid,base,text in captions:
            story['panels'].append(dict(id=pid,act='build',base=base,title=pid.title(),
                question='What does this addition show?',new_idea=text,caption=text,visual_kind='graph'))
        y=offset+amplitude*getattr(math,name)(rate*x+phase)
        shapes={
            'axes':[dict(id='ax',type='axes',x=domain,y=yrange,aspect='independent')],
            'curve':[dict(id='function',type='plot',**{'in':'ax'},function=function,domain=domain)],
            'point':[dict(id='sample',type='dot',**{'in':'ax'},at=[x,y]),
                     dict(id='sample-name',type='label',to='sample',text=f'y={y:.3g}',side='auto')],
        }
        result[identity]=(story,{pid:dict(v=1,mode='panel-shapes',panel=pid,items=items)
                                for pid,items in shapes.items()})
    return result
