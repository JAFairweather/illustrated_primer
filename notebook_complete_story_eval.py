#!/usr/bin/env python3
"""One-call isolated evaluation; no production routing or tablet publication.

The host must independently install complete_story_instructions with the
existing bounded story-panel-v1 wire format. This client sends question data,
never a system prompt or model override. Whole native preparation shares one
deadline with generation. Preview encoding time is recorded separately.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import time
import uuid

from notebook_complete_story_prompt import complete_story_instructions
from notebook_lesson import _text
from notebook_model_transport import (call_story_panel_eval, model_request,
                                      _validated_envelope, ModelTransportError)
from notebook_semantic_reply import parse_semantic_reply
from notebook_story_native import native_story_bundle
from notebook_panel_eval import review_panels
from notebook_playback_preview import CSS, native_lesson_preview


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def evaluate(question, png, endpoint, destination, *, expected_model,
             deadline_ms=30000, call=call_story_panel_eval, clock=time.monotonic):
    """Exactly one attempt, strict model/binding/schema/native checks, no repairs.

    expected_model asserts the owner-configured model, not a selection request.
    Injected call/clock support offline tests, not claims about model behavior.
    """
    _text(question, 600)
    _text(expected_model, 128)
    if Path(endpoint).name != 'notebook-eval.sock':
        raise ModelTransportError('unavailable')
    identity = 'notebook-' + uuid.uuid4().hex
    context = _json(dict(task='lesson', context=dict(question=question)))
    model_request(identity, png, context, deadline_ms)
    destination.mkdir(parents=True, exist_ok=False)
    prompt = complete_story_instructions()
    (destination/'system-prompt.txt').write_text(prompt, encoding='utf-8')
    (destination/'input.png').write_bytes(png)
    (destination/'request.json').write_text(_json(dict(
        request_id=identity, context=json.loads(context), deadline_ms=deadline_ms)), encoding='utf-8')
    result = dict(valid=False, native_preparation_valid=False, first_pass_valid=False,
                  tablet_proven=False, quality_status='unreviewed', call_attempts=0,
                  completed_model_responses=0, retries=0, expected_model=expected_model,
                  intended_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                  host_prompt_attested=False, deadline_ms=deadline_ms)
    start = clock()
    def elapsed():
        return round((clock()-start)*1000)
    def current():
        if clock()-start >= deadline_ms/1000:
            raise ModelTransportError('deadline')
    def observe(raw):
        (destination/'response-wire.json').write_bytes(raw)
    phase = 'model'
    try:
        result['call_attempts'] = 1
        reply = call(endpoint, identity, png, context,
                     deadline_ms=deadline_ms, observe_response=observe)
        reply = _validated_envelope(_json(reply).encode(), identity, 'story-panel-v1')
        result['completed_model_responses'] = 1
        result['metrics'] = reply['metrics']
        result['model_wall_ms'] = elapsed()
        (destination/'response.txt').write_text(reply['text'], encoding='utf-8')
        current()
        if reply['metrics']['model'] != expected_model:
            raise ModelTransportError('model_mismatch')
        phase = 'whole-lesson'
        parsed = parse_semantic_reply(reply['text'])
        current()
        if parsed['mode'] == 'clarify':
            result.update(clarification=True, clarification_text=parsed['text'])
            return result
        if parsed['mode'] != 'lesson' or 'story' not in parsed:
            raise ValueError('complete story-lesson required; plain answers are not visual passes')
        if parsed['story']['question'] != question:
            raise ValueError('story changed the supplied question')
        phase = 'native-preparation'
        bundle = native_story_bundle(parsed['story'], parsed['drafts'])
        current()
        result.update(native_preparation_valid=True, preparation_ms=elapsed(),
                      delivery_points=bundle['delivery_points'],
                      snapshot_points=bundle['snapshot_points'], picture_runs=len(bundle['plans']))
        # Only after the entire answer and native assets validate on time may
        # the offline renderer produce previews. No notebook import exists here.
        phase = 'preview'
        preview_start = clock()
        checked = review_panels(_json(parsed['story']).encode(),
                               _json(parsed['drafts']).encode(), destination/'preview')
        result['preview'] = checked
        if not checked['valid']:
            raise ValueError(checked['error'])
        markup, timing = native_lesson_preview(bundle)
        (destination/'playback.html').write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8"><style>' + CSS + '</style>'
            '<h1>' + html.escape(question) + '</h1><p>One-call offline evaluation. '
            'Planned playback, not a tablet recording or first-visible latency.</p>' + markup + '</html>',
            encoding='utf-8')
        result.update(valid=True, first_pass_valid=True, playback=timing,
                      preview_ms=round((clock()-preview_start)*1000))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        result.update(failed_phase=phase, error=str(exc), error_type=type(exc).__name__)
        if isinstance(exc, ModelTransportError):
            result['transport_error'] = exc.code
    finally:
        result['wall_ms'] = elapsed()
        (destination/'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
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
    args = parser.parse_args()
    if args.command == 'prompt':
        print(complete_story_instructions(), end='')
        return 0
    with args.question.open('rb') as stream:
        question = stream.read(2401).decode('utf-8').strip()
    with args.image.open('rb') as stream:
        png = stream.read(3_000_001)
    result = evaluate(question, png, args.endpoint, args.destination, expected_model=args.expected_model)
    print(json.dumps(result))
    return 0 if result['valid'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
