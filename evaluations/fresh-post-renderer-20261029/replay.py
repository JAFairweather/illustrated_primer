#!/usr/bin/env python3
"""Replay retained model answers offline; no model, server or tablet calls."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from notebook_panel_eval import review_panels
from notebook_story_native import native_story_bundle
from notebook_playback_preview import CSS, native_lesson_preview
from notebook_semantic_reply import parse_semantic_reply


def replay(destination):
    source = Path(__file__).with_name('answers.json')
    raw = source.read_bytes()
    fixture = json.loads(raw)
    destination.mkdir(parents=True, exist_ok=False)
    results, cards = [], []
    measurements = {row['id']: row for row in fixture['report']['rows']}
    for case in fixture['cases']:
        identity = case['id']
        # IDs are fixed fixture metadata, never model-selected output paths.
        if identity not in ('fractions', 'integral', 'inverse-mapping'):
            raise ValueError('unknown fixture identity')
        target = destination / identity
        story, panels = case['story'], case['panels']
        parse_semantic_reply(json.dumps(dict(v=1, mode='story-lesson',
                                            story=story, panels=panels)))
        checked = review_panels(json.dumps(story).encode(),
                                json.dumps(panels).encode(), target)
        if not checked['valid']:
            raise ValueError(identity + ': ' + checked['error'])
        bundle = native_story_bundle(story, panels)
        markup, timing = native_lesson_preview(bundle)
        (target / 'playback.html').write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<title>Offline lesson playback</title><style>' + CSS + '</style>'
            '<h1>' + html.escape(story['question']) + '</h1>'
            '<p>Retained model answer. Simulated native playback, not a tablet '
            'recording or measured Respond-to-visible latency.</p>' + markup + '</html>',
            encoding='utf-8')
        results.append(dict(id=identity, valid=True,
                            delivery_points=bundle['delivery_points'],
                            snapshot_points=bundle['snapshot_points'],
                            planned_playback=timing))
        measured = measurements[identity]
        final_png = checked['panels'][-1]['png']
        cards.append('<article><h2>' + html.escape(identity) + '</h2>'
                     '<img src="' + identity + '/' + final_png + '" alt="Final drawing">'
                     '<p>Original generation: ' + str(measured['wall_ms'] / 1000) +
                     ' s; ' + str(measured['calls']) + ' model calls.</p><p>' +
                     html.escape(measured['quality_notes']) + '</p>'
                     '<a href="' + identity + '/index.html">Every stage</a> · '
                     '<a href="' + identity + '/playback.html">Playback</a></article>')
    (destination / 'index.html').write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Fresh answer replay</title><style>body{font:18px sans-serif;margin:2rem}'
        'section{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}'
        'article{border:1px solid #aaa;padding:1rem}img{width:100%}</style>'
        '<h1>Three fresh answers — offline replay</h1>'
        '<p>No new model calls. Original generation exceeded the 30-second '
        'production deadline in all three cases. Not tablet proof or a full-suite pass.</p>'
        '<section>' + ''.join(cards) + '</section></html>', encoding='utf-8')
    summary = dict(fixture_sha256=hashlib.sha256(raw).hexdigest(),
                   model_calls=0, tablet_proven=False, cases=results)
    (destination / 'replay.json').write_text(json.dumps(summary, indent=2) + '\n',
                                           encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='New output directory; never overwritten')
    print(json.dumps(replay(parser.parse_args().destination)))
