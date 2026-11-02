"""Synthetic geometry only; real controlled tablet pair is checked separately."""
import hashlib
import struct
import unittest
import uuid

from ink import blocks, cid, i4, sub, tag, vu, line_block
from notebook_stroke_asset import _foundation, _block, _lww, _boolean, _string
from notebook_ink_preservation import (compare_preserved, page_strokes, _fields, layout_request,
                                       preservation_baseline, saved_text_cursor_indices)


AUTHOR = uuid.UUID('11111111-2222-3333-4444-555555555555')
LAYER, GROUP, ANCHOR = (0, 11), (1, 29), (1, 28)
END_ID = (0, 0)
ORIGIN = (-464, 267.59375)
KEY = b'synthetic-test-only-text-key-0001'


def encode(fields):
    result = b''
    for n, (kind, value) in fields.items():
        result += cid(n, *value) if kind == 15 else sub(n, value) if kind == 12 else tag(n, kind)+value
    return result


def moved_line(index, points, move=True):
    raw = line_block(GROUP, (1, 34+index), (0, 0),
                     [(x-ORIGIN[0], y-ORIGIN[1], w) for x,y,w in points])
    if move:
        f = _fields(raw[8:]); f[6] = (12, f[6][1]+cid(7, 1, 15+index))
        raw = _block(5, encode(f), 2, 2)
    return raw


def fixture():
    base = _foundation(AUTHOR)
    paths = [[(-459, 289, 2), (-380, 300, 3)], [(-350, 280, 2), (-340, 305, 2)]]
    before = base+b''.join(line_block(LAYER, (1,15+i), (0,0), p) for i,p in enumerate(paths))
    tree = _block(1, cid(1,*GROUP)+cid(2,0,0)+_boolean(3,True)+sub(4,cid(1,*LAYER)))
    group = _block(2, cid(1,*GROUP)+_lww(2,(0,0),_string(2,''))+_lww(3,(0,0),_boolean(2,True))+
                   _lww(7,(1,31),cid(2,*ANCHOR))+_lww(8,(1,32),tag(2,1)+b'\x02')+
                   _lww(9,(1,33),tag(2,4)+struct.pack('<f',35.7480316162))+
                   _lww(10,GROUP,tag(2,4)+struct.pack('<f',ORIGIN[0])), 1, 2)
    link = _block(4, cid(1,*LAYER)+cid(2,1,30)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x02'+cid(2,*GROUP)))
    atom = sub(0,cid(2,*ANCHOR)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x01\x01\n'))
    text = _block(7,cid(1,0,0)+sub(2,sub(1,sub(1,vu(1)+atom))+sub(2,sub(1,vu(0))))+
                  sub(3,struct.pack('<dd',-468,234))+tag(4,4)+struct.pack('<f',936))
    tombstone = _block(5,cid(1,*LAYER)+cid(2,1,15)+cid(3,0,0)+cid(4,0,0)+i4(5,2),2,2)
    after = base+tree+group+link+text+tombstone+b''.join(moved_line(i,p) for i,p in enumerate(paths))
    return before, after


def measurement(raw):
    return {'sha256':hashlib.sha256(raw).hexdigest(), 'first':[*ORIGIN,32,1]}


def change_first_line(raw, mutate):
    parts, changed = [], False
    for kind, block in blocks(raw):
        f = _fields(block[8:]) if kind == 5 else None
        if f and 6 in f and not changed:
            v = _fields(f[6][1][1:]); mutate(v)
            f[6] = (12,b'\x03'+encode(v)); block = _block(5,encode(f),2,2); changed = True
        parts.append(block)
    assert changed
    return raw[:43]+b''.join(parts)


class PreservationTest(unittest.TestCase):
    def test_exact_cursor_indices_follow_crdt_order_and_utf16_not_file_order(self):
        _, raw = fixture()
        root = _fields(next(b[8:] for k,b in blocks(raw) if k == 7))
        section = _fields(root[2][1])
        def atom(identity, left, right, string, deleted=0):
            data = string.encode('utf-8')
            return sub(0,cid(2,*identity)+cid(3,*left)+cid(4,*right)+i4(5,deleted)+
                       sub(6,vu(len(data))+b'\x01'+data))
        first = atom((1,28),END_ID,(2,10),'\nA😀B')
        second = atom((2,10),(1,31),END_ID,'\nC')
        def payload(atoms):
            section[1] = (12,sub(1,vu(len(atoms))+b''.join(atoms)))
            root[2] = (12,encode(section))
            return encode(root)
        expected = {'length':7,'indices':{'1:28':0,'1:29':1,'1:30':2,'1:31':4,'2:10':5,'2:11':6}}
        self.assertEqual(saved_text_cursor_indices(payload([second,first])),expected)
        self.assertEqual(saved_text_cursor_indices(payload([first,second])),expected)
        self.assertNotIn('0:281474976710655',expected['indices'])
        # Changed topology, implicit-character ID overlap, deletion and missing
        # references must never yield plausible-looking cursor coordinates.
        bad = ([first,first], [first],
               [atom((1,28),END_ID,END_ID,'x'),atom((2,10),END_ID,END_ID,'y')],
               [atom((1,28),(2,11),(2,10),'\nA😀B'),atom((2,10),(1,31),(1,28),'\nC')],
               [atom((1,28),END_ID,END_ID,'x',deleted=1)])
        for atoms in bad:
            with self.assertRaises(ValueError):
                saved_text_cursor_indices(payload(atoms))
        with self.assertRaises(ValueError):
            saved_text_cursor_indices(None)

    def test_tree_history_requires_an_independently_empty_leaf(self):
        before, _ = fixture()
        empty = (1, 80)
        tree = _block(1, cid(1,*empty)+cid(2,0,0)+_boolean(3,True)+sub(4,cid(1,*LAYER)))
        group = _block(2, cid(1,*empty)+_lww(2,(0,0),_string(2,''))+_lww(3,(0,0),_boolean(2,True)))
        link = _block(4, cid(1,*LAYER)+cid(2,1,81)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x02'+cid(2,*empty)))
        dead = _block(5, cid(1,*empty)+cid(2,1,82)+cid(3,0,0)+cid(4,0,0)+i4(5,2),2,2)
        def history(event=(1,90), target=empty, parent=END_ID, update=False):
            return _block(1, cid(1,*event)+cid(2,*target)+_boolean(3,update)+sub(4,cid(1,*parent)))
        base = before+tree+group+link+dead
        good = base+history()
        self.assertEqual(len(compare_preserved(before, good)), 2)
        self.assertEqual(layout_request(good)['indices'], [])
        # Revisions touching occupied groups, unknown groups, real parents,
        # duplicate events/targets or a group with live descendants stay held.
        cases = [base+history(target=LAYER), base+history(target=(1,99)),
                 base+history(parent=LAYER), base+history(update=True),
                 good+history(), good+history(event=(1,91)),
                 base+history(event=empty)]
        occupied = line_block(empty,(1,95),END_ID,[(0,0,2),(2,2,2)])
        cases.append(good+occupied)
        image = _block(15,cid(1,*empty)+cid(2,1,96)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x07image'),2,2)
        cases.append(good+image)
        # An otherwise unsupported anchor is inert ONLY while its referenced
        # leaf has no visible content. Adding a line/image makes it reject.
        anchored_group = _block(2,group[8:]+
            _lww(7,(1,84),cid(2,0,281474976710655))+
            _lww(8,(1,85),tag(2,1)+b'\x02')+
            _lww(9,(1,86),tag(2,4)+struct.pack('<f',0))+
            _lww(10,(1,87),tag(2,4)+struct.pack('<f',-464)),1,2)
        inert_anchor=good.replace(group,anchored_group)
        self.assertEqual(len(compare_preserved(before,inert_anchor)),2)
        self.assertEqual(layout_request(inert_anchor)['indices'],[])
        cases.extend((inert_anchor+occupied,inert_anchor+image))
        child = (1,100)
        cases.append(good+_block(1,cid(1,*child)+cid(2,0,0)+_boolean(3,True)+sub(4,cid(1,*empty)))+
                     _block(2,cid(1,*child)+_lww(2,(0,0),_string(2,''))+_lww(3,(0,0),_boolean(2,True)))+
                     _block(4,cid(1,*empty)+cid(2,1,101)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x02'+cid(2,*child))))
        for raw in cases:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                layout_request(raw)
            with self.assertRaises(ValueError):
                compare_preserved(before,raw)

    def test_deleted_image_ranges_cannot_hide_any_live_item(self):
        before, _ = fixture()
        dead = _block(15,cid(1,*LAYER)+cid(2,1,200)+cid(3,0,0)+cid(4,0,0)+i4(5,2),2,2)
        good = before+dead
        self.assertEqual(len(compare_preserved(before,good)),2)
        image = _block(15,cid(1,*LAYER)+cid(2,1,201)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x07image'),2,2)
        stroke = line_block(LAYER,(1,201),END_ID,[(0,0,2),(2,2,2)])
        overlap = _block(5,cid(1,*LAYER)+cid(2,1,201)+cid(3,0,0)+cid(4,0,0)+i4(5,1),2,2)
        for raw in (good+image,good+stroke,good+overlap):
            with self.assertRaisesRegex(ValueError,'tombstone'):
                layout_request(raw)
        with self.assertRaisesRegex(ValueError,'deletion'):
            layout_request(before+_block(15,dead[8:],1,1))
        # A live image in a previous baseline can never vanish into history.
        with self.assertRaisesRegex(ValueError,'image missing'):
            compare_preserved(before+image,good)

    def test_leading_newline_run_keeps_exact_index_zero_anchor(self):
        before, after = fixture()
        text = next(raw for kind, raw in blocks(after) if kind == 7)
        def with_run(value, deleted=0):
            root = _fields(text[8:]); section = _fields(root[2][1])
            atom = sub(0, cid(2,*ANCHOR)+cid(3,0,0)+cid(4,0,0)+i4(5,deleted)+sub(6,value))
            section[1] = (12, sub(1,vu(1)+atom)); root[2] = (12,encode(section))
            return after.replace(text, _block(7,encode(root)))
        for string in ('\n\n', '\nAgent Pi Dog:\n', '\n\nCaption'):
            data = string.encode()
            raw = with_run(vu(len(data))+b'\x01'+data)
            self.assertEqual(layout_request(raw)['anchor'], list(ANCHOR))
            self.assertEqual(layout_request(raw)['indices'], [0])
            measured = dict(measurement(raw),first=[*ORIGIN,32,len(string)])
            self.assertEqual(len(compare_preserved(before,raw,after_measurement=measured)),2)
            with self.assertRaises(ValueError):
                compare_preserved(before,raw,after_measurement=measurement(after))
            if string.startswith('\n\n'):
                group = next(b for k,b in blocks(raw) if k==2 and _fields(b[8:])[1][1]==GROUP)
                fields = _fields(group[8:]); fields[7] = (12,cid(1,1,31)+cid(2,1,29))
                second = raw.replace(group,_block(2,encode(fields),1,2))
                self.assertEqual(layout_request(second)['indices'],[1])
                self.assertEqual(layout_request(second)['anchor'],[1,29])
                measured = dict(measured,sha256=hashlib.sha256(second).hexdigest())
                self.assertEqual(len(compare_preserved(before,second,after_measurement=measured)),2)
        for string,index in (('\nX\n',2), ('\n'*33,32)):
            data=string.encode();raw=with_run(vu(len(data))+b'\x01'+data)
            group=next(b for k,b in blocks(raw) if k==2 and _fields(b[8:])[1][1]==GROUP)
            fields=_fields(group[8:]);fields[7]=(12,cid(1,1,31)+cid(2,ANCHOR[0],ANCHOR[1]+index))
            with self.assertRaisesRegex(ValueError,'unsupported native text anchor'):
                layout_request(raw.replace(group,_block(2,encode(fields),1,2)))
        for value in (b'\x02\x01x\n', b'\x00\x01', b'\x02\x00\n\n',
                      b'\x03\x01\n\n', b'\x01\x01\nextra', b'\x02\x01\n\xff'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                layout_request(with_run(value))
        with self.assertRaises(ValueError):
            layout_request(with_run(b'\x02\x01\n\n',deleted=1))

    def test_layout_request_is_from_saved_group_not_caller_coordinates(self):
        before, after = fixture()
        self.assertEqual(layout_request(before)['indices'], [])
        self.assertEqual(layout_request(after), {'indices':[0], 'anchor':list(ANCHOR), 'sha256':hashlib.sha256(after).hexdigest()})
        # JSON round trip must not alter the baseline's comparison types.
        import json
        from notebook_ink_preservation import compare_baseline
        old = json.loads(json.dumps(preservation_baseline(before,text_key=KEY)))
        self.assertEqual(len(compare_baseline(old, preservation_baseline(after, measurement(after),text_key=KEY))), 2)

    def test_journal_text_is_keyed_not_dictionary_testable(self):
        from notebook_ink_preservation import compare_baseline
        _,raw=fixture()
        a=preservation_baseline(raw,measurement(raw),text_key=KEY)
        b=preservation_baseline(raw,measurement(raw),text_key=b'another-test-only-text-key-000001')
        digest=a['text']['chars']['1:28']
        self.assertIs(a['text']['blank'],True)  # the fixture's text is a run of newlines
        self.assertNotEqual(digest,hashlib.sha256(b'\n').hexdigest())
        self.assertNotEqual(a['text']['chars'],b['text']['chars'])
        with self.assertRaisesRegex(ValueError,'text missing, changed'):
            compare_baseline(a,b)
        import json
        self.assertNotIn(KEY.decode(),json.dumps(a))
        for key in (None,b'',b'too short'):
            with self.assertRaises(ValueError):
                preservation_baseline(raw,measurement(raw),text_key=key)

    def test_reply_blank_lines_may_go_before_old_blank_lines_but_never_before_old_words(self):
        from notebook_ink_preservation import compare_baseline
        def snap(order, blank):
            return dict(style_version=2, authors={}, lines=[], media=[], text=dict(
                layout='L', order=order, chars={k: 'h'+k for k in order}, styles={}, length=len(order), blank=blank))
        compare_baseline(snap(['1:1', '1:2'], True), snap(['2:1', '2:2', '1:1', '1:2'], False))
        for before, after in [(snap(['1:1', '1:2'], False), snap(['2:1', '1:1', '1:2'], False)),
                              (snap(['1:1', '1:2'], True), snap(['2:1', '1:2', '1:1'], False)),
                              (snap(['1:1', '1:2'], True), snap(['2:1', '1:1'], False))]:
            with self.assertRaisesRegex(ValueError, 'text missing, changed'):
                compare_baseline(before, after)
        legacy = snap(['1:1'], True)
        del legacy['text']['blank']
        with self.assertRaisesRegex(ValueError, 'text missing, changed'):
            compare_baseline(legacy, snap(['2:1', '1:1'], False))

    def test_images_are_preserved_not_silently_skipped(self):
        before, after = fixture()
        image = _block(15, cid(1,*LAYER)+cid(2,1,200)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x07opaque-image-value'),2,2)
        old = before+image
        new = after+image
        self.assertEqual(len(compare_preserved(old,new,after_measurement=measurement(new))),2)
        self.assertEqual(len(compare_preserved(before,new,after_measurement=measurement(new))),2)
        for bad in (after, after+image.replace(b'image',b'Image'), after+image+image):
            with self.assertRaises(ValueError):
                compare_preserved(old,bad,after_measurement=measurement(bad))
        f=_fields(image[8:]);f[1]=(15,GROUP)
        changed=after+_block(15,encode(f),2,2)
        with self.assertRaises(ValueError):
            compare_preserved(old,changed,after_measurement=measurement(changed))

    def test_existing_text_and_root_layout_cannot_be_changed_or_removed(self):
        _, before = fixture()
        self.assertEqual(len(compare_preserved(before,before,measurement(before),measurement(before))),2)
        for k,raw in blocks(before):
            if k!=7: continue
            root=_fields(raw[8:])
            variants=[before.replace(raw,b'')]
            moved=dict(root);moved[3]=(12,struct.pack('<dd',-468,250))
            variants.append(before.replace(raw,_block(7,encode(moved))))
            # Keep the first newline so the supported anchor still resolves;
            # add text to the old snapshot and then delete/change it in the new.
            section=_fields(root[2][1]);items=_fields(section[1][1])[1][1]
            atom=sub(0,cid(2,1,100)+cid(3,*ANCHOR)+cid(4,0,0)+i4(5,0)+sub(6,b'\x02\x01Hi'))
            section[1]=(12,sub(1,vu(2)+items[1:]+atom))
            extended=dict(root);extended[2]=(12,encode(section))
            extended_raw=before.replace(raw,_block(7,encode(extended)))
            em=dict(measurement(extended_raw),first=[*ORIGIN,32,3])
            with self.assertRaises(ValueError):
                compare_preserved(extended_raw,before,em,measurement(before))
            for bad in variants:
                with self.assertRaises(ValueError):
                    compare_preserved(before,bad,measurement(before),measurement(bad))

    def test_native_coordinates_and_move_lineage_preserve_all_strokes(self):
        before,after=fixture()
        self.assertEqual(len(compare_preserved(before,after,after_measurement=measurement(after))),2)
        self.assertEqual(len(compare_preserved(before,before)),2)
        a,_=page_strokes(before);b,_=page_strokes(after,measurement(after))
        self.assertEqual([x['points'] for x in a],[x['points'] for x in b])

    def test_no_measurement_no_fitting_and_no_stale_hash(self):
        before,after=fixture()
        for m in (None,dict(measurement(after),sha256='0'*64),
                  dict(measurement(after),first=[-464,268.59375,32,1]),
                  dict(measurement(after),first=[-463,267.59375,32,1]),
                  dict(measurement(after),first=[-464,float('nan'),32,1])):
            with self.assertRaises(ValueError):
                compare_preserved(before,after,after_measurement=m)

    def test_each_style_and_point_attribute_is_protected(self):
        before,after=fixture()
        edits = [lambda f:f.__setitem__(1,(4,struct.pack('<I',18))),
                 lambda f:f.__setitem__(2,(4,struct.pack('<I',1))),
                 lambda f:f.__setitem__(3,(8,struct.pack('<d',3))),
                 lambda f:f.__setitem__(4,(4,struct.pack('<f',1))),
                 lambda f:f.__setitem__(8,(4,b'\x00\x00\x00\xff'))]
        # x/y, speed, width, direction, pressure: NOT just a point count.
        for offset in (0,4,8,10,12,13):
            def mutate(f,offset=offset):
                p=bytearray(f[5][1])
                if offset in (0,4):
                    struct.pack_into('<f',p,offset,struct.unpack_from('<f',p,offset)[0]+1)
                else: p[offset] ^= 1
                f[5]=(12,bytes(p))
            edits.append(mutate)
        for edit in edits:
            bad=change_first_line(after,edit)
            with self.subTest(edit=edits.index(edit)), self.assertRaises(ValueError):
                compare_preserved(before,bad,after_measurement=measurement(bad))

    def test_reanchored_timestamp_is_not_a_visual_style_change(self):
        before, after = fixture()
        changed = change_first_line(after, lambda f: f.__setitem__(6, (15, (1, 1576))))
        self.assertEqual(len(compare_preserved(before, changed, after_measurement=measurement(changed))), 2)
        # Metadata normalization cannot rescue broken lineage or changed ink.
        for edit in (lambda f: f.pop(7),
                     lambda f: f.__setitem__(7, (15, (1, 999))),
                     lambda f: f.__setitem__(3, (8, struct.pack('<d', 3))),
                     lambda f: f.__setitem__(6, (4, struct.pack('<I', 1)))):
            bad = change_first_line(changed, edit)
            with self.assertRaises(ValueError):
                compare_preserved(before, bad, after_measurement=measurement(bad))

    def test_timestamp_normalization_never_reinterprets_legacy_journal(self):
        from notebook_ink_preservation import compare_baseline
        before, after = fixture()
        a = preservation_baseline(before, text_key=KEY)
        b = preservation_baseline(after, measurement(after), text_key=KEY)
        self.assertEqual(a['style_version'], 2)
        self.assertEqual(len(compare_baseline(a, b)), 2)
        del a['style_version']
        with self.assertRaisesRegex(ValueError, 'style comparison version changed'):
            compare_baseline(a, b)

    def test_deleted_replaced_duplicate_or_unrelated_lookalike_cannot_pass(self):
        before,after=fixture()
        live=[r for k,r in blocks(after) if k==5 and 6 in _fields(r[8:])]
        variants=[after.replace(live[0],b''), after+live[0],
                  change_first_line(after,lambda f:f.pop(7)),
                  change_first_line(after,lambda f:f.__setitem__(7,(15,(1,999))))]
        # Even a second lookalike with an unrelated item/move ID is ambiguous.
        f=_fields(live[0][8:]);f[2]=(15,(1,999));f[6]=(12,f[6][1][:-3]+cid(7,1,998))
        variants.append(after+_block(5,encode(f),2,2))
        for bad in variants:
            with self.assertRaises(ValueError):
                compare_preserved(before,bad,after_measurement=measurement(bad))

    def test_changed_anchors_topology_and_versions_are_not_ignored(self):
        before,after=fixture()
        variants=[after[:-1],after+b'bad']
        for kind,raw in blocks(after):
            if kind==2 and _fields(raw[8:])[1][1]==GROUP:
                f=_fields(raw[8:])
                for field,value in ((7,cid(2,1,999)),(8,tag(2,1)+b'\x01'),
                                    (10,tag(2,4)+struct.pack('<f',-460)),(3,_boolean(2,False))):
                    changed=dict(f);changed[field]=(12,cid(1,1,88)+value)
                    variants.append(after.replace(raw,_block(2,encode(changed),1,2)))
                variants.append(after+raw)
            if kind==4 and _fields(raw[8:])[1][1]==LAYER:
                variants.append(after.replace(raw,b''))
            if kind==5 and 6 in _fields(raw[8:]):
                changed=bytearray(raw);changed[6]=3
                variants.append(after.replace(raw,bytes(changed)))
                break
        for bad in variants:
            with self.assertRaises(ValueError):
                compare_preserved(before,bad,after_measurement=measurement(bad))

    def test_an_erased_item_saved_as_a_tombstone_block_is_only_a_dead_range(self):
        before, _ = fixture()
        dead = _block(8,cid(1,*LAYER)+cid(2,1,200)+cid(3,0,0)+cid(4,0,0)+i4(5,1))
        self.assertEqual(len(compare_preserved(before,before+dead)),2)
        stroke = line_block(LAYER,(1,200),END_ID,[(0,0,2),(2,2,2)])
        with self.assertRaisesRegex(ValueError,'duplicate'):  # a live item can never share an erased one's ID
            layout_request(before+dead+stroke)
        for bad in (_block(8,dead[8:],1,2), _block(8,dead[8:-5]+i4(5,0)),
                    _block(8,dead[8:]+sub(6,b'\x03x'))):  # another version, no range, a value: refused
            with self.assertRaises(ValueError):
                layout_request(before+bad)

    def test_changed_author_map_and_live_tombstone_overlap_fail(self):
        before,after=fixture()
        for kind,raw in blocks(after):
            if kind==9:
                bad=after.replace(raw,_block(9,raw[8:-1]+b'\x01'))
                with self.assertRaises(ValueError):
                    compare_preserved(before,bad,after_measurement=measurement(bad))
        tomb=_block(5,cid(1,*GROUP)+cid(2,1,34)+cid(3,0,0)+cid(4,0,0)+i4(5,2),2,2)
        with self.assertRaises(ValueError):
            compare_preserved(before,after+tomb,after_measurement=measurement(after+tomb))


if __name__ == '__main__':
    unittest.main()
