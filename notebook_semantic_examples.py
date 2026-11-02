"""Developer-authored semantic fixtures, not model or tablet acceptance results."""
from copy import deepcopy
from notebook_procedural_demo import examples as procedural_examples


def examples():
    lever={'v':1,'mode':'lesson','intent':'Explain balanced turning effects',
           'scene':{'family':'mechanism','objects':[
               {'id':'beam','component':'lever','arms':{'values':[1,3],'unit':'m'},
                'forces':{'values':[3,1],'unit':'N'}}]},
           'steps':[
               {'reveal':['beam.body'],'caption':'The beam rests on a support and can turn around it.'},
               {'reveal':['beam.forces'],'caption':'The left force is three times larger; both arrows use the same scale.'},
               {'reveal':['beam.arms'],'caption':'The longer right arm gives the smaller force an equal turning effect.'}],
           'claims':[{'object':'beam','predicate':'balanced'}],
           'takeaway':'For perpendicular forces, turning effect is force times arm length. We neglect the beam’s weight.'}
    area={'v':1,'mode':'lesson','intent':'Explain area under an increasing curve',
          'scene':{'family':'quantitative','objects':[
              {'id':'area','component':'riemann_area','polynomial_coefficients_ascending':[0,0,1],
               'interval':[0,1],'partitions':[4,8],'sampling':'left'}]},
          'steps':[
              {'reveal':['area.axes','area.curve'],'caption':'The area below this curve is the quantity we want to measure.'},
              {'reveal':['area.coarse'],'caption':'Left-endpoint rectangles stay beneath an increasing curve, giving a lower estimate.'},
              {'reveal':['area.refinement'],'caption':'Halving the intervals adds narrow strips and improves the lower estimate.'},
              {'reveal':['area.exact_value'],'caption':'The polynomial antiderivative gives the exact area; finite rectangles only approximate it.'}],
          'claims':[{'object':'area','predicate':'increasing'},
                    {'object':'area','predicate':'refinement_improves'},
                    {'object':'area','predicate':'exact_integral','value':{'numerator':1,'denominator':3}}],
          'takeaway':'Refining the rectangles approaches the integral without turning a finite sketch into a proof.'}
    odd={'v':1,'mode':'lesson','intent':'Explain why consecutive odd numbers build a square',
         'scene':{'family':'quantitative','objects':[{'id':'square','component':'odd_square_growth','layers':4}]},
         'steps':[
             {'reveal':['square.layer1'],'caption':'One unit tile starts a one-by-one square.'},
             {'reveal':['square.layer2'],'caption':'An L of three new tiles completes a two-by-two square.'},
             {'reveal':['square.layer3'],'caption':'Five more tiles extend both sides to make a three-by-three square.'},
             {'reveal':['square.layer4'],'caption':'The next border adds four tiles across the top and three down the side, so seven tiles complete four-by-four.'}],
         'claims':[{'object':'square','predicate':'odd_border_growth'},
                   {'object':'square','predicate':'final_area','value':{'numerator':16,'denominator':1}}],
         'takeaway':'At every size k, the new border has k + (k - 1) = 2k - 1 tiles. Starting at one, these odd borders build an n-by-n square, so their sum is n squared.'}
    source=procedural_examples()['water-cycle']
    water={'v':1,'mode':'lesson','intent':'Explain the water cycle',
           'scene':{'family':'causal',
                    'objects':[{'id':o['id'],'component':o['shape'],'label':o['label']} for o in source['objects']],
                    'relations':[dict(r,type='process') for r in source['links']]},
           'steps':[{'reveal':s['add'],'caption':s['caption']} for s in source['steps']],
           'claims':[],'takeaway':source['takeaway']}
    lever_variant=deepcopy(lever)
    lever_variant['scene']['objects'][0]['arms']['values']=[2,5]
    lever_variant['scene']['objects'][0]['forces']['values']=[5,2]
    lever_variant['steps'][1]['caption']='The left force is larger, but magnitude alone does not determine the turning effect.'
    lever_variant['steps'][2]['caption']='Five newtons at two meters balances two newtons at five meters.'
    area_variant=deepcopy(area)
    area_variant['scene']['objects'][0].update(polynomial_coefficients_ascending=[0,0,0,1],interval=[0,2],partitions=[3,6])
    area_variant['claims'][-1]['value']={'numerator':4,'denominator':1}
    water_variant=deepcopy(water)
    water_variant['scene']['objects'][1]['label']='Lake'
    water_variant['steps'][0]['caption']='Sunlight warms the lake, supplying energy for evaporation.'
    water_variant['steps'][2]['caption']='Rain returns condensed water to the surface.'
    fractions={'v':1,'mode':'lesson','intent':'Explain equivalent fractions using equal wholes',
        'scene':{'family':'quantitative','objects':[{'id':'bars','component':'fraction_comparison',
            'fractions':[{'numerator':1,'denominator':2},{'numerator':2,'denominator':4}]}]},
        'steps':[
            {'reveal':['bars.wholes'],'caption':'Start with equal-sized wholes so the amounts can be compared fairly.'},
            {'reveal':['bars.partitions'],'caption':'Split the upper whole into halves and the lower one into quarters.'},
            {'reveal':['bars.first'],'caption':'One of the two equal parts selects half of the upper whole.'},
            {'reveal':['bars.second'],'caption':'Two of the four equal parts reach the same point, selecting the same amount.'}],
        'claims':[{'object':'bars','predicate':'equal'}],
        'takeaway':'Splitting each half into two quarters doubles both counts, not the amount: one half equals two fourths.'}
    fraction_variant=deepcopy(fractions)
    fraction_variant['intent']='Compare two thirds and three fifths'
    fraction_variant['scene']['objects'][0]['fractions']=[{'numerator':2,'denominator':3},{'numerator':3,'denominator':5}]
    fraction_variant['steps'][1]['caption']='Divide the upper whole into thirds and the lower whole into fifths.'
    fraction_variant['steps'][2]['caption']='Two thirds select two of the three equal pieces in the upper whole.'
    fraction_variant['steps'][3]['caption']='Three fifths select less of the equal-sized whole, despite the larger numerator.'
    fraction_variant['claims'][0]['predicate']='first_greater'
    fraction_variant['takeaway']='Compare the selected amounts of equal wholes, not just the counts: two thirds is greater than three fifths.'
    fraction_variant['scene']['objects'][0]['split_partitions']=True
    fraction_variant['steps']=[
        {'reveal':['bars.wholes'],'caption':'Start with two equal-sized wholes.'},
        {'reveal':['bars.upper_partitions'],'caption':'Divide the upper whole into thirds.'},
        {'reveal':['bars.lower_partitions'],'caption':'Divide the lower whole into fifths.'},
        {'reveal':['bars.first'],'caption':'Shade two of the three equal parts: two thirds.'},
        {'reveal':['bars.second'],'caption':'Shade three of the five equal parts: three fifths.'}]
    fraction_variant['takeaway']='Two thirds is greater: it covers more of the same-sized whole.'
    growth={'v':1,'mode':'lesson','intent':'Show how reinvested growth increases later gains',
        'scene':{'family':'quantitative','objects':[{'id':'growth','component':'sampled_chart',
            'x':[0,1,2,3,4],'y':[100,110,121,133.1,146.41],
            'x_label':'Year','y_label':'Balance'}]},
        'steps':[
            {'reveal':['growth.axes'],'caption':'Track an example balance over years, assuming ten percent growth reinvested annually.'},
            {'reveal':['growth.scale'],'caption':'A zero-based balance scale keeps the size of the change in perspective.'},
            {'reveal':['growth.samples'],'caption':'Calculated year-end balances rise from 100 to 110, 121, 133.10 and 146.41.'},
            {'reveal':['growth.links'],'caption':'Straight links guide the eye between yearly samples; later gains are larger because they apply to a larger balance.'}],
        'claims':[{'object':'growth','predicate':'increasing'}],
        'takeaway':'Reinvested growth earns growth of its own; these calculated samples illustrate the mechanism, not a guaranteed return.'}
    motion=deepcopy(growth)
    motion['intent']='Compare distances travelled in equal time intervals during free fall'
    motion['scene']['objects'][0].update(x=[0,1,2,3],y=[0,5,20,45],x_label='Time (s)',y_label='Distance (m)')
    motion['steps'][0]['caption']='For an object dropped from rest, neglect air resistance and use constant downward acceleration of ten meters per second squared.'
    motion['steps'][1]['caption']='Time runs horizontally and distance fallen vertically; this is a graph, not the path of the object.'
    motion['steps'][2]['caption']='Calculated distances after zero, one, two and three seconds are zero, five, twenty and forty-five meters.'
    motion['steps'][3]['caption']='The straight sample links get steeper, showing larger distance increments in equal times; the exact distance-time curve is smooth.'
    motion['takeaway']='Constant acceleration increases speed, so each equal time interval covers more distance; the distance fallen is five times time squared under these assumptions.'
    comparison=deepcopy(growth)
    comparison['intent']='Compare compounded growth against a fixed annual addition'
    comparison['scene']['objects'][0].update(x=[0,1,2,3],y=[100,110,121,133.1],
        label='Compounded',reference={'label':'Fixed gain','y':[100,110,120,130]})
    comparison['steps']=[
        {'reveal':['growth.axes','growth.scale'],'caption':'Compare a calculated example of ten percent annual growth with adding ten per year, both starting from 100.'},
        {'reveal':['growth.samples'],'caption':'Circles mark the compound balances: 100, 110, 121 and 133.10.'},
        {'reveal':['growth.links'],'caption':'Solid straight links guide the eye between annual samples, not an exact continuous curve.'},
        {'reveal':['growth.reference_samples'],'caption':'Crosses mark the fixed-gain balances: 100, 110, 120 and 130 on the same scale.'},
        {'reveal':['growth.reference_links'],'caption':'The dashed comparison shares the first segment, then grows less quickly; the separation is small on this zero-based scale.'},
        {'reveal':['growth.difference'],'caption':'At year three the compound balance exceeds the fixed-gain balance by 3.10.'}]
    comparison['claims'].append({'object':'growth','predicate':'final_above'})
    comparison['takeaway']='Reinvested gains earn gains themselves; in this calculated example compounding ends 3.10 higher after three years.'
    counts={'v':1,'mode':'lesson','intent':'Use group counts to explain a conditional proportion',
        'scene':{'family':'quantitative','objects':[{'id':'group','component':'count_grid',
            'rows':['Condition','No condition'],'columns':['Positive','Negative'],'counts':[[8,2],[9,81]],
            'selected':{'row':0,'column':0,'condition_on':'column'}}]},
        'steps':[
            {'reveal':['group.frame'],'caption':'Sort the 100 people by condition and test result, leaving space for totals.'},
            {'reveal':['group.columns'],'caption':'The two columns distinguish positive and negative test results.'},
            {'reveal':['group.row1'],'caption':'Of the ten people with the condition, eight test positive and two test negative.'},
            {'reveal':['group.row2'],'caption':'Of the 90 people without the condition, nine test positive and 81 test negative.'},
            {'reveal':['group.totals'],'caption':'There are 17 positives altogether, including nine false positives.'},
            {'reveal':['group.selection'],'caption':'Among the underlined Positive group, eight of the 17 have the condition.'}],
        'claims':[{'object':'group','predicate':'selected_fraction','value':{'numerator':8,'denominator':17}}],
        'takeaway':'Conditioning on a positive result changes the denominator to all 17 positives, so the answer is 8/17, not the 8/10 sensitivity.'}
    counts_variant=deepcopy(counts)
    counts_variant['intent']='Find the share of repaired items in one production batch'
    counts_variant['scene']['objects'][0].update(rows=['Batch A','Batch B'],columns=['Repaired','Untouched'],
        counts=[[12,28],[3,57]],selected={'row':1,'column':0,'condition_on':'row'})
    for step,caption in zip(counts_variant['steps'],[
        'Compare two batches using a two-way count grid.',
        'Separate repaired items from untouched items.',
        'Batch A has 12 repaired items and 28 untouched items.',
        'Batch B has three repaired items and 57 untouched items.',
        'The margins show 40 items in Batch A and 60 in Batch B.',
        'Among the underlined Batch B group, three of its 60 items were repaired.']):step['caption']=caption
    counts_variant['claims'][0]['value']={'numerator':1,'denominator':20}
    counts_variant['takeaway']='For the repair share within Batch B, divide its three repaired items by its own total of 60, giving 1/20.'
    motion_check={'v':1,'mode':'lesson','intent':'Renderer-only physical slow-drawing check',
        'scene':{'family':'drawing'},'claims':[],
        'steps':[
            {'caption':'Watch the line grow from left to right over about two seconds.',
             'draw':[{'op':'line','from':[40,40],'to':[540,40]}]},
            {'caption':'Watch the circle trace around its circumference.',
             'draw':[{'op':'circle','center':[170,215],'radius':85}]},
            {'caption':'Watch the rectangle turn each corner without appearing all at once.',
             'draw':[{'op':'rect','origin':[340,130],'size':[180,170]}]}],
        'takeaway':'This is a renderer test, not a model answer; judge motion on the physical display.'}
    return {'motion-check':motion_check,'lever':lever,'lever-variant':lever_variant,'integral':area,'integral-variant':area_variant,
            'water-cycle':water,'water-cycle-variant':water_variant,'odd-squares':odd,
            'fractions':fractions,'fractions-variant':fraction_variant,
            'sampled-growth':growth,'sampled-motion':motion,'sampled-comparison':comparison,
            'count-grid':counts,'count-grid-variant':counts_variant}
