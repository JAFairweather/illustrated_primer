"""One-shot, view-only moves for an explicitly scoped preservation audit.

No pen, content, selection, page switch, or persistent setting commands. A move
is consumed before delivery; a lost/refused command is never automatically
replayed. The tablet independently rechecks identity, geometry and pen idleness.
"""
import copy
import threading
import time
import uuid


class ViewAudit:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.pending = None

    def arm(self, context, dy):
        if type(dy) is not int or not 1 <= abs(dy) <= 1200:
            raise ValueError('audit move must be a nonzero integer within 1200 pixels')
        if not context.get('available') or not context.get('fresh') or not context.get('active'):
            raise ValueError('audit move requires a fresh active native view')
        if context.get('size') != [1404, 1872] or context.get('view', [])[:4] != [1, 0, 0, 1]:
            raise ValueError('audit move requires the verified unzoomed orientation')
        command = {key: copy.deepcopy(context[key]) for key in
                   ('doc', 'page', 'surface', 'view', 'content_revision', 'ink_revision')}
        command.update(id=uuid.uuid4().hex, dy=dy)
        with self.lock:
            if self.pending and self.clock() < self.pending[0]:
                raise ValueError('another audit move is awaiting delivery')
            self.pending = (self.clock()+3, command)
        return {'armed': True, 'id': command['id'], 'expires_in': 3, 'content_write': False}

    def command(self, context, idle=True):
        with self.lock:
            pending, self.pending = self.pending, None
        if not pending or self.clock() >= pending[0] or not idle or not context.get('active'):
            return None
        command = pending[1]
        if any(context.get(key) != command[key] for key in
               ('doc', 'page', 'surface', 'view', 'content_revision', 'ink_revision')):
            return None
        return copy.deepcopy(command)
