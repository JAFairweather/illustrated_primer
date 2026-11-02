import copy
import unittest

from notebook_procedural import (compile_board,_place_labels,_label_bounds,
                                 _object,_object_ports,_primitive,_route,
                                 _bounds,_route_commands,_route_conflicts,
                                 _segment_distance,_trim_path,_hits,_poly,
                                 _label_lines,_label_group,_route_label_candidates,
                                 _object_label_candidates,_group_label_bounds,LabelPlacementError)
from notebook_procedural_demo import examples
from notebook_stroke_asset import storyboard_assets
from unittest.mock import patch
import notebook_procedural


class ProceduralBoardTest(unittest.TestCase):
    def test_wrapped_object_label_uses_full_height_for_clearance(self):
        geometry=_object('cloud',500,255)
        box=_bounds(geometry)
        lines=('Cloud','droplets')
        local=_group_label_bounds(_label_group(lines,0,0))
        candidates=_object_label_candidates(box,(500,255))(local)
        self.assertEqual(len(candidates),16)
        self.assertEqual(candidates[:4],[(500,box[1]-13),(500,box[3]+30),
                                        (500,box[1]-30),(500,box[3]+48)])
        # Old fixed bottom baseline touches this tall wrapped label's owner.
        x,y=candidates[3]
        old=_group_label_bounds(_label_group(lines,x,y))
        self.assertAlmostEqual(old[1]-6,box[3])
        # Full-box candidates maintain the stated gap, even with descenders.
        for index,gap in ((4,14),(6,28)):
            above=_group_label_bounds(_label_group(lines,*candidates[index]))
            below=_group_label_bounds(_label_group(lines,*candidates[index+1]))
            self.assertAlmostEqual(box[1]-above[3],gap)
            self.assertAlmostEqual(below[0]+(below[2]-below[0])/2,500)
            self.assertAlmostEqual(below[1]-box[3],gap)

    def test_five_node_return_loop_keeps_all_labels_and_native_caps(self):
        # Geometry/words from a saved first-pass failure; acceptance here is
        # layout only, not approval of using a water-pool icon for water vapor.
        names=['sun','surface','vapor','cloud','rain']
        shapes=['sun','water','water','cloud','water']
        labels=['Sunlight','Surface water','Water vapor','Cloud droplets','Rainwater']
        links=[('heat','sun','surface','heats'),('evap','surface','vapor','evaporation'),
               ('condense','vapor','cloud','condensation'),('precip','cloud','rain','precipitation'),
               ('return','rain','surface','returns')]
        spec=dict(kind='network',objects=[dict(id=i,shape=s,label=l) for i,s,l in zip(names,shapes,labels)],
            links=[dict(id=i,**{'from':a,'to':b},label=l) for i,a,b,l in links],
            steps=[dict(add=ids,caption='A layout regression fixture.') for ids in
                   (['sun','surface'],['heat','vapor','evap'],['condense','cloud'],['precip','rain','return'])],
            takeaway='Layout test, not verified physical interpretation.')
        original=copy.deepcopy(spec)
        plan=compile_board(spec)
        self.assertEqual(spec,original)
        self.assertEqual(plan,compile_board(spec))
        spec['objects'].reverse()
        self.assertEqual(plan,compile_board(spec))
        layout=plan['procedural']['layout']
        self.assertEqual(layout[0]['objects']['surface']['slot'],[.75,0])
        found={item['id']:item for item in layout[1:]}
        for item in original['objects']+original['links']:
            self.assertEqual(' '.join(found[item['id']]['lines']),item['label'])
            self.assertEqual(found[item['id']]['size'],18)
        self.assertEqual([s['text'] for s in plan['stages']],
                         [s['caption'] for s in original['steps']])
        from notebook_ink_playback import playback_assets
        assets=playback_assets(plan)
        self.assertEqual(len(assets),4)
        self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000 for a in assets))
        self.assertTrue(all(a['playback']['duration_ms']<=30000 for a in assets))
        self.assertLessEqual(sum(a['point_count'] for a in assets),12000)
        # Unrelated scene labels/shapes use the same renderer-owned layout,
        # with no semantic IDs or topic names hard-coded into the algorithm.
        for obj in spec['objects']:
            obj['shape']='box'
        spec['objects'][0]['label']='Collector'
        with self.assertRaises((LabelPlacementError,notebook_procedural.RoutePlacementError)):
            compile_board(spec)  # Wider outlines can still leave insufficient room.
        for obj,label in zip(spec['objects'],('Return','Cooler','Vapor','Tank','Heater')):
            obj['label']=label
            obj['shape']='circle'
        self.assertEqual(len(playback_assets(compile_board(spec))),4)

    def test_four_node_cycle_retains_labels_and_native_budgets(self):
        # Actual second-model failure: precipitation could not fit beside the
        # vertical edge/return arc in the original narrow triangular layout.
        spec={'kind':'network','objects':[
            {'id':'sun','shape':'sun','label':'Sunlight'},
            {'id':'ocean','shape':'water','label':'Ocean'},
            {'id':'cloud','shape':'cloud','label':'Clouds'},
            {'id':'land','shape':'box','label':'Land'}],
            'links':[
                {'id':'heat','from':'sun','to':'ocean','label':'heats surface water'},
                {'id':'evap','from':'ocean','to':'cloud','label':'evaporation'},
                {'id':'precip','from':'cloud','to':'land','label':'precipitation'},
                {'id':'runoff','from':'land','to':'ocean','label':'runoff to sea'}],
            'steps':[
                {'caption':'Sunlight warms surface water.','add':['sun','ocean','heat']},
                {'caption':'Vapor rises and condenses into clouds.','add':['cloud','evap']},
                {'caption':'Rain reaches land and runoff returns to the ocean.','add':['land','precip','runoff']}],
            'takeaway':'Sunlight drives the water cycle.'}
        original=copy.deepcopy(spec)
        plan=compile_board(spec)
        self.assertEqual(spec,original)
        self.assertEqual(plan,compile_board(spec))
        spec['objects'].reverse()
        self.assertEqual(plan,compile_board(spec))
        layout=plan['procedural']['layout']
        self.assertEqual(layout[0]['objects']['ocean']['slot'],[1,1])
        found={item['id']:item for item in layout[1:]}
        for item in original['objects']+original['links']:
            self.assertEqual(' '.join(found[item['id']]['lines']),item['label'])
            self.assertEqual(found[item['id']]['size'],18)
        # Actual native encoding, not merely a successful label search.
        assets=storyboard_assets(plan)
        self.assertEqual(len(assets),3)
        self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000 for a in assets))
        self.assertTrue(all(s['estimated_pen_seconds']<=30 for s in plan['stages']))
        for index,(link,route) in enumerate(zip(original['links'],layout[0]['routes'])):
            self.assertFalse(_route_conflicts(route,_route_commands(route),layout[0]['routes'][:index]))
            for identity,obj in layout[0]['objects'].items():
                col,row=obj['slot']
                shape=next(o['shape'] for o in original['objects'] if o['id']==identity)
                box=_bounds(_object(shape,100+200*col,85+layout[0]['row_gap']*row))
                interior=_trim_path(route) if identity in (link['from'],link['to']) else route
                self.assertFalse(_hits([_poly(interior)],box))

    def test_composition_attempts_bounded_and_only_layout_errors_retry(self):
        for count in (4,5):
            spec={'kind':'network','objects':[{'id':chr(97+i)} for i in range(count)],
                  'links':[{'id':'e'+str(i),'from':chr(97+i),'to':chr(98+i),'label':'next'}
                           for i in range(count-1)]}
            with patch.object(notebook_procedural,'_network',side_effect=LabelPlacementError('full')) as network:
                with self.assertRaisesRegex(LabelPlacementError,'full'):compile_board(spec)
                self.assertEqual(network.call_count,20)
        with patch.object(notebook_procedural,'_network',side_effect=ValueError('bad spec')) as network:
            with self.assertRaisesRegex(ValueError,'bad spec'):compile_board(spec)
            self.assertEqual(network.call_count,1)

    def test_word_wrap_preserves_words_font_and_descender_clearance(self):
        for text in ('evaporation rises','precipitation falls','sunlight warms'):
            lines=_label_lines(text)[0]
            self.assertEqual(' '.join(lines),text)
            self.assertEqual(len(lines),2)
            commands=_label_group(lines,300,160)
            self.assertTrue(all(command['size']==18 for command in commands))
            upper,lower=map(_label_bounds,commands)
            self.assertAlmostEqual(lower[1]-upper[3],6)
        self.assertEqual(_label_lines('Cloud')[0],('Cloud',))

    def test_label_search_backtracks_without_returning_partial_placement(self):
        # A's first location steals B's only unique location. Equal option
        # counts keep A first; C has one location and is placed first overall.
        items=[('a','A',[(100,40),(300,40)]),
               ('b','B',[(100,40),(100,40)]),('c','C',[(500,40)])]
        placed,_=_place_labels(items,[])
        box=_label_bounds(placed['a'][0])
        self.assertAlmostEqual((box[0]+box[2])/2,300)
        self.assertEqual(set(placed),{'a','b','c'})
        with self.assertRaises(LabelPlacementError):
            _place_labels([('a','A',[(100,40)]),('b','B',[(100,40)])],[])

    def test_label_search_has_a_hard_attempt_bound(self):
        positions=[(50+50*i,80) for i in range(10)]
        items=[(str(i),'A',positions) for i in range(11)]
        with self.assertRaisesRegex(LabelPlacementError,'search budget'):
            _place_labels(items,[])

    def test_route_label_positions_are_bounded_and_sampling_independent(self):
        box=(-50,-18,50,0)
        a=_route_label_candidates([(20,80),(520,80)],box)
        b=_route_label_candidates([(20,80),(120,80),(220,80),(520,80)],box)
        self.assertEqual(a,b)
        self.assertEqual(len(a),20)

    def test_long_process_labels_compile_without_wording_or_relationship_repairs(self):
        for labels in [('sunlight warms','evaporation rises','precipitation falls'),
                       ('solar heating','water evaporates','rain returns'),
                       ('warmth','rising vapor','rainfall returns')]:
            with self.subTest(labels=labels):
                spec=examples()['water-cycle']
                spec['objects'][1]['label']='Ocean'
                for link,text in zip(spec['links'],labels):link['label']=text
                before=copy.deepcopy(spec)
                plan=compile_board(spec)
                self.assertEqual(spec,before)
                self.assertEqual(plan,compile_board(spec))
                layout=plan['procedural']['layout']
                self.assertIn(layout[0]['row_gap'],(170,140))
                found={item['id']:item for item in layout[1:]}
                for link in spec['links']:
                    self.assertEqual(' '.join(found[link['id']]['lines']),link['label'])
                    self.assertEqual(found[link['id']]['size'],18)
                boxes=[item['label_box'] for item in layout[1:]]
                for i,box in enumerate(boxes):
                    self.assertTrue(4<=box[0]<box[2]<=596 and 4<=box[1]<box[3]<=356)
                    for other in boxes[i+1:]:
                        self.assertFalse(box[0]<other[2] and box[2]>other[0]
                                         and box[1]<other[3] and box[3]>other[1])
                self.assertEqual(len(storyboard_assets(plan)),3)

    def test_examples_deterministic_no_mutation_real_native_encoder(self):
        for name,spec in examples().items():
            with self.subTest(name=name):
                original=copy.deepcopy(spec)
                plan=compile_board(spec)
                self.assertEqual(plan,compile_board(spec))
                self.assertEqual(spec,original)
                self.assertEqual(len(storyboard_assets(plan)),3)

    def test_lever_parameters_control_both_scales(self):
        for arms,forces in [([1,3],[3,1]),([2,5],[5,2]),([4,1],[1,4])]:
            spec=examples()['lever'];spec.update(arms=arms,forces=forces)
            layout=compile_board(spec)['procedural']['layout'][0]
            a,b=layout['arm_lengths_px'];f,g=layout['force_lengths_px']
            self.assertAlmostEqual(a/b,arms[0]/arms[1])
            self.assertAlmostEqual(f/g,forces[0]/forces[1])

    def test_rejects_duplicates_bad_reveal_and_unknown_fields(self):
        for mutate in [
            lambda s:s['objects'][1].update(id='person'),
            lambda s:s['objects'][1].update(slot=[0,0]),
            lambda s:s['objects'][1].update(slot=[True,0]),
            lambda s:s['objects'][1].update(slot=[300,0]),
            lambda s:s['objects'][1].update(url='https://example.org'),
            lambda s:s['links'][0].update(to='missing'),
            lambda s:s['steps'][0].update(add=['ask']),
            lambda s:s['steps'][1].update(add=['person']),
            lambda s:s['objects'][0].update(label='/tmp/file'),
        ]:
            spec=examples()['short-plan'];mutate(spec)
            with self.assertRaises(ValueError):compile_board(spec)

    def test_no_silent_claim_of_balance(self):
        spec=examples()['lever'];spec['forces']=[5,1]
        layout=compile_board(spec)['procedural']['layout'][0]
        self.assertEqual(layout['moments_Nm'],[5,3])

    def test_candidate_outside_region_does_not_abort_search(self):
        placed,_=_place_labels([('label','A long label',[(0,40),(300,40)])],[])
        self.assertGreater(_label_bounds(placed['label'][0])[0],0)
        self.assertEqual(placed['label'][0]['size'],18)

    def test_layout_is_derived_from_relationships_not_object_order(self):
        spec=examples()['water-cycle']
        original=compile_board(spec)
        spec['objects'].reverse()
        self.assertEqual(compile_board(spec),original)

    def test_named_ports_touch_the_drawn_contour(self):
        for shape in ('circle','box','person','sun','cloud','water'):
            paths=[path for c in _object(shape,300,180) for path in _primitive(c)]
            for name,p in _object_ports(shape,300,180).items():
                def distance(a,b):
                    dx,dy=b[0]-a[0],b[1]-a[1]
                    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
                    return ((p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2)**.5
                self.assertLess(min(distance(a,b) for path in paths for a,b in zip(path,path[1:])),1e-8,(shape,name))

    def test_organic_contours_are_closed_and_smooth_not_bucket_polygons(self):
        for shape in ('cloud','water'):
            contour=_object(shape,300,180)[0]['points']
            self.assertEqual(contour[0],contour[-1])
            self.assertGreater(len(contour),30)
            self.assertLessEqual(len(contour),160)
            # Every knot is interpolated; no noisy/random per-render jitter.
            self.assertEqual(_object(shape,300,180),_object(shape,300,180))

    def test_curved_process_routes_have_clear_separate_directions(self):
        spec=examples()['water-cycle']
        layout=compile_board(spec)['procedural']['layout'][0]
        routes=layout['routes']
        self.assertEqual(len(routes),3)
        for index,(link,points) in enumerate(zip(spec['links'],routes)):
            self.assertEqual(len(points),25)
            self.assertIn(points[0],layout['objects'][link['from']]['ports'].values())
            self.assertIn(points[-1],layout['objects'][link['to']]['ports'].values())
            self.assertFalse(_route_conflicts(points,_route_commands(points),routes[:index]))
            for identity,obj in layout['objects'].items():
                col,row=obj['slot'];shape=next(o['shape'] for o in spec['objects'] if o['id']==identity)
                box=_bounds(_object(shape,100+200*col,85+170*row))
                # Interior cannot cross either endpoint object; unrelated
                # objects must be clear along the entire connector.
                path=_trim_path(points) if identity in (link['from'],link['to']) else points
                self.assertFalse(_hits([_poly(path)],box))

    def test_segment_clearance_detects_crossings_between_vertices(self):
        self.assertEqual(_segment_distance((0,0),(20,20),(0,20),(20,0)),0)
        self.assertEqual(_segment_distance((0,0),(20,0),(0,7),(20,7)),7)
        self.assertEqual(_segment_distance((0,0),(20,0),(10,0),(30,0)),0)

    def test_trim_measures_arc_length_not_sample_count(self):
        self.assertEqual(_trim_path([(0,0),(5,0),(10,0),(50,0)]),[(14.0,0.0),(36.0,0.0)])

    def test_curved_arrowhead_size_does_not_shrink_with_sampling(self):
        points=[(100,100),(200,100),(201,100)]
        head=_route_commands(points)[1]['points']
        self.assertEqual(head,[[191.0,105.0],[201,100],[191.0,95.0]])

    def test_prior_arrowhead_is_an_obstacle_not_only_its_shaft(self):
        old=[(100,100),(200,100)]
        new=[(188,70),(188,130)]
        self.assertTrue(_route_conflicts(new,_route_commands(new),[old]))

    def test_routes_generalize_across_object_shapes_and_directions(self):
        for shape in ('circle','box','person','sun','cloud','water'):
            for destination in ((500,85),(300,255),(100,255)):
                positions={'a':(100,85),'b':destination}
                boxes={i:_bounds(_object(shape,*pos)) for i,pos in positions.items()}
                ports={i:_object_ports(shape,*pos) for i,pos in positions.items()}
                with self.subTest(shape=shape,destination=destination):
                    commands,points=_route('a','b',boxes,ports)
                    self.assertIn(points[0],ports['a'].values())
                    self.assertIn(points[-1],ports['b'].values())
                    for c in commands:_primitive(c)


if __name__ == '__main__':unittest.main()
