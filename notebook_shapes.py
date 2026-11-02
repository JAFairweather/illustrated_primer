"""Small deterministic semantic pen motifs; no device I/O or model coordinates.

Motifs expose named anchors. Scene code composes them, rather than asking the
language model to emit point lists. Points are densely sampled by the compiler
boundary's scene builder before any asset can be provisioned.
"""
import math


def arrow(start, end, head=10):
    dx, dy = end[0]-start[0], end[1]-start[1]
    length = math.hypot(dx,dy)
    if not math.isfinite(length) or length < 1 or not 1 <= head <= 30:
        raise ValueError('bounded nonzero arrow required')
    ux, uy = dx/length, dy/length
    h = min(head,length/3)
    left = (end[0]-h*ux-h*.5*uy,end[1]-h*uy+h*.5*ux)
    right = (end[0]-h*ux+h*.5*uy,end[1]-h*uy-h*.5*ux)
    return [list((start,end)),list((left,end,right))]


def square_growth_layer(n, origin=(60,230), cell=45):
    """Add the next odd L to an (n-1)² lattice, preserving every old edge.

    Grid coordinates grow up/right from a fixed bottom-left anchor. Shared
    boundaries are emitted exactly once across all stages. Sparse alternating
    hatches distinguish adjacent L layers without requiring colors or erasure.
    """
    if type(n) is not int or not 1 <= n <= 6 or type(cell) is not int or not 24 <= cell <= 60:
        raise ValueError('bounded 1..6 layer and 24..60 unit cell required')
    if len(origin) != 2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in origin):
        raise ValueError('finite motif origin required')
    ox, base = origin
    if ox < 0 or base-n*cell < 0:
        raise ValueError('growth motif must remain in positive diagram space')
    def vertices(i,j):
        x,y = ox+i*cell,base-j*cell
        return ((x,y),(x+cell,y),(x+cell,y-cell),(x,y-cell))
    def edges(size):
        result = set()
        for i in range(size):
            for j in range(size):
                v = vertices(i,j)
                result.update(tuple(sorted((v[k],v[(k+1)%4]))) for k in range(4))
        return result
    additions = [(i,j) for i in range(n) for j in range(n) if i == n-1 or j == n-1]
    new_edges = sorted(edges(n)-edges(n-1))
    paths = [list(edge) for edge in new_edges]
    for i,j in additions:
        x,y = ox+i*cell,base-j*cell
        inset = cell*.22
        # Stays strictly inside its own unit cell, never across a border.
        paths.append([(x+inset,y-inset if n%2 else y-cell+inset),
                      (x+cell-inset,y-cell+inset if n%2 else y-inset)])
    top,right = base-n*cell,ox+n*cell
    return dict(paths=paths,edges=new_edges,new_cells=additions,
                added_units=len(additions),total_units=n*n,
                anchors=dict(bottom_left=(ox,base),top_left=(ox,top),top_right=(right,top),
                             bottom_right=(right,base),center=((ox+right)/2,(base+top)/2),
                             label_target=(ox,top+cell/2)))
