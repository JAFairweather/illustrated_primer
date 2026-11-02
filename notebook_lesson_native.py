"""Compile a complete lesson into the existing ordered native block protocol.

Pure preparation: no filesystem, tablet, provisioning or insertion. UUIDs are
allocated here, never accepted from the answering model. A caller must provision
these fresh immutable sources and verify all source bytes before insertion.
An optional equation block must also be registered as native media by the
adapter; it is not a client-ready image reference yet.
"""
import uuid
import copy
import json
import time
import re
import io
import zipfile
import hashlib

from notebook_drawing import compile_storyboard, HAND_STROKES
from notebook_lesson import parse_lesson
from notebook_stroke_asset import storyboard_assets, validate_native_ink_budget, HAND_REGIONS
from notebook_plotter_font import font_budget_fallback


def has_lesson(response):
    return bool(re.search(r'```\s*board-step\b', response))


@font_budget_fallback
def native_lesson_bundle(response):
    plan = parse_lesson(response)  # includes the final equation and all geometry
    return _bundle_from_compiled_lesson(plan)


@font_budget_fallback
def native_semantic_bundle(response, *, reveal=False, playback=False, pen_equations=False, hand=None, opening=None,
                           picture=None):
    """Prepare semantic replies directly; no coordinate-text round trip.

    Pure offline preparation, not live-route enablement. The same existing
    provisioning, page-change and native insertion gates are still required.
    """
    from notebook_semantic_reply import parse_semantic_reply
    reply = parse_semantic_reply(response)
    if reply['mode'] != 'lesson':
        return dict(mode=reply['mode'], plan=None, sources=[],
                    blocks=[dict(kind='text',text=reply['text'],styles=[])])
    if 'story' in reply:
        from notebook_story_native import native_story_bundle
        if type(reveal) is not bool or type(pen_equations) is not bool or reveal and playback:
            raise ValueError('explicit native story playback policy required')
        if pen_equations and not playback:
            raise ValueError('pen equations require native playback support')
        return native_story_bundle(reply['story'],reply['drafts'],playback=playback)
    options = dict(reveal=reveal, playback=playback, pen_equations=pen_equations, hand=hand, opening=opening)
    plan, report = reply['plan'], dict(used=False, reason=reply.get('picture_refused', 'no picture'))
    if picture and 'picture' in reply and 'captions' in reply['picture']:
        try:
            bundle, report = _composite_bundle(plan, reply['picture'], picture(reply['picture']), options)
        except Exception as error:  # the technical figure alone, as the model also wrote it
            report = dict(used=False, reason=f'{type(error).__name__}: {error}'[:300])
    elif picture and 'picture' in reply:
        try:
            plan, report = _pictured_plan(plan, picture(reply['picture']))
            bundle = _bundle_from_compiled_lesson(plan, **options)
        except Exception as error:  # any failure keeps the procedural drawing the model also wrote
            plan, report = reply['plan'], dict(used=False, reason=f'{type(error).__name__}: {error}'[:300])
    if not report['used']:
        bundle = _bundle_from_compiled_lesson(plan, **options)
    bundle['mode'] = 'lesson'
    bundle['picture'] = report
    return bundle


def _composite_bundle(plan, picture, frames, options):
    """The picture as the story's introduction, its own captions with it, then the steps' technical figure and the
    equation below: (bundle, report). The picture takes what the figure leaves of the drawing budget."""
    from notebook_raster_ink import BLOCKS
    from notebook_stroke_asset import validate_native_ink_budget
    technical = _bundle_from_compiled_lesson(plan, **dict(options, opening=None))
    inks = [b for b in technical['blocks'] if b.get('kind') == 'ink' and b.get('role') != 'hand']
    room = dict(points=12000-sum(b['point_count'] for b in inks)-500,
                blocks=BLOCKS-sum(b.get('role') != 'equation' for b in inks))  # the equation has its own place
    if room['blocks'] < 1 or room['points'] < 1500:
        raise ValueError(f'no room for a picture beside the figure: {room}')
    labels, scenes = list(getattr(frames, 'labels', None) or []), getattr(frames, 'scenes', False)
    steps = getattr(frames, 'steps', None)
    captions, frames = list(picture['captions']), list(frames)[:len(picture['captions'])]
    if scenes:  # pictures of their own: those past the room left are not drawn, and their captions follow the last
        frames, labels = frames[:room['blocks']], labels[:room['blocks']]
        steps = (steps or list(range(len(frames))))[:len(frames)]
    elif len(frames) > room['blocks']:
        # Each frame holds all the ink before it: keep the first ones and the finished picture, and the captions of
        # the frames left out go with the last.
        keep = room['blocks']-1
        frames, captions = frames[:keep]+frames[-1:], captions[:keep]+[' '.join(captions[keep:])]
        labels = labels[:keep]+[sum(labels[keep:], [])]
    story = dict(plan, stages=[dict(id=f'story-{i+1}', title=c[:160], text=c) for i, c in enumerate(captions)])
    pictured, report = _pictured_plan(story, frames, labels=labels, scenes=scenes, steps=steps, total=room['points'],
                                      blocks=room['blocks'])
    bundle = _bundle_from_compiled_lesson(plan, intro=pictured, **options)
    validate_native_ink_budget(bundle['blocks'])
    return bundle, dict(report, composite=True)


PICTURE_REMOVED = .05  # share of earlier ink an edit may lose; pen ink cannot be erased


def _pictured_plan(plan, frames, labels=None, scenes=None, steps=None, **room):
    """plan with its drawing replaced by the image model's frames, one stage per step, captions kept. Fewer frames
    than steps (an edit the model never drew) keep every caption: the steps past the last frame join its text. With
    scenes, each frame is a picture of its own, drawn below its step's caption, and a step without one (steps, the
    step of each frame) is written after the picture above it."""
    from notebook_raster_ink import raster_plan
    stages = plan['stages']
    labels = labels if labels is not None else getattr(frames, 'labels', None)  # [(name, box)] per frame
    scenes = scenes if scenes is not None else getattr(frames, 'scenes', False)
    if not 1 <= len(frames) <= len(stages):
        raise ValueError(f'{len(frames)} frames for {len(stages)} steps')
    if scenes:
        return _scened_plan(plan, frames, labels, steps if steps is not None else getattr(frames, 'steps', None), room)
    if len(frames) < len(stages):
        last = len(frames)-1
        stages = stages[:last]+[dict(stages[last], text=' '.join(s['text'] for s in stages[last:]))]
    raster, stats = raster_plan(frames, [s['text'] for s in stages], labels=labels, scenes=scenes, **room)
    if {r['frame'] for r in raster['stages']} != set(range(len(stages))):
        raise ValueError('a picture step added no ink')
    redrawn = next((r['stage'] for r in stats if r['removed'] > PICTURE_REMOVED), None)
    if redrawn is not None:
        # An edit that redrew the picture (IRIS reply, 2026-10-30: 0.115 lost) ends it: the frames before it are kept.
        pictured, report = _pictured_plan(plan, frames[:redrawn], labels=(labels or [])[:redrawn], scenes=scenes, **room)
        return pictured, dict(report, redrawn=redrawn)
    pictured = dict(plan, scene=raster['scene'], width=raster['width'], height=raster['height'],
                    max_step=raster['max_step'], velocity=raster['velocity'],
                    stages=[dict(stages[r['frame']], id=r['id'], paths=r['paths'], annotations=[], continued=r['continued'],
                                 **({'scene': r['scene']} if 'scene' in r else {}))
                            for r in raster['stages']])
    return pictured, dict(used=True, stages=stats, **({'frames': f'{len(frames)} of {len(plan["stages"])}'} if len(frames) < len(plan['stages']) else {}))


def _scened_plan(plan, frames, labels, steps, room):
    """_pictured_plan's plan with each frame a picture of its own under its step's caption; the captions of steps
    that draw none follow, unpictured, in order."""
    from notebook_raster_ink import raster_plan
    stages = plan['stages']
    owners = list(steps if steps is not None else range(len(frames)))[:len(frames)]
    if len(owners) != len(frames) or owners[0] != 0 or owners != sorted(set(owners)) or owners[-1] >= len(stages):
        raise ValueError(f'picture steps {owners} do not fit {len(stages)} steps')
    after = [[s['text'] for s in stages[o+1:end]] for o, end in zip(owners, owners[1:]+[len(stages)])]
    raster, stats = raster_plan(frames, [stages[o]['text'] for o in owners], labels=labels, scenes=True, **room)
    if {r['frame'] for r in raster['stages']} != set(range(len(frames))):
        raise ValueError('a picture step added no ink')
    last = {r['frame']: i for i, r in enumerate(raster['stages'])}
    pictured = dict(plan, scene=raster['stages'][0]['scene'], width=raster['width'], height=raster['height'],
                    max_step=raster['max_step'], velocity=raster['velocity'],
                    stages=[dict(stages[owners[r['frame']]], id=r['id'], paths=r['paths'], annotations=[],
                                 continued=r['continued'], scene=r['scene'],
                                 **({'after': after[r['frame']]} if last[r['frame']] == i and after[r['frame']] else {}))
                            for i, r in enumerate(raster['stages'])])
    return pictured, dict(used=True, stages=stats, scenes=True, pictures=f'{len(frames)} for {len(stages)} steps')


def _bundle_from_compiled_lesson(plan, *, reveal=False, playback=False, pen_equations=False, hand=None, opening=None,
                                 intro=None):
    """Internal common path; callers must validate the complete lesson first. intro, a pictured plan, is drawn first
    with its own captions, and plan's steps follow it."""
    if type(reveal) is not bool or type(playback) is not bool or reveal and playback:
        raise ValueError('explicit native reveal policy required')
    if type(pen_equations) is not bool or pen_equations and not playback:
        raise ValueError('pen equations require native playback support')
    source_doc = str(uuid.uuid4())
    steps, tail, tail_sources = [], [], []
    for part in ([intro] if intro else [])+[plan]:
        steps += _ink_steps(part, source_doc, reveal, playback)
    if plan.get('equation'):
        if pen_equations:
            from notebook_equation_ink import equation_plan
            from notebook_ink_playback import playback_assets
            math_plan=equation_plan(plan['equation'])
            math_program=compile_storyboard(math_plan)
            asset=playback_assets(math_plan)[0]
            page=str(uuid.uuid4())
            tail_sources.append(dict(source_doc=source_doc,source_page=page,data=asset['data']))
            tail.append(dict(kind='ink',role='equation',source_doc=source_doc,source_page=page,
                               sha256=asset['sha256'],stroke_count=asset['stroke_count'],point_count=asset['point_count'],
                               bounds=asset['bounds'],labels='ink-labels',scene=math_plan['scene'],stage='equation',
                               digest=math_program['digest'],width=600,height=200,stage_index=0,stage_count=1,
                               playback=asset['playback']))
        else:
            tail.append(dict(kind='equation', source=plan['equation']))
    # The opening ("James, once upon a time...") and every caption and the takeaway in the operator's chosen
    # hand when they fit, else the opening and takeaway, else the opening, else all typed: words a hand cannot write
    # never fail the reply.
    texts = [text for text, _, _ in steps] + [plan['takeaway']]
    written = ([_hand_blocks(text, hand, source_doc, place) for place, text in enumerate(texts)]
               if hand is not None and playback else [])
    opened = _hand_blocks(opening, hand, source_doc, len(texts)) if written and opening else None
    typed = [None]*len(texts)
    choices = (([(opened, written)] if all(written) else []) + ([(opened, typed[:-1]+written[-1:])] if written[-1] else [])
               if written else []) + ([(opened, typed)] if opened else []) + [(None, typed)]
    for start, words in choices:
        blocks, sources = _lesson_blocks(steps, tail, tail_sources, start, words, plan['takeaway'], playback)
        try:
            validate_native_ink_budget(blocks)  # Includes math BEFORE any provision/import.
            break
        except ValueError:
            if start is None and words is typed:
                raise
    return dict(plan=plan, blocks=blocks, sources=sources)


def _ink_steps(plan, source_doc, reveal, playback):
    """(caption, [ink blocks], [sources]) for each of plan's steps; a continued stage joins the step before it."""
    program = compile_storyboard(plan)
    if playback:
        from notebook_ink_playback import playback_assets
        assets = playback_assets(plan, **({'velocity': plan['velocity']} if 'velocity' in plan else {}))
    elif reveal:
        from notebook_ink_reveal import reveal_assets
        assets = reveal_assets(plan)
    else:
        assets = storyboard_assets(plan)
    # A stage with a scene of its own is a picture of its own, placed by the tablet below the text before it; its
    # stages count from 0 within it.
    scenes = [stage.get('scene', plan['scene']) for stage in plan['stages']]
    steps = []
    for index, (stage, asset) in enumerate(zip(plan['stages'], assets)):
        page = str(uuid.uuid4())
        source = dict(source_doc=source_doc, source_page=page, data=asset['data'])
        block = dict(kind='ink', source_doc=source_doc, source_page=page,
                           sha256=asset['sha256'], stroke_count=asset['stroke_count'],
                           point_count=asset['point_count'], bounds=asset['bounds'],
                           labels='ink-labels', scene=scenes[index], stage=stage['id'],
                           digest=program['digest'], width=plan['width'], height=plan['height'],
                           stage_index=scenes[:index].count(scenes[index]), stage_count=scenes.count(scenes[index]))
        if reveal:
            block['reveal'] = asset['reveal']
        if playback:
            block['playback'] = asset['playback']
        if stage.get('continued'):  # more of the same step's picture: drawn straight after, with no caption of its own
            steps[-1][1].append(block)
            steps[-1][2].append(source)
        else:
            steps.append((stage['text'], [block], [source]))
        steps += [(text, [], []) for text in stage.get('after', [])]  # steps sharing this picture, written below it
    return steps


def _lesson_blocks(steps, tail, tail_sources, opened, words, takeaway, playback):
    # Playback narrates each addition before drawing it. Keep the first block label-only so the first caption also
    # uses the native typewriter path; one picture: introductory caption above, later captions below. Legacy/static
    # clients retain their established ordering, caption after its picture.
    blocks = [dict(kind='text', text='', styles=[])] if playback else []
    sources = []
    if opened:
        blocks += [b for b, _ in opened]
        sources += [s for _, s in opened]
    for (text, block, source), written in zip(steps, words):
        caption = [b for b, _ in written] if written else [dict(kind='text', text=text, styles=[])]
        sources += [s for _, s in written or []] + source
        blocks += caption + block if playback else block + caption
    blocks += tail
    sources += tail_sources
    if words[-1]:
        blocks += [b for b, _ in words[-1]]
        sources += [s for _, s in words[-1]]
    else:
        blocks.append(dict(kind='text', text='Takeaway: '+takeaway, styles=[]))
    return blocks, sources


def _hand_blocks(text, hand, source_doc, place):
    """(block, source) pairs writing text in the hand, or None when the hand cannot write it."""
    from notebook_hand_ink import hand_plans, VELOCITY
    from notebook_ink_playback import playback_assets
    try:
        plans = hand_plans(text, hand, place=place)
    except ValueError:  # includes NativePenBudgetError
        return None
    written = []
    for hand_plan in plans:
        program = compile_storyboard(hand_plan)
        asset = playback_assets(hand_plan, velocity=VELOCITY)[0]
        page = str(uuid.uuid4())
        written.append((dict(kind='ink', role='hand', source_doc=source_doc, source_page=page,
                             sha256=asset['sha256'], stroke_count=asset['stroke_count'],
                             point_count=asset['point_count'], bounds=asset['bounds'], labels='ink-labels',
                             scene=hand_plan['scene'], stage='hand', digest=program['digest'],
                             width=hand_plan['width'], height=hand_plan['height'], stage_index=0, stage_count=1,
                             playback=asset['playback']),
                        dict(source_doc=source_doc, source_page=page, data=asset['data'])))
    return written


def prepare_native_lesson(response, store):
    """Resolve equations before provisioning; return only supported client blocks."""
    bundle = native_lesson_bundle(response)
    return _resolve_equations(bundle,store)


def prepare_semantic_reply(response, store, *, reveal=False, playback=False, pen_equations=False, hand=None,
                           opening=None, picture=None):
    """Offline semantic preparation using the existing registered-media path.

    picture, if given, turns a reply's picture into its frames (PNG bytes, one per step), or raises.
    """
    return _resolve_equations(native_semantic_bundle(response, reveal=reveal, playback=playback, pen_equations=pen_equations,
                                                     hand=hand, opening=opening, picture=picture),store)


def _resolve_equations(bundle, store):
    for block in bundle['blocks']:
        if block['kind'] == 'equation':
            asset = store.equation(block['source'])['asset']
            block.clear()
            block.update(kind='media', asset=asset)
    return bundle


def source_document_files(bundle, template, parent):
    """Fresh source document payloads using the proven native content template.

    No foreground page bytes are copied. Existing page IDs, page-specific tags
    and viewport state are replaced. Publishing the metadata LAST lets the
    native library discover only the fully populated immutable document.
    """
    if str(uuid.UUID(parent)) != parent:
        raise ValueError('canonical source folder identity required')
    sources = bundle['sources']
    inks=validate_native_ink_budget(bundle['blocks'])
    story = bundle.get('mode') == 'story'
    if story != all('story' in b for b in inks):
        raise ValueError('native bundle/story contract mismatch')
    minimum = 1 if story or bundle['plan'].get('semantic', {}).get('family') == 'drawing' else 3
    maximum = 12 if story else 7 + sum(b.get('role') == 'hand' for b in inks)  # six steps, an equation, the words
    if not minimum <= len(sources) <= maximum or (not story and len(inks) != len(sources)):
        raise ValueError('bounded lesson source pages required')
    doc = sources[0]['source_doc']
    pages = [source['source_page'] for source in sources]
    if (str(uuid.UUID(doc)) != doc or len(set(pages)) != len(pages) or
            any(source['source_doc'] != doc or str(uuid.UUID(source['source_page'])) != source['source_page'] for source in sources)):
        raise ValueError('distinct canonical source identities required')
    if story and (any(b['source_doc'] != doc for b in inks) or
            list(dict.fromkeys(b['source_page'] for b in inks)) != pages):
        raise ValueError('native story sources must follow first-use order exactly')
    if not isinstance(template, dict) or not isinstance(template.get('cPages'), dict):
        raise ValueError('native source content template unavailable')
    content = copy.deepcopy(template)
    # Page-specific fields cannot point back into the user's notebook. Other
    # native document settings follow the existing source provisioning path.
    for key in ('pages','redirectionPageMap','pageTags','tags','pageMetadatas'):
        content.pop(key, None)
    content['pageCount'] = len(pages)
    content['cPages'] = {
        'lastOpened': {'timestamp':'1:1','value':pages[0]},
        'pages': [{'id':page, 'idx':{'timestamp':'1:1','value':'b'+chr(97+i)},
                   'template':{'timestamp':'1:1','value':'Blank'}} for i,page in enumerate(pages)]}
    stamp = str(int(time.time()*1000))
    metadata = dict(createdTime=stamp,lastModified=stamp,lastOpenedPage=0,new=True,
                    parent=parent,pinned=False,source='',type='DocumentType',
                    visibleName='Agent lesson source '+doc[:8])
    files = [(doc+'/'+source['source_page']+'.rm',source['data']) for source in sources]
    files.extend([(doc+'.content',json.dumps(content).encode()),
                  (doc+'.metadata',json.dumps(metadata).encode())])
    return doc, files


def provision_lesson_sources(bundle, template, parent, tablet, guard):
    """Publish only fresh source pages, never the destination notebook.

    Each file is byte-verified before the next; metadata is published last so
    native discovery cannot see a partial source. A guard failure leaves only
    unused source files, not partial ink in the foreground notebook. No cleanup
    or overwriting is attempted. The caller has already validated the lesson.
    """
    doc, files = source_document_files(bundle, template, parent)
    base = '/home/root/.local/share/remarkable/xochitl/'
    guard()
    # tablet() historically ignores non-SSH exit codes. Require a success
    # marker as well as byte verification instead of trusting empty stdout.
    command = (f'test ! -e {base}{doc}.content && test ! -e {base}{doc}.metadata '
               f'&& mkdir {base}{doc} && printf source-created')
    if tablet(command) != b'source-created':
        raise ValueError('fresh native lesson source could not be reserved')
    for name, data in files:
        if not 0 < len(data) < 262144:
            raise ValueError('native lesson source exceeds transfer budget')
        guard()
        target = base+name
        command = (f'test ! -e {target} && (set -C; cat > {target}.new) '
                   f'&& mv {target}.new {target} && printf source-published')
        if tablet(command, data) != b'source-published':
            raise ValueError('native lesson source publish failed; reply remains held')
        if tablet(f'dd if={target} bs=262144 count=1 2>/dev/null') != data:
            raise ValueError('native lesson source readback mismatch; reply remains held')
    guard()
    return doc


def lesson_source_archive(bundle, template, parent):
    """Build a fresh native-import package; never publish library metadata ourselves.

    This is preparation only. Native importer completion, the resulting document
    identity and byte-for-byte page readback must be proven before any paste.
    Import may remap the document UUID; do not assume entryForId(original) works.
    """
    doc, files = source_document_files(bundle, template, parent)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            if not 0 < len(data) < 262144:
                raise ValueError('native import member exceeds transfer budget')
            if name.endswith('.metadata'):
                metadata = json.loads(data)
                metadata['visibleName'] = 'Agent lesson source '+doc
                data = json.dumps(metadata).encode()
            archive.writestr(name, data)
        archive.writestr(doc+'.pagedata', 'Blank\n'*len(bundle['sources']))
    data = output.getvalue()
    if len(data) > 2_000_000:
        raise ValueError('native import archive exceeds transfer budget')
    return doc, data


def inspect_source_archive(data, doc, parent, page, expected_strokes, *, story=False):
    """Read-only bounded preflight for our disposable native-import experiment."""
    from ink import strokes
    if type(story) is not bool:
        raise ValueError('explicit story import policy required')
    maximum = 12 if story else 7 + HAND_REGIONS  # six steps, an equation and the handwritten words
    for value in (doc, parent, page):
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError('canonical import identity required')
    if not isinstance(data, bytes) or not 0 < len(data) <= 2_000_000:
        raise ValueError('bounded source archive required')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        # Archive integrity is independent of lesson pedagogy: the validated
        # drawing family may contain one source plus three metadata members.
        if (not 4 <= len(entries) <= maximum+3 or len({e.filename for e in entries}) != len(entries)
                or any(not 0 < e.file_size < 262144 for e in entries)
                or sum(e.file_size for e in entries) > 2_000_000):
            raise ValueError('invalid source archive members or size')
        content = json.loads(archive.read(doc+'.content'))
        metadata = json.loads(archive.read(doc+'.metadata'))
        pages = [p['id'] for p in content['cPages']['pages']]
        if not 1 <= len(pages) <= maximum or len(set(pages)) != len(pages) or page not in pages:
            raise ValueError('invalid import pages')
        for identity in pages:
            if str(uuid.UUID(identity)) != identity:
                raise ValueError('invalid import page identity')
        expected = {doc+'.metadata', doc+'.content', doc+'.pagedata'} | {doc+'/'+p+'.rm' for p in pages}
        if set(archive.namelist()) != expected:
            raise ValueError('foreign path in source archive')
        if (metadata.get('type') != 'DocumentType' or metadata.get('parent') != parent
                or metadata.get('visibleName') != 'Agent lesson source '+doc
                or content.get('fileType') != 'notebook'):
            raise ValueError('invalid import metadata')
        result = None
        for identity in pages:
            raw = archive.read(doc+'/'+identity+'.rm')
            if not raw.startswith(b'reMarkable .lines file, version=6') or not 1 <= len(strokes(raw)) <= HAND_STROKES:
                raise ValueError('invalid import ink')
            if identity == page:
                if len(strokes(raw)) != expected_strokes:
                    raise ValueError('import source count mismatch')
                result = hashlib.sha256(raw).hexdigest()
        return result


def remap_imported_lesson(bundle, imported_doc, parent, destination_doc, tablet, *, validate_source=None):
    """Resolve native import UUIDs only after every saved page matches our ink.

    No device writes, and no mutation of the held bundle on a partial failure.
    The native importer owns registration and ordering; model text owns neither.
    """
    if (not isinstance(imported_doc, str) or str(uuid.UUID(imported_doc)) != imported_doc
            or imported_doc == destination_doc):
        raise ValueError('distinct canonical imported source required')
    base = '/home/root/.local/share/remarkable/xochitl/'
    original_doc = bundle['sources'][0]['source_doc']
    metadata = json.loads(tablet(f'dd if={base}{imported_doc}.metadata bs=65536 count=1 2>/dev/null'))
    if (metadata.get('type') != 'DocumentType' or metadata.get('parent') != parent
            or metadata.get('visibleName') != 'Agent lesson source '+original_doc):
        raise ValueError('imported lesson identity does not match prepared source')
    content = json.loads(tablet(f'dd if={base}{imported_doc}.content bs=262144 count=1 2>/dev/null'))
    pages = [p['id'] for p in content['cPages']['pages']]
    if (len(pages) != len(bundle['sources']) or len(set(pages)) != len(pages)
            or any(not isinstance(p, str) or str(uuid.UUID(p)) != p for p in pages)):
        raise ValueError('imported lesson page count or identity mismatch')
    result = copy.deepcopy(bundle)
    mapping = dict(zip((s['source_page'] for s in bundle['sources']), pages))
    for item in result['sources'] + [b for b in result['blocks'] if b['kind'] == 'ink']:
        item['source_doc'] = imported_doc
        item['source_page'] = mapping[item['source_page']]
    blocks = [b for b in result['blocks'] if b['kind'] == 'ink']
    story = result.get('mode') == 'story'
    if story:
        validate_native_ink_budget(blocks)
    if (not story and len(blocks) != len(pages)) or (
            story and list(dict.fromkeys(b['source_page'] for b in blocks)) != pages):
        raise ValueError('imported lesson source/block count mismatch')
    for page_index, (page, source) in enumerate(zip(pages, result['sources'])):
        selected = [b for b in blocks if b['source_page'] == page] if story else [blocks[page_index]]
        if any((block['source_doc'], block['source_page']) != (imported_doc, page) for block in selected):
            raise ValueError('imported lesson source/block order mismatch')
        data = tablet(f'dd if={base}{imported_doc}/{page}.rm bs=262144 count=1 2>/dev/null')
        if data != source['data']:
            raise ValueError('imported lesson page bytes or order changed')
        # Validate the actual freshly read bytes, not a second SSH read of the
        # same source. The caller still rereads each stage at its native claim.
        if validate_source is not None:
            for block in selected:
                validate_source(block, data)
    return result
