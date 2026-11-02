"""Explicit owner-only IPC client; not selected by production Respond yet.

Accept captured PNG bytes, never a model-specified filename. Full semantic
validation remains here, before the caller may publish against its existing
pending job. No retry, transcript polling, fallback provider, or new job store.
"""
import io
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import time

from PIL import Image
from notebook_lesson import _pairs, _constant
from notebook_semantic_reply import parse_semantic_reply

MAX_IMAGE = 3_000_000
MAX_RESPONSE = 160_000


class ModelTransportError(ValueError):
    """Bounded error code; never includes socket paths or provider diagnostics."""
    def __init__(self, code):
        self.code = code
        super().__init__('Notebook responder: ' + code)


def model_request(request_id, png, context, deadline_ms=15000):
    import base64
    try:
        context_size = len(context.encode('utf-8')) if isinstance(context, str) else 12001
    except UnicodeError:
        raise ModelTransportError('invalid_request') from None
    if (not isinstance(request_id, str) or not re.fullmatch(r'notebook-[0-9a-f]{32}', request_id)
            or not isinstance(png, bytes) or not 1 <= len(png) <= MAX_IMAGE
            or context_size > 12000
            or type(deadline_ms) is not int or not 1 <= deadline_ms <= 90000):
        raise ModelTransportError('invalid_request')
    try:
        with Image.open(io.BytesIO(png)) as image:
            w, h = image.size
            if image.format != 'PNG' or not 0 < w <= 4096 or not 0 < h <= 4096 or w*h > 4_000_000:
                raise ValueError('invalid image')
            image.verify()
        # verify() checks the stream; load() also rejects truncated compressed
        # pixel data. Bounded dimensions avoid a decompression allocation bomb.
        with Image.open(io.BytesIO(png)) as image:
            image.load()
    except Exception:
        raise ModelTransportError('invalid_image') from None
    return {'request_id': request_id, 'image': {'mime_type': 'image/png',
            'data': base64.b64encode(png).decode('ascii')}, 'context': context, 'deadline_ms': deadline_ms}


def _validated_envelope(raw, request_id, response_format, observe_response=None, *, expected_reasoning='medium'):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
        raise ModelTransportError('invalid_response')
    try:
        result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        if not isinstance(result, dict) or result.get('request_id') != request_id:
            raise ModelTransportError('request_mismatch')
        if set(result) == {'request_id', 'error'}:
            allowed = {'busy', 'closed', 'cancelled', 'deadline', 'invalid_request', 'invalid_image',
                       'incomplete_response', 'model_mismatch', 'tools_forbidden', 'invalid_response',
                       'invalid_json', 'reply_too_large', 'provider_error', 'request_too_large'}
            raise ModelTransportError(result['error'] if result['error'] in allowed else 'provider_error')
        if set(result) != {'request_id', 'response_format', 'text', 'metrics'} or result.get('response_format') != response_format:
            raise ModelTransportError('invalid_response')
        if not isinstance(result['text'], str) or len(result['text'].encode('utf-8')) > 24000:
            raise ModelTransportError('invalid_response')
        metrics = result['metrics']
        if (not isinstance(metrics, dict) or set(metrics) != {'elapsed_ms', 'first_text_ms', 'provider',
                'model', 'reasoning_requested', 'requested_output_tokens', 'usage'}
                or metrics['provider'] != 'openai-codex' or metrics['reasoning_requested'] != expected_reasoning
                or not isinstance(metrics['model'], str) or not re.fullmatch(r'[\w.\-/\[\]]{1,128}', metrics['model'])
                or not isinstance(metrics['usage'], dict) or set(metrics['usage'])-{'input','output','cacheRead','cacheWrite'}):
            raise ModelTransportError('invalid_response')
        for value in [metrics['elapsed_ms'], metrics['requested_output_tokens'], *metrics['usage'].values()]:
            if type(value) is not int or not 0 <= value <= 1_000_000_000:
                raise ModelTransportError('invalid_response')
        first = metrics['first_text_ms']
        if first is not None and (type(first) is not int or not 0 <= first <= metrics['elapsed_ms']):
            raise ModelTransportError('invalid_response')
        # Offline evaluation may retain the bounded, request-bound envelope
        # before semantic compilation rejects it. Bytes are immutable; the
        # observer cannot repair or replace the answer being validated.
        if observe_response is not None:
            observe_response(raw)
    except ModelTransportError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ModelTransportError('invalid_response') from None
    return result


def mend_early_close(text):
    """text without the one '}' that closed the top-level object early, when that alone makes it parse; else text.

    The model sometimes ends the lesson object just before its last key, '...}, "picture": {...}}'. Only that
    brace is removed; the semantic compiler still judges every field.
    """
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError as error:
        at = error.pos
        if not error.msg.startswith('Extra data') or text[at-1:at] != '}' or not text[at:].lstrip().startswith(','):
            return text
    except (TypeError, ValueError, RecursionError):
        return text
    mended = text[:at-1]+text[at:]
    try:
        return mended if isinstance(json.loads(mended), dict) else text
    except (ValueError, RecursionError):
        return text


_UNITS = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen '
                  'sixteen seventeen eighteen nineteen'.split(), range(20)))
_TENS = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10)))


def _number_words(phrase):
    """The integer a phrase like 'sixty', 'twenty-five' or 'one hundred five' names (0..999); else None."""
    words = re.split(r'[ -]+', phrase.lower().replace(' and ', ' '))
    total = 0
    if len(words) > 2 and words[1] == 'hundred' and words[0] in _UNITS and 1 <= _UNITS[words[0]] <= 9:
        total, words = _UNITS[words[0]]*100, words[2:]
    elif words[1:] == ['hundred'] and words[0] in _UNITS and 1 <= _UNITS[words[0]] <= 9:
        return _UNITS[words[0]]*100
    if len(words) == 1 and words[0] in _UNITS:
        return total+_UNITS[words[0]]
    if len(words) == 1 and words[0] in _TENS:
        return total+_TENS[words[0]]
    if len(words) == 2 and words[0] in _TENS and words[1] in _UNITS and 1 <= _UNITS[words[1]] <= 9:
        return total+_TENS[words[0]]+_UNITS[words[1]]
    return None


def mend_number_words(text):
    """text with bare spelled-out numbers ('"radius": sixty', '[105, thirty]') written as digits, when that alone
    makes it parse; else text. Words inside strings are never touched; the semantic compiler still judges every
    value. 2026-11-01: two of five replies were refused for this alone."""
    try:
        json.loads(text)
        return text
    except (TypeError, ValueError, RecursionError):
        if not isinstance(text, str):
            return text
    def bare(match):
        number = _number_words(match.group(2))
        return match.group(1)+str(number) if number is not None else match.group(0)
    parts = re.split(r'("(?:\\.|[^"\\])*")', text)
    for k in range(0, len(parts), 2):  # odd parts are JSON strings
        parts[k] = re.sub(r'([:\[,]\s*)([a-zA-Z]+(?:[ -][a-zA-Z]+)*)(?=\s*[,\]}])', bare, parts[k])
    mended = ''.join(parts)
    try:
        return mended if isinstance(json.loads(mended), dict) else text
    except (ValueError, RecursionError):
        return text


def validate_model_result(raw, request_id, *, observe_response=None):
    result = _validated_envelope(raw, request_id, 'semantic-v1', observe_response)
    if isinstance(result.get('text'), str):
        result['text'] = mend_early_close(mend_number_words(result['text']))
    try:
        try:
            parsed = parse_semantic_reply(result.get('text'))
        except ValueError as error:
            # Preserve the adapter's old bounded syntax failure code without
            # parsing twice or weakening the authoritative semantic compiler.
            if isinstance(error.__cause__, json.JSONDecodeError):
                cause = error.__cause__
                rejected = ModelTransportError('invalid_json')
                # Where the JSON broke, so the one repair attempt can say what to fix.
                rejected.detail = (f'the reply was not valid JSON ({cause.msg} at character {cause.pos}, near '
                                   f'{json.dumps(cause.doc[max(0, cause.pos-60):cause.pos+20])})')[:400]
                raise rejected from None
            raise
    except ModelTransportError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
        rejected = ModelTransportError('invalid_response')
        rejected.detail = f'{type(error).__name__}: {error}'[:400]  # for the trace only; the page sees the code
        raise rejected from None
    return {'request_id': request_id, 'response_format': 'semantic-v1', 'text': result['text'], 'parsed': parsed, 'metrics': result['metrics']}


def _private_socket(endpoint):
    if not isinstance(endpoint, str) or not os.path.isabs(endpoint) or os.path.normpath(endpoint) != endpoint:
        raise ModelTransportError('unavailable')
    path = Path(endpoint)
    try:
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ModelTransportError('unavailable')
        info, parent = path.lstat(), path.parent.lstat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o077):
            raise ModelTransportError('unavailable')
    except OSError:
        raise ModelTransportError('unavailable') from None


def _call(endpoint, request_id, png, context, *, deadline_ms, is_current,
          observe_response, validate):
    """One call, fully validate, then return; caller still checks its pending job.

    is_current checks the caller's EXISTING request/page state, not a new lease.
    Cancellation closes this connection; the host aborts that exact model call.
    """
    request = model_request(request_id, png, context, deadline_ms)
    _private_socket(endpoint)
    end = time.monotonic() + deadline_ms/1000 + 2  # bounded IPC flush margin
    def current():
        if not is_current():
            raise ModelTransportError('cancelled')
        if time.monotonic() >= end:
            raise ModelTransportError('deadline')
    current()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(min(1, end-time.monotonic()))
            conn.connect(endpoint)
            current()
            conn.settimeout(max(.001, end-time.monotonic()))
            conn.sendall(json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n')
            data = bytearray()
            while True:
                current()
                if not select.select([conn], [], [], min(.1, max(0, end-time.monotonic())))[0]:
                    continue
                part = conn.recv(16384)
                if not part:
                    raise ModelTransportError('incomplete_response')
                data.extend(part)
                if len(data) > MAX_RESPONSE:
                    raise ModelTransportError('invalid_response')
                if b'\n' in part:
                    if data.index(10) != len(data)-1:
                        raise ModelTransportError('invalid_response')
                    result = validate(bytes(data), request_id, observe_response=observe_response)
                    current()
                    return result
    except ModelTransportError:
        raise
    except (OSError, TimeoutError):
        raise ModelTransportError('unavailable') from None


def call_notebook_model(endpoint, request_id, png, context, *, deadline_ms=15000,
                        is_current=lambda: True, observe_response=None):
    """Production contract: semantic-v1 and full semantic validation, always."""
    return _call(endpoint, request_id, png, context, deadline_ms=deadline_ms,
                 is_current=is_current, observe_response=observe_response, validate=validate_model_result)


def call_story_panel_eval(endpoint, request_id, png, context, *, deadline_ms=30000,
                          observe_response=None):
    """Offline ONLY: bounded text for the story/panel evaluator, not native ink.

    A distinct wire format prevents mixing this result with production replies.
    The caller must parse/compile the story and all panels before previewing.
    """
    if Path(endpoint).name != 'notebook-eval.sock':
        raise ModelTransportError('unavailable')
    def validate(raw, identity, *, observe_response):
        return _validated_envelope(raw, identity, 'story-panel-v1', observe_response)
    return _call(endpoint, request_id, png, context, deadline_ms=deadline_ms,
                 is_current=lambda: True, observe_response=observe_response, validate=validate)


def call_story_panel_model(endpoint, request_id, png, context, *, deadline_ms=30000,
                           is_current=lambda: True, observe_response=None):
    """One production story/panel call; not yet a deliverable notebook reply.

    Only the complete-story producer may assemble these bounded raw pieces.
    Never borrow the separately configured offline evaluation endpoint.
    """
    if Path(endpoint).name == 'notebook-eval.sock':
        raise ModelTransportError('unavailable')
    def validate(raw, identity, *, observe_response):
        return _validated_envelope(raw, identity, 'story-panel-v1', observe_response)
    return _call(endpoint, request_id, png, context, deadline_ms=deadline_ms,
                 is_current=is_current, observe_response=observe_response, validate=validate)
