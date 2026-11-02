"""Incremental, independently bounded answer prose; terminal story/panel data.

This is an opt-in IPC format, not production activation or tablet authority.
Only complete answer records reach on_answer. Drawing records never do. The
existing producer still validates the complete lesson before returning ink.
"""
import json
from pathlib import Path
import select
import socket
import time

from notebook_lesson import _fields, _pairs, _constant, _text
from notebook_model_transport import (ModelTransportError, model_request,
    _private_socket, _validated_envelope, MAX_RESPONSE)


class AnswerRecords:
    def __init__(self, request_id, *, task, on_answer, is_current):
        if task not in ('story', 'panel') or (task == 'story' and not callable(on_answer)):
            raise ModelTransportError('invalid_request')
        self.request_id, self.task = request_id, task
        self.on_answer, self.is_current = on_answer, is_current
        self.raw, self.answers, self.terminal = [], [], None
        self.size = 0

    def current(self):
        if not self.is_current(): raise ModelTransportError('cancelled')

    def accept(self, event):
        self.current()
        _fields(event, {'request_id','response_format','sequence','record'})
        if (event['request_id'] != self.request_id or
                event['response_format'] != 'story-stream-v1' or
                type(event['sequence']) is not int or event['sequence'] != len(self.raw) or
                self.terminal is not None or len(self.raw) >= 4):
            raise ModelTransportError('invalid_response')
        raw = event['record']
        if not isinstance(raw,str): raise ModelTransportError('invalid_response')
        self.size += len(raw.encode('utf-8'))
        if self.size > 24000: raise ModelTransportError('reply_too_large')
        value = json.loads(raw,object_pairs_hook=_pairs,parse_constant=_constant)
        if not isinstance(value,dict) or type(value.get('v')) is not int or value['v'] != 1:
            raise ModelTransportError('invalid_response')
        if value.get('mode') == 'answer-chunk':
            _fields(value, {'v','mode','seq','text'})
            if (self.task != 'story' or type(value['seq']) is not int or
                    value['seq'] != len(self.answers) or len(self.answers) >= 3):
                raise ModelTransportError('invalid_response')
            text = _text(value['text'],160)
            text.encode('utf-8')  # Reject escaped unpaired surrogates before delivery.
            if sum(map(len,self.answers))+len(text)>400:
                raise ModelTransportError('reply_too_large')
            self.current()
            # Mark consumed BEFORE callback. Callback failure or page change
            # closes the request; there is no retry or replay of this prefix.
            self.raw.append(raw);self.answers.append(text)
            self.on_answer(dict(sequence=value['seq'], text=text))
            self.current()
        else:
            allowed = ('story','unavailable') if self.task == 'story' else ('panel-shapes','unavailable')
            if value.get('mode') not in allowed: raise ModelTransportError('invalid_response')
            if value['mode']=='story' and not self.answers:
                raise ModelTransportError('invalid_response')
            self.raw.append(raw);self.terminal=raw

    def finish(self, raw):
        self.current()
        result = _validated_envelope(raw,self.request_id,'story-stream-v1')
        if self.terminal is None or result['text'] != ''.join(self.raw):
            raise ModelTransportError('invalid_response')
        # Return ONLY the terminal task record. The early answer is not
        # silently inserted again in the final lesson or counted as its success.
        return dict(result,text=self.terminal)


def call_story_stream_model(endpoint,request_id,png,context,*,deadline_ms=30000,
                            is_current=lambda:True,on_answer=None):
    request = model_request(request_id,png,context,deadline_ms)
    if not isinstance(endpoint,str) or Path(endpoint).name == 'notebook-eval.sock':
        raise ModelTransportError('unavailable')
    packet=json.loads(context,object_pairs_hook=_pairs,parse_constant=_constant)
    if not isinstance(packet,dict): raise ModelTransportError('invalid_request')
    _private_socket(endpoint)
    end=time.monotonic()+deadline_ms/1000+2
    def current():
        if not is_current(): raise ModelTransportError('cancelled')
        if time.monotonic()>=end: raise ModelTransportError('deadline')
        return True
    records=AnswerRecords(request_id,task=packet.get('task'),on_answer=on_answer,is_current=current)
    current()
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
            conn.settimeout(min(1,max(.001,end-time.monotonic())))
            conn.connect(endpoint);current()
            conn.settimeout(max(.001,end-time.monotonic()))
            conn.sendall(json.dumps(request,ensure_ascii=False).encode()+b'\n')
            pending=bytearray();size=0
            while True:
                current()
                if not select.select([conn],[],[],min(.1,max(0,end-time.monotonic())))[0]: continue
                part=conn.recv(16384)
                if not part: raise ModelTransportError('incomplete_response')
                size+=len(part);pending.extend(part)
                if size>MAX_RESPONSE: raise ModelTransportError('reply_too_large')
                while b'\n' in pending:
                    current()
                    at=pending.index(10)+1;line=bytes(pending[:at]);del pending[:at]
                    event=json.loads(line,object_pairs_hook=_pairs,parse_constant=_constant)
                    if isinstance(event,dict) and 'record' in event:
                        records.accept(event)
                    else:
                        if pending: raise ModelTransportError('invalid_response')
                        return records.finish(line)
    except ModelTransportError: raise
    except (OSError,TimeoutError): raise ModelTransportError('unavailable') from None
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        raise ModelTransportError('invalid_response') from None
