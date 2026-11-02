#!/usr/bin/env python3
"""Offline story → panel generation → preview, with explicit correction policy.

Default: no correction, retry, fallback or tablet import. An opt-in budget
allows one local syntax/field correction for the entire lesson, never an
unbounded repair loop. First-pass results remain separately identifiable.
The independently configured evaluation host must use story-panel-v1 and the
fixed prompt emitted by this module. Production semantic-v1 stays separate.
"""
from copy import deepcopy
import argparse
import hashlib
import html
import json
from pathlib import Path
import time
import uuid

from notebook_lesson import _pairs, _constant, _fields, _text
from notebook_model_transport import call_story_panel_eval, model_request, ModelTransportError
from notebook_panel_eval import review_panels
from notebook_panel_shapes import compile_panel_shapes
from notebook_story_plan import parse_story, panel_packet, MAX_BYTES
from notebook_story_prompt import story_panel_instructions
from notebook_pen_budget import budget_feedback
from notebook_contract_feedback import correction_feedback
from notebook_semantic_reply import parse_semantic_reply
from notebook_story_native import native_story_bundle
from notebook_playback_preview import native_lesson_preview, CSS


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _decode(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('bounded model JSON required')
    value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    if isinstance(value, dict) and value.get('mode') == 'unavailable':
        _fields(value, {'v', 'mode', 'reason'})
        if type(value['v']) is not int or value['v'] != 1:
            raise ValueError('unavailable requires version 1')
        _text(value['reason'], 600)
        raise Unavailable(value['reason'])
    return value


class Unavailable(ValueError):
    """Model explicitly declines unsupported/unclear input; not a visual pass."""


def _prefix(story, length):
    partial = deepcopy(story)
    partial['panels'] = partial['panels'][:length]
    used = {p['act'] for p in partial['panels']}
    partial['acts'] = [act for act in partial['acts'] if act['id'] in used]
    return partial


def evaluate(question, png, endpoint, destination, *, expected_model,
             deadline_ms=30000, call=call_story_panel_eval, max_corrections=0):
    """Retain each request/raw result; use validated bases for later calls.

    expected_model is a check, NOT model selection. Prompt hash records the
    intended configuration, not host attestation. Inspect host config separately.
    call is injectable for tests; fake calls are not evidence of model quality.
    """
    _text(question, 600)
    _text(expected_model, 128)
    if type(max_corrections) is not int or max_corrections not in (0, 1):
        raise ValueError('use zero or one correction for the entire lesson')
    # Validate capture/limits before creating artifacts or making a paid call.
    model_request('notebook-'+'0'*32, png, question, deadline_ms)
    destination.mkdir(parents=True, exist_ok=False)
    prompt = story_panel_instructions()
    (destination/'system-prompt.txt').write_text(prompt, encoding='utf-8')
    (destination/'input.png').write_bytes(png)
    (destination/'question.txt').write_text(question, encoding='utf-8')
    result = dict(valid=False, call_attempts=0, completed_model_responses=0, calls=[], expected_model=expected_model,
                  intended_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                  host_prompt_attested=False, native_delivery_supported=False,
                  native_preparation_valid=False,
                  tablet_proven=False, quality_status='unreviewed', retries=0,
                  max_corrections=max_corrections, corrections_used=0, first_pass_valid=False)
    start = time.monotonic()

    def invoke(task, context, *, correction=False):
        index = len(result['calls'])
        identity = 'notebook-'+uuid.uuid4().hex
        packet = _json(dict(task=task, context=context))
        # Never truncate inherited context to fit: that could change meaning.
        model_request(identity, png, packet, deadline_ms)
        name = f'call-{index:02d}-{task}'
        (destination/(name+'-request.json')).write_text(
            _json(dict(request_id=identity, context=json.loads(packet), deadline_ms=deadline_ms)),
            encoding='utf-8')
        row = dict(task=task, request_id=identity, file=name, correction=correction)
        result['calls'].append(row)
        result['call_attempts'] += 1
        if correction:
            result['corrections_used'] += 1
            result['retries'] += 1
        began = time.monotonic()
        def observe(raw):
            (destination/(name+'-wire.json')).write_bytes(raw)
        try:
            reply = call(endpoint, identity, png, packet, deadline_ms=deadline_ms, observe_response=observe)
            # Production transport has validated envelope; still assert the
            # declared boundary and fixed model here, including injected tests.
            if reply['request_id'] != identity or reply['response_format'] != 'story-panel-v1':
                raise ValueError('evaluation response binding mismatch')
            result['completed_model_responses'] += 1
            row['metrics'] = deepcopy(reply['metrics'])
            (destination/(name+'-response.txt')).write_text(reply['text'], encoding='utf-8')
            if reply['metrics']['model'] != expected_model:
                raise ValueError('evaluation model changed; stop comparison')
            return reply['text']
        finally:
            row['wall_ms'] = round((time.monotonic()-began)*1000)

    def generate_validated(task, context, validate):
        # Transport/binding errors occur outside the validation catch and can
        # never spend correction budget or overlap an unfinished provider.
        raw = invoke(task, context)
        try:
            return raw, validate(raw)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            feedback = correction_feedback(exc)
            if feedback is None:
                raise
            result.setdefault('first_validation_failure', dict(phase=phase, feedback=feedback))
            if result['corrections_used'] >= max_corrections:
                raise
            correction_context = deepcopy(context)
            correction_context['correction'] = dict(previous_output=raw, feedback=feedback)
            # invoke preflights the complete context. Never truncate previous
            # output or inherited shapes to squeeze a repair into the IPC cap.
            raw = invoke(task, correction_context, correction=True)
            return raw, validate(raw)  # No second retry for this or a later panel.

    phase = 'story'
    try:
        def validate_story_reply(raw):
            _decode(raw)  # Includes explicit unavailable handling.
            story = parse_story(raw)
            if story['question'] != question:
                raise ValueError('story changed the supplied question')
            return story
        story_text, story = generate_validated('story', dict(question=question), validate_story_reply)
        (destination/'story.json').write_text(story_text, encoding='utf-8')
        drafts, resolved = {}, {}
        for number, panel in enumerate(story['panels'], 1):
            phase = 'panel:'+panel['id']
            context = panel_packet(story, panel['id'])
            base = resolved.get(panel['base'])
            context['base_items'] = deepcopy(list(base['items'].values())) if base else []
            def validate_panel_reply(raw):
                candidate = _decode(raw)
                candidate_drafts = {**drafts, panel['id']: candidate}
                # Validate the corrected prefix as strictly as a first draft.
                compiled = compile_panel_shapes(_prefix(story, number), candidate_drafts)
                return candidate, compiled['panels']
            _, (candidate, resolved) = generate_validated('panel', context, validate_panel_reply)
            drafts[panel['id']] = candidate
        phase = 'preview'
        shapes = _json(drafts).encode('utf-8')
        reviewed = review_panels(story_text.encode('utf-8'), shapes, destination/'preview')
        result['preview'] = reviewed
        if reviewed['valid']:
            phase = 'native-preparation'
            # Use the production envelope and complete native compiler, not
            # just separate snapshot images. No import or device I/O occurs.
            parse_semantic_reply(_json(dict(v=1, mode='story-lesson', story=story, panels=drafts)))
            bundle = native_story_bundle(story, drafts)
            markup, playback = native_lesson_preview(bundle)
            page = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                    '<title>Offline native lesson playback</title><style>'+CSS+'</style>'
                    '<h1>'+html.escape(question)+'</h1><p>Recorded model output, compiled '
                    'through the native delivery path. Planned animation only, not a '
                    'tablet recording or measured Respond latency.</p>'+markup+'</html>')
            (destination/'playback.html').write_text(page, encoding='utf-8')
            result.update(valid=True, native_preparation_valid=True,
                          delivery_points=bundle['delivery_points'], picture_runs=len(bundle['plans']),
                          playback=playback, playback_file='playback.html')
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        result.update(failed_phase=phase, error=str(exc), error_type=type(exc).__name__)
        if isinstance(exc, ModelTransportError): result['transport_error'] = exc.code
        if isinstance(exc, Unavailable): result['unavailable'] = True
        feedback = budget_feedback(exc)
        if feedback is not None: result['resource_feedback'] = feedback
        contract = correction_feedback(exc)
        if contract is not None: result['contract_feedback'] = contract
    finally:
        result['first_pass_valid'] = result['valid'] and result['corrections_used'] == 0
        result['wall_ms'] = round((time.monotonic()-start)*1000)
        (destination/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prompt')
    run = sub.add_parser('run')
    run.add_argument('question', type=Path)
    run.add_argument('image', type=Path)
    run.add_argument('endpoint')
    run.add_argument('destination', type=Path)
    run.add_argument('--expected-model', required=True)
    run.add_argument('--max-corrections', type=int, choices=(0,1), default=0)
    args = parser.parse_args()
    if args.command == 'prompt':
        print(story_panel_instructions(), end='')
        return 0
    with args.question.open('rb') as stream: question = stream.read(2401).decode('utf-8').strip()
    with args.image.open('rb') as stream: png = stream.read(3_000_001)
    result = evaluate(question, png, args.endpoint, args.destination, expected_model=args.expected_model,
                      max_corrections=args.max_corrections)
    print(json.dumps(result))
    return 0 if result['valid'] else 2


if __name__ == '__main__': raise SystemExit(main())
