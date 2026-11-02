"""Typed native resource failure; never an authorization to relax a limit."""
from copy import deepcopy


class NativePenBudgetError(ValueError):
    """Validated geometry exceeds an existing stroke, point or pen-time cap."""

    def __init__(self, message, *, details=None):
        super().__init__(message)
        # Compiler-owned numeric context only. Never store input prose/paths.
        self.details = deepcopy(details) if details is not None else None


def native_budget_failure(error):
    """Unwrap existing compiler errors without interpreting their prose."""
    for _ in range(8):
        if isinstance(error, NativePenBudgetError):
            return deepcopy(error.details)
        error = getattr(error, '__cause__', None)
        if error is None:
            break
    return None


def budget_feedback(error):
    """Bounded machine-readable feedback; not acceptance or a repair request."""
    failure = native_budget_failure(error)
    if failure is None:
        return None
    attempts = None
    for _ in range(8):
        attempts = getattr(error, 'budget_attempts', None)
        if attempts:
            break
        error = getattr(error, '__cause__', None)
        if error is None:
            break
    return {'version': 1, 'attempts': deepcopy(attempts) if attempts else [{'failure': failure}]}
