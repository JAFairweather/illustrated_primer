#!/usr/bin/env python3
"""Image-input evaluation through an already running notebook host; no tablet I/O.

Prepare ten typeset question images, then collect one untouched response per
question. This is NOT handwriting recognition or Respond latency evidence.
The host's prompt is operator-configured; this protocol does not attest its
digest. The report explicitly retains that limitation for model comparisons.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import textwrap
import time
import uuid

from notebook_lesson_eval import QUESTIONS, render
from notebook_model_transport import call_notebook_model, model_request, ModelTransportError
from notebook_semantic_prompt import semantic_reply_instructions

CONTEXT = 'Read the attached offline test question and teach its main idea.'
CONDITIONS = ('Typeset question PNGs, not human handwriting or tablet captures. '
              'Image-first direct host calls, no transcript, tools, repair or retry. '
              'Expected system prompt is saved, but its use by the host is NOT '
              'attested by this protocol; confirm installation separately. '
              'Timings exclude tablet capture, insertion and save. '
              'Accepted text fallbacks are not visual lesson passes.')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def identity(prompt_hash, image_hash, context):
    return digest(json.dumps([prompt_hash, image_hash, context], separators=(',', ':')).encode())


def prepare_images(destination, *, image_style='legacy'):
    from PIL import Image, ImageDraw, ImageFont
    if image_style not in ('legacy', 'clear'):
        raise ValueError('use legacy or clear question image style')
    prompt = semantic_reply_instructions().encode()
    packet = dict(version=1, response_format='semantic-v1', conditions=CONDITIONS,
                  expected_system_prompt_sha256=digest(prompt), questions=[])
    if image_style == 'clear':
        packet['conditions'] += ' CLEAR input variant: native-resolution 32px text, not the legacy enlarged bitmap.'
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'system-prompt.txt').write_bytes(prompt)
    (destination/'system-prompt.txt').chmod(0o600)
    for name, question in QUESTIONS:
        # Fixed bitmap font, enlarged for image models. Not simulated handwriting.
        if image_style == 'legacy':
            image = Image.new('RGB', (320, 240), 'white')
            draw = ImageDraw.Draw(image)
            draw.text((12, 12), 'OFFLINE TYPESET QUESTION', fill='black')
            draw.multiline_text((12, 42), '\n'.join(textwrap.wrap(question, 40)),
                                fill='black', spacing=8)
            image = image.resize((960, 720), Image.Resampling.NEAREST)
        else:
            image = Image.new('RGB', (960, 720), 'white')
            draw = ImageDraw.Draw(image)
            font = ImageFont.load_default(size=32)
            draw.text((36, 30), 'OFFLINE TYPESET QUESTION', fill='black', font=font)
            text = '\n'.join(textwrap.wrap(question, 42))
            box = draw.multiline_textbbox((36, 120), text, font=font, spacing=14)
            if box[2] > 924 or box[3] > 684:
                raise ValueError('clear question text exceeds its image; do not crop it')
            draw.multiline_text((36, 120), text, fill='black', font=font, spacing=14)
        image.save(destination/(name+'.png'))
        image_hash = digest((destination/(name+'.png')).read_bytes())
        packet['questions'].append(dict(id=name, question=question, image=name+'.png',
            image_sha256=image_hash, context=CONTEXT,
            prompt_sha256=identity(packet['expected_system_prompt_sha256'], image_hash, CONTEXT)))
    save_json(destination/'packet.json', packet)
    return packet


def load_images(packet_path):
    """Preflight the whole packet before spending any model calls."""
    data = packet_path.read_bytes()
    if len(data) > 100_000:
        raise ValueError('packet too large')
    packet = json.loads(data)
    if (packet.get('version') != 1 or packet.get('response_format') != 'semantic-v1'
            or not isinstance(packet.get('questions'), list)
            or not 1 <= len(packet['questions']) <= 20):
        raise ValueError('bounded semantic image packet required')
    prompt = (packet_path.parent/'system-prompt.txt').read_bytes()
    if not 1 <= len(prompt) <= 64_000 or digest(prompt) != packet.get('expected_system_prompt_sha256'):
        raise ValueError('expected system prompt changed')
    prompt.decode('utf-8')
    seen, images = set(), []
    for q in packet['questions']:
        name = q.get('id')
        if (not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9-]{0,40}', name)
                or name in seen or q.get('image') != name+'.png'
                or not isinstance(q.get('question'), str)):
            raise ValueError('invalid or duplicate question identity')
        seen.add(name)
        path = packet_path.parent/q['image']
        if path.is_symlink() or path.stat().st_size > 3_000_000:
            raise ValueError('question must be a bounded local PNG')
        png = path.read_bytes()
        model_request('notebook-'+'0'*32, png, q.get('context'))
        if (digest(png) != q.get('image_sha256') or q.get('prompt_sha256') !=
                identity(digest(prompt), digest(png), q['context'])):
            raise ValueError('question image or context changed')
        images.append(png)
    return packet, images


def prompt_variant(packet_path, destination, prompt_path):
    """Freeze a prompt-only experiment; preserve input bytes and the baseline."""
    packet, images = load_images(packet_path)
    with prompt_path.open('rb') as source:
        prompt = source.read(64_001)
    if not 1 <= len(prompt) <= 64_000 or b'\0' in prompt:
        raise ValueError('variant prompt must be 1..64000 UTF-8 bytes without NUL')
    if not prompt.decode('utf-8').strip():
        raise ValueError('variant prompt must not be blank')
    prompt_hash = digest(prompt)
    if prompt_hash == packet['expected_system_prompt_sha256']:
        raise ValueError('prompt-only variant requires a different prompt')
    variant = copy.deepcopy(packet)
    variant['expected_system_prompt_sha256'] = prompt_hash
    variant['prompt_variant'] = dict(parent_packet_sha256=digest(packet_path.read_bytes()),
        parent_system_prompt_sha256=packet['expected_system_prompt_sha256'])
    variant['conditions'] = packet.get('conditions', CONDITIONS) + (
        ' PROMPT-ONLY variant: question images, question text, context and order '
        'are unchanged. This prepares inputs only; no model calls or host changes.')
    for q in variant['questions']:
        q['prompt_sha256'] = identity(prompt_hash, q['image_sha256'], q['context'])
    # Validate all sources before creating the destination. Existing runs and
    # packets are never overwritten, even if the caller selects the same path.
    destination.mkdir(parents=True, exist_ok=False)
    for q, png in zip(variant['questions'], images):
        path = destination/q['image']
        path.write_bytes(png)
        path.chmod(0o600)
    (destination/'system-prompt.txt').write_bytes(prompt)
    (destination/'system-prompt.txt').chmod(0o600)
    save_json(destination/'packet.json', variant)
    return variant


def collect(packet_path, destination, endpoint, *, deadline_ms=15000,
            continue_on_deadline=False, call=call_notebook_model):
    if type(deadline_ms) is not int or not 1 <= deadline_ms <= 30000:
        raise ValueError('deadline must be 1..30000 ms')
    if type(continue_on_deadline) is not bool:
        raise ValueError('continue_on_deadline must be boolean')
    packet, images = load_images(packet_path)
    destination.mkdir(parents=True, exist_ok=False)
    # Preserve exactly what was sent, independently of future corpus edits.
    (destination/'packet.json').write_bytes(packet_path.read_bytes())
    (destination/'system-prompt.txt').write_bytes((packet_path.parent/'system-prompt.txt').read_bytes())
    (destination/'system-prompt.txt').chmod(0o600)
    for q, png in zip(packet['questions'], images):
        (destination/q['image']).write_bytes(png)
    answers = dict(model='No model response received', answers=[])
    report = dict(version=1, tablet_proven=False, handwriting_proven=False,
        host_prompt_verified=False, conditions=packet.get('conditions', CONDITIONS),
        packet_sha256=digest(packet_path.read_bytes()), request_deadline_ms=deadline_ms,
        continue_on_deadline=continue_on_deadline, rows=[], stopped=False)
    models = set()

    def checkpoint():
        answers['model'] = ', '.join(sorted(models)) or 'No model response received'
        save_json(destination/'answers.json', answers)
        save_json(destination/'run.json', report)

    checkpoint()
    for q, png in zip(packet['questions'], images):
        request_id = 'notebook-'+uuid.uuid4().hex
        row = dict(id=q['id'], request_id=request_id, transport_valid=False,
                   raw_available=False, attempts=1, request_deadline_ms=deadline_ms)
        report['rows'].append(row)
        started = time.monotonic()
        captured = []
        try:
            call(endpoint, request_id, png, q['context'], deadline_ms=deadline_ms,
                 observe_response=captured.append)
            row['transport_valid'] = True
        except ModelTransportError as exc:
            row['error'] = exc.code
            # Default remains stop-on-timeout. A predeclared bounded offline
            # trial may proceed to the NEXT question, never retry this one.
            # Busy/closed/provider failures still stop even in that mode.
            if exc.code not in ('invalid_response', 'invalid_json', 'incomplete_response',
                                'reply_too_large', 'tools_forbidden') and not (
                                    exc.code == 'deadline' and continue_on_deadline):
                report['stopped'] = True
        except Exception:
            row['error'] = 'evaluation_error'
            report['stopped'] = True
        finally:
            row['wall_ms'] = round((time.monotonic()-started)*1000, 3)
        if captured:
            # The transport exposes only a bounded, bound, metrics-checked
            # envelope. Retain it even if full semantic compilation rejected it.
            raw = captured[0]
            (destination/(q['id']+'-wire.json')).write_bytes(raw)
            wire = json.loads(raw)
            row.update(raw_available=True, metrics=wire['metrics'])
            models.add(wire['metrics']['provider']+'/'+wire['metrics']['model'])
            answers['answers'].append(dict(id=q['id'], response=wire.get('text'),
                                           prompt_sha256=q['prompt_sha256']))
            if len(models) > 1:
                row['error'] = 'model_changed'
                report['stopped'] = True
        checkpoint()
        if report['stopped']:
            break
    # Existing cumulative preview/compiler, not another rendering path.
    manifest = render(destination/'packet.json', destination/'answers.json', destination/'rendered')
    manifest['request_deadline_ms'] = deadline_ms
    observations = {row['id']: row for row in report['rows']}
    for row in manifest['rows']:
        observed = observations.get(row['id'])
        if observed:
            row['model_call'] = observed
            if not observed['raw_available'] and observed.get('error'):
                row.update(error=observed['error'], failure_stage='transport')
    save_json(destination/'rendered/manifest.json', manifest)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('destination', type=Path)
    p.add_argument('--image-style', choices=('legacy','clear'), default='legacy')
    p = sub.add_parser('prompt-variant'); p.add_argument('packet', type=Path)
    p.add_argument('destination', type=Path)
    p.add_argument('--system-prompt', required=True, type=Path)
    p = sub.add_parser('collect'); p.add_argument('packet', type=Path)
    p.add_argument('destination', type=Path); p.add_argument('--socket', required=True)
    p.add_argument('--deadline-ms', type=int, default=15000)
    p.add_argument('--continue-on-deadline', action='store_true',
                   help='Try the next question once after a deadline; never retry timed-out questions.')
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare_images(args.destination, image_style=args.image_style)
        print('Prepared', len(result['questions']), 'typeset images; NOT handwriting evidence.')
        return 0
    if args.command == 'prompt-variant':
        result = prompt_variant(args.packet, args.destination, args.system_prompt)
        print('Prepared prompt-only variant:', len(result['questions']), 'unchanged input images; no model calls.')
        return 0
    result = collect(args.packet, args.destination, args.socket, deadline_ms=args.deadline_ms,
                     continue_on_deadline=args.continue_on_deadline)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['stopped'] or any(not row['transport_valid'] for row in result['rows']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
