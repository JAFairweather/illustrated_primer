#!/usr/bin/env python3
"""Offline planner -> batched drawer, plus independent visual criticism.

Fixed host settings are asserted, never selected by a notebook request. Each
role gets one attempt. The critic is deliberately separate from answer latency
and cannot repair or publish anything. No tablet/client/server imports.
"""
import argparse
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
import uuid

from notebook_lesson import _pairs, _constant, _text
from notebook_model_transport import model_request, ModelTransportError
from notebook_panel_eval import review_panels
from notebook_role_eval_transport import call_role_eval, validate_candidate, validate_role_result
from notebook_role_prompts import role_prompt, STORY_DIMENSIONS, PICTURE_DIMENSIONS
from notebook_story_plan import parse_story, validate_story
from notebook_story_native import native_story_bundle


def packed(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def save(path, value):
    path.write_text(packed(value) + '\n', encoding='utf-8')


def checked_config(config, role):
    if not isinstance(config, dict) or set(config) != {'endpoint', 'expected'}:
        raise ValueError('endpoint and expected role configuration required')
    expected = validate_candidate(config['expected'])
    prompt = role_prompt(role)
    if (expected['role'] != role or expected['prompt_sha256'] !=
            hashlib.sha256(prompt.encode()).hexdigest()):
        raise ValueError('role or fixed prompt mismatch')
    if not isinstance(config['endpoint'], str) or Path(config['endpoint']).name != 'notebook-eval.sock':
        raise ValueError('evaluation endpoint required')
    return deepcopy(config)


def invoke(config, role, image, packet, destination, *, deadline_ms=30000,
           call=call_role_eval, clock=time.monotonic):
    """One independently bound call, usable for frozen-input role ablations."""
    config = checked_config(config, role)
    identity = 'notebook-' + uuid.uuid4().hex
    context = packed(packet)
    model_request(identity, image, context, deadline_ms)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'input.png').write_bytes(image)
    (destination/'system-prompt.txt').write_text(role_prompt(role), encoding='utf-8')
    save(destination/'request.json', {'request_id': identity, 'context': packet,
                                    'deadline_ms': deadline_ms})
    save(destination/'candidate.json', config['expected'])
    result = {'role': role, 'input_sha256': hashlib.sha256(context.encode()).hexdigest(),
              'image_sha256': hashlib.sha256(image).hexdigest(), 'attempts': 1,
              'complete': False, 'retries': 0, 'host_prompt_attested': False}
    start = clock()
    try:
        reply = call(config['endpoint'], identity, image, context,
                     expected=config['expected'], deadline_ms=deadline_ms,
                     observe_response=lambda raw: (destination/'response-wire.json').write_bytes(raw))
        reply = validate_role_result(packed(reply).encode(), identity, expected=config['expected'])
        result['metrics'] = reply['metrics']
        (destination/'response.txt').write_text(reply['text'], encoding='utf-8')
        if (clock()-start)*1000 >= deadline_ms:
            raise ModelTransportError('deadline')
        result['complete'] = True
        return reply['text'], result
    except ModelTransportError as exc:
        result['transport_error'] = exc.code
        raise
    finally:
        result['wall_ms'] = round((clock()-start)*1000)
        save(destination/'call.json', result)


def decode(raw):
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 24000:
        raise ValueError('bounded role output required')
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)


def unavailable(value):
    if isinstance(value, dict) and value.get('mode') == 'unavailable':
        if set(value) != {'v', 'mode', 'reason'} or type(value['v']) is not int or value['v'] != 1:
            raise ValueError('invalid unavailable response')
        _text(value['reason'], 280)
        return value['reason']
    return None


def generate(packet, image, configs, destination, *, deadline_ms=30000,
             call=call_role_eval, clock=time.monotonic):
    """Two calls, whole-lesson native validation, then real offline previews.

Deadline is PER CALL, not total lesson latency. Keep planner output unchanged;
the drawer returns only shapes. Independent role benchmarks can call invoke()
with an identical frozen plan instead of conflating planner/drawer changes.
"""
    if set(configs) != {'planner', 'drawer'}:
        raise ValueError('independent planner and drawer configurations required')
    configs = {role: checked_config(configs[role], role) for role in configs}
    if not isinstance(packet, dict) or set(packet) != {'task', 'context'} or packet['task'] != 'story':
        raise ValueError('story input packet required')
    question = packet['context']['question']
    _text(question, 600)
    model_request('notebook-'+'0'*32, image, packed(packet), deadline_ms)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    result = {'valid': False, 'native_preparation_valid': False, 'quality_status': 'unreviewed',
              'tablet_proven': False, 'calls': [], 'retries': 0, 'deadline_per_call_ms': deadline_ms}
    start = clock()
    phase = 'planner'
    try:
        raw, metrics = invoke(configs['planner'], 'planner', image, packet, destination/'planner',
                              deadline_ms=deadline_ms, call=call, clock=clock)
        result['calls'].append(metrics)
        value = decode(raw)
        if unavailable(value):
            result['unavailable'] = value['reason']
            return result
        story = parse_story(raw)
        if story['question'] != question:
            raise ValueError('planner changed the question')
        if len(story['panels']) < 3:
            raise ValueError('illustrated lessons require at least three steps')
        save(destination/'story.json', story)
        phase = 'drawer'
        drawing_packet = {'task': 'draw', 'context': {'story': story}}
        raw, metrics = invoke(configs['drawer'], 'drawer', image, drawing_packet, destination/'drawer',
                              deadline_ms=deadline_ms, call=call, clock=clock)
        result['calls'].append(metrics)
        value = decode(raw)
        if unavailable(value):
            result['unavailable'] = value['reason']
            return result
        if (not isinstance(value, dict) or set(value) != {'v', 'mode', 'panels'} or
                type(value['v']) is not int or value['v'] != 1 or value['mode'] != 'story-shapes'):
            raise ValueError('drawer must return only the complete panel map')
        phase = 'native-preparation'
        bundle = native_story_bundle(story, value['panels'])
        result.update(native_preparation_valid=True,
                      preparation_ms=round((clock()-start)*1000),
                      delivery_points=bundle['delivery_points'], snapshot_points=bundle['snapshot_points'])
        save(destination/'panels.json', value['panels'])
        phase = 'preview'
        preview_start = clock()
        preview = review_panels(packed(story).encode(), packed(value['panels']).encode(), destination/'preview')
        result['preview'] = preview
        if not preview['valid']:
            raise ValueError('whole-lesson preview failed')
        result.update(valid=True, preview_ms=round((clock()-preview_start)*1000))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        result.update(failed_phase=phase, error=str(exc))
        if isinstance(exc, ModelTransportError):
            result['transport_error'] = exc.code
    finally:
        result['wall_ms'] = round((clock()-start)*1000)
        result['attempts'] = sum((destination/role/'request.json').exists() for role in configs)
        save(destination/'result.json', result)
    return result


def parse_review(raw, story):
    """Validate evidence-backed scoring; never turn an unreviewed item into pass."""
    story = validate_story(story)
    value = decode(raw)
    if (not isinstance(value, dict) or set(value) != {'v', 'mode', 'story', 'picture', 'critical_issues'}
            or type(value['v']) is not int or value['v'] != 1 or value['mode'] != 'lesson-review'):
        raise ValueError('lesson-review contract required')
    ids = {'lesson', *(panel['id'] for panel in story['panels'])}
    def evidence(entry, fields):
        if (not isinstance(entry, dict) or set(entry) != fields or
                not isinstance(entry['panel'], str) or entry['panel'] not in ids):
            raise ValueError('specific existing panel evidence required')
        _text(entry['evidence'], 360)
    for category, dimensions in [('story', STORY_DIMENSIONS), ('picture', PICTURE_DIMENSIONS)]:
        scores = value[category]
        if not isinstance(scores, dict) or set(scores) != set(dimensions):
            raise ValueError('all separate score dimensions required')
        for item in scores.values():
            evidence(item, {'score', 'panel', 'evidence'})
            if item['score'] is not None and (type(item['score']) is not int or not 0 <= item['score'] <= 4):
                raise ValueError('score must be null or an integer 0..4')
    issues = value['critical_issues']
    if not isinstance(issues, list) or len(issues) > 12:
        raise ValueError('bounded critical issues required')
    for issue in issues:
        evidence(issue, {'panel', 'evidence'})
    return value


def preview_sheet(story, preview_directory):
    """Real rendered panels at original resolution; refuse rather than shrink.

    This is offline ink, not a screenshot. Captions stay in the text packet.
    A sheet that exceeds the host image budget needs a later per-page review.
    """
    from PIL import Image, ImageDraw
    story = validate_story(story)
    images = []
    for panel in story['panels']:
        with Image.open(Path(preview_directory)/('panel-'+panel['id']+'.png')) as source:
            source.load()
            images.append(source.convert('RGB'))
    ids = [p['id'] for p in story['panels']]
    if 'equation' in story:
        with Image.open(Path(preview_directory)/'equation.png') as source:
            source.load()
            images.append(source.convert('RGB'))
        ids.append('lesson equation')
    width = max(image.width for image in images)
    height = max(image.height for image in images) + 28
    columns = 2 if len(images) > 1 else 1
    rows = (len(images)+columns-1)//columns
    if width*columns > 4096 or height*rows > 4096 or width*columns*height*rows > 4_000_000:
        raise ValueError('preview sheet exceeds image budget; per-page review needed')
    sheet = Image.new('RGB', (width*columns, height*rows), 'white')
    draw = ImageDraw.Draw(sheet)
    for index, (identity, image) in enumerate(zip(ids, images)):
        x, y = index%columns*width, index//columns*height
        draw.text((x+8, y+6), f"{index+1}. {identity}", fill='black')
        sheet.paste(image, (x, y+28))
    output = BytesIO()
    sheet.save(output, format='PNG')
    return output.getvalue()


def critique(story, sources, preview_directory, config, destination, *,
             deadline_ms=30000, call=call_role_eval, clock=time.monotonic):
    """Independent review only; returned scores are uncalibrated model opinions."""
    story = validate_story(story)
    sheet = preview_sheet(story, preview_directory)
    packet = {'task': 'critique', 'context': {'story': story, 'sources': sources,
              'preview_panel_ids': [p['id'] for p in story['panels']]}}
    raw, metrics = invoke(config, 'critic', sheet, packet, destination,
                          deadline_ms=deadline_ms, call=call, clock=clock)
    record = {'valid': False, 'metrics': metrics, 'critic_calibrated': False,
              'human_reviewed': False, 'tablet_proven': False}
    try:
        review = parse_review(raw, story)
        record.update(valid=True, review=review)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        record['error'] = str(exc)
        raise
    finally:
        save(Path(destination)/'review.json', record)
    return review


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prompt = sub.add_parser('prompt')
    prompt.add_argument('role', choices=('planner', 'drawer', 'critic'))
    run = sub.add_parser('generate')
    for name in ('packet', 'image', 'configs', 'destination'):
        run.add_argument(name, type=Path)
    review = sub.add_parser('critique')
    for name in ('story', 'source_packet', 'preview_directory', 'config', 'destination'):
        review.add_argument(name, type=Path)
    args = parser.parse_args()
    if args.command == 'prompt':
        print(role_prompt(args.role), end='')
    elif args.command == 'generate':
        from notebook_panel_eval import read_bounded
        packet = decode(read_bounded(args.packet).decode('utf-8'))
        configs = decode(read_bounded(args.configs).decode('utf-8'))
        with args.image.open('rb') as stream:
            png = stream.read(3_000_001)
        print(json.dumps(generate(packet, png, configs, args.destination)))
    else:
        from notebook_panel_eval import read_bounded
        story = decode(read_bounded(args.story).decode('utf-8'))
        packet = decode(read_bounded(args.source_packet).decode('utf-8'))
        config = decode(read_bounded(args.config).decode('utf-8'))
        print(json.dumps(critique(story, packet['context']['sources'], args.preview_directory,
                                  config, args.destination)))
