"""Local visual fixtures for the procedural engine, not model-quality claims."""
import argparse
import html
import json
from pathlib import Path
import time

from notebook_drawing import preview_svg
from notebook_lesson_eval import preview_png
from notebook_media import render_equation
from notebook_procedural import compile_board
from notebook_stroke_asset import storyboard_assets


def examples():
    lever = {'kind':'lever','arms':[1,3],'forces':[3,1],
             'captions':['A beam turns around its triangular support.',
                         'The left force is three times larger; the arrows use one shared scale.',
                         'The right arm is three times longer, so the turning effects balance.'],
             'equation':'3 × 1 = 1 × 3',
             'takeaway':'A longer arm lets a smaller force produce the same turning effect.'}
    water = {'kind':'network','objects':[
        {'id':'sun','shape':'sun','label':'Sun'},
        {'id':'water','shape':'water','label':'Water'},
        {'id':'cloud','shape':'cloud','label':'Cloud'}],
        'links':[
            {'id':'heat','from':'sun','to':'water','label':'Heat'},
            {'id':'rise','from':'water','to':'cloud','label':'Evaporation'},
            {'id':'rain','from':'cloud','to':'water','label':'Rain'}],
        'steps':[
            {'caption':'Sunlight supplies energy to surface water.','add':['sun','water','heat']},
            {'caption':'Water evaporates; later cooling condenses vapor into cloud droplets.','add':['cloud','rise']},
            {'caption':'Precipitation returns water to the surface, completing this simplified cycle.','add':['rain']}],
        'takeaway':'Sunlight drives evaporation; cooling and gravity help return the water. Arrows show process relationships, not literal trajectories.'}
    message = {'kind':'network','objects':[
        {'id':'person','shape':'person','label':'Writer'},
        {'id':'plan','shape':'box','label':'Short plan'},
        {'id':'engine','shape':'box','label':'Renderer'},
        {'id':'page','shape':'box','label':'Notebook'}],
        'links':[
            {'id':'ask','from':'person','to':'plan','label':'Question'},
            {'id':'describe','from':'plan','to':'engine','label':'Meaning'},
            {'id':'draw','from':'engine','to':'page','label':'Ink'}],
        'steps':[
            {'caption':'A person asks a question; the model makes a compact explanation plan.','add':['person','plan','ask']},
            {'caption':'The renderer turns that meaning into measured, repeatable geometry.','add':['engine','describe']},
            {'caption':'Native pen strokes reveal the explanation in the notebook.','add':['page','draw']}],
        'takeaway':'The model chooses what to explain; code handles the drawing mechanics.'}
    return {'lever':lever,'water-cycle':water,'short-plan':message}


def render(destination, fixtures=None, compiler=compile_board):
    destination.mkdir(parents=True,exist_ok=False)
    panels,results=[],[]
    for name,spec in (fixtures if fixtures is not None else examples()).items():
        begin=time.perf_counter()
        plan=compiler(spec)
        assets=storyboard_assets(plan)
        elapsed=time.perf_counter()-begin
        (destination/(name+'.json')).write_text(json.dumps(spec,indent=2)+'\n')
        cards=[]
        for stage in plan['stages']:
            base=name+'-'+stage['id']
            (destination/(base+'.svg')).write_text(preview_svg(plan,stage['id']))
            preview_png(plan,stage['id']).save(destination/(base+'.png'))
            cards.append('<figure><img src="'+base+'.svg" alt="Cumulative ink stage"><figcaption>'+html.escape(stage['text'])+'</figcaption></figure>')
        equation=''
        if plan.get('equation'):
            render_equation(plan['equation']).save(destination/(name+'-equation.png'))
            equation='<img class="equation" src="'+name+'-equation.png" alt="'+html.escape(plan['equation'],quote=True)+'">'
        panels.append('<section><h2>'+html.escape(name)+'</h2><div class="stages">'+''.join(cards)+'</div>'+equation+'<p>'+html.escape(plan['takeaway'])+'</p><details><summary>Compact input</summary><pre>'+html.escape(json.dumps(spec,indent=2))+'</pre></details></section>')
        results.append({'example':name,'compile_and_native_encode_ms':round(elapsed*1000,3),
                        'input_bytes':len(json.dumps(spec,separators=(',',':')).encode()),
                        'stroke_points':sum(a['point_count'] for a in assets),
                        'native_encoder_pass':True,'tablet_proven':False,
                        'layout':plan.get('semantic',plan.get('procedural'))})
    (destination/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    (destination/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Procedural notebook boards</title><style>body{font:18px system-ui;margin:32px;background:#f4f1e8;color:#172324}section{background:white;padding:24px;margin:24px 0;border-radius:12px}.stages{display:flex;gap:16px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:300px}figure img{width:100%}figcaption{padding:12px;line-height:1.5;border-top:1px solid #ddd}.equation{max-width:300px}pre{font-size:13px;white-space:pre-wrap}p{max-width:900px}</style><h1>Short meaning → procedural pen strokes</h1><p>Developer-authored local fixtures, not live agent answers. Each picture is cumulative; captions stay outside the drawing. No tablet operation or model revision loop.</p>'+''.join(panels))
    return results


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--semantic',action='store_true',help='Render the versioned semantic fixtures and changed-quantity variants')
    args=parser.parse_args()
    if args.semantic:
        from notebook_semantic import compile_semantic
        from notebook_semantic_examples import examples as semantic_examples
        result=render(args.destination,semantic_examples(),compile_semantic)
    else:
        result=render(args.destination)
    print(json.dumps([{k:v for k,v in row.items() if k!='layout'} for row in result],indent=2))
