import copy
from fractions import Fraction
import json
import unittest

from notebook_semantic import compile_semantic,parse_semantic,SemanticError,_rows
from notebook_semantic_examples import examples
from notebook_stroke_asset import storyboard_assets


class SemanticLessonTest(unittest.TestCase):
    def odd_square_spec(self,n):
        spec=examples()['odd-squares']
        spec['scene']['objects'][0]['layers']=n
        spec['steps']=[{'reveal':['square.layer'+str(k)],
                        'caption':f'Add {2*k-1} tiles to complete a {k}-by-{k} square.'}
                       for k in range(1,n+1)]
        spec['claims'][-1]['value']['numerator']=n*n
        return spec

    def test_odd_square_all_sizes_have_exact_nonduplicate_cells_and_edges(self):
        from notebook_motion_program import compile_motion_program
        for n in range(3,7):
            with self.subTest(layers=n):
                spec=self.odd_square_spec(n);before=copy.deepcopy(spec)
                plan=compile_semantic(spec)
                metrics=plan['semantic']['metrics']['square']
                cells=set();edges=set()
                for k,layer in enumerate(metrics['layers'],1):
                    added={tuple(c) for c in layer['new_cells']}
                    self.assertEqual(len(added),2*k-1)
                    self.assertFalse(cells & added)
                    cells.update(added)
                    self.assertEqual(cells,{(x,y) for x in range(k) for y in range(k)})
                    new_edges={tuple(tuple(p) for p in edge) for edge in layer['new_edges']}
                    self.assertFalse(edges & new_edges)
                    edges.update(new_edges)
                    self.assertEqual(len(edges),2*k*(k+1))
                    self.assertEqual(layer['total_units'],k*k)
                    # Expansion of the actual coalesced drawing must recover
                    # exactly the original new unit edges, without overdraw.
                    expanded=[];cell=metrics['cell_size']
                    for a,b in layer['drawn_grid_edges']:
                        axis=0 if a[1]==b[1] else 1
                        length=b[axis]-a[axis]
                        self.assertEqual(length%cell,0)
                        for offset in range(0,int(length),cell):
                            p=list(a);q=list(a)
                            p[axis]+=offset;q[axis]+=offset+cell
                            expanded.append((tuple(p),tuple(q)))
                    self.assertEqual(len(expanded),len(set(expanded)))
                    self.assertEqual(set(expanded),new_edges)
                self.assertEqual(metrics['final_area'],n*n)
                self.assertTrue(plan['equation'].endswith(f'={n}^2={n*n}'))
                self.assertEqual(len(storyboard_assets(plan)),n)
                motion=compile_motion_program(plan)
                self.assertEqual(len(motion['stage_budgets']),n)
                self.assertEqual(spec,before)

    def test_grouped_odd_borders_keep_unit_grid_and_fit_native_caps(self):
        from notebook_semantic import _odd_square_component, _reveal
        spec=self.odd_square_spec(6)
        spec['steps']=spec['steps'][:3]+[{'reveal':['square.layer4','square.layer5','square.layer6'],
            'caption':'The next three borders add 7, 9 and 11 tiles.'}]
        before=copy.deepcopy(spec)
        component=_odd_square_component(spec['scene']['objects'][0])
        commands=_reveal(spec['steps'],'square',component)[-1]['draw']
        self.assertEqual(len(commands),42)
        expected=[c for k in (4,5,6) for c in component['compact_parts']['layer'+str(k)]]
        self.assertEqual(commands,expected)
        for k in (4,5,6):
            part=component['compact_parts']['layer'+str(k)]
            grid=component['metrics']['layers'][k-1]['drawn_grid_edges']
            self.assertEqual([c['points'] for c in part[:-2]],json.loads(json.dumps(grid)))
            self.assertEqual(part[-2]['text'],'+'+str(2*k-1))
            self.assertEqual([c['op'] for c in part[-2:]],['label','line'])
            from notebook_procedural import _label_bounds
            bounds=_label_bounds(part[-2])
            self.assertAlmostEqual((bounds[0]+bounds[2])/2,95)
            self.assertEqual(part[-1]['from'][0],125)
            self.assertEqual(part[-1]['to'][0],170)
        plan=compile_semantic(spec);assets=storyboard_assets(plan)
        self.assertEqual(len(assets),4)
        self.assertEqual(assets[-1]['stroke_count'],46)  # Same grid/labels, five fewer glyph lifts.
        for asset,stage in zip(assets,plan['stages']):
            self.assertLessEqual(asset['point_count'],3000)
            self.assertLessEqual(asset['stroke_count'],64)
            self.assertLessEqual(stage['estimated_pen_seconds'],30)
        self.assertEqual(spec,before)
        self.assertEqual(plan['semantic']['metrics']['square']['final_area'],36)
        individual=compile_semantic(self.odd_square_spec(6))
        self.assertEqual([s['paths'] for s in plan['stages'][:3]],
                         [s['paths'] for s in individual['stages'][:3]])
        self.assertEqual(plan['semantic']['verified_claims'],individual['semantic']['verified_claims'])

    def test_procedural_expansion_does_not_raise_agent_or_native_caps(self):
        from notebook_lesson import compile_lesson
        steps=[{'caption':'Add lines.','draw':[{'op':'line','from':[10,10],'to':[12,10]}]}
               for _ in range(3)]
        steps[0]['draw']=steps[0]['draw']*33
        with self.assertRaisesRegex(ValueError,'1..32'):compile_lesson(steps,'Done.')
        self.assertEqual(len(compile_lesson(steps,'Done.',procedural=True)['stages'][0]['paths']),33)
        with self.assertRaisesRegex(ValueError,'explicit procedural'):compile_lesson(steps,'Done.',procedural=1)
        steps[0]['draw']=[{'op':'arrow','from':[10,10],'to':[30,10]}]*33
        with self.assertRaisesRegex(ValueError,'64 strokes'):compile_lesson(steps,'Done.',procedural=True)
        steps[0]['draw']=[{'op':'line','from':[0,10],'to':[600,10]}]*32
        with self.assertRaisesRegex(ValueError,'budget'):compile_lesson(steps,'Done.',procedural=True)
        for field in ('procedural','command_limit','compact_parts'):
            bad=self.odd_square_spec(3);bad[field]=True
            with self.assertRaises(SemanticError):compile_semantic(bad)

    def test_pythagoras_labels_on_square_borders_move_beside_their_shapes(self):
        # Geometry from the unedited offline Pythagoras failure. The collision
        # check still runs on the final page; a colliding label is moved beside
        # the nearest shape before it rather than left out or costing the drawing.
        spec={'v':1,'mode':'lesson','intent':'A 3-4-5 triangle example.',
              'scene':{'family':'drawing'},'claims':[],
              'takeaway':'This is a numerical example, not a general proof.',
              'steps':[
                  {'caption':'Draw a right triangle.', 'draw':[
                      {'op':'polyline','points':[[200,220],[200,130],[320,220],[200,220]]},
                      {'op':'label','at':[185,235],'text':'right angle','size':16}]},
                  {'caption':'Add squares on its legs.', 'draw':[
                      {'op':'polyline','points':[[200,130],[110,130],[110,220],[200,220],[200,130]]},
                      {'op':'polyline','points':[[200,220],[200,340],[320,340],[320,220],[200,220]]},
                      {'op':'label','at':[125,180],'text':'3² = 9','size':20}]},
                  {'caption':'Mark the example.', 'draw':[
                      {'op':'label','at':[365,150],'text':'one example','size':20}]}]}
        plan=compile_semantic(spec)
        dropped=[text for _,text in plan['dropped_labels']]
        self.assertEqual(dropped,[])
        self.assertEqual(len(plan['stages']),3)
        self.assertIn('3² = 9',[label['text'] for label in plan['anchored_labels']])
        # A step that is only a colliding label is drawn too, its label moved clear.
        spec['steps'][2]['draw']=[{'op':'label','at':[200,175],'text':'inside','size':20}]
        plan=compile_semantic(spec)
        self.assertEqual(plan['dropped_labels'],[])
        self.assertIn('inside',[label['text'] for label in plan['anchored_labels']])

    def test_small_component_expansions_keep_the_normal_command_path(self):
        from unittest.mock import patch
        import notebook_semantic as compiler
        real=compiler.compile_lesson
        for name in ('integral','fractions','odd-squares'):
            with patch.object(compiler,'compile_lesson',wraps=real) as call:
                compile_semantic(examples()[name])
                self.assertFalse(call.call_args.kwargs.get('procedural',False),name)

    def test_odd_square_rejects_invalid_quantity_and_false_or_missing_claims(self):
        for value in (True,3.0,2,7,'4',None):
            spec=self.odd_square_spec(4);spec['scene']['objects'][0]['layers']=value
            with self.assertRaises(SemanticError) as caught:compile_semantic(spec)
            self.assertEqual(caught.exception.code,'invalid_quantity')
        spec=self.odd_square_spec(5);spec['claims'][-1]['value']['numerator']=24
        with self.assertRaises(SemanticError) as caught:compile_semantic(spec)
        self.assertEqual(caught.exception.code,'contradictory_claim')
        for index in (0,1):
            spec=self.odd_square_spec(4);spec['claims'].pop(index)
            with self.assertRaises(SemanticError) as caught:compile_semantic(spec)
            self.assertEqual(caught.exception.code,'missing_claim')

    def test_odd_square_dependency_and_coordinate_escape_refused(self):
        spec=self.odd_square_spec(4)
        spec['steps'][0],spec['steps'][1]=spec['steps'][1],spec['steps'][0]
        with self.assertRaises(SemanticError):compile_semantic(spec)
        spec=self.odd_square_spec(4);spec['steps'][-1]['reveal']=['square.layer5']
        with self.assertRaises(SemanticError):compile_semantic(spec)
        spec=self.odd_square_spec(4);spec['scene']['objects'][0]['origin']=[1,1]
        with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_same_step_dependencies_follow_actual_drawing_order(self):
        spec=self.odd_square_spec(4)
        spec['steps']=[spec['steps'][0],
                       {'reveal':['square.layer2','square.layer3'],'caption':'Two successive L borders grow the square.'},
                       spec['steps'][3]]
        self.assertEqual(len(compile_semantic(spec)['stages']),3)
        spec['steps'][1]['reveal'].reverse()
        with self.assertRaises(SemanticError):compile_semantic(spec)
        spec=examples()['integral'];spec['steps'][0]['reveal'].reverse()
        with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_all_examples_are_deterministic_and_native_encodable(self):
        for name,spec in examples().items():
            with self.subTest(name=name):
                before=copy.deepcopy(spec)
                plan=compile_semantic(spec)
                self.assertEqual(plan,parse_semantic(json.dumps(spec)))
                self.assertEqual(spec,before)
                self.assertEqual(len(storyboard_assets(plan)),len(spec['steps']))
                self.assertFalse(plan['semantic']['prose_verified'])

    def test_quantities_not_captions_control_scales(self):
        spec=examples()['lever-variant']
        metrics=compile_semantic(spec)['semantic']['metrics']['beam']
        self.assertAlmostEqual(metrics['arm_lengths_px'][0]/metrics['arm_lengths_px'][1],2/5)
        self.assertAlmostEqual(metrics['force_lengths_px'][0]/metrics['force_lengths_px'][1],5/2)
        self.assertEqual(metrics['moments_Nm'],[10,10])

    def test_reject_false_claim_without_repairing_quantities(self):
        for name,mutate in [
            ('lever',lambda s:s['scene']['objects'][0]['forces'].update(values=[5,1])),
            ('integral',lambda s:s['claims'][-1].update(value={'numerator':1,'denominator':2})),
        ]:
            spec=examples()[name];mutate(spec);before=copy.deepcopy(spec)
            with self.assertRaises(SemanticError) as caught:compile_semantic(spec)
            self.assertEqual(caught.exception.code,'contradictory_claim')
            self.assertEqual(spec,before)

    def test_component_conclusions_cannot_omit_their_typed_claims(self):
        # Review regression: prose still says equal turning effect, but the
        # quantities are changed and the author tries omitting the guard.
        spec=examples()['lever']
        spec['scene']['objects'][0]['forces']['values']=[5,1]
        spec['claims']=[]
        with self.assertRaises(SemanticError) as caught:compile_semantic(spec)
        self.assertEqual(caught.exception.code,'missing_claim')
        for index in range(3):
            spec=examples()['integral'];spec['claims'].pop(index)
            with self.assertRaises(SemanticError) as caught:compile_semantic(spec)
            self.assertEqual(caught.exception.code,'missing_claim')
        spec=examples()['lever'];spec['claims']*=2
        with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_computed_area_and_nested_rectangles(self):
        for name in ('integral','integral-variant'):
            spec=examples()[name];metric=compile_semantic(spec)['semantic']['metrics']['area']
            coarse,fine=map(Fraction,metric['left_sums'])
            self.assertLess(coarse,fine)
            self.assertLess(fine,Fraction(metric['exact_integral']))
            edges=metric['new_edges']
            for i,(axis,fixed,start,end) in enumerate(edges):
                self.assertLess(Fraction(start),Fraction(end))
                for axis2,fixed2,start2,end2 in edges[i+1:]:
                    if axis==axis2 and fixed==fixed2:
                        self.assertLessEqual(min(Fraction(end),Fraction(end2)),max(Fraction(start),Fraction(start2)))
        self.assertEqual(compile_semantic(examples()['integral'])['semantic']['metrics']['area']['exact_integral'],'1/3')
        self.assertEqual(compile_semantic(examples()['integral-variant'])['semantic']['metrics']['area']['exact_integral'],'4')

    def test_reject_coordinate_paths_and_unsupported_components(self):
        mutations=[lambda s:s['scene']['objects'][0].update(slot=[0,0]),
                   lambda s:s['scene']['objects'][0].update(x=42),
                   lambda s:s['scene']['objects'][0].update(component='script'),
                   lambda s:s.update(url='https://example.org'),
                   lambda s:s.update(takeaway='/tmp/result'),
                   lambda s:s['scene']['objects'][0]['arms'].update(unit='cm'),
                   lambda s:s['scene']['objects'][0]['arms'].update(values=[True,3]),
                   lambda s:s['scene']['objects'][0]['arms'].update(values=[float('nan'),3])]
        for mutate in mutations:
            spec=examples()['lever'];mutate(spec)
            with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_reveal_dependencies_and_all_parts_required(self):
        for steps in [
            [{'reveal':['beam.forces'],'caption':'Forces'}, {'reveal':['beam.body'],'caption':'Body'}, {'reveal':['beam.arms'],'caption':'Arms'}],
            [{'reveal':['beam.body'],'caption':'Body'}, {'reveal':['beam.forces'],'caption':'Forces'}, {'reveal':['beam.forces'],'caption':'Duplicate'}],
        ]:
            spec=examples()['lever'];spec['steps']=steps
            with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_bounded_parser(self):
        for raw in ['{"v":1,"v":1}', '{"value":NaN}', '['*1500+']'*1500, ' '*24001, '```json\n{}\n```']:
            with self.assertRaises(SemanticError):parse_semantic(raw)

    def test_a_network_that_will_not_route_is_drawn_as_rows_of_boxes(self):
        # The IRIS reply of 2026-10-30, refused four times by the network router.
        spec={'v':1,'mode':'lesson','intent':'Explain what IRIS Software Group does','claims':[],
              'scene':{'family':'causal','objects':[
                  {'id':'iris','component':'box','label':'IRIS Software'},
                  {'id':'services','component':'cloud','label':'Accountancy, education, HR and payroll software'},
                  {'id':'jason','component':'person','label':'Jason Dies'}],
               'relations':[{'id':'provides','from':'iris','to':'services','type':'process','label':'provides tools'},
                            {'id':'leads','from':'jason','to':'iris','type':'process','label':'leads strategy'}]},
              'steps':[{'reveal':['iris','services','provides'],'caption':'A workshop sent tools to accountancy teams.'},
                       {'reveal':['jason','leads'],'caption':'Then Jason Dies arrived as chief executive.'}],
              'takeaway':'IRIS makes business software; Jason leads the company.'}
        self.assertEqual(compile_semantic(spec)['semantic']['metrics']['layout'],'rows')
        scene=spec['scene'];steps=[{'add':s['reveal'],'caption':s['caption']} for s in spec['steps']]
        labels=[op['text'] for step in _rows(scene['objects'],scene['relations'],steps)
                for op in step['draw'] if op['op']=='label']
        self.assertEqual(labels,['IRIS Software','Accountancy','Jason Dies'])

    def test_process_not_physical_path(self):
        spec=examples()['water-cycle'];spec['scene']['relations'][0]['type']='light-ray'
        with self.assertRaises(SemanticError) as caught:compile_semantic(spec)
        self.assertEqual(caught.exception.code,'unsupported_component')

    def test_polynomial_domain_and_partition_limits(self):
        for changes in [{'interval':[-1,1]}, {'partitions':[4,9]}, {'partitions':[7,14]},
                        {'polynomial_coefficients_ascending':[1]},
                        {'polynomial_coefficients_ascending':[0,0,-1]},
                        {'sampling':'right'}, {'interval':[1,1]}]:
            spec=examples()['integral'];spec['scene']['objects'][0].update(changes)
            with self.assertRaises(SemanticError):compile_semantic(spec)

    def test_twenty_polynomial_and_partition_variants(self):
        for n in range(2,7):
            for degree in range(1,5):
                with self.subTest(partitions=n,degree=degree):
                    spec=examples()['integral']
                    spec['scene']['objects'][0].update(
                        polynomial_coefficients_ascending=[0]*degree+[1],partitions=[n,2*n])
                    spec['claims'][-1]['value']={'numerator':1,'denominator':degree+1}
                    plan=compile_semantic(spec)
                    self.assertEqual(len(storyboard_assets(plan)),4)
                    self.assertEqual(plan['semantic']['metrics']['area']['exact_integral'],str(Fraction(1,degree+1)))

    def test_fractional_coefficient_and_bound_are_unambiguous(self):
        spec=examples()['integral']
        spec['scene']['objects'][0].update(polynomial_coefficients_ascending=[0,.5],interval=[.5,1])
        spec['claims'][-1]['value']={'numerator':3,'denominator':16}
        plan=compile_semantic(spec)
        self.assertIn(r'\frac{1}{2}x',plan['equation'])
        self.assertIn(r'\int_{\frac{1}{2}}',plan['equation'])
        self.assertEqual(len(storyboard_assets(plan)),4)


if __name__=='__main__':unittest.main()
