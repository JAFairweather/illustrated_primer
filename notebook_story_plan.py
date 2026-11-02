"""Geometry-free story contract, before panel generation or native compilation.

This is not a drawable lesson. A valid story can still be false, unhelpful,
unsupported by the renderer, or too expensive to draw. No model/device I/O.
"""
from copy import deepcopy
import hashlib
import html
import json
import re

from notebook_lesson import _constant, _pairs, _text
from notebook_contract_feedback import ContractError, exact_fields as _fields


MAX_BYTES = 24000
MAX_ACTS = 6
MAX_PANELS = 12
MAX_CAPTION_CHARACTERS = 180
TEMPLATES = ('explain_result', 'explain_concept', 'solve', 'compare')
# Intent categories, NOT a claim that every requested visual is implemented.
VISUAL_KINDS = ('objects', 'number_line', 'graph', 'relationship', 'comparison',
                'geometric', 'equation', 'checklist')


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', value):
        raise ValueError('short lowercase story ID required')
    return value


def _bounded_copy(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > MAX_BYTES:
            raise ValueError('story exceeds byte budget')
        return json.loads(encoded, object_pairs_hook=_pairs, parse_constant=_constant)
    except (TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError('bounded JSON story required') from exc


def parse_story(raw):
    """Accept exactly one complete story object, never fences or partial JSON."""
    try:
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_BYTES:
            raise ValueError('bounded UTF-8 story required')
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('bounded UTF-8 story required') from exc
    return validate_story(value)


def validate_story(value):
    """Validate narrative structure without repairing or judging its content.

    Acts and panels are in reading order. A base is an exact earlier panel
    snapshot, possibly from another act, never the current mutable canvas.
    Numeric geometry, raw shapes and layout instructions have no schema slot.
    """
    story = _bounded_copy(value)
    _fields(story, {'v', 'mode', 'audience', 'template', 'question', 'acts', 'panels', 'takeaway'},
            optional={'equation'})
    if 'equation' in story:
        story['equation'] = _text(story['equation'], 400, equation=True)
    if type(story['v']) is not int or story['v'] != 1 or story['mode'] != 'story':
        raise ValueError('version 1 story required')
    if story['template'] not in TEMPLATES:
        raise ValueError('unknown story template')
    for name, limit in [('audience', 120), ('question', 600), ('takeaway', 600)]:
        _text(story[name], limit)
    acts, panels = story['acts'], story['panels']
    if not isinstance(acts, list) or not 1 <= len(acts) <= MAX_ACTS:
        raise ValueError('use 1..6 story acts')
    if not isinstance(panels, list) or not 1 <= len(panels) <= MAX_PANELS:
        raise ValueError('use 1..12 story panels')
    act_order = {}
    for act_index, act in enumerate(acts):
        _fields(act, {'id', 'beat'}, path=f'/acts/{act_index}')
        identity = _id(act['id'])
        if identity in act_order:
            raise ValueError('duplicate act ID')
        _text(act['beat'], 360)
        act_order[identity] = len(act_order)
    seen, used_acts, last_act = {}, set(), -1
    for panel_index, panel in enumerate(panels):
        path = f'/panels/{panel_index}'
        _fields(panel, {'id', 'act', 'title', 'question', 'new_idea', 'visual_kind', 'caption', 'base'}, path=path)
        identity, act_id = _id(panel['id']), _id(panel['act'])
        if identity in seen:
            raise ValueError('duplicate panel ID')
        if act_id not in act_order or act_order[act_id] < last_act:
            raise ValueError('panels must follow declared act order')
        # Descriptive narrative metadata is not a renderer opcode. Capability
        # is enforced by typed shapes, never by spelling a category label.
        _text(panel['visual_kind'], 48)
        for name, limit in [('title', 100), ('question', 280), ('new_idea', 360)]:
            _text(panel[name], limit)
        # Captions are native prose, not pen labels. Keep the existing text
        # budget; whitespace-token counts neither bound layout nor measure
        # whether a mathematical sentence is clear. Never truncate the text.
        caption = panel['caption']
        if isinstance(caption, str) and len(caption) > MAX_CAPTION_CHARACTERS:
            raise ContractError('panel caption exceeds character budget',
                                code='caption_characters', path=path+'/caption',
                                limit=MAX_CAPTION_CHARACTERS, observed=len(caption))
        _text(caption, MAX_CAPTION_CHARACTERS)
        base = panel['base']
        if base is not None:
            _id(base)
            if base not in seen:
                raise ValueError('base must name an earlier panel; no forward or cyclic references')
            # visual_kind describes the teaching intent, not a canvas type.
            # A graph can become a comparison without changing its inherited
            # axes or ink. The shape compiler enforces exact immutable reuse.
        seen[identity] = panel
        used_acts.add(act_id)
        last_act = act_order[act_id]
    if used_acts != set(act_order):
        raise ValueError('every act needs at least one panel')
    return story


def panel_packet(story, panel_id):
    """Small narrative context for ONE later shape-generation call.

    Includes the chosen panel, its act/ancestry and a compact plan of the
    SAME picture's development, not unrelated pictures or conversation.
    The root needs this lookahead to choose a frame that can fit later steps.
    Base IDs are narrative references; the later
    compiler must supply validated immutable base shapes. This packet alone
    cannot resolve geometry or authorize drawing.
    """
    story = validate_story(story)
    _id(panel_id)
    panels = {p['id']: p for p in story['panels']}
    if panel_id not in panels:
        raise ValueError('unknown story panel')
    panel = panels[panel_id]
    chain, base = [], panel['base']
    while base is not None:
        chain.append(panels[base])
        base = panels[base]['base']
    def root_id(candidate):
        while candidate['base'] is not None:
            candidate = panels[candidate['base']]
        return candidate['id']
    picture_root = root_id(panel)
    picture_plan = [dict(id=p['id'], base=p['base'], new_idea=p['new_idea'])
                    for p in story['panels'] if root_id(p) == picture_root]
    canonical = json.dumps(story, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return deepcopy(dict(
        v=1, kind='panel-narrative-context',
        story_sha256=hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
        audience=story['audience'], question=story['question'], template=story['template'],
        takeaway=story['takeaway'], act=next(a for a in story['acts'] if a['id']==panel['act']),
        panel=panel, base_chain=list(reversed(chain)), picture_plan=picture_plan,
        geometry_resolved=False, native_validated=False))


def outline_html(story):
    """An honest narrative review sheet, not a simulated drawing preview."""
    story = validate_story(story)
    esc = html.escape
    out = ['<!doctype html><html lang="en"><meta charset="utf-8">',
           '<title>Story outline — not a drawing preview</title>',
           '<style>body{max-width:1000px;margin:2rem auto;font:18px/1.5 sans-serif;padding:1rem}',
           '.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}',
           'article{border:1px solid #888;border-radius:8px;padding:1rem}h3{margin-top:0}',
           'small{color:#444}blockquote{margin:1rem 0;border-left:3px solid #555;padding-left:1rem}</style>',
           '<h1>'+esc(story['question'])+'</h1>',
           '<p>Audience: '+esc(story['audience'])+' · '+esc(story['template'])+'</p>',
           '<p><strong>Narrative outline only.</strong> No shapes, layout, native budgets, '
           'mathematical correctness or tablet behavior have been validated.</p>']
    for act in story['acts']:
        out.extend(['<h2>'+esc(act['beat'])+'</h2>', '<section class="panels">'])
        for panel in story['panels']:
            if panel['act'] != act['id']:
                continue
            out.extend(['<article id="'+esc(panel['id'])+'"><h3>'+esc(panel['title'])+'</h3>',
                        '<p>'+esc(panel['question'])+'</p>',
                        '<p>New idea: '+esc(panel['new_idea'])+'</p>',
                        '<blockquote>'+esc(panel['caption'])+'</blockquote>',
                        '<small>'+esc(panel['visual_kind'])+' · '+
                        ('New picture' if panel['base'] is None else
                         'Reuse <a href="#'+esc(panel['base'])+'">'+esc(panel['base'])+'</a>')+
                        '</small></article>'])
        out.append('</section>')
    out.append('<h2>Takeaway</h2><p>'+esc(story['takeaway'])+'</p></html>')
    return '\n'.join(out)
