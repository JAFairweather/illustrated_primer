"""Developer fixtures for general drawing+anchored labels, not model answers."""
from math import hypot


def triangle(a=3,b=4):
    unit=min(90/a,120/b)
    ax,ay=210,230
    A=[ax,ay];B=[ax,ay-a*unit];C=[ax+b*unit,ay]
    # Three new sides per square; its shared triangle edge is not redrawn.
    left=[B,[ax-a*unit,B[1]],[ax-a*unit,ay],A]
    base=[A,[ax,ay+b*unit],[C[0],ay+b*unit],C]
    dx,dy=C[0]-B[0],C[1]-B[1]
    hyp=[B,[B[0]+dy,B[1]-dx],[C[0]+dy,C[1]-dx],C]
    h=hypot(a,b)
    return dict(v=1,mode='lesson',intent='Explain a particular right triangle using side squares',
        scene={'family':'drawing'},claims=[],steps=[
            {'caption':f'The perpendicular legs have lengths {a:g} and {b:g}.','draw':[
                {'op':'line','id':'vertical','from':A,'to':B},
                {'op':'line','id':'base','from':A,'to':C},
                {'op':'line','id':'hypotenuse','from':B,'to':C},
                {'op':'polyline','points':[[ax,ay-12],[ax+12,ay-12],[ax+12,ay]]},
                {'op':'label','target':'vertical','text':f'{a:g}'},
                {'op':'label','target':'base','text':f'{b:g}'}]},
            {'caption':f'The square on the first leg has area {a*a:g}.','draw':[
                {'op':'polyline','id':'first-square','points':left},
                {'op':'label','target':'first-square','text':f'{a:g}²'}]},
            {'caption':f'The square on the second leg has area {b*b:g}.','draw':[
                {'op':'polyline','id':'second-square','points':base},
                {'op':'label','target':'second-square','text':f'{b:g}²'}]},
            {'caption':f'Applying the Pythagorean theorem gives hypotenuse-square area {a*a+b*b:g} and side {h:g}.','draw':[
                {'op':'polyline','id':'third-square','points':hyp},
                {'op':'label','target':'third-square','text':f'{h:g}²'},
                {'op':'label','target':'hypotenuse','text':f'{h:g}'}]}],
        equation=f'{a:g}^2+{b:g}^2={a*a+b*b:g}={h:g}^2',
        takeaway='These correctly scaled side squares illustrate this numerical instance; they do not establish a proof for every right triangle.')


def scattering():
    return dict(v=1,mode='lesson',intent='Show incoming and scattered light with sparse straight rays',
        scene={'family':'drawing'},claims=[],steps=[
            {'caption':'Sunlight contains a mixture of visible wavelengths.','draw':[
                {'op':'circle','id':'sun','center':[80,100],'radius':25},
                {'op':'label','target':'sun','text':'Sun'},
                {'op':'circle','id':'eye','center':[500,270],'radius':15},
                {'op':'label','target':'eye','text':'Observer'}]},
            {'caption':'An air molecule scatters some of the incident sunlight.','draw':[
                {'op':'circle','id':'air','center':[300,150],'radius':6},
                {'op':'label','target':'air','text':'Air molecule'},
                {'op':'arrow','id':'incoming','from':[105,105],'to':[294,149]},
                {'op':'label','target':'incoming','text':'White light'}]},
            {'caption':'Shorter blue wavelengths scatter more strongly, sending blue light toward an observer away from the Sun.','draw':[
                {'op':'arrow','id':'scattered','from':[305,154],'to':[488,260]},
                {'op':'label','target':'scattered','text':'Blue light'}]}],
        takeaway='This simplified ray sketch shows one scattering event, not blue paint in the air; many molecules send scattered light toward us from across the sky.')


def examples():
    return {'anchored-triangle':triangle(),'anchored-triangle-scaled':triangle(6,8),
            'anchored-scattering':scattering()}
