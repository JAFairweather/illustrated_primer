"""One bounded hidden-asset diagnostic, armed by local admin only.

Loading/source cloning never affects the foreground. A separate blank-fixture
paste diagnostic requires independent source/blank preflight and durable claim;
it is NOT a general notebook response adapter or raw pen-input permission.
Results contain status/counts, not notebook content.
Optional ink_bounds is native document-wide itemsBoundingRect telemetry, NOT
the bounds of an individual anchored group or a preservation measurement.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid


class NativeProbe:
    def __init__(self, clock=time.monotonic, claims=None):
        self.clock = clock
        self.lock = threading.Lock()
        self.job = None
        self.result = None
        self.claims = Path(claims) if claims is not None else None

    def arm(self, body, context, source_sha256=None):
        fields = {'doc', 'page', 'surface', 'source_doc', 'source_page'}
        if isinstance(body, dict) and 'cursor_index' in body:
            if (body.get('operation') != 'text-anchor' or type(body['cursor_index']) is not int or
                    not 0 <= body['cursor_index'] <= 262144):
                raise ValueError('bounded read-only text cursor index required')
            fields.add('cursor_index')
        if isinstance(body, dict) and body.get('operation') == 'import-source':
            fields.add('source_parent')
        if not isinstance(body, dict) or set(body) not in (fields, fields | {'operation', 'expected_strokes'}):
            raise ValueError('invalid native probe fields')
        operation = body.get('operation', 'load')
        expected = body.get('expected_strokes', 0)
        if operation not in ('load', 'clone-source', 'paste-blank-test', 'import-source', 'text-anchor') or type(expected) is not int or not 0 <= expected <= 64:
            raise ValueError('invalid source diagnostic operation or stroke count')
        if operation in ('clone-source', 'paste-blank-test', 'import-source') and not expected:
            raise ValueError('source clone probe requires an expected stroke count')
        if operation in ('paste-blank-test', 'import-source', 'text-anchor') and (not isinstance(source_sha256, str) or
                len(source_sha256) != 64 or any(c not in '0123456789abcdef' for c in source_sha256)):
            raise ValueError('blank paste source must pass the independent integrity preflight')
        for field in fields-{'surface', 'cursor_index'}:
            if not isinstance(body[field], str) or str(uuid.UUID(body[field])) != body[field]:
                raise ValueError('native probe requires canonical UUIDs')
        if (not context.get('fresh') or not context.get('active') or
                any(context.get(k) != body[k] for k in ('doc', 'page', 'surface'))):
            raise ValueError('native probe requires the current active page/surface')
        if operation == 'text-anchor' and expected != 0:
            raise ValueError('text anchor probe cannot select strokes')
        if body['doc'] == body['source_doc'] and not (operation == 'text-anchor' and body['page'] != body['source_page']):
            raise ValueError('native probe source must be a separate asset document')
        with self.lock:
            if self.job and self.job['expires'] > self.clock() and self.result is None:
                raise ValueError('native probe is already pending')
            self.job = dict(copy.deepcopy(body), operation=operation, expected_strokes=expected,
                            id=str(uuid.uuid4()), expires=self.clock()+60,
                            revision=context.get('content_revision'), ink=context.get('ink_revision'), claimed=False,
                            source_sha256=source_sha256)
            self.result = None
            return {'armed': True, 'id': self.job['id'], 'expires_in': 60}

    def claim(self, body, context):
        """Durable one-attempt claim for a separately preflighted blank fixture.

        The caller MUST also verify source integrity and blank visible/saved
        destination on every claim. The tablet independently holds native input
        disabled before calling this. This is NOT a general response adapter.
        """
        fields = {'id', 'doc', 'page', 'surface', 'ui_locked'}
        if not isinstance(body, dict) or set(body) != fields or body['ui_locked'] is not True:
            raise ValueError('native blank paste requires the exact locked page')
        with self.lock:
            job = self.job
            if (not job or self.result is not None or job['claimed'] or self.clock() >= job['expires'] or
                    job['operation'] != 'paste-blank-test' or any(body[k] != job[k] for k in fields-{'ui_locked'}) or
                    not context.get('fresh') or not context.get('active') or
                    any(context.get(k) != job[k] for k in ('doc', 'page', 'surface')) or
                    context.get('content_revision') != job['revision'] or context.get('ink_revision') != job['ink']):
                raise ValueError('native blank paste identity or revision changed')
            if self.claims is None:
                raise ValueError('durable native claim store unavailable')
            self.claims.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory = os.open(self.claims, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                info = os.fstat(directory)
                if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise ValueError('native claim directory must be private and owner-only')
                # Destination-wide, not job-ID-wide: restarting/rearming cannot
                # turn an interrupted attempt into another paste on that page.
                name = hashlib.sha256((job['doc']+'/'+job['page']).encode()).hexdigest()+'.json'
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                with os.fdopen(fd, 'w') as stream:
                    json.dump({k: job[k] for k in ('id', 'doc', 'page', 'source_doc', 'source_page')}, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(directory)
            finally:
                os.close(directory)
            job['claimed'] = True
            return {'claimed': True, 'id': job['id']}

    def current_job(self):
        with self.lock:
            return copy.deepcopy(self.job)

    def command(self, body):
        with self.lock:
            if (not self.job or self.result is not None or self.job['expires'] <= self.clock() or
                    not body.get('active') or any(body.get(k) != self.job[k] for k in ('doc', 'page', 'surface'))):
                return None
            keys = ('id', 'doc', 'page', 'surface', 'source_doc', 'source_page',
                    'operation', 'expected_strokes', 'revision', 'ink')
            if self.job['operation'] == 'import-source':
                keys += ('source_parent',)
            if 'cursor_index' in self.job:
                keys += ('cursor_index',)
            return {k: self.job[k] for k in keys}

    def complete(self, body):
        fields = {'id', 'state', 'view_active', 'page_ready', 'controller',
                  'working', 'clone_selected', 'select_rect', 'select_area', 'select_all'}
        if isinstance(body, dict) and 'clone_value' in body:
            fields.add('clone_value')
        if isinstance(body, dict) and 'text_anchor' in body:
            fields.add('text_anchor')
            anchor = body['text_anchor']
            if (not isinstance(anchor, list) or len(anchor) != 4 or
                    any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1000000 for v in anchor) or
                    anchor[2] <= 0 or type(anchor[3]) is not int or anchor[3] < 1):
                raise ValueError('invalid first text anchor coordinates')
        if isinstance(body, dict) and ('text_cursor_index' in body or 'text_bounds' in body):
            fields |= {'text_cursor_index', 'text_bounds'}
            bounds = body.get('text_bounds')
            if (type(body.get('text_cursor_index')) is not int or not 0 <= body['text_cursor_index'] <= 262144 or
                    not isinstance(bounds, list) or len(bounds) != 4 or
                    any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1000000 for v in bounds) or
                    bounds[2] <= 0 or bounds[3] <= 0):
                raise ValueError('invalid native cursor or text bounds')
        if isinstance(body, dict) and 'ink_bounds' in body:
            fields.add('ink_bounds')
            bounds = body['ink_bounds']
            if (not isinstance(bounds,list) or len(bounds)!=4 or
                    any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1000000 for v in bounds) or
                    bounds[2]<0 or bounds[3]<0):
                raise ValueError('invalid native item bounds')
        for field in ('imported_doc', 'imported_page'):
            if isinstance(body, dict) and field in body:
                fields.add(field)
                value = body[field]
                if value is not None and (not isinstance(value, str) or str(uuid.UUID(value)) != value):
                    raise ValueError('invalid imported source identity')
        if isinstance(body, dict) and set(body) == fields | {'selected', 'cloned'}:
            for key in ('selected', 'cloned'):
                if type(body[key]) is not int or not 0 <= body[key] <= 64:
                    raise ValueError('invalid native clone count')
            fields |= {'selected', 'cloned'}
        if (not isinstance(body, dict) or set(body) != fields or
                body['state'] not in ('loaded', 'cloned', 'pasted', 'text-anchor', 'unavailable', 'timeout') or
                any(type(body[k]) is not bool for k in fields-{'id', 'state', 'selected', 'cloned', 'imported_doc', 'imported_page', 'text_anchor', 'text_cursor_index', 'text_bounds', 'ink_bounds'})):
            raise ValueError('invalid native probe result')
        with self.lock:
            if not self.job or body['id'] != self.job['id'] or self.result is not None:
                raise ValueError('native probe result is stale or already received')
            if self.clock() >= self.job['expires']:
                raise ValueError('native probe expired')
            if any(k in body for k in ('text_cursor_index','text_bounds','ink_bounds')) or (body['state']=='text-anchor' and 'cursor_index' in self.job):
                if (self.job['operation'] != 'text-anchor' or body['state'] != 'text-anchor' or
                        'cursor_index' not in self.job or body.get('text_cursor_index') != self.job['cursor_index'] or
                        'text_anchor' not in body or body['text_cursor_index'] > body['text_anchor'][3] or
                        'text_bounds' not in body):
                    raise ValueError('cursor result does not match the requested source index')
            if body['state'] == 'text-anchor' or 'text_anchor' in body:
                if (self.job['operation'] != 'text-anchor' or body['state'] != 'text-anchor' or
                        'text_anchor' not in body or body.get('selected', 0) or body.get('cloned', 0) or
                        body.get('clone_value', False) or not all(body[k] for k in ('view_active', 'page_ready', 'controller')) or body['working']):
                    raise ValueError('text anchor requires the read-only ready source probe')
            if ('imported_doc' in body or 'imported_page' in body) and self.job['operation'] != 'import-source':
                raise ValueError('unexpected imported source identity')
            if self.job['operation'] == 'import-source' and body['state'] == 'cloned' and (
                    not body.get('imported_doc') or not body.get('imported_page') or body['imported_doc'] == self.job['doc']):
                raise ValueError('import probe requires a separate discovered document')
            if body['state'] == 'cloned' and (self.job['operation'] not in ('clone-source', 'import-source') or
                    body.get('selected') != self.job['expected_strokes'] or
                    (body.get('cloned') != self.job['expected_strokes'] and body.get('clone_value') is not True)):
                raise ValueError('native cloned item count does not match the isolated asset')
            if body['state'] == 'pasted' and (self.job['operation'] != 'paste-blank-test' or not self.job['claimed'] or
                    body.get('selected') != self.job['expected_strokes'] or body.get('clone_value') is not True):
                raise ValueError('native paste has no durable attempt or source proof')
            self.result = copy.deepcopy(body)
        return {'accepted': True}

    def snapshot(self):
        with self.lock:
            if not self.job:
                return {'state': 'none'}
            return {'id': self.job['id'], 'state': ('complete' if self.result else
                    'expired' if self.clock() >= self.job['expires'] else 'waiting'),
                    'result': copy.deepcopy(self.result)}
