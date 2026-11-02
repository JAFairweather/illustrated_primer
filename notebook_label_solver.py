"""Bounded joint selection of immutable label-placement candidates.

Choose the label with the fewest currently compatible positions, not just
the fewest before any other label was placed. Forward checking discards a
branch as soon as it strands another label. No geometry, font or words change.
"""


class LabelSearchBudgetExceeded(ValueError):
    pass


def select_labels(options, conflict, *, work_limit=4096, fallback_options=None):
    """Return a complete assignment, or None; never a partial placement.

    Deterministic input/candidate order breaks ties. The work budget charges
    both candidate choices and uncached pair checks, so pruning does not hide
    an unbounded second search. Compatibility is symmetric; cache only pairs
    actually examined, bounded by the same budget. Optional fallback positions
    are considered only after the original domains prove unsatisfiable; the
    same cache and work allowance cover BOTH searches, never a budget reset.
    """
    if type(work_limit) is not int or work_limit < 1:
        raise ValueError('positive label search budget required')
    selected = {}
    cache = {}
    work = 0

    def charge():
        nonlocal work
        work += 1
        if work > work_limit:
            raise LabelSearchBudgetExceeded('label placement search budget exceeded')

    def incompatible(a, b):
        key = tuple(sorted((id(a), id(b))))
        if key not in cache:
            charge()
            cache[key] = conflict(a, b)
        return cache[key]

    def search(domains, causes):
        # None means success; a set names earlier choices implicated in a
        # failure. Track an over-approximation of why each domain lost values.
        # If a failing subtree does not depend on this choice, trying another
        # value here cannot repair it. Backtrack directly to an implicated
        # choice rather than enumerating unrelated annotations.
        if not domains:
            return None
        identity = min(domains, key=lambda key: len(domains[key]))
        failed = set(causes[identity])
        for option in domains[identity]:
            charge()
            remaining = {}
            next_causes = {}
            for other, candidates in domains.items():
                if other == identity:
                    continue
                compatible = tuple(candidate for candidate in candidates
                                   if not incompatible(option, candidate))
                reason = causes[other]
                if len(compatible) != len(candidates):
                    reason = reason | {identity}
                if not compatible:
                    failed.update(reason - {identity})
                    break
                remaining[other] = compatible
                next_causes[other] = reason
            else:
                selected[identity] = option
                reason = search(remaining, next_causes)
                if reason is None:
                    return None
                del selected[identity]
                if identity not in reason:
                    return reason
                failed.update(reason - {identity})
        return failed

    domains = {key: tuple(value) for key,value in options.items()}
    if search(domains, {key: set() for key in domains}) is None:
        return dict(selected)
    if fallback_options and any(fallback_options.values()):
        expanded = {key: value+tuple(fallback_options.get(key, ()))
                    for key,value in domains.items()}
        if search(expanded, {key: set() for key in expanded}) is None:
            return dict(selected)
    return None
