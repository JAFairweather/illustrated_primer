"""Exact saved append proof; synthetic native pages, no tablet authority."""
import copy
import struct
import unittest

from ink import cid, i4, sub, tag, vu, line_block
from notebook_stroke_asset import _block, _foundation, _string
from notebook_ink_preservation import preservation_baseline, compare_baseline, compare_text_append
from test_notebook_ink_preservation import AUTHOR, KEY


def snapshot(old='Earlier note.\n', added='', *, split=False, reverse=False,
             leading='', styles=(), x=-468, move_ink=0, key=KEY):
    atoms=[]
    def atom(identity,left,right,text):
        return sub(0,cid(2,*identity)+cid(3,*left)+cid(4,*right)+i4(5,0)+_string(6,text))
    if old:
        if split and len(old)>1:
            atoms.extend([atom((1,20),(0,0),(1,21),old[:1]),
                          atom((1,21),(1,20),(0,0),old[1:])])
        else: atoms.append(atom((1,20),(0,0),(0,0),old))
    if added:
        atoms.append(atom((2,100),(1,19+len(old)) if old else (0,0),(0,0),added))
    if leading:
        atoms.append(atom((3,100),(0,0),(1,20),leading))
    if reverse: atoms.reverse()
    raw=_foundation(AUTHOR)
    if atoms:
        formats=vu(len(styles))
        for n,(identity,style) in enumerate(styles):
            formats+=bytes([identity[0]])+vu(identity[1])+cid(1,4,n+1)+sub(2,bytes([17,style]))
        raw+=_block(7,cid(1,0,0)+sub(2,sub(1,sub(1,vu(len(atoms))+b''.join(atoms)))+
            sub(2,sub(1,formats)))+sub(3,struct.pack('<dd',x,234))+tag(4,4)+struct.pack('<f',936))
    raw+=line_block((0,11),(1,900),(0,0),[(100+move_ink,100,2),(200+move_ink,100,2)])
    return preservation_baseline(raw,text_key=key)


class SavedTextAppendTests(unittest.TestCase):
    def test_exact_unicode_append_and_bounded_virtual_gap(self):
        before=snapshot()
        expected='Agent Pi Dog:\nEqual parts: 𝑥, café, e\u0301.\n'
        for gap in (0,2,160):
            after=snapshot(added='\n'*gap+expected)
            result=compare_text_append(before,after,expected,text_key=KEY,leading_newlines=gap)
            units=len(expected.encode('utf-16-le'))//2
            self.assertEqual(result,dict(start=14+gap,end=14+gap+units,characters=units,gap=gap))
            self.assertNotIn(expected,str(result))

    def test_native_atom_splitting_and_file_order_do_not_change_identity(self):
        before=snapshot()
        for split,reverse in ((True,False),(False,True),(True,True)):
            after=snapshot(added='Answer.\n',split=split,reverse=reverse)
            self.assertEqual(compare_text_append(before,after,'Answer.\n',text_key=KEY)['end'],22)

    def test_same_length_old_edit_and_same_length_wrong_answer_are_rejected(self):
        before=snapshot();expected='A clear answer.'
        for after in (snapshot(old='earlier note.\n',added=expected),
                      snapshot(added='A wrong answer.'),snapshot(added=expected,key=b'other-key-for-synthetic-test-0000')):
            with self.assertRaises(ValueError):compare_text_append(before,after,expected,text_key=KEY)
        # The legacy preservation check alone intentionally permits arbitrary
        # new suffix text. Exact continuation must additionally verify it.
        wrong=snapshot(added='A wrong answer.')
        self.assertEqual(len(compare_baseline(before,wrong)),1)

    def test_missing_duplicate_prefix_insert_and_extra_characters_are_rejected(self):
        before=snapshot();expected='Answer.\n'
        for after in (snapshot(),snapshot(added=expected*2),snapshot(added=expected+'x'),
                      snapshot(added=expected,leading='Unexpected.\n')):
            with self.assertRaises(ValueError):compare_text_append(before,after,expected,text_key=KEY)
        after=snapshot(added='x\n'+expected)
        with self.assertRaisesRegex(ValueError,'content disagrees'):
            compare_text_append(before,after,expected,text_key=KEY,leading_newlines=2)

    def test_old_ink_layout_and_new_style_on_old_text_remain_protected(self):
        before=snapshot();expected='Answer.\n'
        for after in (snapshot(added=expected,move_ink=1),snapshot(added=expected,x=-467),
                      snapshot(added=expected,styles=[((1,33),2)]),
                      snapshot(added=expected,styles=[((2,100),2)])):
            with self.assertRaises(ValueError):compare_text_append(before,after,expected,text_key=KEY)
        after=snapshot(added=expected,styles=[((2,107),2)])
        self.assertEqual(compare_text_append(before,after,expected,text_key=KEY)['characters'],8)
        old=snapshot(styles=[((1,33),2)])
        after=snapshot(added=expected,styles=[((1,33),2)])
        compare_text_append(old,after,expected,text_key=KEY)

    def test_new_root_text_requires_exact_content_and_preserved_existing_ink(self):
        before=snapshot(old='');after=snapshot(old='',added='Answer.\n')
        self.assertEqual(compare_text_append(before,after,'Answer.\n',text_key=KEY),
                         dict(start=0,end=8,characters=8,gap=0))
        with self.assertRaises(ValueError):compare_text_append(before,before,'Answer.',text_key=KEY)

    def test_additional_ink_or_media_is_not_an_owned_text_append(self):
        before=snapshot();after=snapshot(added='Answer.')
        for kind in ('lines','media'):
            changed=copy.deepcopy(after)
            if kind=='lines':
                extra=copy.deepcopy(changed['lines'][0]);extra['id'][-1]+=1
                extra['points']=[[x+300,y,attrs] for x,y,attrs in extra['points']]
            else:extra=dict(id=[0,11,2,999],value='opaque-new-image',origin=[0,0])
            changed[kind].append(extra)
            self.assertEqual(len(compare_baseline(before,changed)),1)
            with self.assertRaisesRegex(ValueError,'unrelated ink or media'):
                compare_text_append(before,changed,'Answer.',text_key=KEY)

    def test_input_limits_and_private_errors(self):
        before=snapshot();after=snapshot(added='Secret answer.')
        for expected,gap,key in [('',0,KEY),('x'*2001,0,KEY),('\ud800',0,KEY),
                                 ('Secret answer.',True,KEY),('Secret answer.',161,KEY),
                                 ('Secret answer.',-1,KEY),('Secret answer.',0,b'bad')]:
            with self.assertRaises(ValueError) as caught:
                compare_text_append(before,after,expected,text_key=key,leading_newlines=gap)
            self.assertNotIn('Secret answer',str(caught.exception))
        missing=copy.deepcopy(after);missing['text']=None
        with self.assertRaises(ValueError):compare_text_append(before,missing,'Secret answer.',text_key=KEY)


if __name__=='__main__':unittest.main()
