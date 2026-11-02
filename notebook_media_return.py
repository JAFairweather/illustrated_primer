"""Return tool-generated image bytes to ONE pending notebook request.

stdin is the /notebook-media JSON body, not an arbitrary local path or URL.
The caller must first read an admitted, in-scope request and generate its image.
This helper validates correlation before uploading and again via the callback.
"""
import argparse
import json
import re
import sys
import urllib.request
from notebook_auth import local_headers

BASE = 'http://127.0.0.1:8791'


def call(route, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + route, data=data,
                                     headers=local_headers())
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def return_image(request, payload, caption):
    if not re.fullmatch(r'notebook-[0-9a-f]{32}', request):
        raise ValueError('exact notebook request ID required')
    if not isinstance(caption, str) or not caption.strip() or len(caption) > 500:
        raise ValueError('short honest image caption required')
    jobs = call('/notebook-status')['jobs']
    job = next((job for job in jobs if job['request'] == request), None)
    if not job:
        raise ValueError('notebook request is not pending on this server')
    from urllib.parse import quote
    state = call('/answer?page=' + quote(job['page'], safe=''))
    if state.get('request') != request or state.get('state') != 'waiting' or not state.get('media_pending'):
        raise ValueError('request superseded, already answered, expired, or not waiting for media')
    if not isinstance(payload, dict) or set(payload) != {'png', 'kind'}:
        raise ValueError('image bytes and kind only; no paths or remote URLs')
    if payload['kind'] not in ('illustration', 'photo', 'diagram'):
        raise ValueError('unsupported notebook image kind')
    asset = call('/notebook-media', payload)
    reply = caption.strip() + '\n[[notebook-asset:' + asset['asset'] + ']]'
    result = call('/notebook-reply', {'request': request, 'text': reply})
    return {'request': request, 'asset': asset['asset'], 'page': job['page'],
            'state': result['state'], 'note': 'Held for native insertion, not yet proof of display/save'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request')
    parser.add_argument('--bytes', type=int, required=True, dest='length')
    parser.add_argument('--caption', required=True)
    args = parser.parse_args()
    if not 1 <= args.length <= 4_000_000:
        parser.error('JSON body must fit the bounded media endpoint (4 MB)')
    raw = sys.stdin.buffer.read(args.length)
    if len(raw) != args.length:
        parser.error('incomplete image body')
    print(json.dumps(return_image(args.request, json.loads(raw), args.caption)), flush=True)
