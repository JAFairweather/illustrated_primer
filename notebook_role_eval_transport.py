"""Offline role-specific model assertions; never caller-selected host settings.

The private endpoint has an owner-fixed prompt/model/effort. These expectations
check its report, not configure it. They are not cryptographic host attestation.
No production import, prompt injection, model fallback, retry or tablet I/O.
"""
from pathlib import Path
from notebook_model_transport import ModelTransportError, _call
from notebook_role_binding import validate_candidate, validate_bound_result, ROLES, EFFORTS


def validate_role_result(raw, request_id, *, expected, observe_response=None):
    return validate_bound_result(raw, request_id, expected=expected,
        response_format='role-eval-v1', binding_field='evaluation', observe_response=observe_response)


def call_role_eval(endpoint, request_id, png, context, *, expected,
                   deadline_ms=30000, is_current=lambda: True, observe_response=None):
    """One bounded isolated call; expected settings are NOT sent over the wire."""
    candidate = validate_candidate(expected)
    if not isinstance(endpoint, str) or Path(endpoint).name != 'notebook-eval.sock':
        raise ModelTransportError('unavailable')
    def validate(raw, identity, *, observe_response):
        return validate_role_result(raw, identity, expected=candidate, observe_response=observe_response)
    return _call(endpoint, request_id, png, context, deadline_ms=deadline_ms,
                 is_current=is_current, observe_response=observe_response, validate=validate)
