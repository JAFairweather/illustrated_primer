"""Offline parser coverage; sampled coordinates are explicit synthetic data.

These tests do not turn diagnostic telemetry into authenticated capture proof.
"""
import copy
import hashlib
import struct
import unittest

from ink import cid, i4, sub, tag, line_block, blocks
from notebook_anchor_fixture import _fixtures, bottom_anchor_fixtures, anchor_motion_fixtures, BOTTOM
from notebook_stroke_asset import _block, _lww, _string, _boolean
from notebook_ink_preservation import (layout_request, page_strokes,
    preservation_baseline, compare_preserved, NativeTextLengthMismatch)
from test_notebook_ink_preservation import AUTHOR, KEY, change_first_line
from test_notebook_ink_preservation import encode
from notebook_ink_preservation import _fields


def multi_fixture():
    raw = bottom_anchor_fixtures(AUTHOR)[3]['data']  # \nA\n, bottom at index2
    layer, group = (0,11), (1,70)
    raw += _block(1,cid(1,*group)+cid(2,0,0)+_boolean(3,True)+sub(4,cid(1,*layer)))
    raw += _block(2,cid(1,*group)+_lww(2,(0,0),_string(2,''))+
        _lww(3,(0,0),_boolean(2,True))+_lww(7,(1,71),cid(2,1,20))+
        _lww(8,(1,72),tag(2,1)+b'\x02')+
        _lww(9,(1,73),tag(2,4)+struct.pack('<f',0))+
        _lww(10,(1,74),tag(2,4)+struct.pack('<f',-464)),1,2)
    raw += _block(4,cid(1,*layer)+cid(2,1,75)+cid(3,0,0)+cid(4,0,0)+
        i4(5,0)+sub(6,b'\x02'+cid(2,*group)))
    raw += line_block(group,(1,80),(0,0),[(400,200,2),(500,200,2)])
    return raw


def measured(raw):
    return dict(sha256=hashlib.sha256(raw).hexdigest(),
                samples=[[0,-464,267.59375,32,3],[2,-443.234375,337.140625,32,3]])


class MultiAnchorTest(unittest.TestCase):
    def test_top_prefix_preserves_ink_without_assuming_text_box_or_font_offset(self):
        from notebook_anchor_fixture import top_anchor_fixtures, TOP
        from notebook_ink_runs import capture_layout
        before,after=top_anchor_fixtures(AUTHOR)[1:4:2]
        def measurement(asset,y=267.59375):
            return dict(sha256=asset['sha256'],samples=[[0,-464,y,32,asset['length']]])
        self.assertEqual(page_strokes(before['data'],measurement(before))[0],
                         page_strokes(after['data'],measurement(after))[0])
        # Prefix insertion is a diagnostic stimulus, not an allowed response
        # edit. The production preservation policy must still reject it.
        with self.assertRaisesRegex(ValueError,'pre-existing native text'):
            compare_preserved(before['data'],after['data'],measurement(before),measurement(after))
        with self.assertRaisesRegex(ValueError,'old native stroke'):
            compare_preserved(before['data'],before['data'],measurement(before),measurement(before,234))
        for text,anchor in (('',TOP),('\nA',(0,281474976710653))):
            raw=_fixtures(AUTHOR,[('unsupported',text,anchor)])[1]['data']
            with self.assertRaises(ValueError):capture_layout(raw)

    def test_empty_text_and_wrong_root_hold_in_both_capture_modes(self):
        from ink import vu
        from notebook_ink_runs import capture_layout
        raw=multi_fixture()
        text=next(b for k,b in blocks(raw) if k==7)
        root=_fields(text[8:])
        wrong=copy.deepcopy(root);wrong[1]=(15,(1,99))
        cases=[raw.replace(text,_block(7,encode(wrong)))]
        for atoms in ([],[sub(0,cid(2,1,20)+cid(3,0,0)+cid(4,0,0)+i4(5,0)+sub(6,b'\x00\x01'))]):
            empty=copy.deepcopy(root);section=_fields(empty[2][1])
            section[1]=(12,sub(1,vu(len(atoms))+b''.join(atoms)))
            empty[2]=(12,encode(section))
            cases.append(raw.replace(text,_block(7,encode(empty))))
        for bad in cases:
            for fn in (layout_request,lambda b:layout_request(b,allow_multiple=True),capture_layout):
                with self.subTest(size=len(bad),function=fn),self.assertRaises(ValueError):fn(bad)

    def test_prefix_insert_uses_unique_crdt_order_without_legacy_head_guess(self):
        raw=anchor_motion_fixtures(AUTHOR)[3]['data']
        with self.assertRaisesRegex(ValueError,'unambiguous newline'):
            layout_request(raw)
        plan=layout_request(raw,allow_multiple=True)
        self.assertEqual(plan['indices'],[5])
        value=dict(sha256=plan['sha256'],samples=[[5,-443.234375,476.234375,32,7]])
        lines,_=page_strokes(raw,value)
        self.assertEqual([(p[0],p[1]) for p in lines[0]['points']],
                         [(-264,576.234375),(-164,576.234375)])
        # Removing the prefix's link makes two possible heads; the full order
        # resolver must refuse it rather than choosing an anchor geometrically.
        needle=cid(2,1,2000)+cid(3,0,0)+cid(4,1,20)
        self.assertEqual(raw.count(needle),1)
        from notebook_ink_preservation import Reader
        text=next(b for k,b in blocks(raw) if k==7)
        root=_fields(text[8:]);section=_fields(root[2][1])
        items=Reader(_fields(section[1][1])[1][1]);count=items.uint()
        atoms=[items.field(0,12) for _ in range(count)];items.done()
        atoms[1]=atoms[1].replace(needle,cid(2,1,2000)+cid(3,0,0)+cid(4,0,0))
        from ink import vu
        section[1]=(12,sub(1,vu(count)+b''.join(sub(0,a) for a in atoms)))
        root[2]=(12,encode(section))
        bad=raw.replace(text,_block(7,encode(root)))
        with self.assertRaisesRegex(ValueError,'ambiguous native text ordering'):
            layout_request(bad,allow_multiple=True)

    def test_middle_newline_uses_stored_x_not_horizontal_cursor_advance(self):
        raw=_fixtures(AUTHOR,[('middle','\nA\nB',(1,22))])[1]['data']
        plan=layout_request(raw,allow_multiple=True)
        self.assertEqual(plan['indices'],[2])
        value=dict(sha256=plan['sha256'],samples=[[2,-443.234375,337.140625,32,4]])
        lines,_=page_strokes(raw,value)
        self.assertEqual([(p[0],p[1]) for p in lines[0]['points']],
                         [(-264,437.140625),(-164,437.140625)])
        group=next(b for k,b in blocks(raw) if k==2 and 7 in _fields(b[8:]))
        f=_fields(group[8:])
        f[10]=(12,cid(1,1,54)+tag(2,4)+struct.pack('<f',-463))
        changed=raw.replace(group,_block(2,encode(f),1,2))
        with self.assertRaisesRegex(ValueError,'old native stroke'):
            compare_preserved(raw,changed,value,dict(value,sha256=hashlib.sha256(changed).hexdigest()))

    def test_opt_in_plan_maps_all_saved_anchors_and_preserves_legacy_hold(self):
        raw=multi_fixture()
        with self.assertRaises(ValueError):
            layout_request(raw)
        plan=layout_request(raw,allow_multiple=True)
        self.assertEqual(plan,dict(sha256=hashlib.sha256(raw).hexdigest(),length=3,
            indices=[0,2],anchors=[dict(id=list(BOTTOM),index=2),dict(id=[1,20],index=0)]))
        with self.assertRaises(ValueError):
            page_strokes(raw)
        lines,_=page_strokes(raw,measured(raw))
        self.assertEqual([(p[0],p[1]) for p in lines[0]['points']],
                         [(-264,437.140625),(-164,437.140625)])
        self.assertEqual([(p[0],p[1]) for p in lines[1]['points']],
                         [(-64,467.59375),(36,467.59375)])
        self.assertEqual(len(compare_preserved(raw,raw,measured(raw),measured(raw))),2)
        baseline=preservation_baseline(raw,measured(raw),text_key=KEY)
        self.assertNotIn('cursor_indices',baseline['text'])
        self.assertNotIn('newline_ids',baseline['text'])

    def test_samples_must_be_exact_complete_bounded_and_hash_bound(self):
        raw=multi_fixture()
        valid=measured(raw)
        variants=[dict(valid,sha256='0'*64),dict(valid,samples=[]),dict(valid,samples=None)]
        for samples in (valid['samples'][:1],valid['samples']*2,
                        valid['samples']+[[1,-464,300,32,3]]):
            variants.append(dict(valid,samples=samples))
        for index,value in ((0,True),(0,1),(0,-1),(0,262144),(1,float('nan')),
                            (2,1000001),(3,0),(4,True),(4,2)):
            samples=copy.deepcopy(valid['samples']);samples[-1][index]=value
            variants.append(dict(valid,samples=samples))
        for bad in variants:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                page_strokes(raw,bad)
        with self.assertRaises(NativeTextLengthMismatch):
            page_strokes(raw,dict(valid,samples=[[0,-464,267,32,4],[2,-443,337,32,4]]))

    def test_existing_world_geometry_still_cannot_move_or_be_fitted(self):
        raw=multi_fixture()
        changed=copy.deepcopy(measured(raw));changed['samples'][1][2]+=1
        with self.assertRaisesRegex(ValueError,'old native stroke'):
            compare_preserved(raw,raw,measured(raw),changed)
        def shift(fields):
            points=bytearray(fields[5][1]);x=struct.unpack_from('<f',points)[0]
            struct.pack_into('<f',points,0,x+1);fields[5]=(12,bytes(points))
        altered=change_first_line(raw,shift)
        with self.assertRaisesRegex(ValueError,'old native stroke'):
            compare_preserved(raw,altered,measured(raw),measured(altered))

    def test_bottom_uses_final_saved_character_start_not_empty_end_or_surrogate(self):
        for text,expected,length in (('\nA',1,2),('\nA\n',2,3),('\nA\n\n',3,4),('\n😀',1,3)):
            raw=_fixtures(AUTHOR,[('synthetic',text)])[1]['data']
            plan=layout_request(raw,allow_multiple=True)
            self.assertEqual(plan['indices'],[expected])
            self.assertEqual(plan['length'],length)
            self.assertEqual(plan['anchors'],[dict(id=list(BOTTOM),index=expected)])


if __name__=='__main__':
    unittest.main()
