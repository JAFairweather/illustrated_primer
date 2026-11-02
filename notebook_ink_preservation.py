"""Preservation comparison using independently measured native anchors.

No translation is inferred by fitting strokes. The native adapter must supply
hash-bound layout evidence through its authenticated request/capture exchange;
this module cannot authenticate arbitrary measurements by itself. Unsupported
scene topology/versions fail rather than becoming approximate proof.
"""
import hashlib
import hmac
import json
import math
import secrets
import struct


ROOT = (0, 1)
END = (0, 0)
TOP = (0, 281474976710654)
BOTTOM = (0, 281474976710655)
ROUNDING = .0001  # sub-pixel float32 tolerance; controlled live pair has ZERO error


class NativeLayoutUnsupported(ValueError):
    """Legacy anchor query cannot express this page; not a validation bypass.

    A multi-capable caller may reparse the ENTIRE page in exact-anchor mode.
    Malformed text, topology, identity, deletion and resource errors remain
    ordinary ValueErrors and must not trigger a compatibility fallback.
    """


class NativeTextLengthMismatch(ValueError):
    """A capture is unusable until native and serialized text agree exactly."""
    def __init__(self, native, saved):
        super().__init__(f'native text length disagrees with saved snapshot: native={native}, saved={saved}, delta={native-saved}')


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError('truncated native field')
        value = self.data[self.pos:self.pos+size]
        self.pos += size
        return value

    def uint(self):
        value = 0
        for shift in range(0, 63, 7):
            byte = self.take(1)[0]
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError('excessive native integer')

    def field(self, index, kind):
        if self.uint() != index * 16 + kind:
            raise ValueError('unsupported native field order or type')
        if kind == 15:
            return (self.take(1)[0], self.uint())
        if kind == 12:
            return self.take(struct.unpack('<I', self.take(4))[0])
        return self.take({1: 1, 4: 4, 8: 8}[kind])

    def done(self):
        if self.pos != len(self.data):
            raise ValueError('unsupported trailing native fields')


def _fields(data):
    """Unique tagged fields; bytes retained for non-coordinate comparisons."""
    reader, result = Reader(data), {}
    while reader.pos < len(data):
        start = reader.pos
        tag = reader.uint()
        index, kind = divmod(tag, 16)
        reader.pos = start
        if index in result or kind not in (1, 4, 8, 12, 15):
            raise ValueError('duplicate or unsupported native field')
        result[index] = (kind, reader.field(index, kind))
    return result


def _get(fields, index, kind):
    if index not in fields or fields[index][0] != kind:
        raise ValueError('missing or unsupported native field')
    return fields[index][1]


def _lww(fields, index, kind):
    inner = _fields(_get(fields, index, 12))
    if set(inner) != {1, 2}:
        raise ValueError('unsupported native last-write value')
    _get(inner, 1, 15)
    return _get(inner, 2, kind)


def _finite(value):
    if not math.isfinite(value) or abs(value) > 1000000:
        raise ValueError('unsupported native coordinate')
    return value


def _envelope(fields):
    if set(fields) not in ({1, 2, 3, 4, 5}, {1, 2, 3, 4, 5, 6}):
        raise ValueError('unsupported native item envelope')
    ids = [_get(fields, n, 15) for n in range(1, 5)]
    deleted = struct.unpack('<I', _get(fields, 5, 4))[0]
    if deleted and 6 in fields:
        raise ValueError('ambiguous live/deleted native item')
    if not deleted and 6 not in fields:
        raise ValueError('native item has neither value nor deletion')
    return ids[0], ids[1], deleted


def _leading_text_ids(payload):
    """Resolve at most 32 leading newline IDs from one unambiguous live run.

    Every returned ID has an exact UTF-16 cursor index (newlines are one unit).
    Non-leading or split-run anchors stay unsupported. No guessed font metrics.
    """
    root = _fields(payload)
    if _get(root, 1, 15) != END:
        raise ValueError('unsupported root text identity')
    section = _fields(_get(root, 2, 12))
    items = Reader(_get(_fields(_get(section, 1, 12)), 1, 12))
    count = items.uint()
    if not 1 <= count <= 10000:
        raise ValueError('excessive native text atom count')
    heads, ids = [], set()
    for _ in range(count):
        atom = _fields(items.field(0, 12))
        identity = _get(atom, 2, 15)
        if identity in ids or set(atom) != {2, 3, 4, 5, 6}:
            raise ValueError('ambiguous native text atom')
        ids.add(identity)
        if struct.unpack('<I', _get(atom, 5, 4))[0]:
            raise ValueError('deleted native text is not supported')
        if _get(atom, 3, 15) == END:
            heads.append((identity, _get(atom, 6, 12)))
        _get(atom, 4, 15)
    items.done()
    # Native saves can coalesce the leading newline with subsequent text.
    # The run's identity still denotes its FIRST character (cursor index zero).
    # Decode the complete bounded run; never find a later newline or guess an
    # anchor from geometry. Full text ordering is validated separately below.
    if len(heads) != 1:
        raise NativeLayoutUnsupported('first native text anchor is not an unambiguous newline')
    value = Reader(heads[0][1])
    size = value.uint()
    if not 1 <= size <= 262144 or value.take(1) != b'\x01':
        raise ValueError('unsupported first native text encoding')
    string = value.take(size).decode('utf-8')
    value.done()
    if not string.startswith('\n'):
        raise NativeLayoutUnsupported('first native text anchor is not an unambiguous newline')
    count = min(32, len(string)-len(string.lstrip('\n')))
    return [(heads[0][0][0], heads[0][0][1]+i) for i in range(count)]


def _text_state(payload, text_key, *, cursor_indices=False):
    """Retain keyed per-character/style fingerprints, not plaintext prose.

    A native append can split/coalesce string runs, so retain implicit character
    IDs, not whole atom hashes. Deleted/formatting atoms are currently unsupported
    and fail before insertion; do not silently skip edited or unfamiliar text.
    """
    if payload is None:
        return None
    if not isinstance(text_key, bytes) or len(text_key) < 32:
        raise ValueError('external native text preservation key required')
    root = _fields(payload)
    if set(root) not in ({1, 2, 3, 4}, {1, 2, 3, 4, 5}):
        raise ValueError('unsupported root text fields')
    if _get(root, 1, 15) != END:
        raise ValueError('unsupported root text identity')
    section = _fields(_get(root, 2, 12))
    if set(section) != {1, 2}:
        raise ValueError('unsupported root text sections')
    items = Reader(_get(_fields(_get(section, 1, 12)), 1, 12))
    count = items.uint()
    if not 1 <= count <= 10000:
        raise ValueError('excessive native text atom count')
    chars, links, units, length = {}, {}, {}, 0
    newlines, blank = set(), True
    key_for = lambda identity: str(identity[0])+':'+str(identity[1])
    for _ in range(count):
        atom = _fields(items.field(0, 12))
        if set(atom) != {2, 3, 4, 5, 6} or _get(atom, 5, 4) != b'\0'*4:
            raise ValueError('unsupported deleted or formatted native text')
        identity = _get(atom, 2, 15)
        value = Reader(_get(atom, 6, 12))
        size = value.uint()
        if size > 262144 or value.take(1) != b'\x01':
            raise ValueError('unsupported native text encoding')
        string = value.take(size).decode('utf-8')
        value.done()
        if not string or len(chars)+len(string) > 262144:
            raise ValueError('native text exceeds preservation budget')
        blank = blank and string.isspace()
        for offset, character in enumerate(string):
            key = key_for((identity[0], identity[1]+offset))
            if key in chars:
                raise ValueError('ambiguous native text identity')
            # Include the character identity: the private journal must reveal
            # neither a dictionary-testable character nor its repeat frequency.
            chars[key] = hmac.new(text_key, key.encode()+b'\0'+character.encode(), 'sha256').hexdigest()
            if cursor_indices:
                units[key] = len(character.encode('utf-16-le'))//2
                if character == '\n':
                    newlines.add(key)
            left = (identity[0],identity[1]+offset-1) if offset else _get(atom,3,15)
            right = (identity[0],identity[1]+offset+1) if offset+1 < len(string) else _get(atom,4,15)
            links[key] = (key_for(left), key_for(right))
        length += len(string.encode('utf-16-le'))//2
    items.done()
    # Resolve only a unique ordering. Unknown references, cycles and concurrent
    # ambiguous edits are not guessed. New native text must append to this order.
    edges = {key:set() for key in chars}
    incoming = {key:0 for key in chars}
    for key,(left,right) in links.items():
        for a,b in ((left,key),(key,right)):
            if '0:0' in (a,b):
                continue
            if a not in chars or b not in chars:
                raise ValueError('unresolved native text reference')
            if b not in edges[a]:
                edges[a].add(b); incoming[b] += 1
    ready = [key for key,n in incoming.items() if n==0]
    order = []
    while ready:
        if len(ready) != 1:
            raise ValueError('ambiguous native text ordering')
        key = ready.pop(); order.append(key)
        for following in edges[key]:
            incoming[following] -= 1
            if incoming[following] == 0:
                ready.append(following)
    if len(order) != len(chars):
        raise ValueError('cyclic native text ordering')
    indices, cursor = {}, 0
    if cursor_indices:
        for key in order:
            indices[key] = cursor
            cursor += units[key]
        if cursor != length:
            raise ValueError('native cursor length disagrees with saved text')
    formats = Reader(_get(_fields(_get(section, 2, 12)), 1, 12))
    count = formats.uint()
    if count > 10000:
        raise ValueError('excessive native paragraph formats')
    styles = {}
    for _ in range(count):
        key = str(formats.take(1)[0])+':'+str(formats.uint())
        formats.field(1, 15)  # timestamp may change without changing the style
        value = formats.field(2, 12)
        if key in styles:
            raise ValueError('ambiguous native paragraph style')
        styles[key] = hashlib.sha256(value).hexdigest()
    formats.done()
    result = dict(chars=chars, styles=styles, length=length, order=order, blank=blank,
                  layout=hashlib.sha256(_get(root, 3, 12)+_get(root, 4, 4)+
                                       (_get(root, 5, 12) if 5 in root else b'')).hexdigest())
    if cursor_indices:
        result['cursor_indices'] = indices
        result['newline_ids'] = newlines
    return result


def saved_text_cursor_indices(payload):
    """Resolve exact ordinary CRDT character IDs to native UTF-16 indices.

    This is index mapping only, NOT a coordinate measurement or insertion
    authorization. Top/bottom sentinel anchors intentionally have no entry:
    their native geometric semantics must be established separately. Deleted,
    formatted, ambiguous and unresolved atoms retain the strict text checks.
    The extra mapping is transient and never added to preservation journals.
    """
    state = _text_state(payload, secrets.token_bytes(32), cursor_indices=True)
    if state is None:
        raise ValueError('saved native text required for cursor mapping')
    return {'length': state['length'], 'indices': state['cursor_indices']}


def _page_scene(data, measurement=None, *, layout_only=False, text_key=None, allow_multiple=False, include_length=False):
    """Resolve supported saved strokes to page coordinates, retaining all style.

    measurement = {sha256: exact saved page hash, first: [x,y,lineheight,length]}.
    The legacy field name first denotes the requested leading-newline anchor,
    which may be later than index zero when native saves coalesce blank lines.
    The opt-in multi-anchor format replaces first with samples, each exactly
    [cursor_index,x,y,lineheight,length], covering the server-derived indices.
    Top-sentinel Y is native cursor zero, including non-newline initial text
    (six controlled native pairs, 2026-10-29). It is NOT text-bounds top.
    Bottom-sentinel Y is the final saved character's row (controlled native
    plain-text evidence). Sampled groups use saved X origin, not cursor advance;
    ordinary middle-paragraph controls establish this distinction as well.
    It MUST come from the native diagnostic, not from this page's stroke shapes.
    This function cannot authenticate an arbitrary caller's measurements.
    """
    if (not isinstance(data, bytes) or not 43 <= len(data) < 16777216 or
            not data.startswith(b'reMarkable .lines file, version=6')):
        raise ValueError('bounded v6 saved page required')
    sampled = isinstance(measurement, dict) and 'samples' in measurement
    allow_multiple = allow_multiple or sampled
    samples = {}
    if sampled:
        if (set(measurement) != {'sha256','samples'} or
                measurement['sha256'] != hashlib.sha256(data).hexdigest() or
                not isinstance(measurement['samples'],list) or not measurement['samples']):
            raise ValueError('native anchor samples are missing, stale or invalid')
        for sample in measurement['samples']:
            if (not isinstance(sample,list) or len(sample)!=5 or
                    any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1000000 for v in sample) or
                    type(sample[0]) is not int or sample[0]<0 or sample[0]>=262144 or
                    sample[3]<=0 or type(sample[4]) is not int or sample[4]<1 or
                    sample[0]>=sample[4] or sample[0] in samples):
                raise ValueError('invalid or duplicate native cursor sample')
            samples[sample[0]] = sample[1:]
    elif measurement is not None:
        if (set(measurement) != {'sha256', 'first'} or
                measurement['sha256'] != hashlib.sha256(data).hexdigest() or
                not isinstance(measurement['first'], list) or len(measurement['first']) != 4 or
                any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1000000 for v in measurement['first']) or
                measurement['first'][2] <= 0 or type(measurement['first'][3]) is not int or measurement['first'][3] < 1):
            raise ValueError('native anchor measurement is missing, stale or invalid')
    nodes, parents, links, lines, deleted, authors, text = {}, {}, {}, [], [], [], None
    media, tree_history, tree_ids, live_items = [], [], set(), []
    identities, position, point_count = set(), 43, 0
    while position < len(data):
        if position + 8 > len(data):
            raise ValueError('truncated native block')
        size, unused, minimum, version, kind = struct.unpack_from('<IBBBB', data, position)
        end = position + 8 + size
        if end > len(data) or unused != 0 or minimum > version:
            raise ValueError('invalid native block')
        raw, payload = data[position:end], data[position+8:end]
        position = end
        if kind == 9:
            authors.append(hashlib.sha256(raw).hexdigest())
        elif kind == 1:
            f = _fields(payload)
            if version != 1 or set(f) != {1, 2, 3, 4}:
                raise ValueError('unsupported native tree revision')
            node = _get(f, 1, 15)
            p = _fields(_get(f, 4, 12))
            if node in tree_ids or set(p) != {1}:
                raise ValueError('ambiguous native tree parent')
            tree_ids.add(node)
            parent, referenced, update = _get(p, 1, 15), _get(f, 2, 15), _get(f, 3, 1)
            if referenced == END and update == b'\x01':
                parents[node] = parent
            elif referenced != END and update == b'\x00' and parent == END:
                # Observed after native regrouping/reopen. Do not infer general
                # revision semantics: only an independently EMPTY leaf group
                # can make this record irrelevant to preserved visible content.
                tree_history.append((node, referenced))
            else:
                raise ValueError('unsupported native tree revision')
        elif kind == 2:
            f = _fields(payload)
            node = _get(f, 1, 15)
            if version not in (1, 2) or node in nodes or set(f) not in ({1, 2, 3}, {1, 2, 3, 7, 8, 9, 10}):
                raise ValueError('unsupported or duplicate native group')
            if _lww(f, 3, 1) != b'\x01':
                raise ValueError('hidden native group cannot prove visible ink')
            nodes[node] = f
        elif kind == 8:
            # An erased item saved as its own block (seen 2026-10-30 after an
            # erase on a test page): the same dead ID range as a removed line,
            # nothing more. It goes through the same overlap checks below.
            f = _fields(payload)
            parent, item, removed = _envelope(f)
            if version != 1 or set(f) != {1, 2, 3, 4, 5} or not 0 < removed <= 100000:
                raise ValueError('unsupported native tombstone block')
            identity = (*parent, *item)
            if identity in identities:
                raise ValueError('duplicate native item')
            identities.add(identity)
            deleted.append((kind, parent, item, removed))
        elif kind in (4, 5, 15):
            f = _fields(payload)
            parent, item, removed = _envelope(f)
            identity = (*parent, *item)
            if identity in identities:
                raise ValueError('duplicate native item')
            identities.add(identity)
            if removed:
                if kind not in (5, 15) or version != 2 or removed > 100000:
                    raise ValueError('unsupported group deletion')
                deleted.append((kind, parent, item, removed))
                continue
            live_items.append((parent, item))
            value = _get(f, 6, 12)
            if kind == 15:
                # Preserve the ENTIRE opaque image value, identity and resolved
                # parent origin. Do not guess image matrix/resource semantics.
                # New media has a separate saved-resource proof in the adapter.
                if version != 2 or not value.startswith(b'\x07') or len(media) >= 256:
                    raise ValueError('unsupported native image item')
                media.append(dict(id=identity, parent=parent,
                                  value=hashlib.sha256(value).hexdigest()))
                continue
            if kind == 4:
                if version != 1 or not value.startswith(b'\x02'):
                    raise ValueError('unsupported native group link')
                v = _fields(value[1:])
                child = _get(v, 2, 15)
                if set(v) != {2} or child in links:
                    raise ValueError('duplicate native group link')
                links[child] = parent
                continue
            if version != 2 or not value.startswith(b'\x03'):
                raise ValueError('unsupported native line version')
            v = _fields(value[1:])
            if not {1, 2, 3, 4, 5, 6} <= set(v) or set(v)-{1, 2, 3, 4, 5, 6, 7, 8}:
                raise ValueError('unsupported native line attributes')
            _get(v, 1, 4); _get(v, 2, 4); _get(v, 3, 8); _get(v, 4, 4); _get(v, 6, 15)
            _finite(struct.unpack('<d', v[3][1])[0])
            _finite(struct.unpack('<f', v[4][1])[0])
            move = _get(v, 7, 15) if 7 in v else None
            if 8 in v:
                _get(v, 8, 4)  # optional exact RGBA bytes are part of style
            packed = _get(v, 5, 12)
            if not packed or len(packed) % 14 or len(packed) > 1400000:
                raise ValueError('invalid native point list')
            point_count += len(packed)//14
            if len(lines) >= 4096 or point_count > 262144:
                raise ValueError('native preservation comparison exceeds its budget')
            points = []
            for offset in range(0, len(packed), 14):
                x, y = struct.unpack_from('<ff', packed, offset)
                points.append((_finite(x), _finite(y), packed[offset+8:offset+14]))
            # Field 6 is the stroke timestamp, not a visual pen attribute.
            # Native reanchoring can update it while preserving every point,
            # pressure byte and move lineage (controlled tablet pair 2026-10-28).
            # Still parse/validate it above; exclude only this metadata from
            # appearance comparison. Field 7 is checked separately as lineage.
            lines.append(dict(id=identity, parent=parent, author=item[0], move=move, points=points,
                              style={n: entry for n, entry in v.items() if n not in (5, 6, 7)}))
        elif kind == 7:
            if text is not None or version != 1:
                raise ValueError('ambiguous native root text')
            text = payload
        elif kind not in (0, 10, 13, 14):
            raise ValueError('unsupported native scene block')
    if ROOT not in nodes or ROOT in parents or ROOT in links or set(parents) != set(links):
        raise ValueError('incomplete native scene topology')
    if parents != links or set(nodes) != set(parents) | {ROOT}:
        raise ValueError('native scene topology disagrees')
    inert = set()
    occupied = {parent for parent, _ in live_items} | set(parents.values())
    for event, target in tree_history:
        if event in nodes or target not in parents or target in inert or target in occupied:
            raise ValueError('native tree history does not reference a unique empty leaf')
        inert.add(target)
    # Dead ranges belong to a parent's item-ID namespace, not just to lines.
    # Check every live item (including images/group links) even for layout-only
    # requests, so a historical deletion cannot hide a live value.
    ranges = {}
    for kind, parent, item, count in deleted:
        if parent not in nodes:
            raise ValueError('unknown tombstone parent')
        key, low, high = (parent, item[0]), item[1], item[1]+count
        if any(not (high <= a or b <= low) for a, b in ranges.get(key, [])):
            raise ValueError('overlapping native tombstones')
        ranges.setdefault(key, []).append((low, high))
    for parent, item in live_items:
        if any(a <= item[1] < b for a,b in ranges.get((parent, item[0]), [])):
            raise ValueError('live native item overlaps a tombstone')
    # The opt-in path resolves the complete, unique CRDT character order below.
    # A valid prefix insertion can leave multiple runs with left=END; the legacy
    # one-head heuristic must not reject that stronger ordering proof first.
    anchored = [f for node, f in nodes.items() if 7 in f and node not in inert]
    if not allow_multiple and any(_lww(f, 7, 15) == TOP for f in anchored):
        # Select the exact-order/sample path before the legacy leading-newline
        # heuristic; TOP is also valid when the saved text starts with a letter.
        raise NativeLayoutUnsupported('top anchor requires exact native cursor samples')
    leading = _leading_text_ids(text) if anchored and text is not None and not allow_multiple else []
    text_state = _text_state(text, text_key if text_key is not None else secrets.token_bytes(32),
                             cursor_indices=allow_multiple)
    if measurement is not None:
        if text_state is None:
            raise ValueError('native text is absent from saved snapshot')
        for value in samples.values() if sampled else [measurement['first']]:
            if value[3] != text_state['length']:
                raise NativeTextLengthMismatch(value[3], text_state['length'])
    anchors = {_lww(f, 7, 15) for f in anchored}
    if len(anchors) > 1 and not allow_multiple:
        raise NativeLayoutUnsupported('multiple native text anchors are not supported')
    first = next(iter(anchors), None)
    anchor_indices = {}
    for f in anchored:
        identity = _lww(f, 7, 15)
        if _lww(f, 8, 1) != b'\x02':
            raise ValueError('unsupported native text anchor')
        if allow_multiple:
            if text_state is None:
                raise ValueError('native text required for anchored groups')
            key = str(identity[0])+':'+str(identity[1])
            if identity == TOP:
                if not text_state['order']:
                    raise ValueError('top anchor requires nonempty saved text')
                index = 0
            elif identity == BOTTOM:
                # Controlled native plain-text pairs support the final SAVED
                # character's row, including a newline, not the empty end cursor.
                # Use its exact UTF-16 start, never length-1 inside a surrogate.
                if not text_state['order']:
                    raise ValueError('bottom anchor requires nonempty saved text')
                index = text_state['cursor_indices'][text_state['order'][-1]]
            elif key in text_state['newline_ids']:
                index = text_state['cursor_indices'][key]
            else:
                raise ValueError('unsupported native text anchor')
            anchor_indices[identity] = index
        elif first not in leading:
            raise NativeLayoutUnsupported('unsupported native text anchor')
    if sampled and set(samples) != set(anchor_indices.values()):
        raise ValueError('native samples must cover exactly the saved anchors')
    if layout_only:
        if allow_multiple and anchors:
            return {'sha256': hashlib.sha256(data).hexdigest(),
                    'indices': sorted(set(anchor_indices.values())), 'length': text_state['length'],
                    'anchors': [{'id':list(key),'index':anchor_indices[key]} for key in sorted(anchor_indices)]}
        result = {'sha256': hashlib.sha256(data).hexdigest(), 'indices': [leading.index(first)] if anchored else [],
                  'anchor': list(first) if anchored else None}
        if include_length and text_state is not None:
            result['length'] = text_state['length']
        return result
    transforms = {}
    def transform(node, visiting=()):
        if node in transforms:
            return transforms[node]
        if node not in nodes or node in visiting or len(visiting) >= 8:
            raise ValueError('unknown or cyclic native group')
        origin = (0, 0) if node == ROOT else transform(parents[node], (*visiting, node))
        f = nodes[node]
        if 7 in f:
            identity = _lww(f,7,15)
            if (not measurement or (not sampled and identity != first) or _lww(f, 8, 1) != b'\x02' or origin != (0, 0)):
                raise ValueError('unsupported or unmeasured native text anchor')
            value = samples[anchor_indices[identity]] if sampled else measurement['first']
            x = _finite(struct.unpack('<f', _lww(f, 10, 4))[0])
            _finite(struct.unpack('<f', _lww(f, 9, 4))[0])
            # A cursor at a nonempty newline is horizontally advanced, but
            # native anchored ink uses the group's saved X origin. Keep the
            # narrower legacy check; sampled world geometry still compares
            # every old point and detects any changed origin independently.
            if not sampled and abs(x-value[0]) > ROUNDING:
                raise ValueError('native group origin disagrees with measured text')
            origin = (x, value[1])
        transforms[node] = origin
        return origin
    for node in nodes:
        if node not in inert:
            transform(node)
    # A compact tombstone is permissible only as an unambiguous dead ID range;
    # every prior LIVE stroke must still be consumed by the comparison below.
    for line in lines:
        dx, dy = transform(line['parent'])
        line['points'] = [(x+dx, y+dy, attrs) for x,y,attrs in line['points']]
    for item in media:
        item['origin'] = transform(item['parent'])
    if text_state is not None:
        text_state.pop('cursor_indices',None)
        text_state.pop('newline_ids',None)
    return lines, authors, media, text_state


def layout_request(data, *, allow_multiple=False, include_length=False):
    """Server-derived hash and cursor indices; no caller-selected page or index.

    Legacy callers support one leading-newline mode-2 anchor only. Explicit
    multi-anchor callers resolve ordinary newline IDs and the bottom sentinel
    to exact saved UTF-16 indices; they must measure every requested cursor.
    This does not itself establish preservation or authorize any page mutation.
    include_length adds the validated saved UTF-16 length to legacy requests
    without changing their single-cursor measurement/response format.
    """
    # Default callers retain legacy-only behavior. The authenticated InkRuns
    # adapter explicitly retries NativeLayoutUnsupported with allow_multiple;
    # ordinary validation errors never authorize that compatibility fallback.
    return _page_scene(data, layout_only=True, allow_multiple=allow_multiple, include_length=include_length)


def page_strokes(data, measurement=None):
    lines, authors, _, _ = _page_scene(data, measurement)
    return lines, authors


def preservation_baseline(data, measurement=None, *, text_key):
    """JSON-safe resolved geometry for the EXISTING private before-ink journal.

    No plaintext root text, photograph, image URL or raw page is retained. Text
    uses a key held OUTSIDE the journal, not dictionary-testable character hashes.
    Identity/length/order and geometry remain private metadata in the journal.
    """
    if not isinstance(text_key, bytes) or len(text_key) < 32:
        raise ValueError('external native text preservation key required')
    lines, authors, media, text_state = _page_scene(data, measurement, text_key=text_key)
    packed = []
    for line in lines:
        style = [(n, kind, value.hex() if isinstance(value, bytes) else list(value))
                 for n, (kind, value) in sorted(line['style'].items())]
        packed.append(dict(id=list(line['id']), author=line['author'],
                           move=list(line['move']) if line['move'] is not None else None,
                           style=hashlib.sha256(json.dumps(style).encode()).hexdigest(),
                           points=[[x, y, attrs.hex()] for x, y, attrs in line['points']]))
    return dict(sha256=hashlib.sha256(data).hexdigest(), style_version=2, authors=authors, lines=packed, text=text_state,
                media=[dict(id=list(item['id']), value=item['value'], origin=list(item['origin'])) for item in media])


def compare_preserved(before, after, before_measurement=None, after_measurement=None):
    """Consume every old line uniquely; return matched AFTER identities only.

    Complete style and every non-coordinate point byte must be identical. No
    best-fit translation, partial-stroke test or bounding-box match is allowed.
    """
    # Ephemeral for direct offline comparison; never persisted as a baseline.
    key = secrets.token_bytes(32)
    return compare_baseline(preservation_baseline(before, before_measurement, text_key=key),
                            preservation_baseline(after, after_measurement, text_key=key))


def compare_baseline(before, after):
    """Compare server-created normalized snapshots, including existing images."""
    # Old journals hashed timestamps into style. Do not reinterpret their
    # opaque hashes or retroactively acknowledge interrupted replies.
    if before.get('style_version', 1) != after.get('style_version', 1):
        raise ValueError('native style comparison version changed; inspect saved page')
    old, new = before['lines'], after['lines']
    if before['authors'] != after['authors']:
        raise ValueError('native author map changed')
    text, updated = before.get('text'), after.get('text')
    if text is not None:
        rest = iter(updated['order'] if updated is not None else ())
        # Blank lines show nothing: a reply's own blank lines may go in before them (cell division, 10-31), as long as
        # every old one survives unchanged and in order. Journals from before the blank flag stay strict.
        kept = updated is not None and (updated['order'][:len(text['order'])] == text['order'] or
                                        text.get('blank') is True and all(key in rest for key in text['order']))
        if not kept or text['layout'] != updated['layout'] or any(
                updated[k].get(identity) != value for k in ('chars', 'styles') for identity,value in text[k].items()):
            raise ValueError('pre-existing native text missing, changed or moved')
    images = {tuple(item['id']): item for item in after['media']}
    for item in before['media']:
        if images.get(tuple(item['id'])) != item:
            raise ValueError('pre-existing native image missing, changed or moved')
    used = set()
    for a in old:
        candidates = []
        for index, b in enumerate(new):
            if (a['author'] != b['author'] or a['style'] != b['style'] or len(a['points']) != len(b['points'])):
                continue
            if all(attrs == other and abs(x-u) <= ROUNDING and abs(y-v) <= ROUNDING
                   for (x,y,attrs),(u,v,other) in zip(a['points'], b['points'])):
                candidates.append(index)
        if len(candidates) != 1 or candidates[0] in used:
            raise ValueError('old native stroke missing, changed or ambiguous')
        b = new[candidates[0]]
        if (a['id'] != b['id'] and b['move'] != a['id'][2:] and
                not (a['move'] is not None and b['move'] == a['move'])):
            raise ValueError('native move lineage does not preserve the old item')
        used.add(candidates[0])
    return {tuple(new[index]['id']) for index in used}


def compare_text_append(before, after, expected, *, text_key, leading_newlines=0):
    """Prove one exact append using the existing measured preservation snapshots.

    The caller owns page/request/input locking and hash-bound native layout
    captures. This comparison grants no insertion, retry, or final-success
    authority. In particular, native length/cursor settlement alone cannot
    establish it. No new journal or plaintext transcript is created.
    """
    if not isinstance(text_key, bytes) or len(text_key) < 32:
        raise ValueError('external native text preservation key required')
    if (not isinstance(expected, str) or not 1 <= len(expected) <= 2000 or
            type(leading_newlines) is not int or not 0 <= leading_newlines <= 160):
        raise ValueError('bounded expected native append required')
    try:
        expected.encode('utf-8')
        units = len(expected.encode('utf-16-le'))//2
    except UnicodeError:
        raise ValueError('valid Unicode native append required') from None
    compare_baseline(before, after)  # ALL existing ink, images, text and layout.
    if len(after['lines']) != len(before['lines']) or len(after['media']) != len(before['media']):
        raise ValueError('native text append contains unrelated ink or media')
    old, new = before.get('text'), after.get('text')
    if new is None:
        raise ValueError('saved native append is absent')
    previous = old['order'] if old is not None else []
    initial_length = old['length'] if old is not None else 0
    added = new['order'][len(previous):]
    wanted = '\n'*leading_newlines + expected
    if (len(added) != len(wanted) or
            new['length'] != initial_length + leading_newlines + units):
        raise ValueError('saved native append range disagrees')
    for identity, character in zip(added, wanted):
        fingerprint = hmac.new(text_key, identity.encode()+b'\0'+character.encode(),
                               'sha256').hexdigest()
        if not hmac.compare_digest(new['chars'][identity], fingerprint):
            raise ValueError('saved native append content disagrees')
    # A style added to an OLD character is also an intervening edit, even if
    # the previous snapshot had no explicit style for that character.
    old_styles = old['styles'] if old is not None else {}
    new_styles = set(new['styles']) - set(old_styles)
    added_newlines = {identity for identity, character in zip(added,wanted) if character == '\n'}
    if not new_styles <= added_newlines:
        raise ValueError('native append changed an existing or unrelated paragraph style')
    return {'start': initial_length + leading_newlines, 'end': new['length'],
            'characters': units, 'gap': leading_newlines}
