"""Authored data-space panel fixtures, not generated-agent evaluation results."""


def graph_reuse_example():
    story = dict(v=1, mode='story', audience='A new algebra student', template='explain_concept',
        question='How does a graph show a relationship?',
        acts=[dict(id='build',beat='Build one coordinate picture.'),
              dict(id='compare',beat='Return to the original axes and compare another relationship.')],
        panels=[], takeaway='Compare both relationships using the same coordinates and scale.')
    for identity,act,base,caption in (
            ('axes','build',None,'Start with two axes and their scales.'),
            ('curve','build','axes','Each point shows an input and its squared output.'),
            ('mark','build','curve','At one half, the squared output is one quarter.'),
            ('branch','compare','axes','Return to the original axes and draw a straight relationship.')):
        story['panels'].append(dict(id=identity,act=act,base=base,title=identity.title(),
            question='What does this addition show?',new_idea=caption,caption=caption,visual_kind='graph'))
    drawings = {
        'axes':[dict(id='ax',type='axes',x=[0,1],y=[0,1],aspect='independent')],
        'curve':[dict(id='square',type='plot',**{'in':'ax'},coefficients=[0,0,1],domain=[0,1])],
        'mark':[dict(id='half',type='dot',**{'in':'ax'},at=[.5,.25]),
                dict(id='note',type='label',to='half',text='one quarter',side='auto')],
        'branch':[dict(id='linear',type='line',**{'in':'ax','from':[0,0],'to':[1,1]})],
    }
    return story, {identity:dict(v=1,mode='panel-shapes',panel=identity,items=items)
                   for identity,items in drawings.items()}


def relationship_example():
    """Authored contract example; not a model result or causal inference."""
    story = dict(v=1,mode='story',audience='A reader learning diagrams',template='explain_concept',
        question='How can a diagram explain a relationship?',
        acts=[dict(id='explain',beat='Introduce objects, then explain their relationship.')],
        panels=[],takeaway='Read the arrow direction together with its caption, not proximity alone.')
    for identity,base,caption in (
            ('objects',None,'Start with two named objects.'),
            ('forward','objects','The arrow shows information flowing from input to output.'),
            ('observer','forward','A person can receive the output.'),
            ('reverse','objects','Return to the original objects and reverse the information flow.')):
        story['panels'].append(dict(id=identity,act='explain',base=base,title=identity.title(),
            question='What does this addition communicate?',new_idea=caption,caption=caption,visual_kind='relationship'))
    drawings = {
        'objects':[dict(id='input',type='object',shape='box',position='top-left'),
                   dict(id='output',type='object',shape='box',position='top-right'),
                   dict(id='input-name',type='label',to='input',text='Input',side='auto'),
                   dict(id='output-name',type='label',to='output',text='Output',side='auto')],
        'forward':[dict(id='flow',type='connect',**{'from':'input','to':'output'}),
                   dict(id='flow-name',type='label',to='flow',text='data',side='auto')],
        'observer':[dict(id='reader',type='object',shape='person',position='bottom-center'),
                    dict(id='delivery',type='connect',**{'from':'output','to':'reader'})],
        'reverse':[dict(id='feedback',type='connect',**{'from':'output','to':'input'})],
    }
    return story, {identity:dict(v=1,mode='panel-shapes',panel=identity,items=items)
                   for identity,items in drawings.items()}


def primitive_capabilities_example():
    """Renderer fixture, not a generated lesson or a model-quality result."""
    story, _ = graph_reuse_example()
    story.update(question='How do regions, sampled curves and braces build one picture?',
                 audience='A reader of a drawing-language demonstration',
                 acts=[dict(id='build',beat='Add three different kinds of ink to one coordinate picture.')],
                 takeaway='The model describes shapes; the engine calculates the pen strokes.')
    captions = [
        ('axes', None, 'Start with a fixed coordinate frame.'),
        ('zone', 'axes', 'Shade an L-shaped region without filling its empty corner.'),
        ('curve', 'zone', 'Join these measured samples in their supplied order.'),
        ('measure', 'curve', 'Use a brace to identify the horizontal span of the samples.'),
    ]
    story['panels'] = [dict(id=identity,act='build',base=base,title=identity.title(),
        question='What does this addition show?',new_idea=caption,caption=caption,visual_kind='graph')
        for identity,base,caption in captions]
    drawings = {
        'axes':[dict(id='ax',type='axes',x=[0,1],y=[0,1],aspect='independent')],
        'zone':[dict(id='zone',type='shade',**{'in':'ax'},
                     points=[[.1,.1],[.9,.1],[.9,.35],[.4,.35],[.4,.9],[.1,.9]]),
                dict(id='zone-name',type='label',to='zone',text='Region',side='left')],
        'curve':[dict(id='samples',type='plot',**{'in':'ax'},
                      points=[[.5,.55],[.6,.8],[.75,.6],[.9,.8]])],
        'measure':[dict(id='span',type='brace',**{'in':'ax','from':[.5,.9],'to':[.9,.9]},side=1),
                   dict(id='span-name',type='label',to='span',text='span',side='top')],
    }
    return story, {identity:dict(v=1,mode='panel-shapes',panel=identity,items=items)
                   for identity,items in drawings.items()}
