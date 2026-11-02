"""Bounded mathematical functions -> data points, with no executable syntax.

The renderer owns sampling. Parameters describe quantities, never pen paths.
Every sinusoidal extremum is included so frame validation cannot overlook a
peak between uniform samples. Existing downstream ink limits remain binding.
"""
import math

from notebook_lesson import _fields, _number


def function_points(function, domain):
    """Sample offset + amplitude * name(rate*x + phase), phase in radians.

    sin/cos span at most four cycles; exp arguments stay in [-30,30].
    These are bounded smooth-curve approximations, not exact continuous ink.
    No input points are clipped, decimated or replaced to fit an ink budget.
    """
    _fields(function, {'name','amplitude','rate','phase','offset'})
    name=function['name']
    if not isinstance(name,str) or name not in ('sin','cos','exp'):
        raise ValueError('function name must be sin, cos or exp; never code')
    amplitude,rate,phase,offset=[_number(function[k],-1e6,1e6)
                               for k in ('amplitude','rate','phase','offset')]
    if not isinstance(domain,list) or len(domain)!=2:
        raise ValueError('function domain requires two numbers')
    a,b=[_number(v,-1e6,1e6) for v in domain]
    if b-a<1e-9:
        raise ValueError('function domain must increase')
    lo,hi=sorted((rate*a+phase,rate*b+phase))
    if name=='exp':
        if lo < -30 or hi > 30:
            raise ValueError('exponential arguments must remain in [-30,30]')
        intervals=64
    else:
        if max(abs(lo),abs(hi))>10000 or hi-lo>8*math.pi:
            raise ValueError('trigonometric plot requires at most four cycles and bounded phase')
        intervals=max(32,math.ceil((hi-lo)/(2*math.pi)*32))
    if amplitude==0 or rate==0:
        intervals=1
    xs={a,b}
    xs.update(a+(b-a)*i/intervals for i in range(1,intervals))
    if name in ('sin','cos') and rate and amplitude:
        shift=math.pi/2 if name=='sin' else 0
        for k in range(math.ceil((lo-shift)/math.pi),math.floor((hi-shift)/math.pi)+1):
            x=(shift+k*math.pi-phase)/rate
            if a<=x<=b:
                xs.add(x)
    operation={'sin':math.sin,'cos':math.cos,'exp':math.exp}[name]
    values=[[x,offset+amplitude*operation(rate*x+phase)] for x in sorted(xs)]
    if len(values)>160 or any(not math.isfinite(y) for _,y in values):
        raise ValueError('function samples exceed bounded finite geometry')
    return values
