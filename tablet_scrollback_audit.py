"""Capture the isolated continuous test page using guarded native view moves.

No Respond, pen, selection, content writes, page switches or automatic retries.
Images require human visual review; an unchanged saved page alone is not a
visual-layout pass. Always try to restore the starting view, but never bypass a
changed page/surface/content/input guard to do so.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

from notebook_client import call
from tablet_acceptance import tablet, DATA
from tablet_live import capture, settled_frame

DOC = '905df7ae-ff54-46b9-a71e-45bb02bef638'
PAGE = '3ad12986-0467-48fe-986d-d1bd480c4777'


def identity(context):
    return tuple(context.get(key) for key in
                 ('doc', 'page', 'surface', 'content_revision', 'ink_revision'))


def audit(label):
    if not re.fullmatch('[a-z0-9-]{1,60}', label):
        raise ValueError('short unique lowercase audit label required')
    root = Path(os.path.expanduser('~/.buzz/OUTBOX'))
    manifest = root / (label+'.json')
    if manifest.exists() or list(root.glob(label+'-*.png')):
        raise ValueError('audit label already exists; never replace evidence')
    original = call('/notebook-device-context')
    frozen = identity(original)
    if original.get('doc') != DOC or original.get('page') != PAGE:
        raise ValueError('isolated audit page must be foreground')
    original_y = round(original['view'][5])
    if not 0 <= original_y <= 50000 or original['view'][5] != original_y:
        raise ValueError('unsupported initial view')
    data = tablet(f'cat {DATA}/{DOC}/{PAGE}.rm')
    digest = hashlib.sha256(data).hexdigest()
    result = dict(original=original, saved_sha256=digest, frames=[], visual_pass=None,
                  restored=False, note='View-only captures; manually review every historical region.')

    def context():
        current = call('/notebook-device-context')
        if (identity(current) != frozen or not current.get('fresh') or
                not current.get('active') or current.get('view', [])[:5] != [1,0,0,1,-702]):
            raise ValueError('audit page, input, content or view identity changed; stopping')
        return current

    def move(target):
        before = context()
        dy = round(before['view'][5]-target)
        if not dy:
            return before
        if abs(dy) > 1200:
            raise ValueError('audit step too large')
        call('/notebook-audit-view', dict(doc=DOC,page=PAGE,dy=dy))
        end = time.monotonic()+5
        while time.monotonic() < end:
            after = context()
            if abs(after['view'][5]-target) <= .01:
                return after
            if after['view'] != before['view']:
                raise ValueError('unexpected audit viewport; do not resend')
            time.sleep(.1)
        raise ValueError('audit command not observed; do not resend')

    try:
        index = 0
        while True:
            current = context()
            image = settled_frame(capture(tablet), lambda: capture(tablet))
            current_after = context()
            if current_after['view'] != current['view']:
                raise ValueError('view changed during audit capture')
            filename = f'{label}-{index:02d}.png'
            image.save(root/filename)
            result['frames'].append(dict(file=filename,context=current_after))
            manifest.write_text(json.dumps(result,indent=2))
            print('Captured',index,'scene top',current_after['view'][5],flush=True)
            if current_after['view'][5] <= 0:
                break
            move(max(0,current_after['view'][5]-1200))
            index += 1
            if index > 43:
                raise ValueError('audit capture budget exceeded')
    finally:
        try:
            for _ in range(43):
                y = context()['view'][5]
                if y == original_y:
                    result['restored'] = True
                    break
                move(y+max(-1200,min(1200,original_y-y)))
            result['saved_unchanged'] = hashlib.sha256(tablet(f'cat {DATA}/{DOC}/{PAGE}.rm')).hexdigest() == digest
        finally:
            manifest.write_text(json.dumps(result,indent=2))
            print('Restored:',result['restored'],'saved unchanged:',result.get('saved_unchanged'),flush=True)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    audit(parser.parse_args().label)
