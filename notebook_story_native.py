"""Complete typed stories -> existing native text/ink blocks and source assets.

Pure preparation, not a model call or a live rollout. Consecutive extensions
share a picture. Returning to an older snapshot creates a new picture with
exact inherited ink, never an edit of the already-extended original picture.
One immutable source page per original addition can be cloned into more than
one picture. Every actual clone still consumes the ordinary point budget.
"""
from copy import deepcopy
import hashlib
import json
import uuid

from notebook_drawing import compile_storyboard
from notebook_panel_shapes import compile_panel_shapes
from notebook_story_plan import validate_story
from notebook_stroke_asset import storyboard_assets, validate_native_ink_budget


def native_story_bundle(story, drafts, *, playback=True):
    if type(playback) is not bool:
        raise ValueError('explicit story playback policy required')
    story = validate_story(story)
    compiled = compile_panel_shapes(story, drafts)  # ALL panels before assets.
    identity = hashlib.sha256(json.dumps(
        [story, drafts], sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode()).hexdigest()
    panels = story['panels']
    # A run ends when the next panel does not extend the currently drawn tip.
    # Its final plan is the exact layout already frozen by the whole-story
    # compiler; the adapter never performs its own fitting or label placement.
    runs = []
    for index, panel in enumerate(panels):
        if index == 0 or panel['base'] != panels[index-1]['id']:
            runs.append([index])
        else:
            runs[-1].append(index)
    plans, run_for_panel = [], {}
    for run_index, indices in enumerate(runs):
        plan = deepcopy(compiled['panels'][panels[indices[-1]]['id']]['plan'])
        plan['scene'] = 'lesson-story-'+identity[:24]+'-'+str(run_index)
        program = compile_storyboard(plan)
        plans.append(plan)
        for index in indices:
            run_for_panel[index] = (run_index, indices[0], plan, program)

    source_doc = str(uuid.uuid4())
    assets, sources = {}, []
    for panel in panels:
        panel_id = panel['id']
        plan = deepcopy(compiled['panels'][panel_id]['plan'])
        plan['stages'] = [plan['stages'][-1]]
        if playback:
            from notebook_ink_playback import playback_assets
            asset = playback_assets(plan)[0]
        else:
            asset = storyboard_assets(plan)[0]
        page = str(uuid.uuid4())
        sources.append(dict(source_doc=source_doc, source_page=page, data=asset['data']))
        assets[panel_id] = (page, asset)

    blocks = [dict(kind='text', text='', styles=[])]
    for index, panel in enumerate(panels):
        _, first_index, plan, program = run_for_panel[index]
        snapshot = compiled['panels'][panel['id']]['plan']['stages']
        additions = snapshot if index == first_index else snapshot[-1:]
        stage_indices = {s['id']: i for i,s in enumerate(plan['stages'])}
        blocks.append(dict(kind='text', text=panel['caption'], styles=[]))
        for part, stage in enumerate(additions):
            page, asset = assets[stage['id']]
            block = dict(kind='ink',source_doc=source_doc,source_page=page,
                sha256=asset['sha256'],stroke_count=asset['stroke_count'],
                point_count=asset['point_count'],bounds=deepcopy(asset['bounds']),
                labels='ink-labels',scene=plan['scene'],stage=stage['id'],
                digest=program['digest'],width=plan['width'],height=plan['height'],
                stage_index=stage_indices[stage['id']],stage_count=len(plan['stages']),
                story=dict(version=1,id=identity,panels=len(panels),panel=index,
                           part=part,parts=len(additions)))
            if playback:
                block['playback'] = deepcopy(asset['playback'])
            blocks.append(block)
    equation = compiled.get('equation_plan')
    if equation is not None:
        # Already compiled with ALL diagrams, before any asset encoding. Math
        # occupies a distinct final region and never alters inherited ink.
        if playback:
            from notebook_ink_playback import playback_assets
            asset = playback_assets(equation)[0]
        else:
            asset = storyboard_assets(equation)[0]
        page = str(uuid.uuid4())
        sources.append(dict(source_doc=source_doc, source_page=page, data=asset['data']))
        program = compile_storyboard(equation)
        block = dict(kind='ink', role='equation', source_doc=source_doc, source_page=page,
            sha256=asset['sha256'], stroke_count=asset['stroke_count'],
            point_count=asset['point_count'], bounds=deepcopy(asset['bounds']),
            labels='ink-labels', scene=equation['scene'], stage='equation',
            digest=program['digest'], width=equation['width'], height=equation['height'],
            stage_index=0, stage_count=1)
        if playback:
            block['playback'] = deepcopy(asset['playback'])
        blocks.append(block)
        plans.append(deepcopy(equation))
    blocks.append(dict(kind='text',text='Takeaway: '+story['takeaway'],styles=[]))
    inks = validate_native_ink_budget(blocks)
    points = sum(b['point_count'] for b in inks)
    if points > compiled['snapshot_points']:
        raise ValueError('native story contains ink outside validated snapshots')
    return dict(mode='story',story=story,plans=plans,blocks=blocks,sources=sources,
                snapshot_points=compiled['snapshot_points'],delivery_points=points,
                tablet_proven=False)
