"""Request-bound native drawing stage claims, completion and saved-ink proof.

This module never controls a device. The native client must hold actual input
routing/UI disabled; the server supplies fresh geometry and independent source
integrity/blank-layout preflight callbacks. Claims survive process restarts and
are never replayed. Captions/prose are not stored in this journal.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import threading
import uuid

from ink import strokes, line, last_item
from notebook_ink_preservation import (layout_request, preservation_baseline, compare_baseline,
                                       NativeTextLengthMismatch, NativeLayoutUnsupported)

# A validated lesson can carry 12,000 playback points across six stages. The
# old metadata-only 64 KiB read cap rejected valid plans after registration.
# Keep claims/ACKs small; only plans use this matching read/write byte budget.
# A 19-page handwritten lesson is ~1 MB (each hand block ~90 KB): James's 2026-11-01 12:54 reply went over 1 MiB
# and was held. The tablet still bounds each block on its own.
MAX_PLAN_BYTES = 4_194_304


def capture_layout(raw):
    """Keep legacy captures compatible; opt in to exact saved anchor sets.

    At most 64 distinct cursor samples per existing capture transaction. This
    is a bounded live-query budget, not permission to omit additional anchors.
    Oversized pages stay held; no subset is accepted as preservation proof.
    This is the explicit multi-capable adapter policy, not a change to the
    legacy layout_request API: retry only its anchor-capability exception and
    revalidate all saved bytes. A malformed page must not trigger fallback.
    """
    try:
        plan = layout_request(raw, include_length=True)
    except NativeLayoutUnsupported:
        plan = layout_request(raw, allow_multiple=True, include_length=True)
    if len(plan['indices']) > 64:
        raise ValueError('native layout capture exceeds 64 distinct anchors')
    return plan


def saved_stroke_records(data, *, fingerprints=False):
    """Bounded identity-bearing records, not an arbitrary CRDT resolver.

    Duplicate IDs/tombstone revisions are ambiguous here and fail closed. The
    normal native saved snapshots we support have one record per line item.
    Author-map bytes must remain unchanged between baseline and final proof;
    otherwise numeric author IDs alone are not a stable identity comparison.
    """
    if not isinstance(data, bytes) or not 43 <= len(data) < 16_777_216 or not data.startswith(b'reMarkable .lines file, version=6'):
        raise ValueError('bounded native saved page required')
    records, authors, offset = {}, [], 43
    while offset < len(data):
        if len(data)-offset < 8:
            raise ValueError('truncated native block header')
        size, _, _, version, kind = struct.unpack_from('<IBBBB', data, offset)
        end = offset+8+size
        if end > len(data):
            raise ValueError('truncated native block')
        raw = data[offset:end]
        if kind == 9:
            authors.append(hashlib.sha256(raw).hexdigest())
        if kind == 5:
            try:
                parent, item = last_item(raw)
                identity = (*parent, *item)
                parsed = line(raw[8:], version)
            except (IndexError, struct.error, ValueError) as exc:
                raise ValueError('unreadable native line identity or geometry') from exc
            if identity in records:
                raise ValueError('ambiguous repeated native line identity; inspect saved page')
            records[identity] = hashlib.sha256(raw).hexdigest() if fingerprints else parsed
        offset = end
    return records, authors


def _uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('canonical native notebook UUID required')
    return value


def _request(value):
    if not isinstance(value, str) or not re.fullmatch(r'notebook-[0-9a-f]{32}', value):
        raise ValueError('exact notebook request required')
    return value


class InkRuns:
    def __init__(self, directory, text_key=None):
        self.directory = Path(directory)
        self.lock = threading.RLock()
        self.text_key = text_key
        # Transient half of the existing insertion/proof exchange, not another
        # durable job/lease system. A restart discards unfinished measurements.
        self.captures = {}
        self.measurements = {}

    def _text_key(self):
        key = self.text_key() if callable(self.text_key) else self.text_key
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError('external native text preservation key unavailable')
        return key

    def require_unprepared(self, request):
        """Reject reply replacement after ANY existing capture or journal work.

        This reads the existing state only; it never clears a claim or treats
        an unreadable journal as an empty one. Callers hold lock through their
        replacement transaction so registration cannot race this check.
        """
        _request(request)
        with self.lock:
            if any(key[0] == request for key in (*self.captures, *self.measurements)):
                raise ValueError('native drawing capture already prepared')
            directory = self._directory()
            try:
                with os.scandir(directory) as entries:
                    if any(entry.name.startswith((request+'.', request+'-')) for entry in entries):
                        raise ValueError('native drawing journal already prepared')
            finally:
                os.close(directory)

    def stage_started(self, request):
        """Has any drawing stage of this reply been claimed (and so possibly pasted)? Unreadable means yes."""
        _request(request)
        with self.lock:
            try:
                directory = self._directory()
            except (OSError, ValueError):
                return True
            try:
                with os.scandir(directory) as entries:
                    return any(entry.name.startswith(request+'-') for entry in entries)
            except OSError:
                return True
            finally:
                os.close(directory)

    @staticmethod
    def _capture_context(context):
        if not context.get('fresh') or not context.get('active'):
            raise ValueError('native layout capture requires a fresh active page')
        return {k: context[k] for k in ('doc', 'page', 'surface', 'content_revision', 'ink_revision')}

    def begin_capture(self, request, phase, raw, context):
        """Bind a native cursor query to server-read bytes and input revisions.

        Only the authenticated native adapter may return the measurement. A
        hash alone cannot authenticate coordinates; finish_capture also checks
        the outstanding server-issued command and independently rereads bytes.
        """
        _request(request)
        if phase not in ('before', 'after'):
            raise ValueError('invalid native layout phase')
        command = dict(capture_layout(raw), request=request, phase=phase,
                       **self._capture_context(context))
        if not command['indices']:
            raise ValueError('unanchored page needs no native layout query')
        with self.lock:
            if len(self.captures) >= 8 and (request, phase) not in self.captures:
                raise ValueError('native layout capture budget exceeded')
            self.captures[(request, phase)] = (command, raw)
        return copy.deepcopy(command)

    def finish_capture(self, reply, snapshot, read_page):
        """No caller can choose a file, cursor index or old baseline here."""
        if (not isinstance(reply, dict) or set(reply) not in ({'command', 'first'}, {'command', 'samples'})
                or not isinstance(reply['command'], dict)):
            raise ValueError('exact native layout response required')
        command = reply['command']
        key = (command.get('request'), command.get('phase'))
        with self.lock:
            capture = self.captures.get(key)
            if not capture or capture[0] != command:
                raise ValueError('native layout response has no matching outstanding capture')
            field = 'samples' if 'anchors' in command else 'first'
            if set(reply) != {'command', field}:
                raise ValueError('native layout response does not match requested format')
            raw = capture[1]
            expected = {k: command[k] for k in ('doc', 'page', 'surface', 'content_revision', 'ink_revision')}
            def ready():
                current = snapshot()
                # Identity/revision changes are NOT a transient loading wait.
                if any(current.get(k) != value for k,value in expected.items()):
                    raise ValueError('page or input changed during native layout capture')
                if current.get('fresh') and current.get('active'):
                    return True
                if command['phase'] != 'after':
                    raise ValueError('native layout capture requires a fresh active page')
                return False
            def wait_for_context(reason='native layout telemetry is not fresh and active'):
                del self.captures[key]
                return {'measured': False, 'state': 'waiting', 'reason': reason}
            if not ready():
                return wait_for_context()
            current = read_page(command['doc']+'/'+command['page']+'.rm')
            still_ready = ready()
            if current != raw:
                if command['phase'] == 'after':
                    # Autosave may land DURING the read-only cursor query.
                    # Reject malformed snapshots; otherwise discard all old
                    # coordinates and require a new hash-bound measurement.
                    # The final old-content comparison is still mandatory.
                    capture_layout(current)
                    return wait_for_context('native saved snapshot changed; new measurement required')
                raise ValueError('saved page or input changed during native layout capture')
            if not still_ready:
                return wait_for_context()
            measurement = dict(sha256=command['sha256'], **{field: reply[field]})
            try:
                preservation_baseline(raw, measurement, text_key=self._text_key())
            except NativeTextLengthMismatch as exc:
                # Final native text can precede autosave. Never cache mismatched
                # coordinates or accept them as proof. The existing bounded
                # post-write poll must obtain a NEW capture of the saved page.
                # Before-write captures and every identity/input/hash failure
                # remain hard failures; they cannot establish a safe baseline.
                if command['phase'] != 'after':
                    raise
                del self.captures[key]
                return {'measured': False, 'state': 'waiting', 'reason': str(exc)}
            if len(self.measurements) >= 16:
                self.measurements.pop(next(iter(self.measurements)))
            self.measurements[(command['request'], command['sha256'])] = dict(
                measurement=copy.deepcopy(measurement), command=copy.deepcopy(command))
            del self.captures[key]
            return {'measured': True}

    def _directory(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(fd)
            raise ValueError('native ink journal must be private and owner-only')
        return fd

    def _write_once(self, name, value):
        directory = self._directory()
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(directory)
        finally:
            os.close(directory)

    def _read(self, name, budget=65536):
        directory = self._directory()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise ValueError('invalid native ink journal file')
                raw = stream.read(budget+1)
            if len(raw) > budget:
                raise ValueError('native ink journal exceeds its budget')
            return json.loads(raw)
        finally:
            os.close(directory)

    def register(self, request, path, context, blocks, before, *, preservation=False, blank_prose=False):
        _request(request)
        doc, page = path.removesuffix('.rm').split('/')
        _uuid(doc); _uuid(page)
        if path != doc+'/'+page+'.rm':
            raise ValueError('exact native page path required')
        selected = [copy.deepcopy(block) for block in blocks if block.get('kind') == 'ink']
        from notebook_stroke_asset import validate_native_ink_budget
        validate_native_ink_budget(selected)
        if (not context.get('fresh') or not context.get('active') or
                context.get('doc') != doc or context.get('page') != page):
            raise ValueError('native drawing registration requires the active original page')
        for block in selected:
            _uuid(block['source_doc']); _uuid(block['source_page'])
            if not re.fullmatch(r'[a-z0-9-]{1,80}', block['scene']) or not re.fullmatch(r'[a-z0-9-]{1,80}', block['stage']):
                raise ValueError('bounded authored scene/stage required')
        if preservation:
            needed = capture_layout(before)
            capture = self.measurements.get((request, needed['sha256']))
            identity = self._capture_context(context)
            if needed['indices'] and (capture is None or any(capture['command'][k] != value for k,value in identity.items())):
                # Fixed diagnostics only: explain a repeated query without
                # exposing saved text/geometry or reusing stale measurements.
                reason = ('context_changed' if capture is not None else
                          'snapshot_changed' if any(key[0] == request for key in self.measurements) else
                          'initial')
                return {'measure_layout': self.begin_capture(request, 'before', before, context),
                        'layout_reason': reason}
            baseline = preservation_baseline(before, capture['measurement'] if capture else None, text_key=self._text_key())
            baseline['native_capture'] = copy.deepcopy(capture)
        else:
            existing, authors = saved_stroke_records(before, fingerprints=True)
            baseline = dict(records=sorted(existing.items()), authors=authors)
        # Identity plus opaque fingerprint, never user prose/photos/coordinates.
        # Checking only new strokes could falsely approve loss of existing ink.
        if len(json.dumps(baseline).encode()) > 8_388_608:
            raise ValueError('native stroke identity baseline exceeds its budget')
        record = dict(request=request, path=path, doc=doc, page=page, surface=context['surface'],
                      ink_revision=context['ink_revision'], blocks=selected, baseline_version=3 if preservation else 2)
        if blank_prose:
            # The reply types no words, only blank label lines: its ink may start just below the question, over those
            # lines, as long as it stays below any typed text already on the page.
            x, y, width, height = context['text_bounds']
            record['text_floor'] = y+height+20 if height > 0 else None
        if len(json.dumps(record).encode()) > MAX_PLAN_BYTES:
            raise ValueError('native ink plan exceeds its budget')
        with self.lock:
            self._write_once(request+'.before-ids.json', baseline)
            self._write_once(request+'.plan.json', record)
        return {'registered': len(selected)}

    def committed(self, request):
        """Has every drawing stage of this reply committed on the tablet? Not proof that the page saved it."""
        with self.lock:
            plan = self._plan(request)
            for block in plan['blocks']:
                try:
                    self._read(self._name(request, block['scene'], block['stage'], '.done.json'))
                except FileNotFoundError:
                    return False
            return True

    def _plan(self, request):
        record = self._read(_request(request)+'.plan.json', MAX_PLAN_BYTES)
        if record.get('request') != request:
            raise ValueError('native drawing plan identity mismatch')
        _uuid(record['doc']); _uuid(record['page'])
        if record.get('path') != record['doc']+'/'+record['page']+'.rm':
            raise ValueError('native drawing plan path mismatch')
        return record

    def _stage(self, plan, scene, stage):
        for block in plan['blocks']:
            if block['scene'] == scene and block['stage'] == stage:
                _uuid(block['source_doc']); _uuid(block['source_page'])
                return block
        raise ValueError('native stage is not in this exact reply')

    def _name(self, request, scene, stage, suffix):
        # No caller-controlled filename fragments except the canonical request.
        return _request(request)+'-'+hashlib.sha256((str(scene)+'/'+str(stage)).encode()).hexdigest()+suffix

    def _identity(self, plan, query, context):
        changed = ([k for k in ('fresh', 'active') if not context.get(k)] +
                   [k for k in ('doc', 'page', 'surface') if context.get(k) != plan[k]] +
                   ['query page'] * (query.get('page') != plan['path']) +
                   ['query surface'] * (query.get('surface') != plan['surface']) +
                   ['ink_revision'] * (context.get('ink_revision') != plan['ink_revision']) +
                   ['query ink_revision'] * (query.get('ink_revision') != plan['ink_revision']) +
                   ['content_revision'] * (context.get('content_revision') != query.get('revision')))
        if changed:  # the names say which check failed, so a refusal is explainable from the log
            raise ValueError('native ink page, input or layout revision changed: '+', '.join(changed))

    def claim(self, query, snapshot, preflight):
        fields = {'request', 'page', 'scene', 'stage', 'surface', 'revision', 'ink_revision', 'origin', 'ui_locked'}
        if not isinstance(query, dict) or set(query) != fields or query['ui_locked'] is not True:
            raise ValueError('exact locked native ink claim required')
        origin = query['origin']
        if (not isinstance(origin, list) or len(origin) != 2 or
                any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1000000 for v in origin)):
            raise ValueError('bounded finite native drawing origin required')
        with self.lock:
            plan = self._plan(query['request'])
            block = self._stage(plan, query['scene'], query['stage'])
            context = snapshot()
            self._identity(plan, query, context)
            preceding = [b for b in plan['blocks'] if b['scene'] == block['scene'] and b['stage_index'] < block['stage_index']]
            for previous in preceding:
                self._read(self._name(plan['request'], previous['scene'], previous['stage'], '.done.json'))
            if preceding:
                first = self._read(self._name(plan['request'], preceding[0]['scene'], preceding[0]['stage'], '.claim.json'))
                if any(abs(a-b) > 1e-6 for a,b in zip(origin, first['origin'])):
                    raise ValueError('native drawing stages must share the reserved origin')
            else:
                if block['stage_index'] != 0:
                    raise ValueError('native drawing must begin at its first stage')
                x, y, width, height = context['text_bounds']
                # Handwritten captions add no text, so a later region may sit below the regions already written.
                bottom = y+height
                for other in plan['blocks']:
                    if other['scene'] == block['scene'] or other['stage_index'] != 0:
                        continue
                    try:
                        self._read(self._name(plan['request'], other['scene'], other['stage'], '.done.json'))
                        placed = self._read(self._name(plan['request'], other['scene'], other['stage'], '.claim.json'))
                    except FileNotFoundError:
                        continue
                    bottom = max(bottom, placed['origin'][1]+other['height']+30)
                floor = y+height+20
                if 'text_floor' in plan:
                    floor = -math.inf if plan['text_floor'] is None else plan['text_floor']
                # A region wider than the typed column (handwriting) spans it, centred within safe paper.
                across = (origin[0] <= x+1 and origin[0]+block['width'] >= x+width-1 if block['width'] > width else
                          x-1 <= origin[0] <= x+width-block['width']+1)
                if not across or not floor <= origin[1] <= bottom+300:
                    raise ValueError('native diagram must be reserved below the new native prose')
            preflight(copy.deepcopy(block), copy.deepcopy(query), context, not preceding)
            self._identity(plan, query, snapshot())  # I/O may have taken seconds
            self._write_once(self._name(plan['request'], block['scene'], block['stage'], '.claim.json'),
                             dict(query, source_sha256=block['sha256']))
            return {'claimed': True, 'request': plan['request'], 'scene': block['scene'], 'stage': block['stage']}

    def complete(self, query):
        if not isinstance(query, dict) or set(query) != {'request', 'scene', 'stage'}:
            raise ValueError('exact native ink completion required')
        with self.lock:
            plan = self._plan(query['request'])
            block = self._stage(plan, query['scene'], query['stage'])
            self._read(self._name(plan['request'], block['scene'], block['stage'], '.claim.json'))
            try:
                self._write_once(self._name(plan['request'], block['scene'], block['stage'], '.done.json'), query)
            except FileExistsError:
                pass  # Commit ACK is idempotent; it never dispatches another paste.
        return {'accepted': True, 'persisted': False}

    def saved_proof(self, request, read_page, read_source, snapshot=None):
        """Match all stage shapes in saved ink; never equate visible with saved.

        Saved points can be group-local. Match one common translation PER asset,
        never compare raw .rm y to display y. Reopen visual acceptance remains a
        separate check; this reader does not resolve arbitrary CRDT deletions.
        """
        with self.lock:
            plan = self._plan(request)
            for block in plan['blocks']:
                try:
                    self._read(self._name(request, block['scene'], block['stage'], '.done.json'))
                except FileNotFoundError:
                    return {'state': 'waiting', 'reason': 'native stage has not committed'}
            raw = read_page(plan['path'])
            if not raw:
                return {'state': 'waiting', 'reason': 'native page save pending'}
            if plan.get('baseline_version') not in (2, 3):
                return {'state': 'waiting', 'reason': 'legacy drawing has no pre-insertion preservation proof; inspect manually'}
            before = self._read(request+'.before-ids.json', 8_388_608)
            if plan['baseline_version'] == 3:
                try:
                    needed = capture_layout(raw)
                    capture = self.measurements.get((request, needed['sha256']))
                    context = snapshot() if snapshot else None
                    # James may write while a reply draws: new strokes change the ink revision, but the
                    # proof below still needs every old stroke unchanged, every reply stroke found, and a
                    # layout measured at the CURRENT revision. A different page or surface still holds it.
                    if context is not None and (not context.get('fresh') or not context.get('active') or
                            any(context.get(k) != plan[k] for k in ('doc', 'page', 'surface'))):
                        raise ValueError('native page changed')
                    if needed['indices'] and (capture is None or context is not None and
                            any(capture['command'][k] != context[k] for k in ('doc', 'page', 'surface', 'ink_revision', 'content_revision'))):
                        if snapshot is None:
                            return {'state': 'waiting', 'reason': 'native layout measurement required'}
                        return {'state': 'waiting', 'measure_layout': self.begin_capture(request, 'after', raw, context)}
                    after = preservation_baseline(raw, capture['measurement'] if capture else None, text_key=self._text_key())
                    existing = compare_baseline(before, after)
                    target = [value['points'] for value in after['lines'] if tuple(value['id']) not in existing]
                except ValueError as exc:
                    return {'state': 'waiting', 'reason': 'pre-existing ink preservation unproven: '+str(exc)}
            else:
                # Never retrofit old v2 attempts: their original raw geometry
                # cannot be recovered from opaque fingerprints after insertion.
                existing = {tuple(identity): digest for identity, digest in before['records']}
                records, authors = saved_stroke_records(raw)
                if authors != before['authors']:
                    return {'state': 'waiting', 'reason': 'native author map changed; identity proof unavailable'}
                fingerprints, _ = saved_stroke_records(raw, fingerprints=True)
                if any(fingerprints.get(identity) != digest for identity, digest in existing.items()):
                    return {'state': 'waiting', 'reason': 'pre-existing ink is missing or changed; inspect saved page'}
                target = [value[1] for identity, value in records.items() if identity not in existing and value]
            used = set()
            for block in plan['blocks']:
                data = read_source(block)
                if hashlib.sha256(data).hexdigest() != block['sha256']:
                    raise ValueError('native source integrity changed')
                source = [points for _,points,_ in strokes(data)]
                if 'reveal' in block:
                    from notebook_ink_reveal import reveal_source_paths
                    source = reveal_source_paths(block, data)
                if 'playback' in block:
                    from notebook_ink_playback import validate_playback
                    validate_playback(block, data)
                if len(source) != block['stroke_count']:
                    raise ValueError('native source stroke count changed')
                found = match_translated(source, target, used)
                if found is None:
                    return {'state': 'waiting', 'reason': 'native stroke geometry save pending'}
                used.update(found)
            return {'state': 'persisted', 'strokes': len(used),
                    'evidence': 'preserved-old-ink-and-new-saved-native-stroke-identities-and-geometry'}


def match_translated(source, target, used):
    """Find the full asset, not a convenient single line or bounding rectangle."""
    if not source:
        return None
    anchor = max(source, key=len)
    def matches(expected, actual, dx, dy):
        return len(expected) == len(actual) and all(abs(p[0]+dx-q[0]) <= .003 and abs(p[1]+dy-q[1]) <= .003
                                                   for p,q in zip(expected,actual))
    for index, candidate in enumerate(target):
        if index in used or len(anchor) != len(candidate):
            continue
        dx, dy = candidate[0][0]-anchor[0][0], candidate[0][1]-anchor[0][1]
        if not matches(anchor,candidate,dx,dy):
            continue
        found = set()
        for path in source:
            match = next((i for i, points in enumerate(target) if i not in used and i not in found and matches(path,points,dx,dy)), None)
            if match is None:
                break
            found.add(match)
        if len(found) == len(source):
            return found
    return None
