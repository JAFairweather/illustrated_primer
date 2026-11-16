#!/usr/bin/env python3
"""Check a private B3 sample against actual PNG bytes and scored rows.

This is a consistency check, not proof of authorship, consent, or provider calls.
All inputs must stay outside the checkout; stdout contains counts only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from handwriting_accuracy import MODELS, checked_id, read_jsonl, score


def verify(manifest, images, references, outputs, models, config, receipts, replacements=()):
    if set(manifest) != {'version', 'seed', 'eligible_count', 'sample', 'reserves'} or manifest['version'] != 1:
        raise ValueError('invalid frozen sample manifest')
    sample, reserves = manifest['sample'], manifest['reserves']
    if len(sample) != 100 or len(reserves) > 20:
        raise ValueError('sample must contain 100 pages and at most 20 reserves')
    seed = manifest['seed']
    if (not isinstance(seed, str) or not 0 < len(seed) <= 100
            or not isinstance(manifest['eligible_count'], int)
            or manifest['eligible_count'] < len(sample) + len(reserves)):
        raise ValueError('invalid frozen sample metadata')
    frozen = {}
    for row in sample + reserves:
        if set(row) != {'page', 'image_sha256', 'notebook', 'eligible'} or row['eligible'] is not True:
            raise ValueError('invalid sampled page')
        page, digest = checked_id(row)
        if page in frozen:
            raise ValueError('duplicate sampled page')
        frozen[page] = digest
    if len(set(frozen.values())) != len(frozen):
        raise ValueError('duplicate sampled image')
    ranked = sorted(sample + reserves,
                    key=lambda row: (hashlib.sha256((seed + '\0' + row['page']).encode()).hexdigest(),
                                     row['page']))
    if ranked != sample + reserves:
        raise ValueError('sample/reserve order differs from frozen seed')

    selected = {row['page'] for row in sample}
    for index, change in enumerate(replacements):
        if set(change) != {'excluded_page', 'reserve_page', 'reason'} or change['reason'] not in (
                'unclear', 'untranscribable', 'permission_withdrawn'):
            raise ValueError('invalid replacement record')
        if change['excluded_page'] not in selected or index >= len(reserves):
            raise ValueError('replacement does not exclude a selected page')
        if change['reserve_page'] != reserves[index]['page']:
            raise ValueError('reserves must be taken in frozen rank order')
        selected.remove(change['excluded_page'])
        selected.add(change['reserve_page'])
    if len(selected) != 100:
        raise ValueError('final sample must contain 100 distinct pages')

    if set(images) != selected:
        raise ValueError('PNG set differs from final frozen sample')
    for page, path in images.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != frozen[page]:
            raise ValueError('PNG bytes differ from frozen sample')

    refs, outs = list(references), list(outputs)
    if {row.get('page') for row in refs} != selected or len(refs) != 100:
        raise ValueError('reference set differs from final frozen sample')
    for row in refs + outs:
        page, digest = checked_id(row)
        if page not in selected or digest != frozen[page]:
            raise ValueError('scored row differs from frozen image')
    if set(config) != {'prompt_sha256', 'models'} or set(config['models']) != set(models):
        raise ValueError('frozen run configuration differs from model list')
    digests = [config['prompt_sha256'], *config['models'].values()]
    if any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in digests):
        raise ValueError('invalid frozen run digest')
    output_rows = {(row['page'], row['model']): row for row in outs}
    if len(output_rows) != len(outs):
        raise ValueError('duplicate scored output')
    seen_receipts = set()
    for receipt in receipts:
        if set(receipt) != {'page', 'image_sha256', 'model', 'prompt_sha256',
                            'config_sha256', 'output_sha256'}:
            raise ValueError('invalid adapter receipt')
        key = (receipt['page'], receipt['model'])
        if key not in output_rows or key in seen_receipts:
            raise ValueError('adapter receipt set differs from outputs')
        seen_receipts.add(key)
        row = output_rows[key]
        output_digest = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':'),
                                                  ensure_ascii=False).encode('utf-8')).hexdigest()
        if (receipt['image_sha256'] != frozen[receipt['page']]
                or receipt['prompt_sha256'] != config['prompt_sha256']
                or receipt['config_sha256'] != config['models'][receipt['model']]
                or receipt['output_sha256'] != output_digest):
            raise ValueError('adapter receipt differs from frozen run')
    if seen_receipts != set(output_rows):
        raise ValueError('missing adapter receipts')
    result = score(refs, outs, models, require_complete=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--images', required=True, help='private directory of <opaque page>.png')
    parser.add_argument('--references', required=True)
    parser.add_argument('--outputs', required=True)
    parser.add_argument('--run-config', required=True, help='frozen prompt and per-model config digests')
    parser.add_argument('--receipts', required=True, help='adapter-generated row receipts')
    parser.add_argument('--replacements', help='private JSONL replacement ledger')
    parser.add_argument('--model', action='append', choices=MODELS, required=True)
    args = parser.parse_args()
    try:
        checkout = Path(__file__).resolve().parent
        paths = [Path(x) for x in (args.manifest, args.images, args.references, args.outputs,
                                   args.run_config, args.receipts)]
        if args.replacements:
            paths.append(Path(args.replacements))
        if any(path.resolve() == checkout or checkout in path.resolve().parents for path in paths):
            raise ValueError('private inputs must stay outside the checkout')
        image_dir = Path(args.images)
        image_paths = list(image_dir.iterdir())
        if any(not path.is_file() or path.suffix != '.png' for path in image_paths):
            raise ValueError('image directory must contain only PNG files')
        images = {path.stem: path for path in image_paths}
        if len(images) != len(image_paths):
            raise ValueError('duplicate image page')
        manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
        config = json.loads(Path(args.run_config).read_text(encoding='utf-8'))
        replacements = read_jsonl(args.replacements) if args.replacements else ()
        result = verify(manifest, images, read_jsonl(args.references), read_jsonl(args.outputs),
                        args.model, config, read_jsonl(args.receipts), replacements)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f'handwriting_binding: {type(error).__name__}; private input rejected', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
