import json
import unittest

from notebook_worked_lessons import worked_examples, prompt_examples
from notebook_role_prompts import role_prompt
from notebook_story_native import native_story_bundle
from notebook_story_plan import validate_story
from notebook_stroke_asset import validate_native_ink_budget


class WorkedLessonTests(unittest.TestCase):
    def test_all_three_examples_pass_whole_native_preparation(self):
        examples = worked_examples()
        self.assertEqual(set(examples), {'integral','odd-squares','riemann-claim'})
        for name,(story,shapes) in examples.items():
            with self.subTest(name=name):
                validate_story(story)
                for playback in (False,True):
                    bundle = native_story_bundle(story,shapes,playback=playback)
                    self.assertLessEqual(bundle['snapshot_points'],12000)
                    self.assertLessEqual(bundle['delivery_points'],12000)
                    validate_native_ink_budget(bundle['blocks'])
                    self.assertEqual(bundle['blocks'][-2]['role'],'equation')
                    self.assertFalse(bundle['tablet_proven'])

    def test_planner_examples_are_geometry_free_drawer_examples_use_same_stories(self):
        rows = {}
        for role in ('planner','drawer'):
            rendered = prompt_examples(role)
            rows[role] = [json.loads(line) for line in rendered.splitlines() if line.startswith('{')]
            self.assertEqual(len(rows[role]),3)
            self.assertIn(rendered, role_prompt(role))
            self.assertLess(len(role_prompt(role).encode()),64000)
        for plan,draw in zip(rows['planner'],rows['drawer']):
            self.assertEqual(set(plan),{'example','story'})
            self.assertEqual(plan['story'], draw['story'])
            self.assertEqual(draw['answer']['mode'],'story-shapes')
            expected = worked_examples()[plan['example']]
            self.assertEqual(draw['answer']['panels'],expected[1])
        claim = rows['planner'][-1]['story']
        self.assertEqual(len(claim['acts']),5)
        self.assertEqual(len(claim['panels']),10)
        self.assertIn('unreviewed',claim['takeaway'])
        self.assertIn('unreviewed',claim['panels'][8]['caption'])
        self.assertNotEqual(claim['panels'][8]['base'],'old-zone')


if __name__ == '__main__': unittest.main()
