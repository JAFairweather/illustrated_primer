"""Explicit, bounded device acceptance helpers; never overwrite a user notebook.

Run create-test-notebook once, then capture/tap/draw on the isolated test notebook.
Commands use the existing tablet host key even when the .lan DNS spelling fails.
"""
import argparse
import json
import math
import os
import shlex
import subprocess
import time
import uuid
import urllib.parse
import urllib.request
from pathlib import Path
import numpy as np

from tablet_live import capture, draw_paths, pen_frame, pen_point, RESPOND_TAP
from tablet_transport import tablet_ssh
from notebook_auth import local_headers
from ink import pen_text, thin, trace
from notebook_ink import line_art_paths, place_paths
from PIL import Image, ImageFont

SSH = tablet_ssh('root@remarkable.local')
ENV = dict(os.environ, SSH_AUTH_SOCK=os.path.expanduser('~/.ssh/s/r1-agent.sock'))
DATA = '/home/root/.local/share/remarkable/xochitl'


def tablet(command, data=None):
    return subprocess.run([*SSH, command], input=data, capture_output=True,
                          check=True, timeout=30, env=ENV).stdout


def create_test_notebook(source, folder_name='Workflow tests (Codex)'):
    source = str(uuid.UUID(source))
    metadata = json.loads(tablet(f'cat {DATA}/{source}.metadata'))
    if metadata.get('visibleName', '').lower() != 'to pidog':
        raise ValueError('source must be the To pidog notebook')
    content = json.loads(tablet(f'cat {DATA}/{source}.content'))
    folder, doc, page = (str(uuid.uuid4()) for _ in range(3))
    stamp = str(int(time.time() * 1000))
    content.update(pageCount=1, sizeInBytes='0', pageTags=[], tags=[])
    content['cPages'] = {'lastOpened': {'timestamp': '1:1', 'value': page},
                        'original': {'timestamp': '0:0', 'value': -1},
                        'pages': [{'id': page, 'idx': {'timestamp': '1:1', 'value': 'ba'},
                                   'template': {'timestamp': '1:1', 'value': 'P Lines small'}}],
                        'uuids': []}
    content.update(customZoomCenterX=0, customZoomCenterY=936,
                   customZoomScale=1, customZoomPageWidth=1404,
                   customZoomPageHeight=1872, coverPageNumber=-1)
    meta = {'createdTime': stamp, 'lastModified': stamp, 'lastOpenedPage': 0,
            'new': True, 'parent': folder, 'pinned': False, 'source': '',
            'type': 'DocumentType', 'visibleName': 'To pidog'}
    folder_meta = {'createdTime': stamp, 'lastModified': stamp, 'new': True,
                   'parent': '', 'pinned': True, 'type': 'CollectionType',
                   'visibleName': folder_name}
    for identity, extension, value in [(folder, 'metadata', folder_meta),
                                        (doc, 'content', content), (doc, 'metadata', meta)]:
        target = f'{DATA}/{identity}.{extension}'
        # All IDs are newly generated; fail rather than replace any existing file.
        tablet(f'test ! -e {target} && cat > {target}.new && mv {target}.new {target}',
               json.dumps(value, indent=4).encode())
    tablet(f'mkdir {DATA}/{doc}')
    return {'folder': folder, 'doc': doc, 'page': page,
            'name': folder_name + '/To pidog', 'source_unchanged': source}


def tap(x, y):
    x, y = pen_point(x, y)
    frames = [[(3, 0, x), (3, 1, y), (1, 320, 1), (1, 330, 0), (3, 24, 0), (3, 25, 100)],
              [(1, 330, 1), (3, 24, 1500), (3, 25, 0)],
              [(3, 24, 0), (3, 25, 100), (1, 330, 0), (1, 320, 0)]]
    process = subprocess.Popen([*SSH, 'cat > /dev/input/event1'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV)
    try:
        for events in frames:
            process.stdin.write(pen_frame(events)); process.stdin.flush(); time.sleep(.12)
    finally:
        process.stdin.close()
    process.wait(timeout=10)
    if process.returncode:
        raise RuntimeError('tablet input failed')


def create_stroke_fixture(source, plan):
    """Fresh blank foreground plus immutable ink-only source pages, never notes.

    Library discovery may require a setup-only interface reload. This helper
    does not navigate, tap, restart, or modify an existing notebook.
    """
    from notebook_stroke_asset import storyboard_assets
    assets = storyboard_assets(plan)  # reject the whole plan before device I/O
    return _create_asset_fixture(source, assets, 'Native clone tests (Codex)')


def create_storyboard_fixture(source):
    """Provision immutable labelled source pages, plus a NEW empty test notebook."""
    from notebook_ink_catalog import FACTORIES, InkCatalog
    from notebook_stroke_asset import storyboard_assets
    assets = [dict(asset, scene=scene) for scene, factory in FACTORIES.items()
              for asset in storyboard_assets(factory(), ink_labels=True)]
    fixture = _create_asset_fixture(source, assets, 'Storyboard tests (Codex)')
    return _storyboard_catalog(fixture)


def provision_storyboard_source_version(doc):
    """New immutable sources beside an existing diagnostic notebook; no edits to it."""
    from notebook_ink_catalog import FACTORIES
    from notebook_stroke_asset import storyboard_assets
    doc = str(uuid.UUID(doc))
    metadata = json.loads(tablet(f'cat {DATA}/{doc}.metadata'))
    parent = str(uuid.UUID(metadata['parent']))
    folder = json.loads(tablet(f'cat {DATA}/{parent}.metadata'))
    if metadata.get('visibleName') != 'To pidog' or folder.get('visibleName') != 'Storyboard tests (Codex)':
        raise ValueError('new source versions are restricted to the storyboard diagnostic folder')
    assets = [dict(asset, scene=scene) for scene, factory in FACTORIES.items()
              for asset in storyboard_assets(factory(), ink_labels=True)]
    return _storyboard_catalog(_create_asset_document(dict(doc=doc, folder=parent), assets))


def _storyboard_catalog(fixture):
    from notebook_ink_catalog import InkCatalog
    manifest = {'version': 1, 'scenes': {}}
    for asset in fixture['assets']:
        scene = manifest['scenes'].setdefault(asset['scene'], {'digest': asset['program_digest'], 'stages': {}})
        scene['stages'][asset['stage']] = dict(source_doc=fixture['source_doc'], source_page=asset['page'],
            sha256=asset['sha256'], stroke_count=asset['stroke_count'], point_count=asset['point_count'],
            bounds=asset['bounds'], labels=asset['annotations_rendered_as'])
    InkCatalog(manifest)  # never return an invalid registration catalog
    return dict(fixture, catalog=manifest)


def _create_asset_fixture(source, assets, folder_name):
    fixture = create_test_notebook(source, folder_name)
    return _create_asset_document(fixture, assets)


def _create_asset_document(fixture, assets):
    doc = str(uuid.uuid4())
    page_ids = [str(uuid.uuid4()) for _ in assets]
    content = json.loads(tablet(f'cat {DATA}/{fixture["doc"]}.content'))
    content['pageCount'] = len(assets)
    content['cPages']['lastOpened']['value'] = page_ids[0]
    content['cPages']['pages'] = [
        {'id': identity, 'idx': {'timestamp': '1:1', 'value': 'b'+chr(97+i)},
         'template': {'timestamp': '1:1', 'value': 'Blank'}}
        for i, identity in enumerate(page_ids)]
    stamp = str(int(time.time()*1000))
    metadata = dict(createdTime=stamp, lastModified=stamp, lastOpenedPage=0,
                    new=True, parent=fixture['folder'], pinned=False, source='',
                    type='DocumentType', visibleName='Procedural stroke sources')
    tablet(f'mkdir {DATA}/{doc}')
    for identity, asset in zip(page_ids, assets):
        target = f'{DATA}/{doc}/{identity}.rm'
        tablet(f'test ! -e {target} && cat > {target}.new && mv {target}.new {target}', asset['data'])
    for extension, value in (('content', content), ('metadata', metadata)):
        target = f'{DATA}/{doc}.{extension}'
        tablet(f'test ! -e {target} && cat > {target}.new && mv {target}.new {target}',
               json.dumps(value).encode())
    return dict(fixture, source_doc=doc,
                assets=[dict(page=identity, **{k: v for k, v in asset.items() if k != 'data'})
                        for identity, asset in zip(page_ids, assets)])


def require_blank_area(left, top, right, bottom):
    """Refuse a test stroke over existing ink/text/images; gray rules are OK."""
    from PIL import ImageStat
    image = capture(tablet).crop((left, top, right, bottom))
    dark = image.point(lambda value: 255 if value < 110 else 0)
    if ImageStat.Stat(dark).sum[0] > 255 * 5:
        raise ValueError('test target contains existing content; scroll and inspect before drawing')


def hand_letter_paths(text, width, size=30):
    """Clean single-stroke test handwriting, wrapped at words; no bitmap trace."""
    from notebook_plotter_font import label_paths
    if not isinstance(text, str) or not 1 <= len(text) <= 120 or not 100 <= width <= 1050:
        raise ValueError('bounded test handwriting required')
    if type(size) not in (int, float) or not 20 <= size <= 40:
        raise ValueError('test handwriting size must be 20..40')
    lines=[]; line=''
    for word in text.split():
        candidate=(line+' '+word).strip()
        if len(candidate)>48 or label_paths(candidate,24)[1]*size/24+size*.12>width:
            if not line:
                raise ValueError('test word exceeds line width')
            lines.append(line); line=word
        else:
            line=candidate
    if line: lines.append(line)
    paths=[]
    for index,line in enumerate(lines):
        strokes,advance=label_paths(line,24)
        if advance*size/24+size*.12>width:
            raise ValueError('test word exceeds line width')
        paths.extend([[(px*size/24+(24-py)*size/24*.09,
                        py*size/24+index*size*1.65) for px,py in path] for path in strokes])
    return paths, max(1,len(lines))*size*1.65


def write_note(text, x, y, *, hand_lettered=False):
    """Simulated ink, not native text; dense motion avoids dropped long segments."""
    if len(text) > 120 or not 150 <= x <= 1100 or not 100 <= y <= 1550:
        raise ValueError('test note outside safe drawing area')
    paths, height = (hand_letter_paths(text,1200-x) if hand_lettered else
                     pen_text(text, 1200-x, 36, face=ImageFont.load_default(size=36)))
    if y + height >= 1660:
        raise ValueError('test note would run into native bottom controls')
    require_blank_area(x-5, y-5, 1200, y+height+10)
    dense = []
    for path in paths:
        points = []
        for a, b in zip(path, path[1:]):
            steps = max(1, math.ceil(math.dist(a, b) / 2))
            points.extend([(x+a[0]+(b[0]-a[0])*i/steps, y+a[1]+(b[1]-a[1])*i/steps)
                           for i in range(steps)])
        if path:
            points.append((x+path[-1][0], y+path[-1][1]))
        if len(points) > 1:
            dense.append(points)
    draw_paths(dense, SSH, ENV, pace=.009)


def draw_line_art(source, x, y, width=300, height=180):
    """Explicit diagnostic drawing only; never an automatic agent callback."""
    if not (150 <= x and 100 <= y and x+width < 1200 and y+height < 1660):
        raise ValueError('line art outside safe drawing area')
    with Image.open(source) as image:
        plan = line_art_paths(image, width, height)
    # Conversion and all resource bounds pass before checking the actual live
    # destination. Never draw onto existing ink, text, or an imported image.
    require_blank_area(x-5, y-5, x+width+5, y+height+5)
    draw_paths(place_paths(plan, x, y), SSH, ENV, pace=.009)
    return {key: value for key, value in plan.items() if key != 'paths'}


def replay_handwriting(source, x, y):
    """Trace a reviewed ink-only sample, without OCR/retyping or changing its source.

    This is replayed human handwriting, NOT a new live human-written exchange.
    Only small, ink-only exports fit: screenshots with UI must not be passed here.
    """
    if not 150 <= x <= 1100 or not 100 <= y <= 1700:
        raise ValueError('replay outside safe drawing area')
    with Image.open(source) as image:
        if image.width > 960 or image.height > 200:
            raise ValueError('replay requires a small reviewed ink-only sample')
        mask = np.asarray(image.convert('L')) < 110
    ys, xs = np.nonzero(mask)
    if len(xs) < 10:
        raise ValueError('sample contains no handwriting')
    mask = mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
    height, width = mask.shape
    # Lower-left paper remains writable beside Respond. Keep the sample and
    # its preflight padding strictly left of the lower-right control mask.
    lower_left = x + width + 10 < 700 and y + height + 10 < 1792
    if x + width >= 1200 or (y + height >= 1660 and not lower_left):
        raise ValueError('replay would run into native controls')
    paths = trace(thin(mask))
    require_blank_area(x-5, y-5, x+width+10, y+height+10)
    translated = [[(x+px, y+py) for px, py in path] for path in paths if len(path) > 1]
    draw_paths(translated, SSH, ENV, pace=.009)
    return {'source': str(source), 'width': width, 'height': height,
            'paths': len(translated), 'kind': 'replayed human handwriting'}


def notebook_status(doc, page):
    target = f'{uuid.UUID(doc)}/{uuid.UUID(page)}.rm'
    url = 'http://127.0.0.1:8791/answer?page=' + urllib.parse.quote(target)
    request = urllib.request.Request(url, headers=local_headers())
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def watch_reply(doc, page, label, seconds=60):
    """Observe the NEXT human exchange using GET/capture only. Never tap or draw.

    A timeout ends observation, not the notebook job. Captured frames require
    manual review; elapsed age after capture is a conservative visible bound,
    not a claim that the server's written timestamp is first-visible output.
    """
    doc, page = str(uuid.UUID(doc)), str(uuid.UUID(page))
    if not label or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in label):
        raise ValueError('use a short lowercase test label')
    if not 1 <= seconds <= 600:
        raise ValueError('observation window must be 1..600 seconds')
    out = Path(os.path.expanduser('~/.buzz/OUTBOX'))
    previous = notebook_status(doc, page).get('request')
    started = time.monotonic()
    rows, marker, outcome = [], None, 'observation_timeout'
    while time.monotonic() - started < seconds:
        current = notebook_status(doc, page)
        identity = current.get('request')
        if marker and identity != marker:
            outcome = 'superseded'
            break
        if identity and identity != previous:
            marker = identity
            begin = time.monotonic()
            frame = capture(tablet)
            end = time.monotonic()
            frame.save(out / f'{label}-frame-{len(rows):02d}.png')
            current = notebook_status(doc, page)
            row = {'frame': len(rows), 'begin': round(begin-started, 3),
                   'end': round(end-started, 3), 'status': current}
            rows.append(row)
            print(json.dumps(row), flush=True)
            if current.get('request') != marker:
                outcome = 'superseded'
                break
            if current.get('state') in ('written', 'failed', 'no answer'):
                outcome = 'observed_terminal'
                break
        time.sleep(.25)
    result = {'doc': doc, 'page': page, 'label': label, 'mode': 'passive-human-watch',
              'previous_request': previous, 'request': marker, 'outcome': outcome,
              'samples': rows, 'visual_pass': None,
              'note': 'No input injected. Review frames; respond_elapsed_ms after capture bounds visible latency. A timeout never authorizes resending.'}
    (out / f'{label}-timing.json').write_text(json.dumps(result, indent=2))
    print('Recorded', out / f'{label}-timing.json', flush=True)
    return result


def observe_reply(doc, page, label):
    """Capture a single real RESPOND, requiring a NEW correlated request.

    Frames must be visually reviewed; a viewport change isn't automatically a
    response, and 'written' for the previous request is never a new pass.
    """
    doc, page = str(uuid.UUID(doc)), str(uuid.UUID(page))
    if not label or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in label):
        raise ValueError('use a short lowercase test label')
    out = Path(os.path.expanduser('~/.buzz/OUTBOX'))
    def status():
        return notebook_status(doc, page)
    initial = status()
    if initial.get('state') not in ('unknown', 'written'):
        raise ValueError('existing notebook request is pending or failed; observe/recover it without another Respond')
    previous = initial.get('request')
    capture(tablet).save(out / f'{label}-input.png')
    rows = []
    started = time.monotonic()
    utc = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    tap(*RESPOND_TAP)
    for frame in range(60):
        begin = time.monotonic()
        image = capture(tablet)
        end = time.monotonic()
        image.save(out / f'{label}-frame-{frame:02d}.png')
        current = status()
        row = {'frame': frame, 'begin': round(begin-started, 3),
               'end': round(end-started, 3), 'status': current}
        rows.append(row)
        print(json.dumps(row), flush=True)
        if current.get('request') and current['request'] != previous and current['state'] in ('written', 'failed'):
            break
        time.sleep(.25)
    result = {'doc': doc, 'page': page, 'label': label, 'tap_utc': utc,
              'previous_request': previous, 'samples': rows, 'visual_pass': None,
              'note': 'Sampled framebuffer; inspect frames for new answer, not merely UI movement.'}
    (out / f'{label}-timing.json').write_text(json.dumps(result, indent=2))
    print('Recorded', out / f'{label}-timing.json', flush=True)
    return result


def draw_test_dog(top=1440):
    if not 100 <= top <= 1460:
        raise ValueError('dog outside safe native ink area')
    require_blank_area(225, top, 890, top+205)
    write_note('Animal?', 240, top+20)
    def oval(x, y, rx, ry):
        return [(x+rx*math.cos(i*2*math.pi/80), y+ry*math.sin(i*2*math.pi/80)) for i in range(81)]
    paths = [oval(650, 95, 125, 42), oval(800, 60, 35, 35), oval(812, 50, 3, 3),
             [(828,47),(863,55),(865,75),(829,85)], [(790,30),(774,18),(775,54)],
             [(535,80),(493,50),(481,22)], [(565,127),(560,195),(578,195)],
             [(600,135),(607,195),(625,195)], [(704,130),(700,195),(718,195)],
             [(740,122),(748,195),(765,195)], [(760,80),(773,60)]]
    dense = []
    for path in paths:
        points = []
        for a, b in zip(path, path[1:]):
            steps = max(1, math.ceil(math.dist(a, b)/2))
            points.extend([(a[0]+(b[0]-a[0])*i/steps, top+a[1]+(b[1]-a[1])*i/steps)
                           for i in range(steps)])
        points.append((path[-1][0], top+path[-1][1])); dense.append(points)
    draw_paths(dense, SSH, ENV, pace=.009)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create-test-notebook'); create.add_argument('source')
    create.add_argument('--folder', default='Workflow tests (Codex)')
    screen = sub.add_parser('capture'); screen.add_argument('output')
    click = sub.add_parser('tap'); click.add_argument('x', type=int); click.add_argument('y', type=int)
    ink = sub.add_parser('write-note'); ink.add_argument('text'); ink.add_argument('x', type=int); ink.add_argument('y', type=int)
    observe = sub.add_parser('respond'); observe.add_argument('doc'); observe.add_argument('page'); observe.add_argument('label')
    watch = sub.add_parser('watch', help='passive GET/capture observation of the next human Respond; never taps')
    watch.add_argument('doc'); watch.add_argument('page'); watch.add_argument('label')
    watch.add_argument('--seconds', type=int, default=60)
    dog = sub.add_parser('draw-dog'); dog.add_argument('top', type=int, nargs='?', default=1440)
    replay = sub.add_parser('replay-handwriting'); replay.add_argument('source')
    replay.add_argument('x', type=int); replay.add_argument('y', type=int)
    art = sub.add_parser('draw-line-art', help='diagnostic only: trace a reviewed line-art image into checked blank space')
    art.add_argument('source'); art.add_argument('x', type=int); art.add_argument('y', type=int)
    art.add_argument('--width', type=int, default=300); art.add_argument('--height', type=int, default=180)
    args = parser.parse_args()
    if args.command == 'create-test-notebook':
        print(json.dumps(create_test_notebook(args.source, args.folder)))
    elif args.command == 'capture':
        capture(tablet).save(args.output)
    elif args.command == 'tap':
        tap(args.x, args.y)
    elif args.command == 'write-note':
        write_note(args.text, args.x, args.y)
    elif args.command == 'respond':
        observe_reply(args.doc, args.page, args.label)
    elif args.command == 'watch':
        watch_reply(args.doc, args.page, args.label, args.seconds)
    elif args.command == 'draw-dog':
        draw_test_dog(args.top)
    elif args.command == 'replay-handwriting':
        print(json.dumps(replay_handwriting(args.source, args.x, args.y)))
    elif args.command == 'draw-line-art':
        print(json.dumps(draw_line_art(args.source, args.x, args.y, args.width, args.height)))
