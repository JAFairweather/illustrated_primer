#!/usr/bin/env python3
"""Render typed story panels offline; never import into a notebook."""
import argparse
import hashlib
import html
import json
from pathlib import Path

from notebook_story_plan import MAX_BYTES, parse_story
from notebook_lesson import _pairs, _constant
from notebook_panel_shapes import compile_panel_shapes
from notebook_drawing import preview_svg
from notebook_lesson_eval import preview_png
from notebook_stroke_asset import storyboard_assets
from notebook_pen_budget import budget_feedback


def read_bounded(path):
    with path.open('rb') as stream: raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('panel input exceeds byte budget')
    return raw


def review_panels(story_raw, shapes_raw, destination, *, authored_example=None):
    if any(len(raw)>MAX_BYTES for raw in (story_raw,shapes_raw)):
        raise ValueError('panel input exceeds byte budget')
    destination.mkdir(parents=True,exist_ok=False)
    (destination/'story.txt').write_bytes(story_raw)
    (destination/'shapes.txt').write_bytes(shapes_raw)
    result=dict(valid=False, geometry_validated=False, ink_encoding_validated=False,
                native_delivery_supported=False, tablet_proven=False, model_calls=0,
                quality_status='unreviewed', preview_complete=False, panels=[],
                source_sha256=dict(story=hashlib.sha256(story_raw).hexdigest(),
                                   shapes=hashlib.sha256(shapes_raw).hexdigest()))
    if authored_example is not None:result['authored_example']=authored_example
    try:
        story=parse_story(story_raw.decode('utf-8'))
        shapes=json.loads(shapes_raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_constant)
        compiled=compile_panel_shapes(story,shapes)
        # Exercise the real v6 encoder only after the entire story passes.
        # No .rm asset is saved, and no multi-region delivery is implied.
        for panel in compiled['panels'].values():storyboard_assets(panel['plan'])
        if compiled.get('equation_plan') is not None:
            storyboard_assets(compiled['equation_plan'])
        result.update(geometry_validated=True,ink_encoding_validated=True,
                      snapshot_points=compiled['snapshot_points'])
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:
        result.update(error=str(exc),error_type=type(exc).__name__)
        feedback=budget_feedback(exc)
        if feedback is not None:result['resource_feedback']=feedback
    else:
        esc=html.escape
        page=['<!doctype html><html lang="en"><meta charset="utf-8">',
              '<title>Offline panel drawings</title>',
              '<style>body{font:18px/1.5 sans-serif;margin:2rem auto;max-width:1250px;padding:1rem}',
              'section{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:1rem}',
              'article{border:1px solid #999;padding:1rem}img{width:100%;height:auto}',
              'small{color:#444}h2{margin:0}</style>',
              '<h1>'+esc(story['question'])+'</h1>',
              '<p>Offline geometry and v6 encoding checked. Not a tablet screenshot, '
              'mathematical review or delivery proof. Input provenance must be checked '
              'in the originating evaluation; this renderer makes no model calls.</p><section>']
        for panel in story['panels']:
            identity=panel['id'];resolved=compiled['panels'][identity];plan=resolved['plan']
            name='panel-'+identity
            (destination/(name+'.svg')).write_text(preview_svg(plan),encoding='utf-8')
            preview_png(plan,identity).save(destination/(name+'.png'))
            row=dict(id=identity,base=panel['base'],caption=panel['caption'],
                     svg=name+'.svg',png=name+'.png',snapshot_points=resolved['snapshot_points'],
                     added_points=resolved['added_points'],label_layout=resolved['label_layout'])
            result['panels'].append(row)
            page.extend(['<article id="'+identity+'"><h2>'+esc(panel['title'])+'</h2>',
                         '<img src="'+row['png']+'" alt="'+esc(panel['caption'],quote=True)+'">',
                         '<p>'+esc(panel['caption'])+'</p>',
                         '<small>Base: '+esc(panel['base'] or 'new picture')+
                         ' · Added points: '+str(row['added_points'])+'</small></article>'])
        page.append('</section>')
        if compiled.get('equation_plan') is not None:
            equation = compiled['equation_plan']
            (destination/'equation.svg').write_text(preview_svg(equation), encoding='utf-8')
            preview_png(equation, 'equation').save(destination/'equation.png')
            result['equation'] = dict(source=story['equation'], svg='equation.svg', png='equation.png')
            page.extend(['<h2>Equation</h2><img src="equation.png" alt="'+
                         esc(story['equation'], quote=True)+'">'])
        page.extend(['<h2>Takeaway</h2><p>'+esc(story['takeaway'])+'</p></html>'])
        (destination/'index.html').write_text('\n'.join(page),encoding='utf-8')
        result.update(valid=True,preview_complete=True,index='index.html')
    (destination/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    check=sub.add_parser('check')
    check.add_argument('story',type=Path);check.add_argument('shapes',type=Path)
    check.add_argument('destination',type=Path)
    example=sub.add_parser('example')
    example.add_argument('destination',type=Path)
    example.add_argument('--scene',choices=('graph-reuse','relationship','general-primitives'),default='graph-reuse')
    args=parser.parse_args()
    if args.command=='check':
        result=review_panels(read_bounded(args.story),read_bounded(args.shapes),args.destination)
    else:
        from notebook_panel_examples import graph_reuse_example, relationship_example, primitive_capabilities_example
        scenes={'graph-reuse':graph_reuse_example,'relationship':relationship_example,
                'general-primitives':primitive_capabilities_example}
        story,shapes=scenes[args.scene]()
        result=review_panels(json.dumps(story).encode(),json.dumps(shapes).encode(),
                             args.destination,authored_example=args.scene)
    print(json.dumps(result))
    return 0 if result['valid'] else 2


if __name__=='__main__':raise SystemExit(main())
