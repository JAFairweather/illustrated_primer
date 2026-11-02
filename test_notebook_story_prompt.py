"""Compile the actual incremental symbolic example, not a parallel fixture."""
import json
import unittest
from copy import deepcopy

from notebook_story_prompt import story_panel_instructions
from notebook_panel_shapes import compile_panel_shapes
from notebook_story_native import native_story_bundle


class StoryPromptTests(unittest.TestCase):
    def test_inherited_objects_and_connection_accept_label_only_addition(self):
        prompt=story_panel_instructions()
        example=prompt.split('Symbolic development without axes',1)[1]
        drafts={}
        while '{"v":' in example:
            example=example[example.index('{"v":'):]
            value,end=json.JSONDecoder().raw_decode(example)
            drafts[value['panel']]=value
            example=example[end:]
        self.assertEqual(list(drafts),['setup','transfer','meaning'])
        story=dict(v=1,mode='story',audience='New readers',template='explain_concept',
            question='How do diagrams explain a relationship?',
            acts=[dict(id='a',beat='Develop a relationship in three additions.')],
            panels=[],takeaway='Read the direction together with its label.')
        captions=('Start with the two participants.',
                  'An arrow shows a relationship from source to receiver.',
                  'Labels name the participants and explain the relationship.')
        previous=None
        for identity,caption in zip(drafts,captions):
            story['panels'].append(dict(id=identity,act='a',base=previous,title=identity,
                question='What does this step add?',new_idea=caption,
                visual_kind='relationship',caption=caption))
            previous=identity
        before=deepcopy(drafts)
        compiled=compile_panel_shapes(story,drafts)['panels']
        for identity in ('source','receiver'):
            self.assertEqual(compiled['setup']['groups'][identity],
                             compiled['meaning']['groups'][identity])
        self.assertEqual(compiled['transfer']['groups']['flow'],
                         compiled['meaning']['groups']['flow'])
        self.assertTrue(all(item['type']=='label' for item in drafts['meaning']['items']))
        bundle=native_story_bundle(story,drafts)
        self.assertEqual(len(bundle['plans']),1)
        self.assertEqual(len(bundle['sources']),3)
        self.assertLessEqual(bundle['delivery_points'],12000)
        self.assertEqual(drafts,before)


if __name__=='__main__':unittest.main()
