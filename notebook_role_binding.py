"""Check owner-fixed role identities, never select models from request data.

Shared validation for isolated evaluation and production; wire formats remain
distinct. These are consistency assertions, not cryptographic attestation.
"""
import json
import re

from notebook_lesson import _pairs, _constant
from notebook_model_transport import ModelTransportError, MAX_RESPONSE, _validated_envelope

ROLES = ('planner', 'drawer', 'critic')
EFFORTS = ('minimal', 'low', 'medium', 'high', 'xhigh')


def validate_candidate(value):
    fields = {'role', 'harness', 'provider', 'model', 'reasoning_requested',
              'requested_output_tokens', 'prompt_sha256'}
    if (not isinstance(value, dict) or set(value) != fields or
            value['role'] not in ROLES or value['harness'] != 'pi' or
            value['provider'] != 'openai-codex' or
            not isinstance(value['model'], str) or
            not re.fullmatch(r'[\w.\-/\[\]]{1,128}', value['model']) or
            value['reasoning_requested'] not in EFFORTS or
            type(value['requested_output_tokens']) is not int or
            not 1 <= value['requested_output_tokens'] <= 8192 or
            not isinstance(value['prompt_sha256'], str) or
            not re.fullmatch(r'[0-9a-f]{64}', value['prompt_sha256'])):
        raise ModelTransportError('invalid_candidate')
    return dict(value)


def validate_bound_result(raw, request_id, *, expected, response_format,
                          binding_field, observe_response=None):
    expected = validate_candidate(expected)
    try:
        if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
            raise ModelTransportError('invalid_response')
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        if isinstance(value, dict) and set(value) == {'request_id', 'error'}:
            return _validated_envelope(raw, request_id, response_format)
        if not isinstance(value, dict) or set(value) != {'request_id', 'response_format', 'text', 'metrics', binding_field}:
            raise ModelTransportError('invalid_response')
        core = {k: v for k, v in value.items() if k != binding_field}
        _validated_envelope(json.dumps(core, allow_nan=False).encode(), request_id,
                            response_format, expected_reasoning=expected['reasoning_requested'])
        binding = {k: expected[k] for k in ('role', 'harness', 'prompt_sha256')}
        if (value[binding_field] != binding or any(value['metrics'][k] != expected[k]
                for k in ('provider', 'model', 'reasoning_requested', 'requested_output_tokens'))):
            raise ModelTransportError('candidate_mismatch')
        if observe_response is not None:
            observe_response(raw)
        return value
    except ModelTransportError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ModelTransportError('invalid_response') from None
