"""Bounded model response contract for the offline semantic notebook route.

The transport owns request/page identities and image delivery. This parser
neither invokes a model nor enables a live route. Invalid lessons stay errors;
their potentially contradictory prose is never salvaged as a text answer.
"""
import json
import re

from notebook_lesson import _fields, _text, _pairs, _constant
from notebook_semantic import MAX_BYTES, SemanticError, compile_semantic


def _labels(labels,frames):
    """A picture's labels, one list of up to 3 short words per frame, or None: labels the pen cannot letter are left
    off rather than costing the picture."""
    from notebook_plotter_font import label_paths
    if not isinstance(labels,list) or len(labels)!=frames or not all(isinstance(f,list) for f in labels):
        return None
    kept=[]
    for texts in labels:
        kept.append([])
        for text in texts:
            try:
                if len(kept[-1])<3 and isinstance(text,str) and 1<=len(text.strip())<=20:
                    label_paths(text.strip(),20)
                    kept[-1].append(text.strip())
            except ValueError:
                pass
    return kept if any(kept) else None


def _solid(text):
    # A dashed or dotted line rasters into specks the ink drops; planners still ask for "a dashed arrow" (r5-lever, 10-31).
    return re.sub(r'\b(?:dashed|dotted)\s+','',text.strip(),flags=re.I)


def _picture(picture,stages):
    """A picture the image model can draw: a base scene, then one additive edit per later step. With "captions" the
    picture tells the story's introduction in its own captions, one per frame, and the steps follow as the technical
    figure below it."""
    if not isinstance(picture,dict) or not {'base','edits'}<=set(picture)<={'base','edits','captions','labels'}:
        raise ValueError('picture needs base and edits, and may have captions and labels')
    base,edits=picture['base'],picture['edits']
    captions=picture.get('captions')
    if captions is not None:
        if not isinstance(captions,list) or not 1<=len(captions)<=3:
            raise ValueError('a story picture has 1 to 3 captions')
        captions=[_text(c,280) for c in captions]
    frames=len(captions) if captions is not None else stages
    if not isinstance(edits,list) or len(edits)!=frames-1:
        raise ValueError(f'picture needs one edit per {"caption" if captions is not None else "step"} after the first ({frames-1})')
    # An empty edit: that step shares the picture above it and draws none of its own.
    for text,limit in [(base,400)]+[(e,300) for e in edits if e != '']:
        if not isinstance(text,str) or not 3<=len(text.strip())<=limit or any(ord(c)<32 for c in text):
            raise ValueError('picture descriptions are short plain sentences')
    labels=_labels(picture.get('labels'),frames)
    return dict(base=_solid(base),edits=[_solid(e) for e in edits],**({'captions':captions} if captions is not None else {}),
                **({'labels':labels} if labels is not None else {}))


def parse_semantic_reply(raw):
    """Accept one complete JSON lesson, plain answer, clarification, Buzz message to confirm, or confirmation."""
    try:
        if not isinstance(raw,str) or len(raw.encode('utf-8'))>MAX_BYTES:
            raise ValueError('bounded JSON reply required')
        value=json.loads(raw,object_pairs_hook=_pairs,parse_constant=_constant)
        if not isinstance(value,dict) or type(value.get('v')) is not int or value['v']!=1:
            raise ValueError('version 1 reply object required')
        mode=value.get('mode')
        if mode=='story-lesson':
            # The service assembles planner + panel outputs. Accept no source
            # IDs or paths: geometry for EVERY panel is checked before delivery.
            from notebook_panel_shapes import compile_panel_shapes
            from notebook_story_plan import validate_story
            _fields(value,{'v','mode','story','panels'})
            story=validate_story(value['story'])
            compile_panel_shapes(story,value['panels'])
            return dict(mode='lesson',story=story,drafts=value['panels'])
        if mode=='lesson':
            picture=value.pop('picture',None)
            reply=dict(mode=mode,plan=compile_semantic(value))
            if picture is not None:
                try:
                    reply['picture']=_picture(picture,len(reply['plan']['stages']))
                except ValueError as exc:
                    reply['picture_refused']=str(exc)  # the drawn lesson stands; the picture is an extra
            return reply
        if mode=='send':
            # A message the writing asks to post on Buzz, or a handwritten note to text to one of James's contacts.
            # The page shows it and waits for James's yes before it leaves.
            _fields(value,{'v','mode','to','text'}|({'via'} if 'via' in value else set())|({'ink'} if 'ink' in value else set()))
            to,via,ink=value['to'],value.get('via','buzz'),value.get('ink','none')
            if via not in ('buzz','imessage','sms') or ink not in ('above','below','none'):
                raise ValueError('send via is buzz, imessage or sms; ink is above, below or none')
            if (not isinstance(to,list) or not 1<=len(to)<=(3 if via=='buzz' else 1) or
                    any(not isinstance(n,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 '.-]{0,39}",n.strip()) for n in to)):
                raise ValueError('send names one to three Buzz members, or one contact for a text')
            return dict(mode=mode,to=[n.strip() for n in to],text=_text(value['text'],600),
                        **({'via':via,'ink':ink} if via!='buzz' else {}))
        if mode=='confirm':
            _fields(value,{'v','mode','send'})
            if type(value['send']) is not bool:
                raise ValueError('confirm send is true or false')
            return dict(mode=mode,send=value['send'])
        if mode not in ('answer','clarify'):
            raise SemanticError('unsupported_mode','use lesson, story-lesson, answer, clarify, send, or confirm')
        _fields(value,{'v','mode','text'})
        text=value['text']
        if mode=='answer' and isinstance(text,str):
            # Native prose can contain paragraphs; diagram captions cannot.
            # Validate both the whole payload and each line so a line-start
            # heading/path cannot hide behind an earlier paragraph.
            _text(text.replace('\n',' '),1600)
            for line in text.split('\n'):
                if line.strip():_text(line,1600)
                if re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*', line):
                    raise ValueError('plain answers cannot contain raw Markdown tables')
            text=text.strip()
        else:
            text=_text(text,280 if mode=='clarify' else 1600)
        return dict(mode=mode,text=text)
    except SemanticError:
        raise
    except (ValueError,TypeError,KeyError,RecursionError,UnicodeError) as exc:
        raise SemanticError('invalid_schema','invalid semantic reply: '+str(exc)) from exc
