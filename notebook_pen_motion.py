"""Pure bounded motion planning for attended pen-input experiments.

Short contact segments allow the tablet to process telemetry between pen lifts.
This is not a page/input lock and is not wired into the reply adapter. Splitting
preserves the path geometry; it does not erase, retry, or redraw any segment.
"""
import math


def _points(path):
    if not isinstance(path,(list,tuple)) or not 2<=len(path)<=3000:
        raise ValueError('bounded stroke path required')
    points=[]
    for p in path:
        if (not isinstance(p,(list,tuple)) or len(p)!=2 or
                any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>10000 for v in p)):
            raise ValueError('finite stroke point required')
        if not points or tuple(p)!=points[-1]:points.append(tuple(p))
    if sum(math.dist(a,b) for a,b in zip(points,points[1:]))<=0:
        raise ValueError('nonzero stroke required')
    return points


def sample_motion_path(path,max_step=1.25):
    """Densify screen-space paths without changing their shape or corners.

    The native pen pipeline can overshoot sparse endpoints. An attended paired
    test reduced circle radial error from 6.53 to 0.57 px at ~1.1 px spacing.
    Reject expansion beyond 3,000 points; never silently coarsen or truncate.
    This does not change motion duration, acquire a lock, or perform any I/O.
    """
    if type(max_step) not in (int,float) or not .25<=max_step<=2:
        raise ValueError('motion sample spacing must be within 0.25..2 pixels')
    points=_points(path)
    counts=[math.ceil(math.dist(a,b)/max_step) for a,b in zip(points,points[1:])]
    if 1+sum(counts)>3000:raise ValueError('motion sample point budget exceeded')
    result=[points[0]]
    for a,b,count in zip(points,points[1:],counts):
        result.extend(tuple(a[k]+(b[k]-a[k])*i/count for k in (0,1)) for i in range(1,count))
        result.append(b)  # Keep exact original vertices, not rounded interpolation.
    return result


def motion_chunks(path, duration, max_contact=.65):
    """Split a logical stroke by arc length, retaining every original corner.

    Duration is motion time only; native pen-up and telemetry waits add time.
    The caller must stop on any failed guard and never replay an emitted chunk.
    """
    if (type(duration) not in (int,float) or not .1<=duration<=30 or
            type(max_contact) not in (int,float) or not .2<=max_contact<=1):
        raise ValueError('bounded motion/contact duration required')
    points=_points(path)
    total=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    count=math.ceil(duration/max_contact)
    if count>64:raise ValueError('contact segment budget exceeded')
    limit=total/count
    chunks=[];current=[points[0]];travelled=0.0
    for a,endpoint in zip(points,points[1:]):
        length=math.dist(a,endpoint)
        end=travelled+length
        while len(chunks)<count-1 and limit*(len(chunks)+1)<=end:
            fraction=(limit*(len(chunks)+1)-travelled)/length
            joint=tuple(a[k]+fraction*(endpoint[k]-a[k]) for k in (0,1))
            if joint!=current[-1]:current.append(joint)
            chunks.append({'points':current,'duration':duration/count})
            current=[joint]
        if endpoint!=current[-1]:current.append(endpoint)
        travelled=end
    chunks.append({'points':current,'duration':duration-sum(c['duration'] for c in chunks)})
    if len(chunks)!=count:raise ValueError('motion partition did not converge')
    return chunks
