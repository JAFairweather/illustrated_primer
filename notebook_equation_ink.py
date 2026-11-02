"""Bounded equation grammar to ordered single-stroke math, without raster tracing.

Renderer-owned layout: the model supplies the existing equation string only.
This module prepares/validates ink offline; it does not insert or enable it live.
"""
import hashlib
import math
from dataclasses import dataclass, field

from notebook_media import Equation
from notebook_plotter_font import label_paths
from notebook_storyboard import _dense
from notebook_drawing import compile_storyboard


@dataclass
class PenBox:
    width: float
    height: float
    baseline: float
    paths: list = field(default_factory=list)
    limits: bool = False


def canvas(width, height, baseline):
    if not all(math.isfinite(v) and v >= 0 for v in (width, height, baseline)) or width > 16000 or height > 8000:
        raise ValueError('pen equation layout too large')
    return PenBox(max(1,width), max(1,height), baseline)


def shifted(box, x, y):
    return [[(px+x,py+y) for px,py in line] for line in box.paths]


def glyph(text, size):
    out = canvas(1,size*1.35,size)
    advance = 0
    for char in text:
        paths, width = label_paths(char,20)
        scale = size/20
        out.paths.extend([[(advance+x*scale,y*scale) for x,y in p] for p in paths])
        advance += width*scale
    out.width=max(1,advance)
    return out


def row(parts):
    if not parts:
        return glyph(' ',20)
    baseline=max(p.baseline for p in parts)
    out=canvas(sum(p.width for p in parts),baseline+max(p.height-p.baseline for p in parts),baseline)
    x=0
    for part in parts:
        out.paths.extend(shifted(part,x,baseline-part.baseline)); x+=part.width
    return out


def fraction(numerator, denominator, size):
    gap=max(3,size*.13)
    width=max(numerator.width,denominator.width)+2*gap
    bar=numerator.height+gap
    out=canvas(width,bar+gap+denominator.height,bar+size*.27)
    out.paths.extend(shifted(numerator,(width-numerator.width)/2,0))
    out.paths.append([(1,bar),(width-1,bar)])
    out.paths.extend(shifted(denominator,(width-denominator.width)/2,bar+gap))
    return out


def scripts(base, upper, lower):
    up_y=(-upper.height*.2 if base.limits else base.baseline-upper.height-3) if upper else 0
    low_y=base.height-lower.height*.2 if base.limits and lower else base.baseline+4
    shift=max(0,-up_y) if upper else 0
    out=canvas(base.width+max([p.width for p in (upper,lower) if p] or [0]),
               max(base.height,low_y+(lower.height if lower else 0))+shift,base.baseline+shift)
    out.paths.extend(shifted(base,0,shift))
    if upper: out.paths.extend(shifted(upper,base.width,up_y+shift))
    if lower: out.paths.extend(shifted(lower,base.width,low_y+shift))
    return out


def integral(size):
    out=canvas(size*.65,size*2.4,size*1.65);out.limits=True
    segments=[((.57,.12),(.12,-.15),(.40,1.0),(.25,1.35)),
              ((.25,1.35),(.12,2.14),(.15,2.3),(.02,2.05))]
    line=[]
    for a,b,c,d in segments:
        for i in range(41):
            t=i/40
            line.append(tuple(size*((1-t)**3*a[k]+3*(1-t)**2*t*b[k]+3*(1-t)*t*t*c[k]+t**3*d[k]) for k in (0,1)))
    out.paths=[line]
    return out


def radical(body, size):
    left,top=size*.6,6
    height=max(body.height+top+4,size)
    out=canvas(left+body.width+6,height,body.baseline+top)
    out.paths=[[(1,height*.53),(left*.25,height*.48),(left*.48,height-3),(left-2,2),(out.width-2,2)]]
    out.paths.extend(shifted(body,left,top))
    return out


def math_symbol(symbol, size):
    if symbol in ('Delta','times'):
        return glyph({'Delta':'Δ','times':'×'}[symbol],size)
    if symbol=='sum':
        out=glyph('Σ',size*1.6);out.limits=True;return out
    out=canvas(size*1.2,size*1.35,size)
    center=size*.65
    if symbol=='approx':
        out.paths=[[(size*(.1+i/25),center+size*(offset+.06*math.sin(2*math.pi*i/24))) for i in range(25)] for offset in (-.12,.12)]
    elif symbol=='Rightarrow':
        out.paths=[[(size*.1,center+size*d),(size*.8,center+size*d)] for d in (-.1,.1)]
        out.paths.append([(size*.7,center-size*.28),(size*1.1,center),(size*.7,center+size*.28)])
    elif symbol in ('cdots','ldots'):
        y=center if symbol=='cdots' else size
        out.paths=[[(size*x,y),(size*x+.1,y)] for x in (.2,.5,.8)]
    else:
        raise ValueError('unsupported pen math symbol')
    return out


RENDERER=dict(canvas=canvas,glyph=glyph,row=row,fraction=fraction,scripts=scripts,
              integral=integral,radical=radical,math_symbol=math_symbol)


def equation_plan(source):
    """One renderer-owned math region with the SAME stroke/point/time limits.

    Layout wider/taller than the region is rejected, not squeezed unreadably.
    The caller must budget this alongside the complete lesson before insertion.
    """
    if not isinstance(source,str) or not 1<=len(source)<=400:
        raise ValueError('pen equation needs 1..400 characters')
    box=Equation(source,RENDERER).parse(size=36)
    if box.width>560 or box.height>160 or not box.paths:
        raise ValueError('pen equation does not fit its readable region')
    paths=_dense(shifted(box,20,20))
    plan=dict(kind='native-pen-storyboard-plan',scene='equation-'+hashlib.sha256(source.encode()).hexdigest()[:24],
              width=600,height=200,stages=[dict(id='equation',title='Equation',text='Read the mathematical result.',
                                            paths=paths,annotations=[])])
    compile_storyboard(plan)
    return plan
