"""Pure synthetic sources for measuring native text-anchor semantics.

These are diagnostic stimuli, NOT a coordinate model or insertion permission.
No user page, filesystem, tablet or network input. Each pair differs only in
whether one otherwise identical marker is anchored to native text.
Use native measurements of both members; never infer the answer from a font.
"""
import hashlib
import struct
import uuid

from ink import cid, i4, line_block, sub, tag, vu
from notebook_stroke_asset import _block, _boolean, _foundation, _lww, _string


BOTTOM = (0, 281474976710655)
TOP = (0, 281474976710654)
LAYER, GROUP = (0, 11), (1, 50)
TEXT_X, TEXT_Y, TEXT_WIDTH = -468, 234, 936
GROUP_X = -464


def top_anchor_fixtures(author=None):
    """Paired native stimuli, not an assumed top-anchor coordinate rule.

    Include a prefix insertion and heading/wrapping so that cursor-zero,
    text-bounds top and first-line baseline can be distinguished on device.
    """
    return _fixtures(author, [
        ('top-plain', '\nA\nB', TOP),
        ('top-prefix', '\nA\nB', TOP, '\nP\n'),
        ('top-heading', '\nTitle\nBody', TOP, '', [(0,2)]),
        ('top-wrapped', '\n'+'A '*70+'B', TOP),
        ('top-leading-blanks', '\n\n\nA', TOP),
        ('top-nonblank', 'A\nB', TOP),
    ])


def bottom_anchor_fixtures(author=None):
    """Four independent pages: newline/no-newline × anchored/control.

    The marker has identical style/point bytes apart from its coordinate frame.
    A native bounds difference within each pair can isolate the anchor's Y.
    That observed difference still needs comparison with actual cursor/bounds
    readings before any preservation rule is adopted.
    """
    return _fixtures(author, [('no-terminal-newline', '\nA'), ('terminal-newline', '\nA\n')])


def bottom_anchor_stress_fixtures(author=None):
    """Fixed wrapping/paragraph controls; never derive a coordinate rule."""
    wrapped = '\n' + 'A '*70 + 'B'
    result = _fixtures(author, [
        ('last-paragraph', '\nA\nB'),
        ('wrapped-last-paragraph', wrapped),
        ('wrapped-terminal-newline', wrapped+'\n'),
        ('two-terminal-newlines', '\nA\n\n'),
        ('empty-paragraphs-between', '\nA\n\nB\n\n'),
    ])
    return result


def anchor_boundary_fixtures(author=None):
    """Final-newline and ordinary middle-paragraph controls for peer review."""
    wrapped = '\n' + 'A '*70 + 'B\nC'
    return _fixtures(author, [
        ('single-trailing-paragraph', '\nA\nB\n'),
        ('ordinary-middle-paragraph', '\nA\nB', (1,22)),
        ('ordinary-middle-wrapped', wrapped, (1,162)),
    ])


def anchor_motion_fixtures(author=None):
    """Paired saved snapshots: insert text BEFORE unchanged marker/anchor IDs.

    Only the root text block changes between before/after snapshots. Existing
    character IDs, group origin, anchor ID, marker ID/style/points and all other
    blocks are byte-identical. Unanchored controls isolate unrelated motion.
    This tests native layout of saved states, NOT interactive text editing.
    """
    return _fixtures(author, [
        ('ordinary-before', '\nA\nB', (1,22)),
        ('ordinary-after', '\nA\nB', (1,22), '\nP\n'),
        ('bottom-before', '\nA\nB', BOTTOM),
        ('bottom-after', '\nA\nB', BOTTOM, '\nP\n'),
    ])


def anchor_format_fixtures(author=None):
    """Mixed paragraph sizes/lists, plus a wrapped heading and terminal newline.

    Format encoding/enum reference (no dependency or copied implementation):
    https://github.com/ricklupton/rmscene/blob/main/src/rmscene/scene_stream.py
    https://github.com/ricklupton/rmscene/blob/main/src/rmscene/scene_items.py
    These are stimuli only; native metrics must show that styles took effect.
    Inline bold/italic formatting atoms are NOT covered by these cases.
    """
    return _fixtures(author, [
        ('heading-middle', '\nTitle\nBody\nTail', (1,26), '', [(0,2),(6,1),(11,3)]),
        ('heading-bottom', '\nTitle\nBody\nTail', BOTTOM, '', [(0,1),(6,1),(11,2)]),
        ('heading-terminal', '\nTitle\nBody\nTail\n', BOTTOM, '', [(0,1),(6,1),(11,2),(16,1)]),
        ('list-middle', '\nFirst\nSecond\nTail', (1,26), '', [(0,4),(6,5),(13,1)]),
        ('wrapped-heading-bottom', '\n'+'A '*40+'B', BOTTOM, '', [(0,2)]),
    ])


def _fixtures(author, cases):
    author = uuid.UUID(str(author)) if author is not None else uuid.uuid4()
    result = []
    # Match the native notebook's initial blank paragraph in both variants.
    for case in cases:
        name, text = case[:2]
        anchor_id = case[2] if len(case)>2 else BOTTOM
        prefix = case[3] if len(case)>3 else ''
        formats = case[4] if len(case)>4 else []
        atom = sub(0, cid(2,1,20)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+_string(6,text))
        # A separate CRDT run precedes the original first character. Do not
        # renumber that run or its anchored newline when inserting the prefix.
        if prefix:
            atom += sub(0,cid(2,1,2000)+cid(3,0,0)+cid(4,1,20)+i4(5,0)+_string(6,prefix))
        encoded_formats = vu(len(formats))
        for n,(index,style) in enumerate(formats):
            if prefix or text[index] != '\n' or style not in (1,2,3,4,5):
                raise ValueError('fixed synthetic paragraph format required')
            encoded_formats += b'\x01'+vu(20+index)+cid(1,1,3000+n)+sub(2,bytes([17,style]))
        text_block = _block(7, cid(1,0,0)+
            sub(2,sub(1,sub(1,vu(2 if prefix else 1)+atom))+sub(2,sub(1,encoded_formats)))+
            sub(3,struct.pack('<dd',TEXT_X,TEXT_Y))+tag(4,4)+struct.pack('<f',TEXT_WIDTH))
        text = prefix+text
        for anchored in (False, True):
            raw = _foundation(author)+text_block
            if anchored:
                raw += _block(1,cid(1,*GROUP)+cid(2,0,0)+_boolean(3,True)+sub(4,cid(1,*LAYER)))
                raw += _block(2,cid(1,*GROUP)+_lww(2,(0,0),_string(2,''))+
                    _lww(3,(0,0),_boolean(2,True))+_lww(7,(1,51),cid(2,*anchor_id))+
                    _lww(8,(1,52),tag(2,1)+b'\x02')+
                    _lww(9,(1,53),tag(2,4)+struct.pack('<f',0))+
                    _lww(10,(1,54),tag(2,4)+struct.pack('<f',GROUP_X)),1,2)
                raw += _block(4,cid(1,*LAYER)+cid(2,1,55)+cid(3,0,0)+cid(4,0,0)+
                    i4(5,0)+sub(6,b'\x02'+cid(2,*GROUP)))
            x_offset = 0 if anchored else GROUP_X
            raw += line_block(GROUP if anchored else LAYER,(1,60),(0,0),
                [(200+x_offset,100,2),(300+x_offset,100,2)])
            end_nonempty = len(text.rstrip('\n'))
            paragraph_start = text.rfind('\n', 0, end_nonempty)+1
            indices = sorted({0, 1, paragraph_start, end_nonempty-1, end_nonempty, len(text)})
            if anchor_id not in (BOTTOM, TOP):
                indices = sorted(set(indices) | {len(prefix)+anchor_id[1]-20})
            if formats:
                indices = sorted(set(indices) | {index+1 for index,_ in formats if index+1 <= len(text)})
            result.append(dict(name=name+('-anchored' if anchored else '-control'), data=raw,
                sha256=hashlib.sha256(raw).hexdigest(), anchored=anchored,
                terminal_newline=text.endswith('\n'), length=len(text),
                cursor_indices=indices, anchor_id=list(anchor_id), stroke_count=1,
                **({'paragraph_formats':formats} if formats else {})))
    return result
