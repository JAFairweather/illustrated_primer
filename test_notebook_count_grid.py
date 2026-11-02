import copy
from fractions import Fraction
import json
import unittest
from unittest.mock import patch

from notebook_count_grid import count_grid
from notebook_semantic import compile_semantic, SemanticError
from notebook_lesson_native import native_semantic_bundle
from notebook_motion_program import compile_motion_program


def spec(counts=None, row=0, column=0, condition_on='column'):
    counts=counts if counts is not None else [[8,2],[9,81]]
    denominator=sum(counts[row]) if condition_on=='row' else sum(values[column] for values in counts)
    fraction=Fraction(counts[row][column],denominator) if denominator else Fraction(0)
    return {'v':1,'mode':'lesson','intent':'Explain a conditional count using the full comparison grid',
        'scene':{'family':'quantitative','objects':[{'id':'counts','component':'count_grid',
            'rows':['Has','No'],'columns':['Positive','Negative'],'counts':counts,
            'selected':{'row':row,'column':column,'condition_on':condition_on}}]},
        'steps':[{'reveal':['counts.frame'],'caption':'Build a two-way count grid with room for its totals.'},
                 {'reveal':['counts.columns'],'caption':'Separate the two outcomes into columns.'},
                 {'reveal':['counts.row1'],'caption':'Read the counts in the first group.'},
                 {'reveal':['counts.row2'],'caption':'Include the second group as well.'},
                 {'reveal':['counts.totals'],'caption':'Add the two groups to find each outcome total.'},
                 {'reveal':['counts.selection'],'caption':'Divide the selected cell by its underlined group total.'}],
        'claims':[{'object':'counts','predicate':'selected_fraction',
                   'value':{'numerator':fraction.numerator,'denominator':fraction.denominator}}],
        'takeaway':'Use the group being conditioned on as the denominator, not the full population.'}


class CountGridTests(unittest.TestCase):
    def test_named_fixture_exercises_wrapped_row_without_model_call(self):
        from notebook_semantic_examples import examples
        raw=examples()['count-grid']
        self.assertEqual(raw['scene']['objects'][0]['rows'],['Condition','No condition'])
        component=count_grid(raw['scene']['objects'][0])
        self.assertEqual([c['text'] for c in component['parts']['row2'][:2]],['No','condition'])
        bundle=native_semantic_bundle(json.dumps(raw),playback=True,pen_equations=True)
        self.assertEqual(len(bundle['sources']),7)
        self.assertEqual(compile_semantic(raw)['semantic']['metrics']['group']['selected']['fraction'],'8/17')

    def test_natural_row_names_wrap_without_changing_meaning_or_table(self):
        from notebook_procedural import _label_bounds
        raw=spec();obj=raw['scene']['objects'][0]
        obj['rows']=['Condition','No condition']
        original=copy.deepcopy(raw)
        component=count_grid(obj)
        row=component['parts']['row2']
        self.assertEqual([c['text'] for c in row],['No','condition','9','81','90'])
        for command in row[:2]:
            left,top,right,bottom=_label_bounds(command)
            self.assertGreaterEqual(left,8);self.assertLessEqual(right,162)
            self.assertGreaterEqual(top,186);self.assertLessEqual(bottom,234)
        self.assertEqual(component['parts']['frame'],count_grid(spec()['scene']['objects'][0])['parts']['frame'])
        plan=compile_semantic(raw)
        self.assertEqual(raw,original)
        self.assertEqual(plan,compile_semantic(raw))
        self.assertEqual(plan['semantic']['metrics']['counts']['rows'],obj['rows'])
        bundle=native_semantic_bundle(json.dumps(raw),playback=True,pen_equations=True)
        self.assertEqual(len(bundle['sources']),7)
        for budget in compile_motion_program(plan)['stage_budgets'].values():
            self.assertLessEqual(budget['contacts'],64)
            self.assertLessEqual(budget['points'],3000)
            self.assertLessEqual(budget['estimated_pen_seconds'],30)

    def test_wrapped_condition_underline_covers_both_lines(self):
        from notebook_procedural import _group_label_bounds
        raw=spec(row=1,condition_on='row');obj=raw['scene']['objects'][0]
        obj['rows']=['Condition','No condition']
        parts=count_grid(obj)['parts']
        left,_,right,bottom=_group_label_bounds(parts['row2'][:2])
        self.assertEqual(parts['selection'][2]['from'],[left,bottom+8])
        self.assertEqual(parts['selection'][2]['to'],[right,bottom+8])
        compile_semantic(raw)

    def test_short_row_labels_keep_original_geometry(self):
        from notebook_procedural import _label
        parts=count_grid(spec()['scene']['objects'][0])['parts']
        self.assertEqual(parts['row1'][0],_label('Has',85,146))
        self.assertEqual(parts['row2'][0],_label('No',85,216))

    def test_all_cells_and_both_conditioning_axes_use_exact_margins(self):
        for counts in ([[8,2],[9,81]],[[0,7],[11,0]],[[999999,999999],[999999,999999]]):
            for axis in ('row','column'):
                for r in range(2):
                    for c in range(2):
                        with self.subTest(counts=counts,axis=axis,row=r,column=c):
                            raw=spec(counts,r,c,axis);before=copy.deepcopy(raw)
                            plan=compile_semantic(raw)
                            self.assertEqual(before,raw)
                            self.assertEqual(plan,compile_semantic(raw))
                            metric=plan['semantic']['metrics']['counts']
                            self.assertEqual(metric['row_totals'],list(map(sum,counts)))
                            self.assertEqual(metric['column_totals'],[sum(x[i] for x in counts) for i in range(2)])
                            expected=sum(counts[r]) if axis=='row' else sum(x[c] for x in counts)
                            self.assertEqual(metric['selected']['denominator'],expected)
                            self.assertEqual(Fraction(metric['selected']['fraction']),Fraction(counts[r][c],expected))
                            self.assertFalse(metric['input_values_verified'])
                            self.assertFalse(metric['category_interpretation_verified'])
                            bundle=native_semantic_bundle(json.dumps(raw))
                            self.assertEqual(len(bundle['sources']),6)
                            motion=compile_motion_program(plan)
                            self.assertTrue(all(s['points']<=3000 and s['contacts']<=64 and s['estimated_pen_seconds']<=30
                                                for s in motion['stage_budgets'].values()))

    def test_fractions_use_counts_not_percentage_or_inverted_denominator(self):
        raw=spec();component=count_grid(raw['scene']['objects'][0])
        self.assertEqual(component['equation'],r'\frac{8}{17}')
        raw=spec([[4,6],[12,18]])
        self.assertEqual(count_grid(raw['scene']['objects'][0])['equation'],r'\frac{4}{16}=\frac{1}{4}')
        for fraction in ([8,10],[8,100],[17,8]):
            raw=spec();raw['claims'][0]['value']=dict(zip(('numerator','denominator'),fraction))
            with self.assertRaises(SemanticError):compile_semantic(raw)

    def test_selection_boxes_identify_the_actual_cell_and_matching_margin(self):
        from notebook_procedural import _label_bounds
        for axis in ('row','column'):
            for r,c in ((0,0),(0,1),(1,0),(1,1)):
                parts=count_grid(spec(row=r,column=c,condition_on=axis)['scene']['objects'][0])['parts']
                selected=parts['selection']
                expected=[parts['row'+str(r+1)][c+1],
                          parts['row'+str(r+1)][3] if axis=='row' else parts['totals'][c+1]]
                for box,label in zip(selected[:2],expected):
                    left,top,right,bottom=_label_bounds(label)
                    self.assertEqual(box['origin'],[left-8,top-8])
                    self.assertEqual(box['size'],[right-left+16,bottom-top+16])
                edges=[tuple(sorted((tuple(line['from']),tuple(line['to'])))) for line in parts['frame']]
                self.assertEqual(len(edges),len(set(edges)))

    def test_unknown_fields_bad_counts_labels_and_empty_denominator_allocate_nothing(self):
        mutations=[{'counts':[[True,2],[9,81]]},{'counts':[[8.0,2],[9,81]]},
            {'counts':[[8,-2],[9,81]]},{'counts':[[1000000,2],[9,81]]},
            {'counts':[[8,2,1],[9,81]]},{'counts':[[0,2],[0,81]]},
            {'rows':['A','a']},{'columns':['Total','B']},{'rows':['A'*11,'B']},
            {'columns':['MMMMMMMMMM','WWWWWWWWWW']},
            {'rows':['/tmp/file','B']},{'url':'https://example.org'}, {'origin':[0,0]},
            {'selected':{'row':True,'column':0,'condition_on':'column'}},
            {'selected':{'row':0,'column':2,'condition_on':'column'}},
            {'selected':{'row':0,'column':0,'condition_on':'population'}}]
        for changes in mutations:
            with self.subTest(changes=changes):
                raw=spec();raw['scene']['objects'][0].update(changes)
                with patch('notebook_lesson_native.storyboard_assets') as encode,patch('notebook_lesson_native.uuid.uuid4') as identity:
                    with self.assertRaises(SemanticError):native_semantic_bundle(json.dumps(raw))
                    encode.assert_not_called();identity.assert_not_called()

    def test_row_order_is_free_but_totals_and_selection_require_their_data(self):
        raw=spec();raw['steps'][2],raw['steps'][3]=raw['steps'][3],raw['steps'][2]
        compile_semantic(raw)
        for index in (1,2,3,4):
            raw=spec();raw['steps'][index],raw['steps'][5]=raw['steps'][5],raw['steps'][index]
            with self.assertRaises(SemanticError):compile_semantic(raw)
        raw=spec();raw['claims']=[]
        with self.assertRaises(SemanticError):compile_semantic(raw)


if __name__=='__main__':unittest.main()
