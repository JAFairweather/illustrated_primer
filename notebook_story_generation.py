"""Bounded image -> story -> panels -> complete validated delivery envelope.

No tablet I/O, retries, shared chat, provider selection or publication. The
caller owns the pending page binding. One deadline covers all model calls and
compilation, not a fresh thirty seconds for every panel. Model output remains
typed semantic intent; deterministic compilation owns the stroke geometry.
"""
from copy import deepcopy
import json
import time
import uuid

from notebook_lesson import _pairs, _constant, _fields, _text
from notebook_model_transport import (ModelTransportError, model_request,
                                      call_story_panel_model, _validated_envelope)
from notebook_panel_shapes import compile_panel_shapes
from notebook_story_plan import parse_story, panel_packet, MAX_BYTES
from notebook_semantic_reply import parse_semantic_reply


def _json(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def _prefix(story,length):
    result=deepcopy(story);result['panels']=result['panels'][:length]
    used={p['act'] for p in result['panels']}
    result['acts']=[a for a in result['acts'] if a['id'] in used]
    return result


class _Unavailable(Exception):
    def __init__(self,reason):self.reason=reason


def _decode(raw):
    if not isinstance(raw,str) or len(raw.encode('utf-8'))>MAX_BYTES:
        raise ValueError('bounded story/panel JSON required')
    value=json.loads(raw,object_pairs_hook=_pairs,parse_constant=_constant)
    if isinstance(value,dict) and value.get('mode')=='unavailable':
        _fields(value,{'v','mode','reason'})
        if type(value['v']) is not int or value['v']!=1:
            raise ValueError('version 1 unavailable required')
        raise _Unavailable(_text(value['reason'],280))
    return value


def generate_notebook_story(endpoint,request_id,png,*,deadline_ms=30000,
                            is_current=lambda:True,call=None,clock=time.monotonic,
                            image_context=None,on_answer=None,roles=None):
    """Return only a whole valid lesson or explicit clarification, never partial ink.

    PNG is caller-prepared visual input, not a model-chosen path or transcript.
    Legacy calls use one configured host. Optional owner-fixed production roles
    bind each story/panel call independently; identity changes within a role fail.
    The injected call/clock are for offline tests, not endpoint configuration.
    Optional on_answer enables the separately configured story-stream-v1 host.
    It receives independently validated prose before drawing generation; that
    prose is not a successful visual answer. The caller owns guarded delivery.
    """
    model_request(request_id,png,'',deadline_ms)  # preflight before calls
    if image_context is not None:
        model_request(request_id,png,image_context,deadline_ms)
    streaming=on_answer is not None
    bindings=None;role_metrics=[]
    if roles is not None:
        from notebook_role_transport import (validate_roles, call_production_role,
                                              validate_production_result)
        bindings=validate_roles(roles)
        if streaming or endpoint is not None:
            raise ModelTransportError('invalid_request')
        call=call or call_production_role
    elif streaming:
        if not callable(on_answer): raise ModelTransportError('invalid_request')
        from notebook_story_stream import call_story_stream_model
        call=call or call_story_stream_model
    else:
        call=call or call_story_panel_model
    started=clock();end=started+deadline_ms/1000;metrics=[];first_text=None
    answer_chunks=0;first_answer=None
    def current():
        if not is_current():raise ModelTransportError('cancelled')
        if clock()>=end:raise ModelTransportError('deadline')
        return True
    def deliver(chunk):
        nonlocal answer_chunks,first_answer
        current()
        if first_answer is None: first_answer=round((clock()-started)*1000)
        on_answer(chunk)
        answer_chunks+=1
        current()
    def invoke(task,context):
        nonlocal first_text
        current()
        remaining=max(1,int((end-clock())*1000))
        identity=request_id if not metrics else 'notebook-'+uuid.uuid4().hex
        if image_context is not None:
            context=dict(context,image_context=image_context)
        packet=_json(dict(task=task,context=context))
        model_request(identity,png,packet,remaining)  # never truncate context
        began=clock()
        options=dict(on_answer=deliver if task=='story' else None) if streaming else {}
        role='planner' if task=='story' else 'drawer'
        target=bindings[role]['socket'] if bindings else endpoint
        if bindings: options['expected']=dict(bindings[role]['expected'])
        reply=call(target,identity,png,packet,deadline_ms=remaining,is_current=current,**options)
        current()
        # Validate the injected boundary too; no assumed test/mock privilege.
        if bindings:
            reply=validate_production_result(_json(reply).encode(),identity,expected=bindings[role]['expected'])
        else:
            reply=_validated_envelope(_json(reply).encode(),identity,
                                      'story-stream-v1' if streaming else 'story-panel-v1')
        m=reply['metrics']
        if not bindings and metrics and (m['provider'],m['model'])!=(metrics[0]['provider'],metrics[0]['model']):
            raise ModelTransportError('model_mismatch')
        metrics.append(m)
        if bindings: role_metrics.append(dict(role=role,**m))
        if first_text is None and m['first_text_ms'] is not None:
            first_text=round((began-started)*1000)+m['first_text_ms']
        return reply['text'],_decode(reply['text'])
    try:
        raw,_=invoke('story',dict(input='latest handwritten question in the supplied notebook image'))
        story=parse_story(raw)
        drafts,resolved={},{}
        for number,panel in enumerate(story['panels'],1):
            current()
            context=panel_packet(story,panel['id'])
            base=resolved.get(panel['base'])
            context['base_items']=deepcopy(list(base['items'].values())) if base else []
            _,candidate=invoke('panel',context)
            drafts[panel['id']]=candidate
            resolved=compile_panel_shapes(_prefix(story,number),drafts)['panels']
            current()
        text=_json(dict(v=1,mode='story-lesson',story=story,panels=drafts))
    except _Unavailable as unavailable:
        text=_json(dict(v=1,mode='clarify',text=unavailable.reason))
    # Includes full response byte cap and whole-story validation. Invalid
    # geometry is never salvaged into apparently successful prose.
    parsed=parse_semantic_reply(text)
    current()
    elapsed=round((clock()-started)*1000)
    # Provider timers and local timers can differ slightly; report a bounded
    # first token measurement, not a first-visible-ink claim.
    total=dict(metrics[0],elapsed_ms=elapsed,first_text_ms=min(first_text,elapsed) if first_text is not None else None,
        requested_output_tokens=sum(m['requested_output_tokens'] for m in metrics),
        usage={key:sum(m['usage'].get(key,0) for m in metrics)
               for key in set().union(*(m['usage'] for m in metrics))})
    result=dict(request_id=request_id,response_format='semantic-v1',text=text,parsed=parsed,
                metrics=total,calls=len(metrics))
    if bindings:
        # Do not attribute aggregate usage to the planner's model/effort.
        for key in ('provider','model','reasoning_requested','requested_output_tokens'):
            result['metrics'].pop(key)
        result['role_calls']=role_metrics
    if streaming:
        result['answer_stream']=dict(chunks=answer_chunks,first_validated_answer_ms=first_answer,
                                     respond_to_first_visible_answer_ms=None)
    return result
