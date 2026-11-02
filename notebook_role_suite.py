#!/usr/bin/env python3
"""Controlled offline role comparison over a frozen corpus. Never device I/O.

Two planners see identical questions. Both drawers see each accepted plan;
both critics see each accepted drawing. This is a full role cross, not a
fallback ladder. Transport failures stop collection unless an explicitly
enabled, read-only idle check proves a deadline's provider has terminated.
Invalid content remains a first-pass result, not repaired.
"""
import argparse
from copy import deepcopy
import html
import json
from pathlib import Path
import socket
import time

from notebook_role_corpus import load_corpus, planner_input, digest
from notebook_role_eval import (checked_config, invoke, decode, unavailable,
                                critique, packed, save)
from notebook_role_eval_transport import call_role_eval
from notebook_model_transport import model_request, ModelTransportError
from notebook_story_plan import parse_story
from notebook_story_native import native_story_bundle
from notebook_panel_eval import review_panels
from notebook_role_prompts import role_prompt
from notebook_story_suite import _read, _load


KEYS = {'p0': 'planner', 'p1': 'planner', 'd0': 'drawer', 'd1': 'drawer',
        'c0': 'critic', 'c1': 'critic'}


def inputs(packet_path, configs, deadline_ms):
    """Validate every source, image and fixed binding before any model call."""
    packet_path = Path(packet_path)
    packet = _load(packet_path)
    if (type(packet.get('v')) is not int or packet['v'] != 1 or
            packet.get('kind') != 'role-comparison-inputs'):
        raise ValueError('frozen role-comparison packet required')
    raw_corpus, corpus = load_corpus(packet_path.parent/'reviewer-corpus.json')
    if digest(raw_corpus) != packet.get('corpus_sha256'):
        raise ValueError('frozen corpus changed')
    if not isinstance(configs, dict) or set(configs) != set(KEYS):
        raise ValueError('exactly p0,p1,d0,d1,c0,c1 configurations required')
    configs = {key: checked_config(configs[key], role) for key, role in KEYS.items()}
    if len({c['endpoint'] for c in configs.values()}) != 6:
        raise ValueError('six distinct fixed endpoints required')
    for left,right in (('p0','p1'),('d0','d1'),('c0','c1')):
        if configs[left]['expected'] == configs[right]['expected']:
            raise ValueError('two distinct candidates required for each role')
    rows = packet.get('questions')
    if not isinstance(rows, list) or len(rows) != len(corpus['questions']):
        raise ValueError('keep the complete frozen question set')
    loaded = []
    for row, original in zip(rows, corpus['questions']):
        identity = original['id']
        if (set(row) != {'id','context','context_sha256','image','image_sha256'} or
                row['id'] != identity or row['context'] != identity+'.json' or
                row['image'] != identity+'.png'):
            raise ValueError('question order or local filename changed')
        context_bytes = _read(packet_path.parent/row['context'], 24000)
        image = _read(packet_path.parent/row['image'], 3_000_000)
        if digest(context_bytes) != row['context_sha256'] or digest(image) != row['image_sha256']:
            raise ValueError('question context or image changed')
        context = decode(context_bytes.decode('utf-8'))
        if context != planner_input(corpus, original):
            raise ValueError('question context differs from allowed corpus fields')
        model_request('notebook-'+'0'*32, image, packed(context), deadline_ms)
        loaded.append((identity, context, image, context_bytes))
    return packet, configs, loaded, raw_corpus


def confirm_idle(endpoint):
    """Read existing Pi responder state without introducing a health protocol.

    In notebook_pi_responder.respond, closed/busy precede input validation.
    The empty object MUST fail input validation before active is assigned or a
    provider is invoked. Thus invalid_request proves idle at this instant;
    busy/closed/unknown/transport failure prove nothing. Never send valid input.
    Use only with the installed source-verified Pi host, not an arbitrary API.
    """
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(2)
            stream.connect(endpoint)
            stream.sendall(b'{}\n')
            raw = b''
            while b'\n' not in raw and len(raw) <= 1024:
                part = stream.recv(1025-len(raw))
                if not part: break
                raw += part
        return decode(raw.decode('utf-8')) == {'request_id':None,'error':'invalid_request'}
    except (OSError, ValueError, UnicodeError):
        return False


def _trial(destination, action, idle_check=None):
    """Keep content rejection distinct from transport stop and unavailable."""
    record = dict(valid=False, tablet_proven=False, quality_status='unreviewed',
                  respond_to_first_visible_answer_ms=None)
    try:
        record.update(action())
    except ModelTransportError as exc:
        record['transport_error'] = exc.code
        if exc.code == 'deadline' and idle_check is not None and idle_check():
            record['provider_idle_after_deadline'] = True
        else:
            raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        record['error'] = str(exc)
    finally:
        if destination.exists():
            if (destination/'call.json').exists():
                record['metrics'] = _load(destination/'call.json')
            save(destination/'result.json', record)
    return record


def collect(packet_path, configs, destination, *, deadline_ms=30000,
            call=call_role_eval, clock=time.monotonic, progress=lambda row: None,
            idle_check=None):
    packet, configs, questions, raw_corpus = inputs(packet_path, configs, deadline_ms)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save(destination/'configs.json', configs)
    save(destination/'packet.json', packet)
    (destination/'reviewer-corpus.json').write_bytes(raw_corpus)
    for identity, _, image, context_bytes in questions:
        (destination/(identity+'.png')).write_bytes(image)
        (destination/(identity+'.json')).write_bytes(context_bytes)
    summary = dict(v=1, kind='role-cross-comparison', stopped=False, complete=False,
        packet_sha256=digest(Path(packet_path).read_bytes()), configs=configs,
        deadline_per_call_ms=deadline_ms, retries=0, tablet_proven=False,
        continue_after_confirmed_deadline=idle_check is not None,
        critic_calibrated=False, dollar_cost=None, rows=[],
        prompt_hashes={r: digest(role_prompt(r).encode()) for r in set(KEYS.values())})
    active = None
    try:
        for identity, packet_in, image, _ in questions:
            row = dict(id=identity, question=packet_in['context']['question'], planners={}, drawings={})
            summary['rows'].append(row)
            for planner in ('p0','p1'):
                path = destination/identity/planner
                active = str(path.relative_to(destination))
                def plan():
                    raw, metrics = invoke(configs[planner], 'planner', image, packet_in, path,
                                          deadline_ms=deadline_ms, call=call, clock=clock)
                    value = decode(raw)
                    if unavailable(value): return dict(unavailable=value['reason'])
                    story = parse_story(raw)
                    if story['question'] != row['question'] or len(story['panels']) < 3:
                        raise ValueError('planner changed question or omitted lesson steps')
                    save(path/'story.json', story)
                    return dict(valid=True, metrics=metrics)
                row['planners'][planner] = _trial(path, plan,
                    (lambda: idle_check(configs[planner]['endpoint'])) if idle_check else None)
            for planner in ('p0','p1'):
                if not row['planners'][planner]['valid']: continue
                story = _load(destination/identity/planner/'story.json', 24000)
                for drawer in ('d0','d1'):
                    pair = planner+'-'+drawer
                    path = destination/identity/pair
                    active = str(path.relative_to(destination))
                    def draw():
                        raw, metrics = invoke(configs[drawer], 'drawer', image,
                            {'task':'draw','context':{'story':story}}, path,
                            deadline_ms=deadline_ms, call=call, clock=clock)
                        value = decode(raw)
                        if unavailable(value): return dict(unavailable=value['reason'])
                        if (not isinstance(value,dict) or set(value) != {'v','mode','panels'} or
                                type(value['v']) is not int or value['v'] != 1 or value['mode'] != 'story-shapes'):
                            raise ValueError('drawer must return only the complete panel map')
                        bundle = native_story_bundle(story, value['panels'])
                        save(path/'story.json', story)
                        save(path/'panels.json', value['panels'])
                        preview = review_panels(packed(story).encode(), packed(value['panels']).encode(), path/'preview')
                        if not preview['valid']: raise ValueError('whole-lesson preview failed')
                        return dict(valid=True, native_preparation_valid=True, metrics=metrics,
                            snapshot_points=bundle['snapshot_points'], delivery_points=bundle['delivery_points'],
                            model_wall_ms=row['planners'][planner]['metrics']['wall_ms']+metrics['wall_ms'],
                            preview=preview)
                    drawing = _trial(path, draw,
                        (lambda: idle_check(configs[drawer]['endpoint'])) if idle_check else None)
                    row['drawings'][pair] = drawing
                    if drawing['valid']:
                        drawing['critics'] = {}
                        for critic in ('c0','c1'):
                            critic_path = path/critic
                            active = str(critic_path.relative_to(destination))
                            def judge():
                                review = critique(story, packet_in['context']['sources'], path/'preview',
                                    configs[critic], critic_path, deadline_ms=deadline_ms, call=call, clock=clock)
                                return dict(valid=True, review=review)
                            drawing['critics'][critic] = _trial(critic_path, judge,
                                (lambda: idle_check(configs[critic]['endpoint'])) if idle_check else None)
                    save(destination/'run.json', summary)
                    report(destination, summary)
                    progress(deepcopy(dict(question=identity, pair=pair, valid=drawing['valid'])))
            save(destination/'run.json', summary)
            report(destination, summary)
            progress(dict(question=identity, question_finished=True))
        summary['complete'] = True
    except ModelTransportError as exc:
        summary.update(stopped=True, stop_reason=exc.code, stopped_at=active)
    except BaseException:
        summary.update(stopped=True, stop_reason='collector_interrupted', stopped_at=active)
        raise
    finally:
        save(destination/'run.json', summary)
        report(destination, summary)
    return summary


def report(destination, summary=None):
    """Side-by-side original results; never treat an absent branch as failure."""
    destination = Path(destination)
    summary = summary or _load(destination/'run.json', 2_000_000)
    packet = _load(destination/'packet.json')
    esc = lambda value: html.escape(str(value), quote=True)
    page = ['<!doctype html><meta charset="utf-8"><title>Role comparison</title>',
        '<style>body{font:17px/1.5 sans-serif;margin:2rem}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}section{border:1px solid #aaa;padding:1rem}img{width:100%}pre{white-space:pre-wrap}</style>',
        '<h1>Frozen questions: planner × drawer, independent critics</h1>',
        '<p>Offline typeset inputs, not handwriting or tablet timing. First attempt only. '
        'Geometry validation is not teaching-quality approval; critic scores are uncalibrated. '
        'Respond-to-first-visible-answer is NOT MEASURED here. Provider first_text_ms '
        'may be a JSON token, not an answer character; model completion is a separate metric. '
        'Three prompt-worked topics are in-context examples, not held-out generalization tests.</p>',
        '<p>Complete: '+esc(summary['complete'])+'; stopped: '+esc(summary.get('stop_reason','no'))+'</p>',
        '<details><summary>Fixed candidates and conditions</summary><pre>'+esc(packed(summary['configs']))+'</pre></details>']
    rows = {row['id']:row for row in summary['rows']}
    for question in packet['questions']:
        identity = question['id']
        row = rows.get(identity)
        page.append('<h2>'+esc(row['question'] if row else identity)+'</h2>')
        if row is None:
            page.append('<p>Not attempted.</p>'); continue
        page.append('<div class="grid">')
        for planner in ('p0','p1'):
            trial = row['planners'].get(planner)
            page.append('<section><h3>'+planner+' — story</h3><pre>'+esc(packed(trial) if trial else 'Not attempted.')+'</pre>')
            source = destination/identity/planner/'response.txt'
            if source.exists(): page.append('<details><summary>Original story response</summary><pre>'+esc(_read(source,24000).decode())+'</pre></details>')
            page.append('</section>')
        page.append('</div><div class="grid">')
        for pair in ('p0-d0','p0-d1','p1-d0','p1-d1'):
            drawing = row['drawings'].get(pair)
            page.append('<section><h3>'+pair+'</h3>')
            if not drawing:
                page.append('<p>Not attempted (upstream rejection or collection stopped).</p>')
            elif not drawing['valid']:
                page.append('<pre>'+esc(packed(drawing))+'</pre>')
            else:
                page.append('<p>Planner + drawer model wall time: '+esc(drawing['model_wall_ms'])+' ms. Excludes capture, rendering, delivery and critics.</p>')
                for panel in drawing['preview']['panels']:
                    page.append('<figure><img src="'+esc(identity+'/'+pair+'/preview/'+panel['png'])+'"><figcaption>'+esc(panel['caption'])+'</figcaption></figure>')
                if drawing['preview'].get('equation'):
                    page.append('<img alt="Final pen equation" src="'+esc(identity+'/'+pair+'/preview/equation.png')+'">')
                story = _load(destination/identity/pair/'story.json',24000)
                page.append('<p>Takeaway: '+esc(story['takeaway'])+'</p>')
                page.append('<details><summary>Separate story/picture scores from both critics</summary><pre>'+esc(packed(drawing.get('critics',{})))+'</pre></details>')
            page.append('</section>')
        page.append('</div>')
    page.append('<p>Token usage and timings are retained per call in call.json. Dollar cost is not known for these subscription calls.</p>')
    (destination/'index.html').write_text('\n'.join(page),encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('configs', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--deadline-ms', type=int, default=30000)
    parser.add_argument('--continue-after-confirmed-deadline', action='store_true',
        help='Only for the source-verified Pi host: one no-provider idle probe, no retry')
    args = parser.parse_args()
    result = collect(args.packet, _load(args.configs), args.destination,
        deadline_ms=args.deadline_ms, progress=lambda row: print(packed(row),flush=True),
        idle_check=confirm_idle if args.continue_after_confirmed_deadline else None)
    print(packed({'complete':result['complete'],'stopped':result['stopped'],
                  'questions_started':len(result['rows'])}),flush=True)
    raise SystemExit(2 if result['stopped'] else 0)
