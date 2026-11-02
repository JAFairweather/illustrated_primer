from copy import deepcopy
import unittest
from unittest.mock import patch

from notebook_label_candidates import corner_callouts
from notebook_panel_shapes import _candidates, compile_panel_shapes
from notebook_panel_examples import relationship_example
from notebook_procedural import LabelPlacementError
from notebook_stroke_asset import storyboard_assets


class CornerCalloutTests(unittest.TestCase):
    def test_finite_candidates_use_measured_asymmetric_label_extents(self):
        bounds=(100,80,140,120);box=(-30,-40,50,5)
        result=corner_callouts(bounds,box)
        self.assertEqual(len(result),12)
        self.assertEqual(len(set(result)),12)
        self.assertEqual(result[:4],[(14,63),(14,172),(206,63),(206,172)])
        self.assertEqual(result,corner_callouts(bounds,box))
        # Every candidate has exactly twelve units of vertical clearance.
        self.assertTrue(all(y+box[3]==68 or y+box[1]==132 for _,y in result))

    def test_existing_candidates_keep_order_and_unattached_labels_do_not_expand(self):
        bounds=(100,80,140,120);box=(-30,-40,50,5)
        before=_candidates(bounds,'top')(box)
        extended=_candidates(bounds,'top',callouts=True)
        self.assertEqual(extended(box),before)
        self.assertEqual(extended.fallback(box),corner_callouts(bounds,box))
        self.assertFalse(hasattr(_candidates(bounds,'top'),'fallback'))

    def crowded_picture(self):
        story,_=relationship_example()
        story['panels'][2]['base']='objects'
        story['panels'][3]['base']='observer'
        drawings={
            'objects':[
                dict(id='a',type='object',shape='circle',position='top-left'),
                dict(id='b',type='object',shape='circle',position='bottom-left'),
                dict(id='c',type='object',shape='circle',position='top-right'),
                dict(id='a-label',type='label',to='a',text='Input a',side='left'),
                dict(id='b-label',type='label',to='b',text='Input b (b ≠ a)',side='left'),
                dict(id='c-label',type='label',to='c',text='Output c',side='right')],
            'forward':[
                dict(id='ac',type='connect',**{'from':'a','to':'c'}),
                dict(id='bc',type='connect',**{'from':'b','to':'c'})],
            'observer':[
                dict(id='ca',type='connect',**{'from':'c','to':'a'}),
                dict(id='cb',type='connect',**{'from':'c','to':'b'})],
            'reverse':[dict(id='note',type='label',to='c',
                             text='Two required outputs',side='bottom')]}
        return story,{key:dict(v=1,mode='panel-shapes',panel=key,items=items)
                      for key,items in drawings.items()}

    def test_two_annotations_share_owner_without_mutating_any_input(self):
        story,drafts=self.crowded_picture();original=deepcopy((story,drafts))
        with patch('notebook_panel_shapes.corner_callouts',return_value=[]):
            with self.assertRaises(LabelPlacementError):compile_panel_shapes(story,drafts)
        result=compile_panel_shapes(story,drafts)['panels']
        self.assertEqual((story,drafts),original)
        for key,commands in result['objects']['groups'].items():
            self.assertEqual(commands,result['reverse']['groups'][key])
        self.assertTrue(result['reverse']['label_layout'][0]['leaders'])
        self.assertTrue(all(asset['stroke_count']<=64 and asset['point_count']<=3000
            for asset in storyboard_assets(result['reverse']['plan'])))


if __name__=='__main__':unittest.main()
