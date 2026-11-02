"""Coordinate frames need not be visible axes; no question-specific rules."""
from copy import deepcopy
import unittest

from notebook_panel_examples import graph_reuse_example
from notebook_panel_shapes import compile_panel_shapes
from notebook_story_native import native_story_bundle


def fixture():
    story, drafts = graph_reuse_example()
    # A coordinate-only frame must introduce real geometry in the same step.
    drafts['axes']['items'].append(dict(id='shape', type='circle',
        **{'in':'ax'}, center=[.5,.5], radius=.2))
    drafts['axes']['items'][0]['aspect'] = 'equal'
    return story, drafts


class FrameVisibilityTests(unittest.TestCase):
    def test_explicit_default_is_ink_identical(self):
        story, drafts = fixture()
        original = compile_panel_shapes(story, drafts)
        drafts['axes']['items'][0]['visible'] = True
        result = compile_panel_shapes(story, drafts)
        for identity, panel in original['panels'].items():
            for field in ('plan','frames','groups','item_bounds','label_layout'):
                self.assertEqual(panel[field], result['panels'][identity][field])

    def test_hidden_frame_removes_only_decorations_and_keeps_reuse_exact(self):
        story, drafts = fixture()
        before = compile_panel_shapes(story, drafts)
        drafts['axes']['items'][0]['visible'] = False
        original = deepcopy(drafts)
        after = compile_panel_shapes(story, drafts)
        self.assertEqual(drafts, original)
        for identity, panel in after['panels'].items():
            self.assertEqual(panel['frames'], before['panels'][identity]['frames'])
            self.assertEqual(panel['groups']['ax'], [])
            self.assertIsNone(panel['item_bounds']['ax'])
            self.assertFalse(any(key.startswith('__ax-') for key in panel['groups']))
            for key, item in panel['items'].items():
                if item['type'] not in ('axes','label'):
                    self.assertEqual(panel['groups'][key], before['panels'][identity]['groups'][key])
        self.assertLess(after['snapshot_points'], before['snapshot_points'])
        self.assertEqual(after['panels']['axes']['plan']['stages'],
                         after['panels']['mark']['plan']['stages'][:1])
        bundle = native_story_bundle(story, drafts)
        self.assertLessEqual(bundle['delivery_points'],12000)

    def test_visibility_is_strict_boolean(self):
        for invalid in (None, 0, 1, 'false', [], {}):
            story, drafts = fixture()
            drafts['axes']['items'][0]['visible'] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError,'boolean'):
                compile_panel_shapes(story,drafts)

    def test_hidden_frames_cannot_be_labeled_even_by_later_panels(self):
        for identity in ('axes','mark','branch'):
            story, drafts = fixture()
            drafts['axes']['items'][0]['visible'] = False
            drafts[identity]['items'].append(dict(id='title',type='label',to='ax',text='x',side='bottom'))
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError,'hidden coordinate frame'):
                compile_panel_shapes(story,drafts)

    def test_hiding_does_not_relax_ranges_or_allow_invisible_steps(self):
        story, drafts = fixture()
        drafts['axes']['items'][0]['visible'] = False
        drafts['branch']['items'][0]['to'] = [2,2]
        with self.assertRaises(ValueError): compile_panel_shapes(story,drafts)
        story, drafts = graph_reuse_example()
        drafts['axes']['items'][0]['visible'] = False
        with self.assertRaises(ValueError): compile_panel_shapes(story,drafts)


if __name__ == '__main__': unittest.main()
