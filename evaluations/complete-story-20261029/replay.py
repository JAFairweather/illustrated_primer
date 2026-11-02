#!/usr/bin/env python3
"""Revalidate all retained answers, including failures; no model or tablet IO."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from notebook_semantic_reply import parse_semantic_reply
from notebook_story_native import native_story_bundle
from notebook_panel_eval import review_panels


def replay(destination):
    fixture = json.loads(Path(__file__).with_name('answers.json').read_text())
    assert len(fixture['cases']) == 14
    for case in fixture['cases']:
        if hashlib.sha256(case['response'].encode()).hexdigest() != case['response_sha256']:
            raise ValueError('retained response hash mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    rows, cards = [], []
    for number, case in enumerate(fixture['cases']):
        row = dict(id=case['id'], originally_valid=case['result']['valid'], valid=False)
        try:
            parsed = parse_semantic_reply(case['response'])
            if parsed['mode'] == 'clarify':
                row['clarification'] = parsed['text']
            elif parsed['mode'] != 'lesson' or 'story' not in parsed:
                raise ValueError('complete story-lesson required')
            else:
                bundle = native_story_bundle(parsed['story'], parsed['drafts'])
                folder = 'case-'+str(number)  # no model-selected file paths
                checked = review_panels(json.dumps(parsed['story']).encode(),
                    json.dumps(parsed['drafts']).encode(), destination/folder)
                row.update(valid=checked['valid'], native_prepared=True,
                    snapshot_points=bundle['snapshot_points'],
                    delivery_points=bundle['delivery_points'])
                if checked['valid']:
                    row['preview'] = folder+'/index.html'
                else:
                    row['error'] = checked['error']
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
            row['error'] = str(error)
        rows.append(row)
        body = ('<a href="'+row['preview']+'">Stage-by-stage preview</a>' if row['valid']
                else html.escape(row.get('error') or row.get('clarification', 'No lesson')))
        cards.append('<article><h2>'+html.escape(case['id'])+'</h2>'+body+'</article>')
    result = dict(model_calls=0, tablet_proven=False, cases=rows,
                  valid=sum(row['valid'] for row in rows))
    (destination/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (destination/'index.html').write_text('<!doctype html><meta charset="utf-8">'
        '<h1>Retained answers: current compiler replay</h1><p>No new generation, '
        'no tablet evidence. Failures are preserved.</p>'+''.join(cards))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    print(json.dumps(replay(parser.parse_args().destination)))
