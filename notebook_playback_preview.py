"""Offline, script-free playback of the exact native asset's pen paths.

This previews planned geometry/timing, not tablet refresh or delivery latency.
No model call, device I/O, source import, or alternate persistent writer.
"""
import base64
import html
import io
import math

from notebook_ink_playback import playback_assets, validate_playback


CSS = '''
.pen-preview{background:white;border:1px solid #ddd;padding:16px;margin:16px 0}
.pen-preview>input{margin-right:8px}
.pen-preview svg{display:block;width:100%;height:auto;background:white}
.pen-preview .pen-path{stroke-dasharray:var(--length);stroke-dashoffset:var(--length);visibility:hidden}
.pen-preview .pen-caption,.pen-preview .pen-takeaway{visibility:hidden}
.pen-preview .pen-character{visibility:hidden;white-space:pre-wrap}
.pen-preview>input:checked~svg .pen-path{animation:pen-draw var(--duration) linear var(--start) forwards}
.pen-preview>input:checked~p .pen-character{animation:pen-caption 1ms step-end var(--start) both}
.pen-preview>input:checked~.pen-caption,.pen-preview>input:checked~.pen-takeaway{animation:pen-caption 1ms step-end var(--start) both}
@keyframes pen-draw{from{visibility:visible;stroke-dashoffset:var(--length)}to{visibility:visible;stroke-dashoffset:0}}
@keyframes pen-caption{from{visibility:hidden}to{visibility:visible}}
@media(prefers-reduced-motion:reduce){
 .pen-preview>input:checked~svg .pen-path{animation:none;visibility:visible;stroke-dashoffset:0}
 .pen-preview>input:checked~.pen-caption,.pen-preview>input:checked~.pen-takeaway{animation:none;visibility:visible}
 .pen-preview>input:checked~p .pen-character{animation:none;visibility:visible}
}
'''


def typing_units(text):
    """Mirror the conservative client reveal grouping; not a full segmenter."""
    if not isinstance(text,str) or len(text.encode('utf-16-le'))//2>2000:
        raise ValueError('Caption reveal exceeds text budget')
    result,join,regional=[],False,0
    for char in text:
        code=ord(char)
        if 0x590<=code<=0x1cff or 0xa800<=code<=0xabff:
            return [text]
        mark=any(a<=code<=b for a,b in ((0x300,0x36f),(0x1ab0,0x1aff),
            (0x1dc0,0x1dff),(0x20d0,0x20ff),(0xfe00,0xfe0f),(0xfe20,0xfe2f),
            (0x1f3fb,0x1f3ff),(0xe0100,0xe01ef)))
        flag=0x1f1e6<=code<=0x1f1ff
        if result and (mark or join or code==0x200d or flag and regional%2):
            result[-1]+=char
        else:
            result.append(char)
        join=code==0x200d
        regional=regional+1 if flag else 0
    return result


def native_lesson_preview(bundle):
    """Preview resolved native blocks, including math and planned text cadence.

    Uses the exact source bytes/descriptor pair destined for native import.
    This is a logical layout, not xochitl pagination or measured editor speed.
    All geometry validates before any HTML is returned; no device calls.
    """
    from notebook_stroke_asset import validate_native_ink_budget
    validate_native_ink_budget(bundle['blocks'])
    sources={(s['source_doc'],s['source_page']):s['data'] for s in bundle['sources']}
    if len(sources)!=len(bundle['sources']):
        raise ValueError('duplicate native preview source')
    parts,regions,events=[],{},[]
    elapsed=motion=0.0
    for block in bundle['blocks']:
        start=elapsed
        if block['kind']=='text':
            units=typing_units(block['text'])
            characters=[]
            for unit in units:
                elapsed+=31
                characters.append(f'<span class="pen-character" style="--start:{elapsed:.6f}ms">{html.escape(unit)}</span>')
            parts.append('<p class="pen-prose">'+''.join(characters)+'</p>')
            events.append(dict(kind='text',start_ms=start,end_ms=elapsed,units=len(units)))
        elif block['kind']=='ink':
            descriptor=validate_playback(block,sources[(block['source_doc'],block['source_page'])])
            scene=block['scene']
            if scene not in regions:
                regions[scene]=dict(width=block['width'],height=block['height'],paths=[])
                parts.append(regions[scene])
            region=regions[scene]
            if (region['width'],region['height'])!=(block['width'],block['height']):
                raise ValueError('native preview region changed dimensions')
            for index,points in enumerate(descriptor['paths']):
                length=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
                duration=max(descriptor['minimum_stroke_ms'],1000*length/descriptor['velocity'])
                timing=f'--start:{elapsed:.6f}ms;--duration:{duration:.6f}ms;--length:{length:.9f}'
                if length==0:
                    x,y=points[0]
                    path=f'<circle class="pen-path" cx="{x}" cy="{y}" r="1" fill="black" stroke="none" style="{timing}"/>'
                else:
                    coordinates=' '.join(f'{x},{y}' for x,y in points)
                    path=f'<polyline class="pen-path" points="{coordinates}" style="{timing}"/>'
                region['paths'].append(path)
                elapsed+=duration
                if index+1<len(descriptor['paths']):elapsed+=descriptor['pen_up_ms']
            motion+=elapsed-start
            events.append(dict(kind='ink',role=block.get('role','diagram'),scene=scene,
                               start_ms=start,end_ms=elapsed,strokes=block['stroke_count']))
        else:
            raise ValueError('native preview requires text and playback ink only')
    body=[]
    for part in parts:
        if isinstance(part,str):body.append(part)
        else:
            body.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {part["width"]} {part["height"]}" '
                'role="img" aria-label="Native stroke region" fill="none" stroke="black" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round">'+''.join(part['paths'])+'</svg>')
    markup=('<div class="pen-preview"><input type="checkbox" aria-label="Draw native lesson; uncheck to reset"> '
        'Draw native lesson (uncheck to reset)<span class="meta"> — planned sequence, not a tablet recording.</span>'
        +''.join(body)+'</div>')
    return markup,dict(valid=True,tablet_proven=False,total_motion_ms=motion,total_planned_ms=elapsed,
                       events=events,excludes='model, network, native editor settlement, insertion and save delays')


def playback_preview(plan):
    """Return an embeddable checkbox-controlled player and timing summary.

    All stages validate before HTML is returned. Native-decoded paths retain
    order, corners and pen lifts. Captions appear after their stage's strokes.
    No inter-stage transport/save delays are simulated. The existing static
    previews remain available below this additional playback view.
    """
    assets = playback_assets(plan)
    paths, captions, stages = [], [], []
    elapsed = 0.0
    for stage, asset in zip(plan['stages'], assets):
        descriptor = validate_playback(asset, asset['data'])
        start = elapsed
        for index, points in enumerate(descriptor['paths']):
            length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
            duration = max(descriptor['minimum_stroke_ms'], 1000*length/descriptor['velocity'])
            timing = f'--start:{elapsed:.6f}ms;--duration:{duration:.6f}ms;--length:{length:.9f}'
            # The tablet gives a zero-length native dot a bounded visible dwell.
            if length == 0:
                x, y = points[0]
                paths.append(f'<circle class="pen-path" cx="{x}" cy="{y}" r="1" '
                             f'fill="black" stroke="none" style="{timing}"/>')
            else:
                coordinates = ' '.join(f'{x},{y}' for x, y in points)
                paths.append(f'<polyline class="pen-path" points="{coordinates}" style="{timing}"/>')
            elapsed += duration
            if index+1 < len(descriptor['paths']):
                elapsed += descriptor['pen_up_ms']
        stages.append(dict(id=stage['id'], start_ms=start, end_ms=elapsed,
                           strokes=asset['stroke_count'], points=asset['point_count']))
        captions.append(f'<p class="pen-caption" style="--start:{elapsed:.6f}ms">'
                        f'{len(stages)}. {html.escape(stage["text"])}</p>')
    summary = dict(valid=True, velocity=descriptor['velocity'], total_motion_ms=elapsed, stages=stages,
                   tablet_proven=False, excludes='model, network, native insertion and save delays')
    equation = ''
    if plan.get('equation'):
        from notebook_media import render_equation
        png = io.BytesIO()
        render_equation(plan['equation']).save(png, format='PNG')
        encoded = base64.b64encode(png.getvalue()).decode('ascii')
        equation = (f'<p class="pen-caption" style="--start:{elapsed:.6f}ms">'
                    '<img style="max-width:100%" alt="Rendered lesson equation" '
                    f'src="data:image/png;base64,{encoded}"></p>')
    # aria-label avoids duplicate IDs when both model columns share a scene.
    markup = ('<div class="pen-preview">'
              '<input type="checkbox" aria-label="Draw lesson; uncheck to reset"> Draw lesson (uncheck to reset)'
              '<span class="meta"> — planned strokes only; not a tablet recording.</span>'
              f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {plan["width"]} {plan["height"]}" '
              'role="img" aria-label="Progressive native-stroke lesson preview" '
              'fill="none" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
              + ''.join(paths) + '</svg>' + ''.join(captions) + equation
              + f'<p class="pen-takeaway" style="--start:{elapsed:.6f}ms">Takeaway: '
              + html.escape(plan['takeaway']) + '</p></div>')
    return markup, summary
