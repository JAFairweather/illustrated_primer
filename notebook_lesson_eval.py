#!/usr/bin/env python3
"""Prepare identical model packets and render their unedited first-pass lessons.

No model SDK, credentials, tablet or server I/O. Model runners supply raw JSON
answers; this tool exposes validation failures instead of fixing weak answers.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import time

from notebook_drawing import compile_storyboard, preview_svg
from notebook_lesson import LessonLayoutError, parse_lesson
from notebook_media import render_equation
from notebook_replies import notebook_prompt
from notebook_stroke_asset import storyboard_assets
from notebook_pen_budget import budget_feedback


QUESTIONS = [
    ('integral', 'Explain the definite integral of x squared from 0 to 1 using an area picture and compute it.'),
    ('gravity', 'Why does an apple dropped from rest fall farther in each equal time interval? Ignore air resistance.'),
    ('odd-squares', 'Show why the sum of the first n odd numbers equals n squared, not just a few numerical examples.'),
    ('compound-interest', 'Compare $100 growing at 10% per year with $100 gaining $10 per year over three years.'),
    ('transistor', 'Explain how an NPN transistor can switch a lamp in a simple low-side circuit, with a base resistor.'),
    ('blue-sky', 'Why is the daytime sky blue? Show sunlight, air scattering and the observer without implying air is blue paint.'),
    ('bayes', 'A condition affects 10 of 100 people. A test catches 8 of those 10 and falsely flags 9 of the other 90. Use a 2 by 2 count grid to explain the chance a positive person has the condition.'),
    ('fractions', 'Show visually why one half and two fourths represent the same amount.'),
    ('water-cycle', 'Explain how sunlight drives evaporation, condensation and precipitation in the water cycle.'),
    ('pythagoras', 'Use a right triangle with legs 3 and 4 and squares on its sides to explain why the hypotenuse is 5; distinguish this example from a general proof.'),
]


def preview_png(plan, through_stage):
    """Viewable OFFLINE lesson geometry, using the same paths as preview_svg.

    Labels are already plotter strokes. No substitute font, SVG execution,
    external renderer, device I/O, or claim of native screenshot equivalence.
    """
    from PIL import Image, ImageDraw
    program = compile_storyboard(plan)
    stages = [s['id'] for s in plan['stages']]
    if through_stage not in stages:
        raise ValueError('unknown preview stage')
    selected = set(stages[:stages.index(through_stage)+1])
    scale = 2
    image = Image.new('RGB', (program['width']*scale, program['height']*scale), 'white')
    draw = ImageDraw.Draw(image)
    for operation in program['operations']:
        if operation['stage'] not in selected:
            continue
        if operation['kind'] == 'annotation':
            raise ValueError('lesson PNG preview requires stroke labels, not font annotations')
        if operation['kind'] != 'stroke':
            continue
        points = [(x*scale, y*scale) for x,y in operation['path']]
        draw.line(points, fill='black', width=2*scale, joint='curve')
        for x,y in (points[0], points[-1]):
            draw.ellipse((x-scale,y-scale,x+scale,y+scale), fill='black')
    return image.resize((program['width'],program['height']), Image.Resampling.LANCZOS)


def prepare(destination, *, semantic=False):
    packet = {'version':1, 'conditions':'Fixed text questions; no handwriting reader or tablet. Unedited first-pass model answers.',
              'questions':[]}
    if semantic:
        from notebook_semantic_prompt import semantic_reply_instructions
        packet['response_format']='semantic-v1'
        packet['conditions']+=' Semantic vocabulary is intentionally bounded; text fallbacks are not visual lesson passes.'
    for identity, question in QUESTIONS:
        prompt = (semantic_reply_instructions()+'\nCurrent question (text-only offline test):\n'+question
                  if semantic else notebook_prompt(question+' Give a 3–6 step board lesson.',
                  '(offline fixed question; no page image)', 'offline-eval-'+identity, ink_enabled=True))
        packet['questions'].append({'id':identity, 'question':question, 'prompt':prompt,
                                   'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'packet.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
    return packet


def _load(path, limit=1_000_000):
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError('evaluation file too large')
    return json.loads(data)


def check_draft(source, destination, *, semantic=False):
    """Author-side preview of one raw reply; never insert, repair or retry it.

    Unlike the fixed-packet evaluator this is explicitly an assisted drafting
    tool. Each invocation gets a new directory, preserving earlier attempts.
    The compiler and real asset encoder run, but no native assets are written.
    """
    from notebook_lesson import MAX_RESPONSE
    if type(semantic) is not bool:
        raise ValueError('explicit semantic draft policy required')
    if semantic:
        from notebook_semantic import MAX_BYTES
        limit = MAX_BYTES
    else:
        limit = MAX_RESPONSE
    with source.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('draft exceeds bounded UTF-8 input size')
    response = data.decode('utf-8')
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'draft.txt').write_bytes(data)
    result = dict(valid=False, compiler_valid=False, assisted_draft=True, tablet_proven=False,
                  response_format='semantic-v1' if semantic else 'board-step-v1', visual_lesson=False,
                  quality_review=None, quality_status='unreviewed',
                  source_sha256=hashlib.sha256(data).hexdigest(),
                  stages=[], diagnostic_only=False, preview_complete=False,
                  notice='Compiler success is not a correctness or teaching-quality verdict. '
                         'Inspect every cumulative preview and its caption before finalizing. '
                         'The stages list may be partial unless preview_complete is true.')
    plan = None
    phase = 'parse'
    try:
        if semantic:
            from notebook_lesson_native import native_semantic_bundle
            phase = 'compile-and-encode'
            bundle = native_semantic_bundle(response)
            if bundle['mode']=='story':
                raise ValueError('multi-panel stories require the story-panel evaluator')
            plan = bundle['plan']
            result['mode'] = bundle['mode']
            assets = [block for block in bundle['blocks'] if block['kind']=='ink']
            if plan is None:
                result.update(valid=True,compiler_valid=True,preview_complete=True,
                              text=bundle['blocks'][0]['text'])
        else:
            plan = parse_lesson(response)
            phase = 'encode'
            # Validate the same v6 encoder as delivery without writing .rm files.
            assets = storyboard_assets(plan)
        if plan is not None:
            result.update(valid=True, compiler_valid=True, points=sum(a['point_count'] for a in assets),
                          estimated_pen_seconds=sum(s['estimated_pen_seconds'] for s in plan['stages']))
    except LessonLayoutError as exc:
        plan = exc.diagnostic_plan
        result.update(error=str(exc), failure_stage=phase, diagnostic_only=True,
                      layout_collisions=exc.collisions)
    except Exception as exc:
        # An encoder failure does not erase a bounded, already parsed picture.
        # Unexpected failures are explicit tool errors, not compiler acceptance.
        result.update(error=str(exc), error_type=type(exc).__name__, failure_stage=phase,
                      diagnostic_only=plan is not None)
        feedback = budget_feedback(exc)
        if feedback is not None:
            result['resource_feedback'] = feedback
    if plan is not None:
        try:
            result['takeaway'] = plan['takeaway']
            for stage in plan['stages']:
                name = stage['id'] + ('-rejected' if result['diagnostic_only'] else '')
                (destination/(name+'.svg')).write_text(preview_svg(plan,stage['id']))
                preview_png(plan,stage['id']).save(destination/(name+'.png'))
                result['stages'].append(dict(svg=name+'.svg', png=name+'.png', caption=stage['text']))
            if plan.get('equation'):
                render_equation(plan['equation']).save(destination/'equation.png')
                result['equation'] = 'equation.png'
                # The bounded math renderer follows TeX's one-atom script
                # rule. Flag ambiguous shorthand without silently regrouping
                # a mathematically meaningful expression such as x^2y.
                result['equation_notes'] = list(dict.fromkeys(
                    f'Heuristic: {match[0]!r} scripts only its first character; use '
                    f'{match[1]}{{{match[2]}}} if all characters belong in the script, '
                    f'or {match[1]}{{{match[2][0]}}}{match[2][1:]} to explicitly keep the rest outside. '
                    'Inspect equation.png.'
                    for match in re.finditer(r'([_^])\s*([A-Za-z0-9]{2,})',plan['equation'])))
            result['preview_complete'] = True
        except Exception as exc:
            # diagnostic_only describes rejected geometry, not a renderer error.
            result.update(valid=False, preview_error=str(exc),
                          preview_error_type=type(exc).__name__)
    result['visual_lesson'] = bool(result['valid'] and plan is not None and result['preview_complete'])
    (destination/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def render(packet_path, answers_path, destination):
    packet, answers = _load(packet_path), _load(answers_path)
    response_format=packet.get('response_format','board-step-v1')
    if response_format not in ('board-step-v1','semantic-v1'):
        raise ValueError('unknown evaluation response format')
    if not isinstance(answers, dict) or set(answers) != {'model','answers'} or not isinstance(answers['model'],str):
        raise ValueError('answers require model provenance and answers list')
    if not isinstance(answers['answers'], list) or len(answers['answers']) > 20:
        raise ValueError('bounded answers list required')
    indexed = {}
    allowed = {q['id'] for q in packet['questions']}
    for answer in answers['answers']:
        if (not isinstance(answer,dict) or set(answer) != {'id','response','prompt_sha256'} or
                not isinstance(answer['id'],str) or answer['id'] not in allowed or answer['id'] in indexed):
            raise ValueError('unknown, duplicate or invalid answer identity')
        indexed[answer['id']] = answer
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {'version':1, 'model':answers['model'], 'tablet_proven':False,
                'conditions':packet.get('conditions', ''),
                'packet_sha256':hashlib.sha256(packet_path.read_bytes()).hexdigest(),
                'source_sha256':hashlib.sha256(answers_path.read_bytes()).hexdigest(),
                'rows':[]}
    for q in packet['questions']:
        row = {'id':q['id'],'question':q['question'],'valid':False,'quality_review':None,'stages':[]}
        manifest['rows'].append(row)
        answer = indexed.get(q['id'])
        if answer is None:
            row['error'] = 'No model answer supplied.'
            continue
        if answer['prompt_sha256'] != q['prompt_sha256']:
            row['error'] = 'Prompt identity mismatch; not a comparable evaluation.'
            continue
        # Preserve raw output even when it fails validation. Never repair it.
        (destination/(q['id']+'-raw.json')).write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
        try:
            started=time.perf_counter()
            if response_format=='semantic-v1':
                from notebook_lesson_native import native_semantic_bundle
                row.update(visual_lesson=False,
                           response_bytes=(len(answer['response'].encode('utf-8'))
                                           if isinstance(answer['response'],str) else None))
                try:
                    bundle=native_semantic_bundle(answer['response'])
                finally:
                    row['compile_native_ms']=round((time.perf_counter()-started)*1000,3)
                row['mode']=bundle['mode']
                if bundle['mode']=='story':
                    raise ValueError('multi-panel stories require the story-panel evaluator')
                if bundle['mode']!='lesson':
                    row.update(valid=True,text=bundle['blocks'][0]['text'])
                    continue  # Accepted text is explicitly NOT a visual lesson.
                plan=bundle['plan']
                assets=[dict(data=source['data'],stroke_count=block['stroke_count'],
                             point_count=block['point_count'])
                        for source,block in zip(bundle['sources'],
                            (b for b in bundle['blocks'] if b['kind']=='ink'))]
            else:
                plan = parse_lesson(answer['response'])
                assets = storyboard_assets(plan)
            row.update(valid=True,takeaway=plan['takeaway'],
                       points=sum(a['point_count'] for a in assets),
                       estimated_pen_seconds=sum(s['estimated_pen_seconds'] for s in plan['stages']))
            for stage, asset in zip(plan['stages'],assets):
                name = q['id']+'-'+stage['id']
                (destination/(name+'.svg')).write_text(preview_svg(plan,stage['id']))
                preview_png(plan,stage['id']).save(destination/(name+'.png'))
                (destination/(name+'.rm')).write_bytes(asset['data'])
                row['stages'].append({'svg':name+'.svg','png':name+'.png','caption':stage['text'],
                                      'strokes':asset['stroke_count'],'points':asset['point_count']})
            if plan.get('equation'):
                name = q['id']+'-equation.png'
                render_equation(plan['equation']).save(destination/name)
                row['equation'] = name
            if response_format=='semantic-v1':
                row['visual_lesson']=True  # Entire preview/encode completed.
            # Keep static acceptance distinct from planned playback acceptance.
            # Neither is proof of physical e-ink animation or saved delivery.
            from notebook_playback_preview import playback_preview
            try:
                player, row['playback'] = playback_preview(plan)
                name = q['id']+'-playback.html'
                (destination/name).write_text(player)
                row['playback']['html'] = name
            except ValueError as exc:
                row['playback'] = dict(valid=False, error=str(exc), tablet_proven=False)
            if response_format=='semantic-v1':
                from notebook_playback_preview import native_lesson_preview
                try:
                    native_bundle=native_semantic_bundle(answer['response'],playback=True,pen_equations=True)
                    player,row['native_playback']=native_lesson_preview(native_bundle)
                    name=q['id']+'-native-playback.html'
                    (destination/name).write_text(player)
                    row['native_playback']['html']=name
                except ValueError as exc:
                    row['native_playback']=dict(valid=False,error=str(exc),tablet_proven=False)
        except LessonLayoutError as exc:
            row.update(valid=False, error=str(exc), diagnostic_only=True,
                       diagnostic_stages=[])
            # Never create .rm assets or promote this rejected plan to valid.
            # Syntax/bounds/budget failures do not get this preview pathway.
            for stage in exc.diagnostic_plan['stages']:
                name = q['id']+'-'+stage['id']+'-rejected'
                (destination/(name+'.svg')).write_text(preview_svg(exc.diagnostic_plan,stage['id']))
                preview_png(exc.diagnostic_plan,stage['id']).save(destination/(name+'.png'))
                row['diagnostic_stages'].append({'svg':name+'.svg','png':name+'.png','caption':stage['text']})
        except (ValueError, TypeError, OverflowError) as exc:
            row.update(valid=False,error=str(exc))
            feedback = budget_feedback(exc)
            if feedback is not None:
                row['resource_feedback'] = feedback
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def compare(left, right, destination, *, assisted=False, prompt_packets=None):
    from notebook_playback_preview import CSS as playback_css
    directories = (left,) if right is None else (left,right)
    runs = [_load(directory/'manifest.json') for directory in directories]
    reviews = [_load(directory/'quality-review.json') if (directory/'quality-review.json').exists() else {}
               for directory in directories]
    if prompt_packets is not None:
        if right is None or len(prompt_packets) != 2:
            raise ValueError('prompt comparison requires two runs and two packets')
        from notebook_model_eval import load_images, digest
        packets = [load_images(path) for path in prompt_packets]
        base, candidate = [p[0] for p in packets]
        if any(run['packet_sha256'] != digest(path.read_bytes())
               for run,path in zip(runs,prompt_packets)):
            raise ValueError('prompt comparison run does not match its packet')
        if candidate.get('prompt_variant') != dict(
                parent_packet_sha256=runs[0]['packet_sha256'],
                parent_system_prompt_sha256=base['expected_system_prompt_sha256']):
            raise ValueError('candidate is not a declared variant of this baseline')
        def inputs(packet):
            return [{k:v for k,v in q.items() if k!='prompt_sha256'}
                    for q in packet['questions']]
        if inputs(base) != inputs(candidate) or packets[0][1] != packets[1][1]:
            raise ValueError('prompt-only comparison requires unchanged question inputs')
        if base['expected_system_prompt_sha256'] == candidate['expected_system_prompt_sha256']:
            raise ValueError('prompt-only comparison requires changed instructions')
    elif len(runs)==2 and runs[0]['packet_sha256'] != runs[1]['packet_sha256']:
        raise ValueError('model runs used different evaluation packets')
    if len(runs)==2 and len(runs[0]['rows']) != len(runs[1]['rows']):
        raise ValueError('model runs have different question counts')
    esc = html.escape
    content = ['<!doctype html><html lang="en"><meta charset="utf-8">',
               '<meta name="viewport" content="width=device-width, initial-scale=1">',
               '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:">',
               '<title>Chalkboard lessons — model comparison</title>',
               '<style>body{font:16px system-ui;margin:32px;color:#20231f;background:#f5f4ef}'
               'h1{font-size:26px}article{margin:40px 0}.models{display:grid;grid-template-columns:1fr 1fr;gap:24px}'
               'section{min-width:0}figure{margin:16px 0;background:white;border:1px solid #ddd;padding:16px}'
               'svg{width:100%;height:auto}figcaption{line-height:1.45;padding-top:12px;border-top:1px solid #eee}'
               '.bad{border-left:4px solid #b34b36;padding:16px;background:#fff}.meta{color:#666;font-size:13px}'
               '@media(max-width:800px){.models{grid-template-columns:1fr}}'+playback_css+'</style>',
               '<h1>'+('Chalkboard lesson review' if right is None else 'One question, two chalkboard lessons')+'</h1>',
               '<p>'+('Identical question inputs; different system prompts' if prompt_packets is not None else
                       'One saved question packet' if right is None else 'Identical base question packets')+'; unedited saved model answers. Every picture is cumulative native-stroke geometry.'
               ' Validation is not a teaching-quality score. Offline only; no tablet latency or handwriting recognition is measured.</p>']
    if right is None:
        content.append('<style>.models{grid-template-columns:1fr;max-width:900px}</style>')
    if prompt_packets is not None:
        content.append('<p class="bad"><strong>Prompt-only comparison:</strong> '
            'A uses the baseline instructions; B uses the candidate instructions. '
            'Question image bytes, text, context and order are verified unchanged. '
            'A single sample per question does not establish a reliable improvement.</p>')
        for label,packet in zip(('A','B'),(base,candidate)):
            content.append('<p class="meta">'+label+' expected system prompt SHA256: '+
                esc(packet['expected_system_prompt_sha256'])+'</p>')
    if runs[0].get('conditions'):
        content.append('<p class="meta"><strong>Run conditions:</strong> '+esc(runs[0]['conditions'])+'</p>')
    deadlines = [run.get('request_deadline_ms') for run in runs]
    if any(value is not None for value in deadlines):
        content.append('<p class="meta">Actual request deadlines below are recorded by the collector; '
                       'historical limits mentioned in the question packet are not the current run settings.</p>')
        if len(runs) == 2 and (None in deadlines or deadlines[0] != deadlines[1]):
            content.append('<p class="bad"><strong>Unequal or unrecorded time budgets:</strong> '
                           'Do not interpret this as a controlled model-only or prompt-only comparison.</p>')
    # Keep full supplied provenance, but do not repeat a multi-paragraph model
    # label above every picture and vertically misalign the comparison columns.
    labels = ['Model '+chr(65+i) for i in range(len(runs))]
    content.append('<div class="models">')
    for label, run in zip(labels, runs):
        deadline = run.get('request_deadline_ms')
        budget = 'Not recorded (legacy run)' if deadline is None else str(deadline)+' ms'
        content.append('<section><h2>'+label+'</h2><p class="meta">'+esc(run['model'])+
                       '</p><p class="meta">Request deadline: '+esc(budget)+'</p></section>')
    content.append('</div>')
    if assisted:
        content.append('<p class="bad"><strong>Assisted comparison:</strong> revised answers also received '
                       'compiler results, visual previews and quality feedback. This is not an unassisted '
                       'model benchmark or a measurement of live reply latency. Original answers remain separate.</p>')
    if any(row.get('error') == 'No model answer supplied.' for run in runs for row in run['rows']):
        content.append('<p class="bad"><strong>Incomplete comparison:</strong> model answers are still missing; '
                       'empty cells are not model failures.</p>')
    for rows in zip(*(run['rows'] for run in runs)):
        a=rows[0]
        if any(row['id']!=a['id'] for row in rows):
            raise ValueError('question order mismatch')
        content.append('<article><h2>'+esc(a['question'])+'</h2><div class="models">')
        for label,directory,run,row,review in zip(labels,directories,runs,rows,reviews):
            content.append('<section><h3>'+label+'</h3>')
            if not row['valid']:
                label = ('No answer released by host: ' if row.get('failure_stage') == 'transport' else
                         'Awaiting model answer: ' if row.get('error') == 'No model answer supplied.' else 'Held by compiler: ')
                content.append('<p class="bad">'+label+esc(row.get('error','unknown failure'))+'</p>')
                if row.get('resource_feedback'):
                    content.append('<details><summary>Measured resource failure (not a repaired lesson)</summary><pre>'+
                                   esc(json.dumps(row['resource_feedback'],indent=2))+'</pre></details>')
                if row.get('diagnostic_only'):
                    content.append('<p class="bad"><strong>Rejected layout — diagnostic preview only.</strong> '
                                   'Not accepted, not repaired, no native ink assets generated.</p>')
                    for i,stage in enumerate(row['diagnostic_stages'],1):
                        content.append('<figure>'+(directory/stage['svg']).read_text()+
                            '<figcaption><strong>Rejected step '+str(i)+'.</strong> '+
                            esc(stage['caption'])+'</figcaption></figure>')
            elif row.get('mode') in ('answer','clarify'):
                content.append('<p class="bad"><strong>Accepted '+esc(row['mode'])+
                               '; not a visual lesson.</strong></p><p>'+esc(row['text'])+'</p>')
            else:
                native = row.get('native_playback')
                if native and not native['valid']:
                    content.append('<p class="bad">Native text/math playback held: '+esc(native['error'])+'</p>')
                playback = native if native and native['valid'] else row.get('playback')
                if playback and playback['valid']:
                    content.append((directory/playback['html']).read_text())
                    content.append('<p class="meta">Planned stroke time: '+
                                   str(round(playback['total_motion_ms']/1000,1))+
                                   ' s. Excludes model, network, native insertion and save delays.</p>')
                    if playback.get('total_planned_ms') is not None:
                        content.append('<p class="meta">Including planned character reveal: '+
                                       str(round(playback['total_planned_ms']/1000,1))+
                                       ' s; native editor settlement and device layout are not simulated.</p>')
                elif playback:
                    content.append('<p class="bad">Static preview only; playback held: '+
                                   esc(playback['error'])+'</p>')
                for i,stage in enumerate(row['stages'],1):
                    content.append('<figure>'+ (directory/stage['svg']).read_text() +
                        '<figcaption><strong>'+str(i)+'.</strong> '+esc(stage['caption'])+'</figcaption></figure>')
                if row.get('equation'):
                    import base64
                    data = base64.b64encode((directory/row['equation']).read_bytes()).decode()
                    content.append('<img style="max-width:100%" alt="Rendered equation" src="data:image/png;base64,'+data+'">')
                content.append('<p><strong>Takeaway:</strong> '+esc(row['takeaway'])+'</p>')
                content.append('<p class="meta">'+str(row['points'])+' points; '+
                               str(round(row['estimated_pen_seconds'],1))+' s estimated pen budget, not observed latency.</p>')
            if row['id'] in review:
                assessment = review[row['id']]
                content.append('<p class="bad"><strong>Visual/content review: '+esc(assessment['verdict'])+
                               '</strong> — '+esc(assessment['notes'])+'</p>')
            content.append('</section>')
        content.append('</div></article>')
    destination.write_text('\n'.join(content+['</html>']))


def examples(destination):
    """Visible compiler fixtures, explicitly NOT evidence of model quality."""
    from notebook_lesson_examples import EXAMPLES
    packet = prepare(destination)
    answers = {'model':'AUTHORED WORKED EXAMPLES — not a model evaluation', 'answers':[
        dict(id=q['id'],prompt_sha256=q['prompt_sha256'],response=EXAMPLES[q['id']]())
        for q in packet['questions'] if q['id'] in EXAMPLES]}
    source = destination/'authored-examples.json'
    source.write_text(json.dumps(answers,ensure_ascii=False,indent=2)+'\n')
    result = render(destination/'packet.json',source,destination/'rendered')
    content = ['<!doctype html><html lang="en"><meta charset="utf-8">',
               '<title>Authored chalkboard examples — not model results</title>',
               '<style>body{font:18px system-ui;margin:32px;color:#222}.columns{display:flex;gap:32px}'
               'section{flex:1;min-width:0}figure{margin:24px 0}svg{width:100%;height:auto}'
               'figcaption{padding-top:12px;line-height:1.5}h2{font-size:22px}</style>',
               '<h1>Authored worked examples</h1><p>Compiler and layout demonstration only. '
               'These are the examples included in the prompt, not PiDog or second-model answers; '
               'no tablet result is claimed.</p><div class="columns">']
    for row in result['rows']:
        if row['id'] not in EXAMPLES:
            continue
        if not row['valid']:
            raise ValueError('authored example failed: '+row['error'])
        content.append('<section><h2>'+html.escape(row['question'])+'</h2>')
        for i,stage in enumerate(row['stages'],1):
            content.append('<figure>'+(destination/'rendered'/stage['svg']).read_text()+
                           '<figcaption>'+str(i)+'. '+html.escape(stage['caption'])+'</figcaption></figure>')
        content.append('<p><strong>Takeaway:</strong> '+html.escape(row['takeaway'])+'</p></section>')
    (destination/'preview.html').write_text('\n'.join(content+['</div></html>']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('destination',type=Path)
    p.add_argument('--semantic',action='store_true',help='Use compact semantic JSON, not model-authored coordinates')
    p = sub.add_parser('examples'); p.add_argument('destination',type=Path)
    p = sub.add_parser('check',help='Check and preview one raw draft OFFLINE; never write to the tablet')
    p.add_argument('source',type=Path,help='UTF-8 final-answer draft; board-step fences by default')
    p.add_argument('destination',type=Path,help='New directory for this draft and cumulative previews')
    p.add_argument('--semantic',action='store_true',help='Check the current semantic JSON reply contract')
    p = sub.add_parser('render'); p.add_argument('packet',type=Path); p.add_argument('answers',type=Path); p.add_argument('destination',type=Path)
    p = sub.add_parser('compare'); p.add_argument('left',type=Path); p.add_argument('right',type=Path); p.add_argument('destination',type=Path)
    p.add_argument('--assisted',action='store_true',help='Disclose additional preview/compiler/quality feedback')
    p.add_argument('--prompt-packets',nargs=2,type=Path,metavar=('BASE','CANDIDATE'),
                   help='Explicit prompt-only comparison; verify unchanged image/context inputs')
    p = sub.add_parser('report',help='Show one model run without inventing a second comparator')
    p.add_argument('source',type=Path); p.add_argument('destination',type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.destination,semantic=args.semantic)
        print('Prepared',len(result['questions']),'identical questions in',args.destination)
    elif args.command == 'examples':
        examples(args.destination)
        print('Authored examples (NOT model results):',args.destination/'preview.html')
    elif args.command == 'render':
        result = render(args.packet,args.answers,args.destination)
        print('Valid',sum(row['valid'] for row in result['rows']),'of',len(result['rows']),'model answers;',args.destination)
    elif args.command == 'report':
        compare(args.source,None,args.destination)
        print('Single-run report:',args.destination)
    elif args.command == 'check':
        try:
            result = check_draft(args.source,args.destination,semantic=args.semantic)
        except Exception as exc:
            # Includes output IO failure: we cannot promise result.json exists
            # on an unwritable/full filesystem, but stdout remains explicit.
            print(json.dumps({'valid':False,'quality_status':'unreviewed',
                              'error':str(exc),'error_type':type(exc).__name__}))
            return 2
        print(json.dumps(dict(result,destination=str(args.destination.resolve())),ensure_ascii=False))
        return 0 if result['valid'] else 2
    else:
        compare(args.left,args.right,args.destination,assisted=args.assisted,
                prompt_packets=args.prompt_packets)
        print('Comparison:',args.destination)


if __name__ == '__main__':
    sys.exit(main())
