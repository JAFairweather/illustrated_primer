#!/usr/bin/env python3
"""Freeze image questions, collect first-pass story runs, compare panel previews.

Offline only. Reuses existing question/image packets without selecting easier
questions. Production endpoints, prompts and tablet contents are never changed.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil

from notebook_lesson import _pairs, _constant, _fields, _text
from notebook_model_eval import load_images
from notebook_model_transport import model_request, call_story_panel_eval
from notebook_story_model_eval import evaluate
from notebook_story_prompt import story_panel_instructions


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def _read(path, limit):
    if path.is_symlink(): raise ValueError('evaluation inputs must not be symlinks')
    with path.open('rb') as stream: data=stream.read(limit+1)
    if len(data)>limit: raise ValueError('evaluation input exceeds size limit')
    return data


def _load(path, limit=100000):
    return json.loads(_read(path,limit),object_pairs_hook=_pairs,parse_constant=_constant)


def prepare(source_packet, destination):
    """Keep ALL original question text/image bytes/order; change task protocol."""
    source, images = load_images(source_packet)
    prompt = story_panel_instructions().encode('utf-8')
    packet = dict(v=1, response_format='story-panel-v1',
                  source_packet_sha256=digest(source_packet.read_bytes()),
                  prompt_sha256=digest(prompt), questions=[])
    for old,png in zip(source['questions'],images):
        question = old['question']; _text(question,600)
        packet['questions'].append(dict(id=old['id'],question=question,image=old['image'],
                                      image_sha256=digest(png)))
    destination.mkdir(parents=True,exist_ok=False)
    for row,png in zip(packet['questions'],images):
        (destination/row['image']).write_bytes(png)
    prompt_path=destination/'system-prompt.txt'
    prompt_path.write_bytes(prompt); prompt_path.chmod(0o600)
    _save(destination/'packet.json',packet)
    return packet


def load_packet(path, *, require_current_prompt=True):
    packet = _load(path)
    _fields(packet,{'v','response_format','source_packet_sha256','prompt_sha256','questions'})
    if type(packet['v']) is not int or packet['v']!=1 or packet['response_format']!='story-panel-v1':
        raise ValueError('version 1 story-panel packet required')
    prompt = _read(path.parent/'system-prompt.txt',64000)
    if digest(prompt)!=packet['prompt_sha256'] or (require_current_prompt and prompt!=story_panel_instructions().encode('utf-8')):
        raise ValueError('frozen prompt differs from this evaluator; do not silently replace it')
    if not isinstance(packet['questions'],list) or not 1<=len(packet['questions'])<=20:
        raise ValueError('use 1..20 fixed questions')
    seen, images = set(), []
    for row in packet['questions']:
        _fields(row,{'id','question','image','image_sha256'})
        identity=row['id']
        if not isinstance(identity,str) or not re.fullmatch('[a-z][a-z0-9-]{0,40}',identity) or identity in seen:
            raise ValueError('invalid or duplicate question identity')
        seen.add(identity); _text(row['question'],600)
        if row['image']!=identity+'.png': raise ValueError('fixed local question image required')
        png=_read(path.parent/row['image'],3_000_000)
        if digest(png)!=row['image_sha256']: raise ValueError('question image changed')
        model_request('notebook-'+'0'*32,png,row['question'])
        images.append(png)
    return packet,images


def collect(packet_path, destination, endpoint, *, expected_model, max_questions=None,
            deadline_ms=30000, call=call_story_panel_eval, max_corrections=0):
    packet, images = load_packet(packet_path)
    count=len(images) if max_questions is None else max_questions
    if type(count) is not int or not 1<=count<=len(images): raise ValueError('invalid question limit')
    if type(max_corrections) is not int or max_corrections not in (0,1):
        raise ValueError('use zero or one correction for the entire lesson')
    # Validate the entire packet and settings before any artifacts or calls.
    _text(expected_model,128)
    model_request('notebook-'+'0'*32,images[0],'check',deadline_ms)
    destination.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(packet_path,destination/'packet.json')
    (destination/'system-prompt.txt').write_text(story_panel_instructions(),encoding='utf-8')
    for row,png in zip(packet['questions'],images):(destination/row['image']).write_bytes(png)
    summary=dict(v=1,packet_sha256=digest(packet_path.read_bytes()),expected_model=expected_model,
                 deadline_ms=deadline_ms,max_questions=count,max_corrections=max_corrections,rows=[],stopped=False,
                 tablet_proven=False,host_prompt_attested=False,quality_status='unreviewed')
    try:
        for row,png in zip(packet['questions'][:count],images[:count]):
            result=evaluate(row['question'],png,endpoint,destination/row['id'],
                            expected_model=expected_model,deadline_ms=deadline_ms,call=call,
                            max_corrections=max_corrections)
            summary['rows'].append(dict(id=row['id'],valid=result['valid'],
                first_pass_valid=result['first_pass_valid'],corrections_used=result['corrections_used'],
                result=row['id']+'/result.json',wall_ms=result['wall_ms']))
            # A timed-out provider may still be alive. Never start another
            # question on that host without separately verifying termination.
            switched=any(c.get('metrics',{}).get('model',expected_model)!=expected_model for c in result['calls'])
            if result.get('transport_error') or switched:
                summary.update(stopped=True,stop_reason=result.get('transport_error','model_changed'))
                break
            _save(destination/'run.json',summary)
    except BaseException:
        summary.update(stopped=True,stop_reason='collector_interrupted')
        raise
    finally:
        _save(destination/'run.json',summary)
    return summary


def compare(left, right, destination):
    """Self-contained side-by-side page. Missing answers are NOT failures."""
    directories=[left,right]
    packets=[load_packet(d/'packet.json',require_current_prompt=False)[0] for d in directories]
    if packets[0]!=packets[1] or (left/'packet.json').read_bytes()!=(right/'packet.json').read_bytes():
        raise ValueError('comparison requires identical fixed question packets')
    runs=[_load(d/'run.json') for d in directories]
    packet_hash=digest((left/'packet.json').read_bytes())
    for run in runs:
        if run.get('packet_sha256')!=packet_hash: raise ValueError('run/packet mismatch')
        ids=[row['id'] for row in run['rows']]
        if ids!=[q['id'] for q in packets[0]['questions'][:len(ids)]]:
            raise ValueError('run question order changed')
    destination.mkdir(parents=True,exist_ok=False)
    esc=html.escape
    out=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Story model comparison</title>',
         '<style>body{font:18px/1.5 sans-serif;max-width:1500px;margin:2rem auto;padding:1rem}',
         '.pair{display:grid;grid-template-columns:1fr 1fr;gap:1rem}',
         '.model{border:1px solid #aaa;padding:1rem}img{width:100%;height:auto}',
         '.warn{background:#fff2cd;padding:.6rem}pre{white-space:pre-wrap}figure{margin:1rem 0}</style>',
         '<h1>Identical questions, independent story/panel responses</h1>',
         '<p>Offline only. Geometry acceptance is not teaching-quality approval. '
         'No handwriting recognition, tablet latency or native delivery is proven. '
         'Host prompt installation must be verified separately.</p>']
    if runs[0].get('deadline_ms')!=runs[1].get('deadline_ms'):
        out.append('<p class="warn">Unequal per-call time budgets: not a model-only comparison.</p>')
    if runs[0].get('max_corrections',0)!=runs[1].get('max_corrections',0):
        out.append('<p class="warn">Unequal correction budgets: not a model-only comparison.</p>')
    indexes=[{r['id']:r for r in run['rows']} for run in runs]
    for question in packets[0]['questions']:
        identity=question['id']
        out.extend(['<h2>'+esc(question['question'])+'</h2><div class="pair">'])
        for side,(directory,run,index) in enumerate(zip(directories,runs,indexes)):
            out.append('<section class="model"><h3>Expected model: '+esc(run['expected_model'])+'</h3>')
            out.append('<p>Per-call limit: '+str(run['deadline_ms'])+' ms</p>')
            out.append('<p>Correction budget per lesson: '+str(run.get('max_corrections',0))+'</p>')
            if identity not in index:
                out.append('<p class="warn">Not attempted — no model result.</p></section>')
                continue
            row=index[identity]
            if row['result']!=identity+'/result.json': raise ValueError('unexpected result path')
            result=_load(directory/row['result'])
            out.append('<p>Full pipeline: '+str(result['wall_ms'])+' ms; '
                       +str(result['call_attempts'])+' call attempts.</p>')
            out.append('<p>First-pass valid: '+str(result.get('first_pass_valid',result['valid']))+
                       '; corrections used: '+str(result.get('corrections_used',0))+'.</p>')
            out.append('<p>Complete native preparation: '+
                       ('validated offline' if result.get('native_preparation_valid') else 'not validated')+
                       '. Tablet behavior remains unproven.</p>')
            if result.get('first_validation_failure'):
                out.append('<details><summary>Original validation failure (not erased by correction)</summary><pre>'+
                           esc(json.dumps(result['first_validation_failure'],indent=2))+'</pre></details>')
            if not result['valid']:
                out.append('<p class="warn">Held at '+esc(result.get('failed_phase','unknown'))+
                           ': '+esc(result.get('error','No accepted preview.'))+'</p>')
            else:
                preview=result['preview']
                if not preview.get('preview_complete'): raise ValueError('accepted run has no complete preview')
                if result.get('native_preparation_valid'):
                    if result.get('playback_file')!='playback.html':
                        raise ValueError('unexpected native playback path')
                    target=f'{side}-{identity}-playback.html'
                    (destination/target).write_bytes(_read(directory/identity/'playback.html',3_000_000))
                    out.append('<p><a href="'+target+'">Play caption-before-drawing sequence</a> '
                               '(planned animation, not a tablet recording).</p>')
                for panel in preview['panels']:
                    name=panel['png']
                    if not re.fullmatch(r'panel-[a-z][a-z0-9-]{0,31}\.png',name):
                        raise ValueError('unexpected panel image path')
                    source=directory/identity/'preview'/name
                    target=f'{side}-{identity}-{name}'
                    (destination/target).write_bytes(_read(source,3_000_000))
                    out.append('<figure><img src="'+target+'" alt="'+esc(panel['caption'],quote=True)+
                               '"><figcaption>'+esc(panel['caption'])+'</figcaption></figure>')
                story=_load(directory/identity/'story.json',24000)
                out.append('<p><strong>Takeaway:</strong> '+esc(story['takeaway'])+'</p>')
            out.append('<details><summary>Per-call model timing and usage</summary><pre>'+
                       esc(json.dumps(result['calls'],indent=2))+'</pre></details></section>')
        out.append('</div>')
    out.append('</html>')
    (destination/'index.html').write_text('\n'.join(out),encoding='utf-8')
    return dict(index=str(destination/'index.html'),questions=len(packets[0]['questions']))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('source',type=Path);prep.add_argument('destination',type=Path)
    run=sub.add_parser('collect');run.add_argument('packet',type=Path);run.add_argument('destination',type=Path)
    run.add_argument('endpoint');run.add_argument('--expected-model',required=True)
    run.add_argument('--max-questions',type=int);run.add_argument('--deadline-ms',type=int,default=30000)
    run.add_argument('--max-corrections',type=int,choices=(0,1),default=0)
    view=sub.add_parser('compare');view.add_argument('left',type=Path);view.add_argument('right',type=Path)
    view.add_argument('destination',type=Path)
    args=parser.parse_args()
    if args.command=='prepare': result=prepare(args.source,args.destination)
    elif args.command=='collect':
        result=collect(args.packet,args.destination,args.endpoint,expected_model=args.expected_model,
                       max_questions=args.max_questions,deadline_ms=args.deadline_ms,
                       max_corrections=args.max_corrections)
    else: result=compare(args.left,args.right,args.destination)
    print(json.dumps(result))
    return 2 if result.get('stopped') else 0


if __name__=='__main__':raise SystemExit(main())
