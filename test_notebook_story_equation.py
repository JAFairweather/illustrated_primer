"""Final equations share the whole story's offline/native validation boundary."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from ink import strokes
from notebook_equation_ink import equation_plan
from notebook_drawing import compile_storyboard
from notebook_panel_examples import graph_reuse_example
from notebook_panel_eval import review_panels
from notebook_panel_shapes import compile_panel_shapes
from notebook_role_eval import preview_sheet
from notebook_story_native import native_story_bundle
from notebook_story_plan import validate_story
from notebook_stroke_asset import validate_native_ink_budget


class StoryEquationTests(unittest.TestCase):
    def fixture(self):
        story, drafts = graph_reuse_example()
        story['equation'] = r'\int_0^1 x^2\,dx=\frac{1}{3}'
        return story, drafts

    def test_final_pen_equation_preserves_every_diagram_and_shares_budget(self):
        story, drafts = self.fixture()
        baseline = deepcopy(story); del baseline['equation']
        before = compile_panel_shapes(baseline, drafts)
        after = compile_panel_shapes(story, drafts)
        self.assertEqual(before['panels'], after['panels'])
        self.assertEqual(after['equation_plan'], equation_plan(story['equation']))
        self.assertEqual(after['snapshot_points'], before['snapshot_points'] +
                         compile_storyboard(after['equation_plan'])['points'])
        for playback in (False, True):
            original = native_story_bundle(baseline, drafts, playback=playback)
            bundle = native_story_bundle(story, drafts, playback=playback)
            self.assertEqual(len(bundle['sources']), len(original['sources'])+1)
            def geometry(b):
                return [[points for _,points,_ in strokes(s['data'])] for s in b['sources']]
            self.assertEqual(geometry(original), geometry(bundle)[:-1])
            equation = bundle['blocks'][-2]
            self.assertEqual((equation['kind'],equation['role']), ('ink','equation'))
            self.assertNotIn('story', equation)
            self.assertEqual('playback' in equation, playback)
            self.assertTrue(bundle['blocks'][-1]['text'].startswith('Takeaway:'))
            self.assertEqual(bundle['delivery_points'],
                             sum(b['point_count'] for b in validate_native_ink_budget(bundle['blocks'])))

    def test_equation_grammar_is_data_only_and_fails_before_any_assets(self):
        story, drafts = self.fixture()
        for bad in (None, '', '/tmp/result', 'https://example.com', r'\input{file}',
                    r'\unknown{x}', 'x'*40, r'\frac{1}', 'x'*401):
            candidate = deepcopy(story); candidate['equation'] = bad
            with self.subTest(bad=bad), patch('notebook_story_native.storyboard_assets') as assets, \
                    patch('notebook_ink_playback.playback_assets') as playback:
                with self.assertRaises(ValueError):
                    native_story_bundle(candidate, drafts)
                assets.assert_not_called(); playback.assert_not_called()
        candidate = deepcopy(story)
        candidate['equation'] = '  \\frac{1}{2}\n= \\frac{2}{4} '
        self.assertEqual(validate_story(candidate)['equation'], r'\frac{1}{2} = \frac{2}{4}')

    def test_late_equation_cannot_bypass_story_point_budget(self):
        story, drafts = self.fixture()
        from notebook_panel_shapes import compile_storyboard as real_compile
        def inflated(plan):
            result = real_compile(plan)
            if plan['scene'].startswith('equation-'):
                result['points'] = 12000  # isolate aggregate-boundary behavior
            return result
        with patch('notebook_panel_shapes.compile_storyboard', side_effect=inflated), \
                patch('notebook_story_native.storyboard_assets') as assets, \
                patch('notebook_ink_playback.playback_assets') as playback:
            with self.assertRaisesRegex(ValueError, 'whole-story'):
                native_story_bundle(story, drafts)
            assets.assert_not_called(); playback.assert_not_called()

    def test_equation_not_reordered_duplicated_or_disguised_as_story_part(self):
        story, drafts = self.fixture(); blocks = native_story_bundle(story,drafts)['blocks']
        for change in ('duplicate','reorder','descriptor','scene','points'):
            candidate = deepcopy(blocks); eq = candidate[-2]
            if change == 'duplicate': candidate.insert(-1,deepcopy(eq))
            if change == 'reorder': candidate.insert(0,candidate.pop(-2))
            if change == 'descriptor': eq['story'] = deepcopy(candidate[2]['story'])
            if change == 'scene': eq['scene'] = candidate[2]['scene']
            if change == 'points': eq['point_count'] = 3001
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_native_ink_budget(candidate)

    def test_preview_and_critic_show_the_actual_equation_not_just_its_source(self):
        story, drafts = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)/'preview'
            result = review_panels(json.dumps(story).encode(), json.dumps(drafts).encode(), dest)
            self.assertTrue(result['valid'], result)
            svg = (dest/'equation.svg').read_text()
            self.assertIn('<polyline', svg)
            self.assertNotIn('<text', svg); self.assertNotIn('<image', svg)
            page = (dest/'index.html').read_text()
            self.assertLess(page.index('equation.png'), page.index('<h2>Takeaway'))
            sheet = Image.open(BytesIO(preview_sheet(story,dest)))
            self.assertEqual(sheet.size, (1200,1164))
            with Image.open(dest/'equation.png') as equation:
                self.assertEqual(sheet.crop((0,804,600,1004)).tobytes(), equation.convert('RGB').tobytes())
            (dest/'equation.png').unlink()
            with self.assertRaises(FileNotFoundError): preview_sheet(story,dest)


if __name__ == '__main__': unittest.main()
