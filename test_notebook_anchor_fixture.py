"""Structural fixtures and regression checks for independently measured anchors."""
import hashlib
import unittest
import uuid

from ink import blocks
from notebook_anchor_fixture import bottom_anchor_fixtures, bottom_anchor_stress_fixtures, anchor_boundary_fixtures, anchor_motion_fixtures, anchor_format_fixtures, BOTTOM
from notebook_ink_preservation import _fields, _lww, page_strokes, saved_text_cursor_indices


class AnchorFixtureTest(unittest.TestCase):
    def test_top_controls_require_exact_cursor_zero_measurement(self):
        from notebook_anchor_fixture import top_anchor_fixtures, TOP
        from notebook_ink_preservation import layout_request
        from notebook_ink_runs import capture_layout
        assets=top_anchor_fixtures('11111111-2222-3333-4444-555555555555')
        self.assertEqual(len(assets),12)
        for control,anchored in zip(assets[::2],assets[1::2]):
            text=lambda a:next(b[8:] for k,b in blocks(a['data']) if k==7)
            self.assertEqual(text(control),text(anchored))
            self.assertEqual(anchored['anchor_id'],list(TOP))
            self.assertLess(len(anchored['data']),4096)
            for a in (control,anchored):
                self.assertIn(0,a['cursor_indices'])
                self.assertTrue(all(0<=n<=a['length'] for n in a['cursor_indices']))
            with self.assertRaises(ValueError):
                page_strokes(anchored['data'])
            plan=layout_request(anchored['data'],allow_multiple=True)
            self.assertEqual(plan['indices'],[0])
            self.assertEqual(plan['anchors'],[{'id':list(TOP),'index':0}])
            self.assertEqual(capture_layout(anchored['data']),plan)
            # Measured on OS 3.29: control bounds Y=96; TOP bounds
            # Y=363.59375; cursor-zero Y=267.59375, not text-box Y=234.
            measurement={'sha256':anchored['sha256'],
                         'samples':[[0,-464,267.59375,32,anchored['length']]]}
            lines,_=page_strokes(anchored['data'],measurement)
            self.assertEqual([(p[0],p[1]) for p in lines[0]['points']],
                             [(-264,367.59375),(-164,367.59375)])
            for invalid in (
                dict(measurement,sha256='0'*64),
                dict(measurement,samples=[[1,-464,267.59375,32,anchored['length']]]),
                dict(measurement,samples=[[0,-464,267.59375,32,anchored['length']+1]]),
            ):
                with self.assertRaises(ValueError):page_strokes(anchored['data'],invalid)
        nontext=lambda a:[(k,b) for k,b in blocks(a['data']) if k!=7]
        self.assertEqual(nontext(assets[1]),nontext(assets[3]))

    def test_mixed_paragraph_styles_are_paired_without_changing_marker_geometry(self):
        from notebook_ink_preservation import _text_state,layout_request
        assets=anchor_format_fixtures('11111111-2222-3333-4444-555555555555')
        self.assertEqual(len(assets),10)
        for control,anchored in zip(assets[::2],assets[1::2]):
            text=lambda a:next(b[8:] for k,b in blocks(a['data']) if k==7)
            self.assertEqual(text(control),text(anchored))
            state=_text_state(text(anchored),b'fixed-synthetic-test-key-0000000000',cursor_indices=True)
            self.assertEqual(len(state['styles']),len(anchored['paragraph_formats']))
            self.assertEqual(set(state['styles']),{f'1:{20+i}' for i,_ in anchored['paragraph_formats']})
            self.assertTrue(set(state['styles'])<=state['newline_ids'])
            plan=layout_request(anchored['data'],allow_multiple=True)
            self.assertTrue(set(plan['indices'])<=set(anchored['cursor_indices']))
            self.assertEqual(len(page_strokes(control['data'])[0]),1)

    def test_motion_changes_only_text_preserving_anchor_and_ink_identity(self):
        assets=anchor_motion_fixtures('11111111-2222-3333-4444-555555555555')
        self.assertEqual(len(assets),8)
        for i in (0,1,4,5):
            before,after=assets[i],assets[i+2]
            nontext=lambda a:[(k,b) for k,b in blocks(a['data']) if k!=7]
            state=lambda a:saved_text_cursor_indices(next(b[8:] for k,b in blocks(a['data']) if k==7))
            self.assertEqual(nontext(before),nontext(after))
            self.assertEqual(before['anchor_id'],after['anchor_id'])
            a,b=state(before),state(after)
            self.assertEqual((a['length'],b['length']),(4,7))
            self.assertEqual((a['indices']['1:22'],b['indices']['1:22']),(2,5))
            for key,index in a['indices'].items():
                self.assertEqual(b['indices'][key],index+3)
            self.assertEqual([b['indices'][f'1:{n}'] for n in (2000,2001,2002)],[0,1,2])

    def test_boundary_controls_sample_exact_ordinary_middle_newlines(self):
        assets=anchor_boundary_fixtures('11111111-2222-3333-4444-555555555555')
        self.assertEqual(len(assets),6)
        for control,anchored in zip(assets[::2],assets[1::2]):
            text=lambda a:next(b[8:] for k,b in blocks(a['data']) if k==7)
            self.assertEqual(text(control),text(anchored))
            if anchored['anchor_id'] != list(BOTTOM):
                state=saved_text_cursor_indices(text(anchored))
                key=':'.join(map(str,anchored['anchor_id']))
                self.assertIn(state['indices'][key],anchored['cursor_indices'])
                self.assertLess(state['indices'][key],state['length']-1)

    def test_stress_cases_are_fixed_bounded_and_sample_paragraph_boundaries(self):
        assets = bottom_anchor_stress_fixtures('11111111-2222-3333-4444-555555555555')
        self.assertEqual(len(assets),10)
        self.assertEqual(len({a['sha256'] for a in assets}),10)
        for a in assets:
            self.assertLess(len(a['data']),4096)
            self.assertLessEqual(len(a['cursor_indices']),6)
            self.assertEqual(a['cursor_indices'],sorted(set(a['cursor_indices'])))
            self.assertEqual(a['cursor_indices'][-1],a['length'])
            self.assertEqual([k for k,_ in blocks(a['data'])].count(5),1)
        self.assertEqual(assets[0]['cursor_indices'],[0,1,3,4])
        self.assertEqual(assets[2]['cursor_indices'],[0,1,141,142])
        self.assertEqual(assets[8]['cursor_indices'],[0,1,4,5,7])

    def test_four_controlled_sources_are_bounded_and_distinct(self):
        author=uuid.UUID('11111111-2222-3333-4444-555555555555')
        assets=bottom_anchor_fixtures(author)
        self.assertEqual(assets,bottom_anchor_fixtures(author))
        self.assertEqual(len({a['sha256'] for a in assets}),4)
        for asset in assets:
            raw=asset['data']
            self.assertLess(len(raw),4096)
            self.assertEqual(asset['sha256'],hashlib.sha256(raw).hexdigest())
            kinds=[k for k,_ in blocks(raw)]
            self.assertEqual(kinds.count(5),1)
            self.assertEqual(kinds.count(7),1)
            self.assertNotIn(15,kinds)
            payload=next(b[8:] for k,b in blocks(raw) if k==7)
            state=saved_text_cursor_indices(payload)
            self.assertEqual(state['length'],asset['length'])
            self.assertEqual(asset['cursor_indices'],list(range(state['length']+1)))
            if asset['anchored']:
                group=next(_fields(b[8:]) for k,b in blocks(raw)
                           if k==2 and 7 in _fields(b[8:]))
                self.assertEqual(_lww(group,7,15),BOTTOM)
                # The fixture does not smuggle an unproven coordinate rule
                # into the preservation parser just to make the test pass.
                with self.assertRaises(ValueError):
                    page_strokes(raw)
            else:
                lines,_=page_strokes(raw)
                self.assertEqual(len(lines),1)
                self.assertEqual([(p[0],p[1]) for p in lines[0]['points']],
                                 [(-264,100),(-164,100)])

    def test_text_and_marker_style_are_identical_within_each_pair(self):
        assets=bottom_anchor_fixtures('11111111-2222-3333-4444-555555555555')
        for control,anchored in (assets[:2],assets[2:]):
            get=lambda asset,kind: next(b[8:] for k,b in blocks(asset['data']) if k==kind)
            self.assertEqual(get(control,7),get(anchored,7))
            # The containing group and X coordinate frame are the deliberate
            # experimental variable; all pen style fields must be identical.
            left=_fields(_fields(get(control,5))[6][1][1:])
            right=_fields(_fields(get(anchored,5))[6][1][1:])
            self.assertEqual({k:v for k,v in left.items() if k!=5},
                             {k:v for k,v in right.items() if k!=5})


if __name__=='__main__':
    unittest.main()
