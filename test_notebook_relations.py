import copy
import json
import unittest
from unittest.mock import patch

from notebook_lesson import compile_lesson, _primitive
from notebook_lesson_native import native_semantic_bundle
from notebook_procedural import _hits
from notebook_relations import resolve_connections, _plan_routes
from notebook_semantic import compile_semantic, SemanticError, CAPABILITIES


def lesson(domain='math'):
    names = ('Input', 'Image', 'Map') if domain == 'math' else ('Sensor', 'Alarm', 'Signal')
    return [
        {'caption': 'Identify the two entities.', 'draw': [
            {'op': 'circle', 'id': 'a', 'center': [110, 180], 'radius': 45},
            {'op': 'rect', 'id': 'b', 'origin': [400, 140], 'size': [110, 80]},
            {'op': 'label', 'target': 'a', 'text': names[0]},
            {'op': 'label', 'target': 'b', 'text': names[1]}]},
        {'caption': 'The directed relation links them.', 'draw': [
            {'op': 'connect', 'from': 'a', 'to': 'b', 'id': 'edge'}]},
        {'caption': 'Name the relation separately from its endpoints.', 'draw': [
            {'op': 'label', 'target': 'edge', 'text': names[2]}]}]


def spec(steps):
    return dict(v=1, mode='lesson', intent='Explain a directed relationship',
                scene={'family': 'drawing'}, steps=steps, claims=[],
                takeaway='The arrow shows the direction of the relationship.')


class ConnectionTests(unittest.TestCase):
    def test_joint_allocation_routes_merge_then_split_without_moving_shapes(self):
        from notebook_procedural import _route, _route_conflicts, RoutePlacementError
        for reflected in (False, True):
            centers=[(70,80),(70,260),(250,170),(500,80),(500,260)]
            centers=[(600-x if reflected else x,y) for x,y in centers]
            shapes=[dict(op='circle',id=name,center=list(center),radius=22)
                    for name,center in zip('abcde',centers)]
            source=[dict(caption='Identify five entities.',draw=shapes),
                    dict(caption='Two entities connect to the shared middle.',draw=[
                        dict(op='connect',id='ac',**{'from':'a','to':'c'}),
                        dict(op='connect',id='bc',**{'from':'b','to':'c'})]),
                    dict(caption='The middle connects to two more entities.',draw=[
                        dict(op='connect',id='cd',**{'from':'c','to':'d'}),
                        dict(op='connect',id='ce',**{'from':'c','to':'e'}),
                        {'op':'brace','from':[50 if reflected else 550,58],
                         'to':[50 if reflected else 550,282],'side':-1 if reflected else 1}])]
            before=copy.deepcopy(source)
            def greedy(pending,boxes,ports,route):
                selected={};previous=[]
                for i,(_,_,_,a,b) in enumerate(pending):
                    selected[i]=route(a,b,boxes,ports,previous)
                    previous.append(selected[i][1])
                return selected
            with patch('notebook_relations._plan_routes',greedy):
                with self.assertRaises(RoutePlacementError):resolve_connections(source)
            resolved,records=resolve_connections(source)
            self.assertEqual(source,before)
            self.assertEqual(resolved[0],source[0])
            self.assertEqual([(r['source'],r['target']) for r in records],
                             [('a','c'),('b','c'),('c','d'),('c','e')])
            self.assertEqual([r['step'] for r in records],[2,2,3,3])
            self.assertEqual((resolved,records),resolve_connections(source))
            previous=[]
            for step in resolved[1:]:
                commands=[c for c in step['draw'] if c['op']!='brace']
                for i in range(0,len(commands),2):
                    route=[{k:v for k,v in c.items() if k!='id'} for c in commands[i:i+2]]
                    self.assertFalse(_route_conflicts(route[0]['points'],route,previous))
                    previous.append(route[0]['points'])
            plan=compile_lesson(source,'Relations retain their declared directions and stages.')
            for stage in plan['stages']:
                self.assertLessEqual(stage['points'],3000)
                self.assertLessEqual(len(stage['paths']),64)
                self.assertLessEqual(stage['estimated_pen_seconds'],30)

    def test_joint_route_planning_happy_path_is_byte_identical_and_linear(self):
        from notebook_procedural import _route
        calls=[]
        def record(*args,**kwargs):
            result=_route(*args,**kwargs);calls.append(copy.deepcopy(result));return result
        with patch('notebook_procedural._route',record):
            resolved,records=resolve_connections(lesson())
        self.assertEqual(len(calls),1)
        commands=[{k:v for k,v in c.items() if k!='id'} for c in resolved[1]['draw']]
        self.assertEqual(commands,calls[0][0])

    def test_joint_route_search_is_bounded_and_does_not_swallow_other_errors(self):
        from notebook_procedural import RoutePlacementError
        pending=[(0,i,None,'a','b') for i in range(12)]
        calls=[]
        def blocked(a,b,boxes,ports,previous):
            calls.append((a,b))
            if len(previous)==11:raise RoutePlacementError('no clear connector route')
            return [],[(0,0),(1,1)]
        with self.assertRaises(RoutePlacementError):_plan_routes(pending,{}, {},blocked)
        self.assertEqual(len(calls),48)
        for error in (ValueError('invalid geometry'),RuntimeError('unexpected failure')):
            calls=[]
            def broken(*args):calls.append(args);raise error
            with self.assertRaises(type(error)):_plan_routes(pending,{}, {},broken)
            self.assertEqual(len(calls),1)
        self.assertEqual(_plan_routes([],{}, {},blocked),{})

    def test_same_engine_two_domains_native_budgets_and_honest_claims(self):
        for domain in ('math', 'sensor'):
            source = lesson(domain); saved = copy.deepcopy(source)
            plan = compile_semantic(spec(source))
            self.assertEqual(source, saved)
            self.assertEqual(plan, compile_semantic(spec(source)))
            self.assertEqual(plan['connections'][0]['start'], [155, 180])
            self.assertEqual(plan['connections'][0]['end'], [400, 180])
            self.assertEqual([x['target'] for x in plan['anchored_labels']], ['a', 'b', 'edge'])
            self.assertFalse(plan['semantic']['metrics']['mathematics_verified'])
            self.assertEqual(plan['semantic']['verified_claims'], [])
            bundle = native_semantic_bundle(json.dumps(spec(source)))
            self.assertEqual(len(bundle['sources']), 3)
            for stage in plan['stages']:
                self.assertLessEqual(stage['points'], 3000)
                self.assertLessEqual(len(stage['paths']), 64)
                self.assertLessEqual(stage['estimated_pen_seconds'], 30)

    def test_later_obstacle_affects_earlier_connection_not_original_geometry(self):
        source = lesson()
        source[2]['draw'] = [{'op': 'rect', 'origin': [260, 130], 'size': [60, 100]}]
        saved = copy.deepcopy(source)
        resolved, records = resolve_connections(source)
        self.assertEqual(source, saved)
        self.assertEqual(resolved[0], source[0])
        self.assertEqual(resolved[2], source[2])
        route = [{k: v for k, v in c.items() if k != 'id'} for c in resolved[1]['draw']]
        self.assertFalse(_hits(route, (255, 125, 325, 235)))
        self.assertGreater(len(route[0]['points']), 2)
        self.assertEqual((resolved, records), resolve_connections(source))
        compile_lesson(source, 'The relation avoids a later obstacle.')

    def test_fixed_label_whole_box_is_a_routing_obstacle(self):
        source = lesson()
        source[2]['draw'] = [{'op': 'label', 'at': [250, 190], 'text': 'Keep', 'size': 20}]
        resolved, _ = resolve_connections(source)
        route = [{k: v for k, v in c.items() if k != 'id'} for c in resolved[1]['draw']]
        points = [p for path in _primitive(source[2]['draw'][0]) for p in path]
        xs, ys = zip(*points)
        self.assertFalse(_hits(route, (min(xs)-5, min(ys)-5, max(xs)+5, max(ys)+5)))
        compile_lesson(source, 'Preserve the explicit label.')

    def test_direction_size_and_orientation_do_not_need_topic_rules(self):
        for start, end in (([110,180],[455,180]), ([455,180],[110,180]),
                           ([300,70],[300,290]), ([110,75],[460,285])):
            for radius in (12, 35, 50):
                source = [{'caption': 'Two endpoints.', 'draw': [
                    {'op': 'circle', 'id': 'a', 'center': start, 'radius': radius},
                    {'op': 'circle', 'id': 'b', 'center': end, 'radius': radius},
                    {'op': 'connect', 'from': 'a', 'to': 'b'}]}]
                plan = compile_lesson(source, 'Follow the direction.', allow_short=True)
                record = plan['connections'][0]
                import math
                self.assertAlmostEqual(math.dist(record['start'], start), radius)
                self.assertAlmostEqual(math.dist(record['end'], end), radius)

    def test_bad_references_fields_and_geometry_allocate_nothing(self):
        mutations = [
            lambda s: s[1]['draw'][0].update(to='missing'),
            lambda s: s[1]['draw'][0].update(to='a'),
            lambda s: s[1]['draw'][0].update(to='edge'),
            lambda s: s[1]['draw'][0].update(url='https://example.com'),
            lambda s: s[1]['draw'][0].update(id='a'),
            lambda s: s[1]['draw'][0].update(id='../file'),
            lambda s: s[1]['draw'][0].update(points=[[0,0],[1,1]]),
            lambda s: s.reverse(),
            lambda s: s[0]['draw'][1].update(id='a'),
            lambda s: s[0]['draw'][0].update(radius=float('nan')),
            lambda s: s[0]['draw'].__setitem__(0, {'op':'line','id':'a','from':[70,180],'to':[150,180]}),
            lambda s: s[1]['draw'].extend([{'op':'connect','from':'a','to':'b'}] * 12),
        ]
        for mutate in mutations:
            source = lesson(); mutate(source)
            with self.subTest(source=source), patch('notebook_lesson_native.storyboard_assets') as encode, \
                    patch('notebook_lesson_native.uuid.uuid4') as allocate:
                with self.assertRaises(SemanticError): native_semantic_bundle(json.dumps(spec(source)))
                encode.assert_not_called(); allocate.assert_not_called()

    def test_many_to_one_relation_keeps_two_inputs_and_clear_routes(self):
        from notebook_procedural import _route_conflicts
        source = [{'caption': 'Two distinct inputs can share one output.', 'draw': [
            {'op':'circle','id':'a','center':[100,90],'radius':30},
            {'op':'circle','id':'b','center':[100,270],'radius':30},
            {'op':'rect','id':'c','origin':[430,150],'size':[80,60]}]},
            {'caption': 'The first input maps to this output.', 'draw': [
                {'op':'connect','from':'a','to':'c'}]},
            {'caption': 'The second input maps to the same output.', 'draw': [
                {'op':'connect','from':'b','to':'c'}]}]
        resolved, records = resolve_connections(source)
        self.assertEqual([(r['source'],r['target']) for r in records], [('a','c'),('b','c')])
        first = resolved[1]['draw'][0]['points']
        second = resolved[2]['draw'][0]['points']
        self.assertFalse(_route_conflicts(second, resolved[2]['draw'], [first]))
        compile_lesson(source, 'The output alone does not identify which input was used.')

    def test_expansion_is_counted_against_existing_command_budget(self):
        source = lesson()
        source[1]['draw'].extend([{'op':'line','from':[30,30],'to':[35,30]}] * 31)
        with patch('notebook_lesson_native.storyboard_assets') as encode:
            with self.assertRaisesRegex(SemanticError, 'expanded connections exceed'):
                native_semantic_bundle(json.dumps(spec(source)))
            encode.assert_not_called()

    def test_reciprocal_fan_in_routes_without_moving_objects(self):
        from notebook_procedural import _route_conflicts
        for reflected in (False, True):
            def center(x, y):
                return [600-x if reflected else x, y]
            source = [
                {'caption': 'Identify the three objects.', 'draw': [
                    {'op':'circle','id':'a','center':center(150,120),'radius':45},
                    {'op':'circle','id':'b','center':center(150,250),'radius':45},
                    {'op':'circle','id':'c','center':center(450,185),'radius':50}]},
                {'caption': 'Both sources send to the shared destination.', 'draw': [
                    {'op':'connect','from':'a','to':'c','id':'ac'},
                    {'op':'connect','from':'b','to':'c','id':'bc'}]},
                {'caption': 'The destination can send to either source.', 'draw': [
                    {'op':'connect','from':'c','to':'a','id':'ca'},
                    {'op':'connect','from':'c','to':'b','id':'cb'}]}]
            saved = copy.deepcopy(source)
            resolved, records = resolve_connections(source)
            self.assertEqual(source, saved)
            self.assertEqual(resolved[0], source[0])
            self.assertEqual((resolved, records), resolve_connections(source))
            self.assertEqual([(r['source'],r['target']) for r in records],
                             [('a','c'),('b','c'),('c','a'),('c','b')])
            previous = []
            for step in resolved[1:]:
                for i in range(0, len(step['draw']), 2):
                    commands = [{k:v for k,v in c.items() if k != 'id'}
                                for c in step['draw'][i:i+2]]
                    points = commands[0]['points']
                    self.assertFalse(_route_conflicts(points, commands, previous))
                    previous.append(points)
            plan = compile_lesson(source, 'Direction remains explicit in both directions.')
            for stage in plan['stages']:
                self.assertLessEqual(stage['points'], 3000)
                self.assertLessEqual(len(stage['paths']), 64)
                self.assertLessEqual(stage['estimated_pen_seconds'], 30)

    def test_reciprocal_routes_support_rectangles_and_vertical_layout(self):
        for shape in ('circle', 'rect'):
            for positions in ([(150,120),(150,250),(450,185)],
                              [(240,75),(370,75),(305,250)]):
                objects = []
                for identity, (x,y) in zip('abc', positions):
                    objects.append(dict(op='circle',id=identity,center=[x,y],radius=35)
                                   if shape == 'circle' else
                                   dict(op='rect',id=identity,origin=[x-30,y-30],size=[60,60]))
                source = [dict(caption='Identify the objects.', draw=objects),
                          dict(caption='Send to the destination.', draw=[
                              {'op':'connect','from':a,'to':'c'} for a in 'ab']),
                          dict(caption='Send back to either source.', draw=[
                              {'op':'connect','from':'c','to':b} for b in 'ab'])]
                plan = compile_lesson(source, 'Follow each direction separately.')
                self.assertEqual(len(plan['connections']), 4)

    def test_detour_search_is_bounded_simple_and_only_a_fallback(self):
        from notebook_procedural import _route_detours, _segment_distance
        ports = {
            'a': dict(left=(100,100), right=(160,100), top=(130,70), bottom=(130,130)),
            'b': dict(left=(400,220), right=(460,220), top=(430,190), bottom=(430,250))}
        paths = list(_route_detours('a', 'b', ports))
        self.assertGreater(len(paths), 0)
        self.assertLessEqual(len(paths), 448)
        self.assertEqual(paths, list(_route_detours('a', 'b', ports)))
        for path in paths:
            self.assertIn(path[0], ports['a'].values())
            self.assertIn(path[-1], ports['b'].values())
            self.assertLessEqual(len(path), 6)
            segments = list(zip(path,path[1:]))
            for i,(a,b) in enumerate(segments):
                for c,d in segments[i+2:]:
                    self.assertGreaterEqual(_segment_distance(a,b,c,d), 6)
        with patch('notebook_procedural._route_detours') as detours:
            resolve_connections(lesson())
            # Creating a generator is harmless; established paths must not
            # iterate it or change their geometry just because it is available.
            detours.return_value.__iter__.assert_not_called()

    def test_over_budget_geometry_rejected_before_routing(self):
        source = lesson()
        source[0]['draw'].extend([{'op':'circle','center':[300,180],'radius':170}] * 27)
        with patch('notebook_procedural._route') as route:
            with self.assertRaises(ValueError): compile_lesson(source, 'Do not route excessive ink.')
            route.assert_not_called()

    def test_full_barrier_holds_instead_of_moving_entities(self):
        source = lesson()
        source[2]['draw'] = [{'op':'rect','origin':[275,0],'size':[50,360]}]
        with patch('notebook_lesson_native.storyboard_assets') as encode:
            with self.assertRaisesRegex(SemanticError, 'no clear connector route'):
                native_semantic_bundle(json.dumps(spec(source)))
            encode.assert_not_called()

    def test_no_connection_is_identity_and_no_new_proof_claims(self):
        source = lesson(); source[1]['draw'] = [{'op':'line','from':[155,180],'to':[400,180]}]
        self.assertIs(resolve_connections(source)[0], source)
        self.assertIn('connect', CAPABILITIES['drawing']['commands'])
        candidate = spec(lesson()); candidate['claims'] = [{'proof_verified': True}]
        with self.assertRaises(SemanticError): compile_semantic(candidate)


if __name__ == '__main__':
    unittest.main()
