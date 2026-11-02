#!/usr/bin/env python3
"""Offline narrative-contract review; never a model or tablet runner."""
import argparse
import hashlib
import json
from pathlib import Path

from notebook_story_plan import MAX_BYTES, parse_story, panel_packet, outline_html


def check_story(source, destination):
    with source.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    return review_story(raw, destination)


def review_story(raw, destination, *, authored_example=None):
    if len(raw) > MAX_BYTES:
        raise ValueError('story exceeds bounded input size')
    # An exclusive directory preserves previous drafts and their outcomes.
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'story.txt').write_bytes(raw)
    result = dict(story_valid=False, geometry_validated=False, native_validated=False,
                  tablet_proven=False, quality_status='unreviewed', model_calls=0,
                  input_sha256=hashlib.sha256(raw).hexdigest(), panels=[], outline=None,
                  notice='Narrative outline only; not a rendered lesson or a quality verdict.')
    if authored_example is not None:
        result['authored_example'] = authored_example
    try:
        story = parse_story(raw.decode('utf-8'))
    except ValueError as exc:
        result.update(error=str(exc), error_type=type(exc).__name__)
    else:
        (destination/'outline.html').write_text(outline_html(story), encoding='utf-8')
        for panel in story['panels']:
            name = 'panel-'+panel['id']+'.json'
            (destination/name).write_text(json.dumps(panel_packet(story, panel['id']),
                                                     ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            result['panels'].append(dict(id=panel['id'], context=name, base=panel['base']))
        result.update(story_valid=True, outline='outline.html')
    (destination/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check')
    check.add_argument('source', type=Path)
    check.add_argument('destination', type=Path)
    example = sub.add_parser('example')
    example.add_argument('name', choices=['odd-borders'])
    example.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.command == 'check':
        result = check_story(args.source, args.destination)
    else:
        from notebook_story_examples import story_examples
        raw = json.dumps(story_examples()[args.name], ensure_ascii=False, indent=2).encode('utf-8')
        result = review_story(raw, args.destination, authored_example=args.name)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['story_valid'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
