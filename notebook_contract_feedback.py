"""Bounded, value-free feedback for correcting typed lesson syntax.

This module never repairs input. It reports only declared schema keys, static
JSON paths and counts; arbitrary unexpected keys/values are not echoed.
"""
from copy import deepcopy
import json
from notebook_pen_budget import budget_feedback


class ContractError(ValueError):
    def __init__(self, message, *, code, path, **details):
        super().__init__(message)
        self.feedback = dict(code=code, path=path, **details)


def exact_fields(value, required, *, path='/', optional=()):
    optional = set(optional)
    expected = sorted(required | optional)
    detail = {'optional_keys': sorted(optional)} if optional else {}
    if not isinstance(value, dict):
        raise ContractError('typed object required at '+path, code='object_required',
                            path=path, expected_keys=expected, **detail)
    missing = sorted(required-set(value))
    unexpected = len(set(value)-required-optional)
    if missing or unexpected:
        raise ContractError('missing or unknown drawing fields at '+path,
                            code='object_fields', path=path, expected_keys=expected,
                            missing_keys=missing, unexpected_key_count=unexpected, **detail)


_DATA = {'id', 'type', 'in'}
ITEM_FIELDS = {
    'axes': {'id', 'type', 'x', 'y', 'aspect'},
    'line': _DATA | {'from', 'to'},
    'arrow': _DATA | {'from', 'to'},
    'brace': _DATA | {'from', 'to', 'side'},
    'shade': _DATA | {'points'},
    'vline': _DATA | {'value'},
    'hline': _DATA | {'value'},
    'dot': _DATA | {'at'},
    'rect': _DATA | {'x', 'y'},
    'region': _DATA | {'x', 'y', 'fill'},
    'circle': _DATA | {'center', 'radius'},
    'polyline': _DATA | {'points'},
    'plot': _DATA | {'coefficients', 'domain'},
    'riemann': _DATA | {'coefficients', 'domain', 'baseline', 'count', 'sample'},
    'area': _DATA | {'coefficients', 'domain', 'baseline', 'fill'},
    'label': {'id', 'type', 'to', 'text', 'side'},
    'object': {'id', 'type', 'shape', 'position'},
    'connect': {'id', 'type', 'from', 'to'},
}

# Rectangle outlines predate filled regions. An explicit fill is the same
# bounded capability for either spelling, not a discarded unexpected field.
# Region keeps its required fill; old rect inputs remain outlines unchanged.
ITEM_OPTIONAL_FIELDS = {'rect': {'fill'}, 'axes': {'visible'}}


def item_fields(value, *, path='/'):
    if not isinstance(value, dict):
        raise ContractError('typed panel item required at '+path,
                            code='object_required', path=path)
    kind = value.get('type')
    if not isinstance(kind, str) or kind not in ITEM_FIELDS:
        # Unsupported capabilities are not reinterpreted as a formatting error.
        raise ValueError('unsupported typed panel shape')
    # Sampled curves are data, not executable expressions. Exactly one plot
    # representation is accepted; mixed coefficients/points are not repaired.
    required = ITEM_FIELDS[kind]
    if kind == 'plot':
        if 'points' in value:
            required = _DATA | {'points'}
        elif 'function' in value:
            required = _DATA | {'function','domain'}
    exact_fields(value, required, path=path,
                 optional=ITEM_OPTIONAL_FIELDS.get(kind, ()))


def correction_feedback(error):
    """Only typed contract/resource failures qualify for a correction call.

    Transport, model binding, unavailable answers, geometric constraints
    and arbitrary ValueErrors do not. Malformed JSON includes position only.
    Resource feedback never changes a limit or authorizes extra attempts.
    """
    if isinstance(error, ContractError):
        return deepcopy(error.feedback)
    if isinstance(error, json.JSONDecodeError):
        return dict(code='json_syntax', path='/', line=error.lineno, column=error.colno)
    resource = budget_feedback(error)
    if resource is not None:
        return dict(code='native_resource_budget', path='/', resource=resource)
    return None
