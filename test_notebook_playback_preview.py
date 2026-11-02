import copy
import json
import math
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from notebook_ink_playback import playback_assets
from notebook_lesson_eval import prepare, render, compare
from notebook_playback_preview import CSS, playback_preview, native_lesson_preview, typing_units
from notebook_lesson_native import native_semantic_bundle
from notebook_semantic import compile_semantic
from notebook_semantic_examples import examples


class PlaybackPreviewTests(unittest.TestCase):
    def test_native_sequence_uses_exact_math_ink_and_waits_for_captions(self):
        bundle=native_semantic_bundle(json.dumps(examples()['fractions-variant']),playback=True,pen_equations=True)
        markup,summary=native_lesson_preview(bundle)
        self.assertFalse(summary['tablet_proven'])
        self.assertNotIn('<img',markup)
        self.assertNotIn('<script',markup)
        self.assertEqual(markup.count('<svg '),2,'one growing diagram and one equation')
        previous=0
        for event,block in zip(summary['events'],bundle['blocks']):
            self.assertAlmostEqual(event['start_ms'],previous)
            self.assertEqual(event['kind'],block['kind'])
            duration=block['playback']['duration_ms'] if block['kind']=='ink' else 31*len(typing_units(block['text']))
            self.assertAlmostEqual(event['end_ms']-event['start_ms'],duration)
            previous=event['end_ms']
        self.assertEqual(summary['events'][-2]['role'],'equation')
        self.assertGreater(summary['total_planned_ms'],summary['total_motion_ms'])
        svgs=re.findall(r'<svg.*?</svg>',markup)
        math_paths=list(ET.fromstring(svgs[-1]))
        expected=bundle['blocks'][-2]['playback']['paths']
        self.assertEqual(len(math_paths),len(expected))
        for element,points in zip(math_paths,expected):
            self.assertEqual([list(map(float,p.split(','))) for p in element.attrib['points'].split()],points)

    def test_native_preview_rejects_changed_asset_and_escapes_prose(self):
        bundle=native_semantic_bundle(json.dumps(examples()['fractions-variant']),playback=True,pen_equations=True)
        bundle['blocks'][-1]['text']='<script> & unsafe'
        markup,_=native_lesson_preview(bundle)
        self.assertNotIn('<script>',markup)
        self.assertIn('&lt;',markup)
        bundle['sources'][-1]['data']+=b'changed'
        with self.assertRaises(ValueError):native_lesson_preview(bundle)

    def test_caption_groups_match_native_client(self):
        import subprocess
        samples=['A\u0301', '👨‍👩‍👧 🇺🇸', 'مرحبا', 'x' * 2000, 'Takeaway: 2/3 > 3/5']
        qmd=Path(__file__).with_name('xochitl')/'herdRespond.qmd'
        source=qmd.read_text()
        function=source[source.index('function herdTypingUnits('):source.index('function herdStartTyping(')]
        script=function+'\nconsole.log(JSON.stringify('+json.dumps(samples)+'.map(herdTypingUnits)));'
        actual=json.loads(subprocess.check_output(['node','-e',script],text=True))
        self.assertEqual([typing_units(s) for s in samples],actual)
        with self.assertRaises(ValueError):typing_units('😀'*1001)

    def test_same_native_geometry_order_and_velocity(self):
        plan = compile_semantic(examples()['motion-check'])
        original = copy.deepcopy(plan)
        markup, summary = playback_preview(plan)
        self.assertEqual(plan, original)
        svg = ET.fromstring(re.search(r'<svg.*?</svg>', markup).group())
        paths = list(svg)
        expected = [p for a in playback_assets(plan) for p in a['playback']['paths']]
        self.assertEqual(len(paths), len(expected))
        elapsed = 0
        for element, points in zip(paths, expected):
            decoded = [list(map(float, p.split(','))) for p in element.attrib['points'].split()]
            self.assertEqual(decoded, points)
            timing = dict(x.split(':') for x in element.attrib['style'].split(';'))
            self.assertAlmostEqual(float(timing['--start'][:-2]), elapsed, places=5)
            duration = 1000*sum(math.dist(a,b) for a,b in zip(points,points[1:]))/600
            self.assertAlmostEqual(float(timing['--duration'][:-2]), duration, places=5)
            elapsed += duration  # One path per stage; no fake inter-stage overhead.
        self.assertAlmostEqual(summary['total_motion_ms'], elapsed)
        self.assertFalse(summary['tablet_proven'])
        self.assertEqual(summary['stages'][-1]['end_ms'], elapsed)
        self.assertNotIn('<script', markup)
        self.assertIn('prefers-reduced-motion:reduce', CSS)
        self.assertIn('linear var(--start) forwards', CSS)  # No visibility during delay.

    def test_pen_lifts_and_captions_follow_each_stage(self):
        plan = compile_semantic(examples()['integral'])
        markup, summary = playback_preview(plan)
        assets = playback_assets(plan)
        elapsed = 0
        for stage, asset in zip(summary['stages'], assets):
            self.assertAlmostEqual(stage['start_ms'], elapsed)
            elapsed += asset['playback']['duration_ms']
            self.assertAlmostEqual(stage['end_ms'], elapsed)
            self.assertIn(f'class="pen-caption" style="--start:{elapsed:.6f}ms"', markup)
        self.assertAlmostEqual(summary['total_motion_ms'], elapsed)
        self.assertLess(markup.index('alt="Rendered lesson equation"'), markup.index('Takeaway:'))
        self.assertIn('src="data:image/png;base64,', markup)

    def test_escape_prose_and_preserve_native_dots(self):
        plan = compile_semantic(examples()['motion-check'])
        plan['takeaway'] = '<script>alert("x")</script> & takeaway'
        plan['stages'][0]['text'] = '<img src=x> & caption'
        plan['stages'][0]['paths'] = [[(20,30),(20,30)]]
        markup, summary = playback_preview(plan)
        self.assertNotIn('<script>', markup)
        self.assertNotIn('<img', markup)
        self.assertIn('&lt;img src=x&gt; &amp; caption', markup)
        self.assertIn('<circle class="pen-path" cx="20.0" cy="30.0"', markup)
        self.assertEqual(summary['stages'][0]['end_ms'], 10)

    def test_whole_lesson_rejects_before_preview(self):
        plan = compile_semantic(examples()['motion-check'])
        plan['stages'][-1]['paths'] = [[(0,0),(9999,0)]]
        with self.assertRaises(ValueError):
            playback_preview(plan)

    def test_report_embeds_player_and_retains_static_on_playback_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = prepare(root/'packet', semantic=True)
            q = packet['questions'][0]
            response = json.dumps(examples()['integral'])
            source = root/'answers.json'
            source.write_text(json.dumps(dict(model='TEST FIXTURE', answers=[dict(
                id=q['id'], prompt_sha256=q['prompt_sha256'], response=response)])))
            result = render(root/'packet/packet.json', source, root/'rendered')
            self.assertTrue(result['rows'][0]['playback']['valid'])
            self.assertTrue(result['rows'][0]['native_playback']['valid'])
            compare(root/'rendered', root/'rendered', root/'comparison.html')
            report = (root/'comparison.html').read_text()
            self.assertEqual(report.count('class="pen-preview"'), 2)
            self.assertEqual(report.count('TEST FIXTURE'), 2)  # Once per model, not per question.
            self.assertIn('<h3>Model A</h3>', report)
            self.assertIn('<h3>Model B</h3>', report)
            self.assertIn("default-src 'none'", report)
            self.assertNotIn('<script', report)
            self.assertIn('Including planned character reveal:',report)
            with patch('notebook_playback_preview.playback_assets', side_effect=ValueError('<budget>')), \
                 patch('notebook_playback_preview.native_lesson_preview',side_effect=ValueError('<budget>')):
                held = render(root/'packet/packet.json', source, root/'held')
            row = held['rows'][0]
            self.assertTrue(row['valid'])
            self.assertTrue(row['visual_lesson'])
            self.assertFalse(row['playback']['valid'])
            self.assertFalse(row['native_playback']['valid'])
            self.assertTrue(row['stages'])
            compare(root/'held', None, root/'held.html')
            self.assertIn('playback held: &lt;budget&gt;', (root/'held.html').read_text())
            self.assertEqual(json.loads((root/'held/integral-raw.json').read_text())['response'], response)


if __name__ == '__main__':
    unittest.main()
