"""Private fixed production roles; no evaluation socket reuse or retries."""
import json
from pathlib import Path

from notebook_lesson import _pairs, _constant
from notebook_model_transport import ModelTransportError, _call
from notebook_role_binding import validate_candidate, validate_bound_result


def validate_roles(roles):
    if not isinstance(roles, dict) or set(roles) != {'planner', 'drawer'}:
        raise ModelTransportError('invalid_candidate')
    result = {}
    for role, binding in roles.items():
        if not isinstance(binding, dict) or set(binding) != {'socket', 'expected'}:
            raise ModelTransportError('invalid_candidate')
        expected = validate_candidate(binding['expected'])
        endpoint = binding['socket']
        if (expected['role'] != role or not isinstance(endpoint, str) or
                not Path(endpoint).is_absolute() or '..' in Path(endpoint).parts or
                str(Path(endpoint)) != endpoint or len(endpoint.encode('utf-8')) > 100 or
                Path(endpoint).name != f'notebook-{role}.sock'):
            raise ModelTransportError('invalid_candidate')
        result[role] = dict(socket=endpoint, expected=expected)
    return result


def validate_production_result(raw, request_id, *, expected, observe_response=None):
    candidate = validate_candidate(expected)
    if candidate['role'] not in ('planner', 'drawer'):
        raise ModelTransportError('invalid_candidate')
    return validate_bound_result(raw, request_id, expected=candidate,
        response_format='role-production-v1', binding_field='production', observe_response=observe_response)


def call_production_role(endpoint, request_id, png, context, *, expected,
                         deadline_ms=30000, is_current=lambda: True, observe_response=None):
    candidate = validate_candidate(expected)
    role = candidate['role']
    if (role not in ('planner', 'drawer') or not isinstance(endpoint, str) or
            Path(endpoint).name != f'notebook-{role}.sock'):
        raise ModelTransportError('unavailable')
    try:
        packet = json.loads(context, object_pairs_hook=_pairs, parse_constant=_constant)
        if (not isinstance(packet, dict) or set(packet) != {'task', 'context'} or
                packet['task'] != ('story' if role == 'planner' else 'panel') or
                not isinstance(packet['context'], dict)):
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise ModelTransportError('invalid_request') from None
    def validate(raw, identity, *, observe_response):
        return validate_production_result(raw, identity, expected=candidate, observe_response=observe_response)
    return _call(endpoint, request_id, png, context, deadline_ms=deadline_ms,
                 is_current=is_current, observe_response=observe_response, validate=validate)
