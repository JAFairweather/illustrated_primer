#!/usr/bin/env python3
"""Freeze a seeded B3 sample from a private, human-checked candidate manifest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def select(rows, seed, count=100, reserves=20):
    if not isinstance(seed, str) or not seed or len(seed) > 100:
        raise ValueError('bounded nonempty sample seed required')
    seen = set()
    seen_images = set()
    eligible = []
    for row in rows:
        if set(row) != {'page', 'image_sha256', 'notebook', 'eligible'}:
            raise ValueError('candidate metadata shape is invalid')
        page, image_hash, notebook = row['page'], row['image_sha256'], row['notebook']
        if not isinstance(page, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', page):
            raise ValueError('invalid opaque page id')
        if not isinstance(image_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', image_hash):
            raise ValueError('invalid image hash')
        if not isinstance(notebook, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', notebook):
            raise ValueError('invalid opaque notebook id')
        if not isinstance(row['eligible'], bool) or page in seen:
            raise ValueError('invalid eligibility or duplicate page')
        seen.add(page)
        if row['eligible']:
            if image_hash in seen_images:
                raise ValueError('duplicate eligible image')
            seen_images.add(image_hash)
            eligible.append(row)
    if len(eligible) < count:
        raise ValueError('fewer than 100 eligible real pages')
    ranked = sorted(eligible, key=lambda row: (hashlib.sha256((seed + '\0' + row['page']).encode()).hexdigest(), row['page']))
    return {'version': 1, 'seed': seed, 'eligible_count': len(eligible),
            'sample': ranked[:count], 'reserves': ranked[count:count + reserves]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--candidates', required=True)
    parser.add_argument('--seed', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        source = Path(args.candidates)
        target = Path(args.output)
        checkout = Path(__file__).resolve().parent
        if checkout in source.resolve().parents or checkout in target.resolve().parents:
            raise ValueError('private manifests must stay outside the checkout')
        if target.exists():
            raise ValueError('sample manifest already exists')
        rows = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line.strip()]
        result = select(rows, args.seed)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(result, output, indent=2, sort_keys=True)
            output.write('\n')
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f'handwriting_sample: {type(error).__name__}; private input rejected', file=sys.stderr)
        return 1
    print(json.dumps({'eligible_count': result['eligible_count'], 'selected': len(result['sample']),
                      'reserves': len(result['reserves'])}, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
