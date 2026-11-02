"""Fail-closed native stroke session boundary; no automatic device integration.

Current production geometry telemetry deliberately cannot satisfy this lease:
the native UI must implement and test the reservation before any caller wires
this executor to device input. It narrows checks to every event but does NOT
by itself serialize xochitl navigation or distinguish simultaneous human ink.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import uuid


class PenLease:
    def __init__(self, snapshot, request, digest, stage, clock=time.monotonic):
        if not re.fullmatch(r'notebook-[0-9a-f]{32}', request):
            raise ValueError('exact notebook request required')
        if not re.fullmatch(r'[0-9a-f]{64}', digest) or not re.fullmatch(r'[a-z0-9-]{1,80}', stage):
            raise ValueError('bounded compiled stage identity required')
        self.snapshot, self.request, self.digest, self.stage = snapshot, request, digest, stage
        self.clock, self.deadline = clock, clock()+30
        first = self.snapshot()
        self.identity = (first.get('doc'), first.get('page'), first.get('surface'))
        for value in self.identity[:2]:
            if not isinstance(value, str) or str(uuid.UUID(value)) != value:
                raise ValueError('native drawing requires exact document/page UUIDs')
        if not isinstance(self.identity[2], str) or not self.identity[2]:
            raise ValueError('native drawing surface identity required')
        reservation = first.get('reservation') or {}
        self.layer = reservation.get('layer') if isinstance(reservation, dict) else None
        self.view = tuple(first.get('view', []))
        self.check()

    def check(self):
        current = self.snapshot()
        reserve = current.get('reservation') or {}
        if not isinstance(reserve, dict):
            raise RuntimeError('invalid native drawing reservation')
        if (self.clock() > self.deadline or not current.get('fresh') or not current.get('active')
                or current.get('age_ms', 99999) > 750
                or current.get('control_lease') is not True
                or reserve.get('ui_locked') is not True
                or reserve.get('request') != self.request or reserve.get('digest') != self.digest
                or reserve.get('stage') != self.stage or reserve.get('tool') != 17
                or not isinstance(reserve.get('layer'), str) or not reserve['layer']
                or len(reserve['layer']) > 80 or reserve['layer'] != self.layer):
            raise RuntimeError('native drawing reservation is absent, expired or no longer safe')
        if (current.get('doc'), current.get('page'), current.get('surface')) != self.identity:
            raise RuntimeError('native drawing page or view instance changed')
        view = current.get('view', [])
        if (len(view) != 6 or len(self.view) != 6
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in view)
                or any(abs(a-b) > 1e-6 for a, b in zip(view, self.view))):
            raise RuntimeError('native drawing viewport moved')
        return True


class StageJournal:
    """Durable one-attempt claim per request/stage, including across restarts.

    The directory must be an application-owned private writable directory.
    No recovery-by-deletion API is provided: inspect partial ink, do not replay.
    """
    def __init__(self, directory, request, stage, digest):
        if not re.fullmatch(r'notebook-[0-9a-f]{32}', request) or not re.fullmatch(r'[a-z0-9-]{1,80}', stage):
            raise ValueError('canonical stage identity required')
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('compiled program digest required')
        directory = Path(directory)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        name = hashlib.sha256((request+'\n'+stage).encode()).hexdigest()+'.jsonl'
        self.path = directory/name
        self.identity = {'request': request, 'stage': stage, 'digest': digest}
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(directory_fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError('native stage journal directory must be private and owner-only')
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
            self.stream = os.fdopen(fd, 'w')
            try:
                self.record('intent', 0)
                os.fsync(directory_fd)  # Claim survives restart before pen input begins.
            except BaseException:
                self.stream.close()
                raise
        finally:
            os.close(directory_fd)

    def record(self, state, completed):
        if state not in ('intent', 'stroke', 'visible', 'attention') or type(completed) is not int or completed < 0:
            raise ValueError('invalid native stage journal event')
        self.stream.write(json.dumps(dict(self.identity, state=state, completed=completed))+'\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


def execute_stage(lease, projected, directory, emit, verify_visible):
    """Run reviewed paths with a real UI lease and caller-supplied guarded input.

    emit(path, guard) must use the pen driver's per-event guard and release on
    failure. A successful result means visible, NOT saved/persisted. No live
    emit/UI-reservation adapter is connected by this module.
    """
    if projected.get('kind') != 'projected-native-pen-plan' or projected.get('digest') != lease.digest or projected.get('stage') != lease.stage:
        raise ValueError('projected geometry does not match the reserved stage')
    paths = projected.get('paths')
    if not isinstance(paths, list) or not paths or len(paths) > 64 or sum(map(len, paths)) > 6000:
        raise ValueError('bounded nonempty projected paths required')
    checked = []
    for path in paths:
        if not isinstance(path, (list, tuple)) or len(path) < 2:
            raise ValueError('native stage contains an invalid stroke')
        points = []
        for point in path:
            if (not isinstance(point, (list, tuple)) or len(point) != 2
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in point)
                    or not (130 <= point[0] <= 1304 and 210 <= point[1] <= 1792)):
                raise ValueError('native stage points must stay on safe paper')
            if points and math.dist(points[-1], point) > 2.01:
                raise ValueError('native stage must be densely sampled')
            points.append(tuple(point))
        checked.append(tuple(points))
    paths = tuple(checked)  # Never let caller mutation change a validated stroke.
    lease.check()  # Must fail BEFORE journal/input for telemetry-only callers.
    journal = StageJournal(directory, lease.request, lease.stage, lease.digest)
    completed = 0
    try:
        for path in paths:
            lease.check()
            emit(path, lease.check)
            completed += 1
            journal.record('stroke', completed)
        lease.check()
        if verify_visible(projected) is not True:
            raise RuntimeError('native drawing did not pass visible geometry verification')
        journal.record('visible', completed)
        return {'state': 'visible', 'strokes': completed, 'persisted': False}
    except BaseException:
        try:
            journal.record('attention', completed)
        except OSError:
            pass  # Preserve the input failure; durable initial claim still blocks replay.
        raise
    finally:
        journal.close()
