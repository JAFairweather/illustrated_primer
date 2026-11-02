import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from notebook_lesson_eval import prepare, render, compare, examples, preview_png, check_draft, QUESTIONS
from notebook_lesson_examples import integral_example, odd_squares_example
from notebook_lesson import LessonLayoutError, format_lesson, parse_lesson


class LessonEvalTest(unittest.TestCase):
    def test_author_check_flags_ambiguous_scripts_without_changing_equation(self):
        from PIL import Image
        from notebook_media import render_equation
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'draft.txt'
            original = integral_example()
            begin = original.index('```math\n')+len('```math\n')
            end = original.index('\n```',begin)
            for equation,name,warnings in [('F_load × 1 = F_effort × 3','words',2),
                                           ('x^2y','product',1),
                                           ('F_{load} = 3 F_{effort}','grouped',0)]:
                raw = original[:begin]+equation+original[end:]
                source.write_text(raw)
                result = check_draft(source,root/name)
                self.assertTrue(result['valid'])
                self.assertEqual(len(result['equation_notes']),warnings)
                for note in result['equation_notes']:
                    self.assertTrue(note.startswith('Heuristic:'))
                    self.assertIn('explicitly keep the rest outside',note)
                with Image.open(root/name/'equation.png') as image:
                    self.assertEqual(image.tobytes(),render_equation(equation).tobytes())
                self.assertEqual((root/name/'draft.txt').read_text(),raw)
            # Whitespace is baseline spacing, not script grouping. One-atom
            # semantics are unchanged with or without that space.
            for raw,explicit in [('x^2y','x^{2}y'),('x^2 y','x^{2} y')]:
                self.assertEqual(render_equation(raw).tobytes(),render_equation(explicit).tobytes())

    def test_author_check_retains_exact_draft_and_previews_without_native_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'answer.txt'
            raw = (odd_squares_example()+'\r\n').encode('utf-8')
            source.write_bytes(raw)
            result = check_draft(source,root/'checked')
            self.assertTrue(result['valid'])
            self.assertTrue(result['compiler_valid'])
            self.assertTrue(result['preview_complete'])
            self.assertEqual(result['quality_status'],'unreviewed')
            self.assertTrue(result['assisted_draft'])
            self.assertFalse(result['tablet_proven'])
            self.assertIsNone(result['quality_review'])
            self.assertEqual(result['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual((root/'checked/draft.txt').read_bytes(),raw)
            self.assertEqual(source.read_bytes(),raw)
            self.assertEqual(json.loads((root/'checked/result.json').read_text()),result)
            self.assertEqual(list((root/'checked').glob('*.rm')),[])
            counts = [(root/'checked'/s['svg']).read_text().count('<polyline') for s in result['stages']]
            self.assertTrue(all(a < b for a,b in zip(counts,counts[1:])))
            self.assertTrue(all((root/'checked'/s['png']).is_file() for s in result['stages']))
            with self.assertRaises(FileExistsError):
                check_draft(source,root/'checked')
            self.assertEqual((root/'checked/draft.txt').read_bytes(),raw)

    def test_author_check_preserves_compiler_failure_and_rejected_geometry(self):
        steps = [
            {'caption':'Reference.', 'draw':[{'op':'line','from':[20,90],'to':[300,90]}]},
            {'caption':'Collision.', 'draw':[{'op':'label','at':[80,100],'text':'BAD'}]},
            {'caption':'Comparison.', 'draw':[{'op':'circle','center':[400,200],'radius':20}]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'draft.txt'
            source.write_text(format_lesson(steps,'Rejected fixture.'))
            with patch('notebook_lesson_eval.storyboard_assets') as encoder:
                result = check_draft(source,root/'collision')
                encoder.assert_not_called()
            self.assertFalse(result['valid'])
            self.assertTrue(result['diagnostic_only'])
            self.assertIn('label collision',result['error'])
            collision = result['layout_collisions'][0]
            self.assertEqual(collision['label'],'step 2 command 1')
            self.assertEqual(collision['other'],'step 1 command 1')
            self.assertEqual(collision['crossing_segment'],[[20,90],[300,90]])
            self.assertEqual(collision['other_bounds'],[20,90,300,90])
            self.assertEqual(collision['clearance_pixels'],2)
            self.assertEqual((root/'collision/draft.txt').read_text(),source.read_text())
            self.assertEqual(len(result['stages']),3)
            self.assertTrue(all('rejected' in s['png'] for s in result['stages']))
            self.assertEqual(list((root/'collision').glob('*.rm')),[])
            source.write_text('malformed raw answer')
            result = check_draft(source,root/'syntax')
            self.assertFalse(result['valid'])
            self.assertFalse(result['diagnostic_only'])
            self.assertNotIn('layout_collisions',result)
            self.assertEqual(result['stages'],[])
            self.assertEqual(list((root/'syntax').glob('*.png')),[])
            source.write_text(odd_squares_example())
            with patch('notebook_lesson_eval.storyboard_assets',side_effect=ValueError('encoder failure')):
                result = check_draft(source,root/'encoder')
            self.assertFalse(result['valid'])
            self.assertEqual(result['error'],'encoder failure')
            self.assertEqual(result['failure_stage'],'encode')
            self.assertTrue(result['diagnostic_only'])
            self.assertEqual(len(result['stages']),4)
            self.assertFalse(result['compiler_valid'])
            self.assertTrue(result['preview_complete'])
            with patch('notebook_lesson_eval.preview_png',side_effect=KeyError('preview failure')):
                result = check_draft(source,root/'broken-preview')
            self.assertFalse(result['valid'])
            self.assertTrue(result['compiler_valid'])
            self.assertFalse(result['preview_complete'])
            self.assertFalse(result['diagnostic_only'])
            self.assertIn('stages list may be partial',result['notice'])
            self.assertEqual(result['preview_error_type'],'KeyError')
            self.assertEqual(json.loads((root/'broken-preview/result.json').read_text()),result)

    def test_author_check_cli_status_and_bounded_input(self):
        import subprocess
        import sys
        from notebook_lesson import MAX_RESPONSE
        script = Path(__file__).with_name('notebook_lesson_eval.py')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'draft.txt'
            source.write_bytes(b'x'*(MAX_RESPONSE+1))
            with self.assertRaisesRegex(ValueError,'bounded'):
                check_draft(source,root/'too-big')
            self.assertFalse((root/'too-big').exists())
            source.write_bytes(b'\xff')
            with self.assertRaises(UnicodeDecodeError):
                check_draft(source,root/'invalid-utf8')
            self.assertFalse((root/'invalid-utf8').exists())
            for raw,name,expected in [(integral_example(),'valid',0),('bad','bad',2)]:
                source.write_text(raw)
                run = subprocess.run([sys.executable,str(script),'check',str(source),str(root/name)],
                                     capture_output=True,text=True,check=False)
                self.assertEqual(run.returncode,expected,run.stderr)
                result = json.loads(run.stdout)
                self.assertEqual(result['valid'],expected == 0)
                self.assertEqual(result['destination'],str((root/name).resolve()))
            self.assertTrue((root/'valid/equation.png').is_file())
            run = subprocess.run([sys.executable,str(script),'check',str(source),str(root/'valid')],
                                 capture_output=True,text=True,check=False)
            self.assertEqual(run.returncode,2)
            self.assertEqual(json.loads(run.stdout)['error_type'],'FileExistsError')
            self.assertEqual((root/'valid/draft.txt').read_text(),integral_example())

    def test_viewable_preview_uses_cumulative_geometry_and_no_font_substitution(self):
        from PIL import ImageChops
        plan = parse_lesson(odd_squares_example())
        first = preview_png(plan,plan['stages'][0]['id'])
        last = preview_png(plan,plan['stages'][-1]['id'])
        self.assertEqual(first.size,(600,360))
        self.assertEqual(first.mode,'RGB')
        self.assertEqual(first.getpixel((599,359)),(255,255,255))
        self.assertIsNotNone(ImageChops.difference(first,last).getbbox())
        darkness = lambda image: sum(i*n for i,n in enumerate(image.convert('L').histogram()))
        self.assertLess(darkness(last),darkness(first))
        with self.assertRaisesRegex(ValueError,'unknown preview stage'):
            preview_png(plan,'missing')
        plan['stages'][0]['paths'][0][0] = (-1,0)
        with self.assertRaises(ValueError):
            preview_png(plan,plan['stages'][0]['id'])

    def test_rejected_layout_has_diagnostic_svg_but_never_native_assets(self):
        steps = [
            {'caption':'Draw the reference.', 'draw':[{'op':'line','from':[20,90],'to':[300,90]}]},
            {'caption':'This label incorrectly crosses it.',
             'draw':[{'op':'label','at':[80,100],'text':'BAD'}]},
            {'caption':'Add the comparison.', 'draw':[{'op':'circle','center':[400,200],'radius':20}]},
        ]
        response = format_lesson(steps,'A rejected test fixture.')
        with self.assertRaises(LessonLayoutError):
            parse_lesson(response)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = prepare(root/'packet')
            q = packet['questions'][0]
            source = root/'answers.json'
            source.write_text(json.dumps({'model':'TEST ONLY','answers':[
                dict(id=q['id'],prompt_sha256=q['prompt_sha256'],response=response)]}))
            result = render(root/'packet/packet.json',source,root/'render')
            row = result['rows'][0]
            self.assertFalse(row['valid'])
            self.assertEqual(row['stages'],[])
            self.assertTrue(row['diagnostic_only'])
            self.assertEqual(len(row['diagnostic_stages']),3)
            from PIL import Image
            for stage in row['diagnostic_stages']:
                with Image.open(root/'render'/stage['png']) as image:
                    self.assertEqual(image.size,(600,360))
            self.assertEqual(list((root/'render').glob('*.rm')),[])
            self.assertNotIn('diagnostic_stages',result['rows'][1])
            counts = [(root/'render'/s['svg']).read_text().count('<polyline')
                      for s in row['diagnostic_stages']]
            self.assertTrue(all(a < b for a,b in zip(counts,counts[1:])))
            compare(root/'render',root/'render',root/'comparison.html')
            output = (root/'comparison.html').read_text()
            self.assertIn('Rejected layout — diagnostic preview only.',output)
            self.assertIn('Held by compiler: lesson label collision',output)
            self.assertEqual(json.loads((root/'render/integral-raw.json').read_text())['response'],response)

    def test_authored_preview_is_explicitly_not_a_model_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'examples'
            manifest = examples(root)
            self.assertEqual(sum(row['valid'] for row in manifest['rows']),2)
            html = (root/'preview.html').read_text()
            self.assertIn('not PiDog or second-model answers',html)
            self.assertIn('no tablet result is claimed',html)
            self.assertEqual(html.count('<figure>'),7)

    def test_packet_has_ten_fixed_identical_reproducible_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = prepare(root/'a'), prepare(root/'b')
            self.assertEqual(first,second)
            self.assertEqual(len(first['questions']),10)
            self.assertEqual(len({q['id'] for q in first['questions']}),len(QUESTIONS))
            for q in first['questions']:
                self.assertEqual(hashlib.sha256(q['prompt'].encode()).hexdigest(),q['prompt_sha256'])
                self.assertIn('```board-step',q['prompt'])
            with self.assertRaises(FileExistsError):
                prepare(root/'a')

    def test_first_pass_failures_are_retained_not_repaired_and_previews_are_cumulative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = prepare(root/'packet')
            answers = {'model':'AUTHORED TEST FIXTURES — not a model run','answers':[
                dict(id=q['id'],prompt_sha256=q['prompt_sha256'],response=answer)
                for q,answer in zip(packet['questions'],(integral_example(),'invalid raw answer',odd_squares_example()))]}
            answers['answers'][2]['prompt_sha256'] = 'wrong prompt'
            source = root/'answers.json'
            source.write_text(json.dumps(answers))
            result = render(root/'packet/packet.json',source,root/'render')
            self.assertFalse(result['tablet_proven'])
            self.assertEqual(sum(row['valid'] for row in result['rows']),1)
            self.assertEqual(json.loads((root/'render/gravity-raw.json').read_text())['response'],'invalid raw answer')
            self.assertNotIn('diagnostic_stages',result['rows'][1])
            self.assertEqual(list((root/'render').glob('gravity*.svg')),[])
            self.assertIn('Prompt identity mismatch',result['rows'][2]['error'])
            self.assertIn('No model answer',result['rows'][3]['error'])
            row = result['rows'][0]
            self.assertTrue(all((root/'render'/s['png']).is_file() for s in row['stages']))
            self.assertIsNone(row['quality_review'])
            counts = [(root/'render'/stage['svg']).read_text().count('<polyline') for stage in row['stages']]
            self.assertTrue(all(a < b for a,b in zip(counts,counts[1:])))
            self.assertTrue((root/'render/integral-step-1.rm').read_bytes().startswith(b'reMarkable .lines'))
            compare(root/'render',root/'render',root/'compare.html')
            html = (root/'compare.html').read_text()
            self.assertIn('Held by compiler',html)
            self.assertIn('Incomplete comparison:',html)
            self.assertIn('Awaiting model answer:',html)
            self.assertIn('not observed latency',html)
            self.assertIn('Run conditions:',html)
            self.assertIn(packet['conditions'],html)
            self.assertLess(html.index('<svg'),html.index('<figcaption>'))
            compare(root/'render',root/'render',root/'assisted.html',assisted=True)
            self.assertIn('Assisted comparison:',(root/'assisted.html').read_text())
            self.assertIn('not an unassisted',(root/'assisted.html').read_text())
            self.assertNotIn('Assisted comparison:',html)
            (root/'render/quality-review.json').write_text(json.dumps({'integral':{
                'verdict':'Needs <review>', 'notes':'A label crosses a line.'}}))
            compare(root/'render',root/'render',root/'reviewed.html')
            reviewed = (root/'reviewed.html').read_text()
            self.assertIn('Needs &lt;review&gt;',reviewed)
            self.assertIn('A label crosses a line.',reviewed)
            with self.assertRaises(FileExistsError):
                render(root/'packet/packet.json',source,root/'render')

    def test_duplicate_answers_and_unmatched_runs_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = prepare(root/'packet')
            q = packet['questions'][0]
            answer = dict(id=q['id'],prompt_sha256=q['prompt_sha256'],response=integral_example())
            source = root/'answers.json'
            source.write_text(json.dumps({'model':'fixture','answers':[answer,answer]}))
            with self.assertRaisesRegex(ValueError,'duplicate'):
                render(root/'packet/packet.json',source,root/'bad')
            self.assertFalse((root/'bad').exists())
            source.write_text(json.dumps({'model':'<script>not executable</script>','answers':[answer]}))
            render(root/'packet/packet.json',source,root/'left')
            render(root/'packet/packet.json',source,root/'right')
            compare(root/'left',root/'right',root/'compare.html')
            self.assertNotIn('<script>',(root/'compare.html').read_text())
            path = root/'right/manifest.json'
            manifest = json.loads(path.read_text())
            manifest['rows'].pop()
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'question counts'):
                compare(root/'left',root/'right',root/'compare.html')


if __name__ == '__main__':
    unittest.main()
