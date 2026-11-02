from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from notebook_panel_examples import relationship_example
from notebook_panel_shapes import compile_panel_shapes
from notebook_panel_objects import lower_symbolic, SHAPES, POSITIONS
from notebook_panel_eval import review_panels
from notebook_procedural import _bounds, _hits, _object_ports


class SymbolicPanelTests(unittest.TestCase):
    def short(self, length=1):
        story,drafts=relationship_example()
        story['panels']=story['panels'][:length]
        return story,{panel['id']:drafts[panel['id']] for panel in story['panels']}

    def test_objects_connections_and_historical_branch_preserve_exact_ink(self):
        story,drafts=relationship_example();original=deepcopy(drafts)
        result=compile_panel_shapes(story,drafts);panels=result['panels']
        self.assertEqual(drafts,original)
        self.assertEqual(panels['objects']['frames'],{})
        for identity,group in panels['objects']['groups'].items():
            self.assertEqual(group,panels['observer']['groups'][identity])
        self.assertEqual(panels['forward']['groups']['flow'],panels['observer']['groups']['flow'])
        self.assertNotIn('flow',panels['reverse']['groups'])
        self.assertNotIn('reader',panels['reverse']['items'])
        self.assertEqual([s['id'] for s in panels['reverse']['plan']['stages']],['objects','reverse'])
        self.assertFalse(result['native_delivery_supported'])
        self.assertEqual(result['snapshot_points'],sum(p['snapshot_points'] for p in panels.values()))

    def test_named_positions_and_contours_have_no_model_pixel_coordinates(self):
        for shape in SHAPES:
            for position in POSITIONS:
                story,drafts=self.short()
                drafts['objects']['items']=[dict(id='thing',type='object',shape=shape,position=position)]
                panel=compile_panel_shapes(story,drafts)['panels']['objects']
                self.assertGreater(panel['added_points'],0)
                left,top,right,bottom=panel['item_bounds']['thing']
                self.assertTrue(0<=left<right<=600 and 0<=top<bottom<=360)

    def test_connections_attach_to_contour_ports_and_avoid_frozen_labels(self):
        story,drafts=relationship_example();panels=compile_panel_shapes(story,drafts)['panels']
        for panel_id,connection,source,target in (
                ('forward','flow','input','output'),('observer','delivery','output','reader'),
                ('reverse','feedback','output','input')):
            panel=panels[panel_id];commands=panel['groups'][connection]
            path=commands[0]['points']
            for point,identity in ((path[0],source),(path[-1],target)):
                obj=panel['items'][identity]
                ports=_object_ports(obj['shape'],*POSITIONS[obj['position']])
                self.assertIn(tuple(point),ports.values())
            for identity,item in panel['items'].items():
                if item['type']=='label':
                    self.assertFalse(_hits(commands,_bounds(panel['groups'][identity])))

    def test_objects_cannot_occupy_old_slots_or_cover_old_connections(self):
        story,drafts=self.short(2)
        drafts['forward']['items']=[dict(id='duplicate',type='object',shape='box',position='top-left')]
        with self.assertRaisesRegex(ValueError,'already occupied'):compile_panel_shapes(story,drafts)
        story,drafts=self.short(3)
        # The first arrow spans the top-center slot. Never move it or draw a
        # new box around its shaft to make the new object appear connected.
        drafts['observer']['items']=[dict(id='obstacle',type='object',shape='box',position='top-center')]
        with self.assertRaisesRegex(ValueError,'cover existing ink'):compile_panel_shapes(story,drafts)

    def test_connectors_route_around_intermediate_objects(self):
        story,drafts=self.short(2)
        drafts['objects']['items']=[dict(id=identity,type='object',shape='box',position=position)
            for identity,position in [('a','top-left'),('b','top-right'),('obstacle','top-center')]]
        drafts['forward']['items']=[dict(id='edge',type='connect',**{'from':'a','to':'b'})]
        panel=compile_panel_shapes(story,drafts)['panels']['forward']
        self.assertFalse(_hits(panel['groups']['edge'],panel['item_bounds']['obstacle']))
        self.assertGreater(len(panel['groups']['edge'][0]['points']),2)

    def test_invalid_shape_slot_raw_fields_and_missing_targets_are_rejected(self):
        for changes in [dict(shape='arbitrary-svg'),dict(position=[100,85]),dict(position='anywhere'),
                        dict(path='/tmp/shape'),dict(x=100),dict(url='https://example.org')]:
            story,drafts=self.short();drafts['objects']['items'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):compile_panel_shapes(story,drafts)
        for source,target in [('input','input'),('missing','output'),('input-name','output')]:
            story,drafts=self.short(2)
            drafts['forward']['items']=[dict(id='edge',type='connect',**{'from':source,'to':target})]
            with self.subTest(source=source,target=target),self.assertRaisesRegex(ValueError,'distinct earlier'):
                compile_panel_shapes(story,drafts)

    def test_mathematical_and_symbolic_frames_cannot_be_mixed(self):
        axes=dict(id='axes',type='axes',x=[0,1],y=[0,1],aspect='equal')
        obj=dict(id='obj',type='object',shape='circle',position='top-left')
        for items in ([axes,obj],[obj,axes]):
            story,drafts=self.short();drafts['objects']['items']=items
            with self.assertRaisesRegex(ValueError,'separate pictures'):compile_panel_shapes(story,drafts)

    def test_connection_count_is_bounded_before_routing(self):
        items={name:dict(id=name,type='object',shape='box',position=position)
               for name,position in [('a','top-left'),('b','top-right')]}
        for number in range(8):items['edge-'+str(number)]={'type':'connect'}
        with self.assertRaisesRegex(ValueError,'eight symbolic'):
            lower_symbolic(dict(id='extra',type='connect',**{'from':'a','to':'b'}),items,{}, {})

    def test_offline_preview_uses_native_encoder_without_device_delivery(self):
        story,drafts=relationship_example()
        with tempfile.TemporaryDirectory() as temp:
            result=review_panels(json.dumps(story).encode(),json.dumps(drafts).encode(),Path(temp)/'preview',
                                 authored_example='relationship')
            self.assertTrue(result['valid']);self.assertTrue(result['ink_encoding_validated'])
            self.assertEqual(result['authored_example'],'relationship')
            self.assertEqual(result['model_calls'],0)
            self.assertFalse(result['tablet_proven'])
            self.assertEqual(len(list((Path(temp)/'preview').glob('*.png'))),4)
            self.assertFalse(list(Path(temp).rglob('*.rm')))


if __name__=='__main__':unittest.main()
