#!/usr/bin/env python3
"""Score private handwriting transcriptions without printing page content.

Inputs are JSONL outside the checkout. References have page, image_sha256, text;
outputs have page, image_sha256, model and either text or error. The public
summary contains only counts and aggregate edit rates.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata


MODELS = ('gemini-3.5-flash-lite', 'gpt-5.6-luna', 'gpt-6-astra')
REQUIRED_B3_MODELS = {'gemini-3.5-flash-lite', 'gpt-5.6-luna'}
ERRORS = {'timeout', 'unavailable', 'invalid_response', 'provider_error'}


def normalize(value):
    if not isinstance(value, str):
        raise ValueError('transcription must be text')
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', value)).strip()


def distance(a, b):
    """Levenshtein distance, using memory proportional to the shorter input."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as source:
        for line in source:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError('each input row must be an object')
                yield value


def checked_id(row):
    page, digest = row.get('page'), row.get('image_sha256')
    if not isinstance(page, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', page):
        raise ValueError('invalid opaque page id')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('invalid image digest')
    return page, digest


def score(references, outputs, models=MODELS, require_complete=False):
    refs = {}
    for row in references:
        if set(row) != {'page', 'image_sha256', 'text'}:
            raise ValueError('reference row needs page, image_sha256, text')
        page, digest = checked_id(row)
        if page in refs:
            raise ValueError('duplicate reference page')
        ref = normalize(row['text'])
        if not ref:
            raise ValueError('blank reference page is ineligible')
        if '[unclear]' in ref.casefold():
            raise ValueError('uncertain reference needs a reserve page')
        refs[page] = (digest, ref)
    if not refs:
        raise ValueError('no reference pages')
    if require_complete and len(refs) != 100:
        raise ValueError('complete B3 report requires 100 reference pages')
    if len(set(models)) != len(models) or not models or any(m not in MODELS for m in models):
        raise ValueError('unknown or duplicate model')
    if require_complete and not REQUIRED_B3_MODELS.issubset(models):
        raise ValueError('complete B3 report requires Gemini baseline and Pi comparator')
    seen = set()
    data = {model: {'scored': 0, 'errors': 0, 'char_edits': 0, 'ref_chars': 0,
                    'word_edits': 0, 'ref_words': 0} for model in models}
    for row in outputs:
        if set(row) not in ({'page', 'image_sha256', 'model', 'text'},
                            {'page', 'image_sha256', 'model', 'error'}):
            raise ValueError('output row needs exactly one of text or error')
        page, digest = checked_id(row)
        model = row.get('model')
        if page not in refs or model not in data or digest != refs[page][0]:
            raise ValueError('unknown page/model or mismatched input image')
        if (page, model) in seen:
            raise ValueError('duplicate page/model output')
        seen.add((page, model))
        stats = data[model]
        if 'error' in row:
            if row['error'] not in ERRORS:
                raise ValueError('unknown error code')
            stats['errors'] += 1
            continue
        ref = refs[page][1]
        hyp = normalize(row['text'])
        stats['scored'] += 1
        stats['char_edits'] += distance(ref, hyp)
        stats['ref_chars'] += len(ref)
        rw, hw = ref.split(), hyp.split()
        stats['word_edits'] += distance(rw, hw)
        stats['ref_words'] += len(rw)
    summary = {'version': 1, 'pages': len(refs), 'normalization': 'NFC; whitespace runs to one space; trim; case and punctuation preserved',
               'models': {}}
    for model, stats in data.items():
        stats['missing'] = len(refs) - stats['scored'] - stats['errors']
        stats['cer'] = stats['char_edits'] / stats['ref_chars'] if stats['ref_chars'] else None
        stats['wer'] = stats['word_edits'] / stats['ref_words'] if stats['ref_words'] else None
        summary['models'][model] = stats
        if require_complete and (stats['missing'] or stats['errors']):
            raise ValueError('complete B3 report requires all model outputs')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--references', required=True)
    parser.add_argument('--outputs', required=True)
    parser.add_argument('--model', action='append', choices=MODELS, required=True)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    try:
        checkout = Path(__file__).resolve().parent
        if checkout in Path(args.references).resolve().parents or checkout in Path(args.outputs).resolve().parents:
            raise ValueError('private transcriptions must stay outside the checkout')
        result = score(read_jsonl(args.references), read_jsonl(args.outputs),
                       args.model, args.require_complete)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f'handwriting_accuracy: {type(error).__name__}; private input rejected', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
