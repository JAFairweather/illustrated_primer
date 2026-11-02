import copy
import json
import unittest
import xml.etree.ElementTree as ET

from ink import strokes
from notebook_drawing import compile_storyboard, preview_svg
from notebook_lesson import LessonLayoutError, compile_lesson, format_lesson, parse_lesson, _segment_hits_box
from notebook_lesson_examples import EXAMPLES
from notebook_plotter_font import GLYPHS, SUPERSCRIPTS, label_paths
from notebook_stroke_asset import storyboard_assets
from notebook_storyboard import _dense


class MathematicalGlyphTests(unittest.TestCase):
    def test_unicode_minus_and_relations_have_real_bounded_strokes(self):
        self.assertEqual(label_paths('−'), label_paths('-'))
        for symbol in ('≤', '≥', '≠'):
            paths, width = label_paths(symbol, 18)
            self.assertTrue(paths)
            self.assertGreater(width, 0)
            self.assertTrue(all(0 <= x <= 12 and 0 <= y <= 18
                                for path in paths for x,y in path))
            self.assertNotEqual(paths, label_paths('=', 18)[0])


def steps():
    return [{'caption': 'Add this part of the picture.',
             'draw': [{'op': 'line', 'from': [30,30+i*30], 'to': [100,30+i*30]}]}
            for i in range(3)]


class LessonTest(unittest.TestCase):
    def test_equation_whitespace_and_spaced_division_are_not_paths(self):
        for source in ('P = 40 / 2 = 20', 'P = W / t', 'W = 20 × 2 = 40',
                       'W = Fd\n= 20 \\times 2\n= 40'):
            plan = parse_lesson(format_lesson(steps(), 'Same work, less time.', source))
            self.assertNotIn('\n', plan['equation'])
            self.assertEqual(len(storyboard_assets(plan)), 3)
        for source in ('/tmp/file', '/ 2', 'x /tmp/file', '~/private', r'C:\private',
                       'https://example.org', r'\input{secret}', 'x\x00y'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                compile_lesson(steps(), 'Conclusion.', source)
        source = steps()
        source[0]['caption'] = 'One sentence.\nAnother line.'
        with self.assertRaises(ValueError):
            compile_lesson(source, 'Conclusion.')

    def test_currency_labels_are_real_bounded_pen_paths(self):
        paths, advance = label_paths('$133.10', 20)
        self.assertGreaterEqual(len(paths), 7)  # No bridges between seven characters.
        self.assertGreater(advance, 0)
        source = steps()
        source[0]['draw'] = [{'op':'label','at':[200,100],'text':'$133.10'}]
        plan = compile_lesson(source, 'Interest also earns interest.')
        self.assertEqual(len(storyboard_assets(plan)), 3)

    def test_a_label_past_an_edge_slides_inside_and_keeps_its_shape(self):
        from notebook_lesson import _primitive
        inside = _primitive({'op':'label','at':[100,100],'text':'rising moist air','size':18})
        for at in ([560,100], [100,359], [0,8]):
            with self.subTest(at=at):
                moved = _primitive({'op':'label','at':at,'text':'rising moist air','size':18})
                self.assertTrue(all(0 <= x <= 600 and 0 <= y <= 360 for path in moved for x,y in path))
                dx, dy = moved[0][0][0]-inside[0][0][0], moved[0][0][1]-inside[0][0][1]
                self.assertEqual([[(round(x-dx,6),round(y-dy,6)) for x,y in p] for p in moved],
                                 [[(round(x,6),round(y,6)) for x,y in p] for p in inside])
        source = steps()
        source[0]['draw'] = [{'op':'label','at':[560,200],'text':'counterclockwise','size':18}]
        compile_lesson(source, 'It fits.')

    def test_the_operator_can_put_labels_in_the_primer_hand(self):
        import notebook_lesson
        from notebook_lesson import _primitive
        command = {'op':'label','at':[40,100],'text':'warm air rises','size':20}
        plotter = _primitive(command)
        try:
            notebook_lesson.label_hand = 'primer'
            primer = _primitive(command)
            self.assertNotEqual(primer, plotter)
            self.assertEqual(primer, _primitive(command))
            self.assertTrue(all(0 <= x <= 600 and 0 <= y <= 360 for path in primer for x,y in path))
            self.assertLess(len(primer), len(plotter), 'joined letters take fewer pen lifts')
            source = steps()
            source[0]['draw'].append({'op':'label','at':[40,300],'text':'σ = 1/2','size':18})
            compile_lesson(source, 'Labels in the primer hand still compile.')
        finally:
            notebook_lesson.label_hand = 'plotter'

    def test_both_prompt_examples_round_trip_as_native_ink_and_cumulative_svg(self):
        for name, example in EXAMPLES.items():
            with self.subTest(example=name):
                plan = parse_lesson(example())
                assets = storyboard_assets(plan)
                self.assertEqual(len(assets), len(plan['stages']))
                total = 0
                for stage, asset in zip(plan['stages'], assets):
                    self.assertEqual(len(strokes(asset['data'])), len(stage['paths']))
                    self.assertLessEqual(asset['point_count'], 3000)
                    self.assertLessEqual(asset['stroke_count'], 64)
                    self.assertLessEqual(stage['estimated_pen_seconds'], 30)
                    total += asset['stroke_count']
                    root = ET.fromstring(preview_svg(plan, stage['id']))
                    self.assertEqual(len(root.findall('{http://www.w3.org/2000/svg}polyline')), total)
                    self.assertFalse(root.findall('{http://www.w3.org/2000/svg}text'))

    def test_all_eight_operations_are_nonexecuting_bounded_paths(self):
        commands = [
            {'op':'line','from':[30,30],'to':[70,30]},
            {'op':'arrow','from':[30,60],'to':[70,60]},
            {'op':'circle','center':[130,70],'radius':20},
            {'op':'rect','origin':[180,40],'size':[50,40]},
            {'op':'polyline','points':[[260,40],[270,70],[290,55]]},
            {'op':'plot','points':[[320,70],[340,60],[360,40]]},
            {'op':'brace','from':[390,40],'to':[450,40],'side':1},
            {'op':'label','at':[460,70],'text':'x²','size':20},
        ]
        source = steps()
        source[0]['draw'] = commands
        original = copy.deepcopy(source)
        plan = compile_lesson(source, 'One growing picture.')
        self.assertEqual(source, original)
        self.assertEqual(compile_storyboard(plan)['required_operations'], ['caption','stroke'])

    def test_last_bad_step_invalidates_the_whole_response(self):
        for bad in [
            {'op':'line','from':[0,0],'to':[601,2]},
            {'op':'line','from':[False,0],'to':[2,2]},
            {'op':'line','from':[10**400,0],'to':[2,2]},
            {'op':'circle','center':[20,20],'radius':30},
            {'op':'rect','origin':[590,10],'size':[20,20]},
            {'op':'plot','points':'lambda x: x*x'},
            {'op':'line','from':[0,0],'to':[2,2],'url':'https://example.org'},
            {'op':'label','at':[601,20],'text':'off the page'},
            {'op':'label','at':[30,30],'text':'unsupported ∂'},
            {'op':'label','at':[30,30],'text':'/tmp/file'},
            {'op':'label','at':[30,30],'text':"__import__('os')"},
            {'op':'brace','from':[10,0],'to':[90,0],'side':-1},
            {'op':[]},
        ]:
            source = steps()
            source[-1]['draw'] = [bad]
            with self.subTest(command=bad), self.assertRaises(ValueError):
                parse_lesson(format_lesson(source,'Conclusion.'))

    def test_strict_json_and_response_framing_reject_ambiguous_or_injected_input(self):
        good = format_lesson(steps(), 'Conclusion.')
        variants = [good.replace('"op":"line"','"op":"line","op":"arrow"',1),
                    good.replace('[30,30]','[NaN,30]',1),
                    good.replace('[30,30]','[Infinity,30]',1),
                    'Introduction\n'+good, good+'\n```python\nprint(1)\n```',
                    good.replace('Takeaway: ', 'Conclusion: '),
                    good.replace('```board-step','```json',1),
                    good.replace('"caption":','"unexpected":0,"caption":',1),
                    good+'x'*48000]
        for text in variants:
            with self.subTest(text=text[:80]), self.assertRaises(ValueError):
                parse_lesson(text)

    def test_stage_count_font_strokes_and_total_points_are_limited(self):
        for source in (steps()[:2], steps()*3):
            with self.assertRaises(ValueError):
                compile_lesson(source, 'Conclusion.')
        source = steps()
        source[-1]['draw'] = [{'op':'label','at':[20,30+i*30],'text':'H'*24} for i in range(3)]
        with self.assertRaisesRegex(ValueError, '64 strokes'):
            compile_lesson(source, 'Conclusion.')
        with self.assertRaisesRegex(ValueError, 'budget'):
            _dense([[(0,0),(600,0)]]*11)

    def test_captions_and_takeaway_cannot_leak_raw_markup(self):
        for text in ('**Important**','`code`','# Heading',r'Use \frac{1}{2}', '[link](elsewhere)'):
            source = steps()
            source[1]['caption'] = text
            with self.subTest(text=text), self.assertRaisesRegex(ValueError,'markup'):
                compile_lesson(source,'Conclusion.')
            with self.assertRaisesRegex(ValueError,'markup'):
                compile_lesson(steps(),text)
        source = steps()*2
        for i, stage in enumerate(source):
            stage = copy.deepcopy(stage)
            stage['draw'] = [{'op':'polyline','points':[[20,20],[580,20],[20,40],[580,40],
                            [20,60],[580,60],[20,80],[580,80],[20,100]]}]
            source[i] = stage
        with self.assertRaisesRegex(ValueError,'point budget'):
            compile_lesson(source,'Conclusion.')

    def test_actual_expanded_geometry_enforces_thirty_seconds(self):
        plan = compile_lesson(steps(), 'Conclusion.')
        plan['stages'][-1]['paths'] = [[(i,10) for i in range(46)]]*64
        with self.assertRaisesRegex(ValueError, 'drawing-time'):
            compile_storyboard(plan)

    def test_invalid_equation_is_rejected_before_returning_a_plan(self):
        with self.assertRaises(ValueError):
            compile_lesson(steps(), 'Conclusion.', r'\input{file}')

    def test_label_collision_is_checked_across_the_complete_lesson(self):
        source = steps()
        source[0]['draw'] = [{'op':'label','at':[200,140],'text':'blue-rich','size':16}]
        source[2]['draw'] = [{'op':'arrow','from':[190,100],'to':[300,180]}]
        with self.assertRaisesRegex(ValueError, r'step 1 command 1 label.*step 3 command 1 arrow'):
            compile_lesson(source,'Conclusion.')
        # Reversing the reveal order cannot evade the same final-page check.
        with self.assertRaisesRegex(ValueError, 'label collision'):
            compile_lesson(list(reversed(source)),'Conclusion.')
        source[2]['draw'] = [{'op':'label','at':[204,140],'text':'another','size':16}]
        with self.assertRaisesRegex(ValueError, 'label collision'):
            compile_lesson(source,'Conclusion.')

    def test_label_inside_shape_and_diagonal_near_label_remain_valid(self):
        source = steps()
        source[0]['draw'] = [{'op':'label','at':[200,140],'text':'8','size':16}]
        source[1]['draw'] = [{'op':'rect','origin':[180,100],'size':[100,70]}]
        # Segment bbox contains the label bbox, but the segment does not hit it.
        source[2]['draw'] = [{'op':'line','from':[190,100],'to':[270,150]}]
        compile_lesson(source,'Conclusion.')
        source[2]['draw'] = [{'op':'line','from':[190,132],'to':[270,132]}]
        with self.assertRaisesRegex(ValueError, 'label collision'):
            compile_lesson(source,'Conclusion.')

    def test_collision_diagnostics_are_bounded_and_do_not_repair_the_input(self):
        source = steps()
        source[0]['draw'] = [{'op':'label','at':[50,50+i*30],'text':'A'} for i in range(10)]
        source[2]['draw'] = [{'op':'line','from':[40,40+i*30],'to':[90,40+i*30]} for i in range(10)]
        original = copy.deepcopy(source)
        with self.assertRaises(LessonLayoutError) as caught:
            compile_lesson(source,'Conclusion.')
        self.assertEqual(source,original)
        collisions = caught.exception.collisions
        self.assertEqual(len(collisions),8)
        self.assertEqual(json.loads(json.dumps(collisions)),collisions)
        for item in collisions:
            self.assertEqual(set(item), {'label','text','clearance_box','clearance_pixels',
                                         'other','other_op','other_bounds','crossing_segment'})
            self.assertTrue(_segment_hits_box(*item['crossing_segment'],item['clearance_box']))
        # Same source continues to fail; no repair or cached acceptance.
        with self.assertRaises(LessonLayoutError):
            compile_lesson(source,'Conclusion.')

    def test_arrowhead_is_checked_not_only_its_shaft(self):
        source = steps()
        source[0]['draw'] = [{'op':'label','at':[188,104],'text':'.','size':12}]
        source[2]['draw'] = [{'op':'line','from':[100,100],'to':[200,100]}]
        compile_lesson(source,'Conclusion.')
        source[2]['draw'][0]['op'] = 'arrow'
        with self.assertRaisesRegex(LessonLayoutError, 'label collision') as caught:
            compile_lesson(source,'Conclusion.')
        crossing = caught.exception.collisions[0]['crossing_segment']
        self.assertNotEqual(crossing,[[100,100],[200,100]])
        self.assertTrue(_segment_hits_box(*crossing,caught.exception.collisions[0]['clearance_box']))

    def test_plotter_labels_are_original_open_paths_and_superscripts_are_raised(self):
        paths, width = label_paths('x²')
        self.assertTrue(width > 0)
        # x is exactly two open strokes; 2 is one open stroke, no bitmap outline.
        self.assertEqual(len(paths), 3)
        self.assertTrue(all(path[0] != path[-1] for path in paths))
        normal, _ = label_paths('2')
        raised, _ = label_paths('²')
        self.assertLess(max(y for p in raised for _,y in p),max(y for p in normal for _,y in p))
        for size in (True, 0, 100, float('nan')):
            with self.assertRaises(ValueError):
                label_paths('x', size)

    def test_prompt_layout_box_contains_every_supported_plotter_glyph(self):
        # The model-facing estimate must remain conservative if the font changes.
        for size in (12, 20, 28):
            for glyph in list(GLYPHS) + list(SUPERSCRIPTS):
                text = 'A ' + glyph + 'gy²'
                paths, _ = label_paths(text, size)
                for path in paths:
                    for x, y in path:
                        with self.subTest(size=size, glyph=glyph):
                            self.assertGreaterEqual(x, 0)
                            self.assertLessEqual(x, .9*size*len(text))
                            self.assertGreaterEqual(y-size, -1.32*size-1e-9)
                            self.assertLessEqual(y-size, size/3+1e-9)


if __name__ == '__main__':
    unittest.main()
