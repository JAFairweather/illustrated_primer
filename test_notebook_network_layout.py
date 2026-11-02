"""Topology-owned layout, with no subject-specific geometry or answer repair."""
import copy
import unittest
from unittest.mock import patch

import notebook_procedural as board
from notebook_ink_playback import playback_assets


def graph(edges, count):
    return ([{'id':chr(97+i)} for i in range(count)],
            [{'id':'edge'+str(i),'from':a,'to':b,'label':'next'}
             for i,(a,b) in enumerate(edges)])


class NetworkLayoutTest(unittest.TestCase):
    def test_dag_ranks_advance_every_edge_deterministically(self):
        for edges,count in [([],1),([('a','b')],2),
                            ([('a','c'),('b','c')],3),
                            ([('a','b'),('a','c'),('b','d'),('c','d')],4),
                            ([('a','c'),('b','c'),('a','d')],4),
                            ([('a','b'),('b','c'),('c','d'),('d','e')],5)]:
            with self.subTest(edges=edges):
                objects,links=graph(edges,count)
                original=copy.deepcopy((objects,links))
                slots=board._layered_network_slots(objects,links)
                positions=dict(zip(board._network_order(objects,links),slots))
                self.assertEqual(slots,board._layered_network_slots(objects[::-1],links[::-1]))
                self.assertEqual((objects,links),original)
                for source,target in edges:
                    self.assertLess(positions[source][0],positions[target][0])
                for x,y in slots:
                    self.assertTrue(0<=x<=2 and 0<=y<=1)

    def test_cycles_and_overcrowded_ranks_have_no_layered_fallback(self):
        for edges,count in [([('a','b'),('b','a')],2),([],4),
                            ([('a','b'),('b','c'),('c','d'),('d','e'),('e','f')],6)]:
            objects,links=graph(edges,count)
            self.assertIsNone(board._layered_network_slots(objects,links))

    def test_same_dependency_topology_preserves_two_different_topics(self):
        for labels,link_labels in [
                (['Lemma 1','Lemma 2','Theorem','Incomplete proof'],
                 ['supports','supports','alone is not enough']),
                (['Sensor A','Sensor B','Controller','Single input'],
                 ['reports','reports','reports alone'])]:
            objects,links=graph([('a','c'),('b','c'),('a','d')],4)
            names={'a':'lemma1','b':'lemma2','c':'theorem','d':'gap'}
            for obj in objects:obj['id']=names[obj['id']]
            for link in links:
                link['from']=names[link['from']]
                link['to']=names[link['to']]
            for obj,label in zip(objects,labels):obj.update(shape='box',label=label)
            for link,label in zip(links,link_labels):link['label']=label
            spec=dict(kind='network',objects=objects,links=links,steps=[
                dict(add=['lemma1','lemma2'],caption='Introduce the two inputs.'),
                dict(add=['theorem'],caption='Introduce the shared result.'),
                dict(add=['edge0','edge1'],caption='Connect the inputs to the result.'),
                dict(add=['gap','edge2'],caption='Show the separate branch.')],
                takeaway='The connections show the supplied dependencies.')
            original=copy.deepcopy(spec)
            slots=board._layered_network_slots(objects,links)
            # Exercise the layered arrangement for both vocabularies; the
            # saved proof wording naturally fails all established candidates.
            plan=board.compile_board(spec)
            stages,layout=board._network(spec,170,slots)
            layered=board.compile_lesson(stages,spec['takeaway'])
            self.assertEqual(spec,original)
            self.assertEqual(plan,board.compile_board(spec))
            if labels[0]=='Lemma 1':
                self.assertEqual(plan['procedural']['layout'],layout)
            found={item['id']:item for item in layout[1:]}
            for item in objects+links:
                self.assertEqual(' '.join(found[item['id']]['lines']),item['label'])
            self.assertEqual([s['text'] for s in layered['stages']],
                             [s['caption'] for s in spec['steps']])
            assets=playback_assets(layered)
            self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000 for a in assets))
            self.assertTrue(all(a['playback']['duration_ms']<=30000 for a in assets))
            self.assertLessEqual(sum(a['point_count'] for a in assets),12000)
            for i,(link,path) in enumerate(zip(links,layout[0]['routes'])):
                self.assertFalse(board._route_conflicts(path,board._route_commands(path),layout[0]['routes'][:i]))
                for identity,obj in layout[0]['objects'].items():
                    x,y=obj['slot']
                    bounds=board._bounds(board._object('box',100+200*x,85+170*y))
                    interior=board._trim_path(path) if identity in (link['from'],link['to']) else path
                    self.assertFalse(board._hits([board._poly(interior)],bounds))

    def test_invalid_input_and_native_budget_errors_never_retry(self):
        with patch.object(board,'_layered_network_slots') as fallback:
            with self.assertRaises(ValueError):board.compile_board({'kind':'network','objects':[]})
            fallback.assert_not_called()
        objects,links=graph([('a','b')],2)
        spec=dict(kind='network',objects=objects,links=links)
        with patch.object(board,'_network',return_value=([],[])) as network:
            with patch.object(board,'compile_lesson',side_effect=ValueError('native budget')):
                with self.assertRaisesRegex(ValueError,'native budget'):
                    board.compile_board(dict(spec,takeaway='Keep budgets.'))
            self.assertEqual(network.call_count,1)

    def test_join_and_downstream_result_can_use_vertical_ranks(self):
        for labels in (['Lemma A','Lemma B','A AND B','Theorem'],
                       ['Power','Signal','Both present','Ready'],
                       ['Approval A','Approval B','Both approvals','Release']):
            objects,links=graph([('a','c'),('b','c'),('c','d')],4)
            for obj,label in zip(objects,labels):obj.update(shape='box',label=label)
            for link,label in zip(links,['Required input','Required input','Valid deduction']):
                link['label']=label
            spec=dict(kind='network',objects=objects,links=links,steps=[
                dict(add=['a'],caption='Introduce the first input.'),
                dict(add=['b'],caption='Introduce the second input.'),
                dict(add=['c','edge0'],caption='The first input is required.'),
                dict(add=['edge1'],caption='The second input is also required.'),
                dict(add=['d','edge2'],caption='Show the downstream result.')],
                takeaway='The given dependencies require both inputs.')
            original=copy.deepcopy(spec)
            base=board._layered_network_slots(objects,links)
            slots=[(2*y,x/2) for x,y in base]
            stages,layout=board._network(spec,170,slots)
            plan=board.compile_board(spec)
            self.assertEqual(plan,board.compile_board(spec))
            self.assertEqual(spec,original)
            if labels[0]=='Lemma A':self.assertEqual(plan['procedural']['layout'],layout)
            self.assertEqual([s['text'] for s in plan['stages']],
                             [s['caption'] for s in spec['steps']])
            found={item['id']:item for item in layout[1:]}
            for item in objects+links:
                self.assertEqual(' '.join(found[item['id']]['lines']),item['label'])
            for index,path in enumerate(layout[0]['routes']):
                self.assertFalse(board._route_conflicts(path,board._route_commands(path),
                                                        layout[0]['routes'][:index]))
            assets=playback_assets(board.compile_lesson(stages,spec['takeaway']))
            self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000 for a in assets))
            self.assertTrue(all(a['playback']['duration_ms']<=30000 for a in assets))
            self.assertLessEqual(sum(a['point_count'] for a in assets),12000)

    def test_only_typed_spatial_failures_retry_with_bounded_work(self):
        objects,links=graph([('a','c'),('b','c'),('c','d')],4)
        spec=dict(kind='network',objects=objects,links=links,takeaway='Keep the limits.')
        for failure in (board.LabelPlacementError,board.RoutePlacementError):
            with patch.object(board,'_network',side_effect=failure('spatial')) as network:
                with self.assertRaisesRegex(failure,'spatial'):board.compile_board(spec)
                self.assertEqual(network.call_count,20)
                self.assertEqual([c.kwargs['allow_detours'] for c in network.call_args_list],
                                 [False]*10 + [True]*10)
        with patch.object(board,'_network',side_effect=ValueError('invalid schema')) as network:
            with self.assertRaisesRegex(ValueError,'invalid schema'):board.compile_board(spec)
            self.assertEqual(network.call_count,1)

    def test_detours_only_after_all_clean_arrangements_and_no_budget_retry(self):
        objects,links=graph([('a','c'),('b','c'),('c','d')],4)
        spec=dict(kind='network',objects=objects,links=links,takeaway='Keep the limits.')
        outcomes = [board.RoutePlacementError('occupied')] * 10 + [([], [])]
        with patch.object(board,'_network',side_effect=outcomes) as network, \
                patch.object(board,'compile_lesson',side_effect=ValueError('native budget')):
            with self.assertRaisesRegex(ValueError,'native budget'):
                board.compile_board(spec)
            self.assertEqual(network.call_count,11)
            self.assertEqual([c.kwargs['allow_detours'] for c in network.call_args_list],
                             [False]*10 + [True])

    def test_compact_grid_handles_entry_into_cycle_without_rewriting(self):
        fixtures=[
            (['Sun','Surface water','Water vapor','Cloud droplets'],
             ['Solar heating','Evaporation','Cooling: condensation','Precipitation'],
             ['sun','water','box','cloud']),
            (['Request','Pending','Executing','Finished'],
             ['Submit request','Dispatch','Complete execution','Schedule again'],
             ['box']*4),
            (['Power source','Store','Consumer','Return'],
             ['Supplies energy','Transfers','Processing','Returns'],
             ['circle','box','box','box'])]
        for labels,edge_labels,shapes in fixtures:
            with self.subTest(labels=labels):
                objects,links=graph([('a','b'),('b','c'),('c','d'),('d','b')],4)
                for obj,label,shape in zip(objects,labels,shapes):obj.update(label=label,shape=shape)
                for link,label in zip(links,edge_labels):link['label']=label
                spec=dict(kind='network',objects=objects,links=links,steps=[
                    dict(add=['a','b','edge0'],caption='Introduce the input and first state.'),
                    dict(add=['c','edge1'],caption='Show the next state.'),
                    dict(add=['d','edge2'],caption='Continue through the cycle.'),
                    dict(add=['edge3'],caption='Return to the earlier state.')],
                    takeaway='The supplied connection closes the loop.')
                original=copy.deepcopy(spec)
                slots,gap=list(board._network_attempts(spec))[-2]
                self.assertEqual(slots,[(0,0),(1,0),(0,1),(1,1)])
                plan=board.compile_board(spec)
                layout=plan['procedural']['layout']
                if labels[0]=='Sun':
                    self.assertEqual([item['slot'] for item in layout[0]['objects'].values()],
                                     [list(slot) for slot in slots])
                self.assertEqual(plan,board.compile_board(spec))
                self.assertEqual(spec,original)
                found={item['id']:item for item in layout[1:]}
                for item in objects+links:
                    self.assertEqual(' '.join(found[item['id']]['lines']),item['label'])
                self.assertEqual([s['text'] for s in plan['stages']],
                                 [s['caption'] for s in spec['steps']])
                for index,path in enumerate(layout[0]['routes']):
                    self.assertFalse(board._route_conflicts(path,board._route_commands(path),
                                                            layout[0]['routes'][:index]))
                assets=playback_assets(plan)
                self.assertTrue(all(a['stroke_count']<=64 and a['point_count']<=3000 for a in assets))
                self.assertTrue(all(a['playback']['duration_ms']<=30000 for a in assets))
                self.assertLessEqual(sum(a['point_count'] for a in assets),12000)

    def test_compact_grid_is_bounded_for_all_supported_counts(self):
        for count in range(3,7):
            objects,links=graph([(chr(97+i),chr(97+(i+1)%count)) for i in range(count)],count)
            slots,gap=list(board._network_attempts(dict(objects=objects,links=links)))[-2]
            self.assertEqual(len(set(slots)),count)
            self.assertTrue(all(0<=x<=1 and 0<=y<=1 for x,y in slots))
            self.assertEqual(gap,170)


if __name__=='__main__':
    unittest.main()
