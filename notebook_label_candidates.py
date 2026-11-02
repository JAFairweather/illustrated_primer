"""Bounded edge-aligned label candidates; no geometry or safety decisions.

The whole-scene placement solver still checks every returned candidate. These
fallbacks slide a label along an object's edge, never move its geometry or an
explicitly positioned label, and never change text or font size.
"""


def edge_slides(bounds, local_box, gaps=(12, 24, 36), *, along_edge=False):
    left, top, right, bottom = bounds
    lx, ly, rx, ry = local_box
    # Match the existing solver's six-unit label padding plus four-unit inset.
    min_x, max_x = 10-lx, 590-rx
    min_y, max_y = 10-ly, 350-ry
    if min_x > max_x or min_y > max_y:
        return []
    cx, cy = (left+right)/2, (top+bottom)/2
    center = min(max(cx, min_x), max_x)
    baseline = min(max(cy-(ly+ry)/2, min_y), max_y)
    result = []
    for gap in gaps:
        # Keep the owner's centre within the label's projection: clipping
        # candidates to the canvas must not turn them into remote captions.
        if center+lx <= cx <= center+rx:
            result.extend(((center, top-gap-ry),
                           (center, bottom+gap-ly)))
        if baseline+ly <= cy <= baseline+ry:
            result.extend(((right+gap-lx, baseline),
                           (left-gap-rx, baseline)))
    if not along_edge:
        return result
    # An owner's midpoint can coincide with a later divider. Slide along the
    # same edge instead of detaching the label to a remote canvas position.
    # Region pointers independently choose a clear edge anchor; the joint
    # solver still checks every label, pointer and obstacle without shrinking.
    for fraction in (.25, .75, .125, .875):
        x = left+(right-left)*fraction
        y = top+(bottom-top)*fraction-(ly+ry)/2
        for gap in gaps:
            if min_x <= x <= max_x:
                result.extend(((x,top-gap-ry),(x,bottom+gap-ly)))
            if min_y <= y <= max_y:
                result.extend(((right+gap-lx,y),(left-gap-rx,y)))
    return result


def corner_callouts(bounds, local_box, *, diagonal=False):
    """Twelve nearby alternatives for labels with checked ownership pointers.

    Leave the usual vertical clearance but extend horizontally beyond a busy
    corner. This lets two annotations share an owner without stacking text or
    shrinking it. These are candidates only: the caller must validate the
    complete pointer, text box, canvas bounds and other annotations. A point
    has no extended edge to slide along: diagonal candidates gain clearance
    in both dimensions instead of hugging a nearby axis or curve.
    """
    left, top, right, bottom = bounds
    lx, ly, rx, ry = local_box
    return [(x, y) for gap in (36, 48, 60)
            for x in (left-gap-rx, right+gap-lx)
            for y in (top-(gap if diagonal else 12)-ry,
                      bottom+(gap if diagonal else 12)-ly)]
