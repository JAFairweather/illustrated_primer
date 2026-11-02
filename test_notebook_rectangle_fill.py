from copy import deepcopy
import unittest
from unittest.mock import patch

from notebook_contract_feedback import correction_feedback
from notebook_panel_examples import graph_reuse_example
from notebook_panel_shapes import compile_panel_shapes
from notebook_stroke_asset import storyboard_assets
from notebook_story_prompt import story_panel_instructions


class RectangleFillTests(unittest.TestCase):
    def fixture(self, kind, fill):
        story, drafts = graph_reuse_example()
        story['panels'] = story['panels'][:3]
        story['acts'] = story['acts'][:1]
        drafts = {key:drafts[key] for key in ('axes','curve','mark')}
        item = dict(id='area',type=kind,**{'in':'ax'},x=[.2,.7],y=[.2,.6])
        if fill != 'omitted': item['fill'] = fill
        drafts['curve']['items'] = [item,
            dict(id='area-label',type='label',to='area',text='Area',side='top')]
        drafts['mark']['items'] = [dict(id='p',type='dot',**{'in':'ax'},at=[.9,.9])]
        return story,drafts

    def test_same_fill_same_paths_bounds_label_attachment_and_native_cost(self):
        for fill in ('none','hatch'):
            compiled=[]
            for kind in ('rect','region'):
                story,drafts=self.fixture(kind,fill);original=deepcopy(drafts)
                compiled.append(compile_panel_shapes(story,drafts))
                self.assertEqual(original,drafts)
            a,b=compiled
            self.assertEqual(a['snapshot_points'],b['snapshot_points'])
            for identity in ('axes','curve','mark'):
                left,right=a['panels'][identity],b['panels'][identity]
                for field in ('plan','groups','item_bounds','label_layout'):
                    self.assertEqual(left[field],right[field])
                left_assets=storyboard_assets(left['plan'])
                right_assets=storyboard_assets(right['plan'])
                self.assertEqual([(x['stroke_count'],x['point_count']) for x in left_assets],
                                 [(x['stroke_count'],x['point_count']) for x in right_assets])
            self.assertEqual(a['panels']['curve']['groups']['area'],
                             a['panels']['mark']['groups']['area'])

    def test_omitted_fill_preserves_old_outline_and_explicit_hatch_adds_ink(self):
        panels=[]
        for fill in ('omitted','none','hatch'):
            story,drafts=self.fixture('rect',fill)
            panels.append(compile_panel_shapes(story,drafts)['panels']['curve'])
        self.assertEqual(panels[0]['plan'],panels[1]['plan'])
        self.assertEqual(len(panels[0]['groups']['area']),1)
        self.assertGreater(len(panels[2]['groups']['area']),1)
        self.assertGreater(panels[2]['added_points'],panels[0]['added_points'])

    def test_unsupported_fill_is_never_ignored_or_treated_as_syntax(self):
        for fill in ('solid','diagonal','url()',True,0,None,[],{}):
            for kind in ('rect','region'):
                with self.subTest(fill=fill,kind=kind):
                    story,drafts=self.fixture(kind,fill)
                    with self.assertRaises(ValueError) as caught:
                        compile_panel_shapes(story,drafts)
                    self.assertIsNone(correction_feedback(caught.exception))

    def test_hatching_is_still_subject_to_the_same_native_limits(self):
        # A rectangle is not a bypass around ordinary command/stroke budgets.
        for kind in ('rect','region'):
            story,drafts=self.fixture(kind,'hatch')
            lines=[dict(op='line',**{'from':[100,100],'to':[110,110]}) for _ in range(65)]
            with patch('notebook_panel_shapes._hatch_region',return_value=lines):
                with self.assertRaises(ValueError):compile_panel_shapes(story,drafts)

    def test_prompt_declares_optional_rectangle_fill_and_axis_title_edges(self):
        prompt=story_panel_instructions()
        self.assertIn('optional fill:"none" or "hatch" (default "none")',prompt)
        self.assertIn('Unknown fields and\nfill styles are rejected, not ignored.',prompt)
        self.assertIn('use bottom for the x-axis and left for the y-axis',prompt)


if __name__=='__main__':unittest.main()
