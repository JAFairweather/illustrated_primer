"""herd-board-primer offline: wrapping, what it narrates, and how it follows a request through the trace."""
import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

import numpy as np

import notebook_trace as trace
from notebook_tablet_input import ink_bottom

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader('herd_board_primer', str(HERE/'herd-board-primer'))
spec = importlib.util.spec_from_loader(loader.name, loader)
primer = importlib.util.module_from_spec(spec)
loader.exec_module(primer)
SPEECH = primer.voice.speech  # the real one: each test patches it out
REQUEST = 'notebook-'+'c'*32


def line(stage, outcome='ok', request=REQUEST, **more):
    return json.dumps(dict(t=time.strftime('%Y-%m-%dT%H:%M:%S'), request=request, stage=stage, outcome=outcome,
                           **more))+'\n'


class PrimerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.trace = os.path.join(self.tmp.name, 'trace.jsonl')
        Path(self.trace).write_text('')
        self.saved = trace.TRACE, primer.REPLIES, primer.CONFIG, primer.STEP
        trace.TRACE, primer.REPLIES = self.trace, self.tmp.name
        primer.CONFIG = os.path.join(self.tmp.name, 'lessons.json')
        Path(primer.CONFIG).write_text(json.dumps(dict(notebooks=[], reader='James', reply_hand='primer',
                                                       opening='once upon a time...')))
        self.addCleanup(self.restore)
        speech = unittest.mock.patch.object(primer.voice, 'speech', return_value=None)  # never the real Gemini
        self.speech = speech.start()
        self.addCleanup(speech.stop)
        tales = unittest.mock.patch.object(primer, 'TALES', self.tmp.name)
        tales.start()
        self.addCleanup(tales.stop)

    def restore(self):
        trace.TRACE, primer.REPLIES, primer.CONFIG, primer.STEP = self.saved

    def reply(self, value):
        Path(self.tmp.name, REQUEST+'.json').write_text(json.dumps(dict(text=json.dumps(value))))

    def test_a_long_question_wraps_inside_the_margins(self):
        lines = primer.wrap('What are the Navier-Stokes equations and why are they so hard to solve, honestly?')
        self.assertGreater(len(lines), 1)
        for text in lines:
            self.assertLessEqual(primer.handwriting_paths(text, primer.SIZE, hand='reader')[1], primer.RIGHT-primer.LEFT)

    def test_a_lesson_is_narrated_from_the_opening_through_each_step_to_the_takeaway(self):
        self.reply(dict(mode='lesson', steps=[dict(caption='... there was a girl named Mira who had a little boat.'),
                                              dict(caption='She sent a pulse of sound.')], takeaway='Sonar listens.'))
        self.assertEqual(primer.narration(REQUEST), [
            'James, once upon a time there was a girl named Mira who had a little boat.',
            'She sent a pulse of sound.', 'Sonar listens.'])
        # Saved as the model wrote it: the lesson closed one brace early, which the server mends (5fdba26e).
        early = json.dumps(dict(mode='lesson', steps=[dict(caption='... a robot named Nia.')]))[:-1]+'}, "picture": {}}'
        Path(self.tmp.name, REQUEST+'.json').write_text(json.dumps(dict(text=early)))
        self.assertEqual(primer.narration(REQUEST), ['James, once upon a time a robot named Nia.'])
        self.reply(dict(mode='lesson', picture=dict(base='a', edits=['b'], captions=['... a robot named Nix.', 'Nix looked.']),
                        steps=[dict(caption='The zeros sit on one line.')], takeaway='Still open.'))
        self.assertEqual(primer.narration(REQUEST), ['James, once upon a time a robot named Nix.', 'Nix looked.',
                                                     'The zeros sit on one line.', 'Still open.'], 'the story, then the figure')
        self.reply(dict(mode='answer', text='Forty-two.'))
        self.assertEqual(primer.narration(REQUEST), ['Forty-two.'])

    def test_it_narrates_while_the_tablet_draws_and_says_the_rest_when_the_page_is_written(self):
        self.reply(dict(mode='lesson', steps=[dict(caption='... a robot.'), dict(caption='Two.'), dict(caption='Three.')]))
        primer.STEP = 0.2
        with open(self.trace, 'a') as f:
            f.write(line('page_read')+line('submitted')+line('rendered')+line('state', 'writing'))
        printed = io.StringIO()
        with open(self.trace, 'a') as f:
            f.write(line('press', request='notebook-'+'d'*32))  # another request's lines are not followed
        with contextlib.redirect_stdout(printed):
            # The page is written after the first step has been said: the rest come at once.
            def written():
                with open(self.trace, 'a') as f:
                    f.write(line('acknowledged'))
            threading.Timer(.3, written).start()
            self.assertTrue(primer.follow(REQUEST, 0))
        said = [json.loads(x) for x in printed.getvalue().splitlines()]
        self.assertEqual([x.get('stage') for x in said if 'stage' in x], ['reading', 'thinking', 'drawing', 'done'])
        self.assertEqual([x['say'] for x in said if 'say' in x], ['James, once upon a time a robot.', 'Two.', 'Three.'])

    def test_each_line_carries_the_narrators_voice_and_the_end_comes_with_done(self):
        self.reply(dict(mode='lesson', steps=[dict(caption='One.'), dict(caption='Two.')]))
        self.speech.side_effect = lambda text: ('wav:'+text).encode()
        Path(self.trace).write_text(line('rendered')+line('state', 'writing')+line('acknowledged'))
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertTrue(primer.follow(REQUEST, 0))
        said = [json.loads(x) for x in printed.getvalue().splitlines()]
        heard = [base64.b64decode(x['audio']).decode() for x in said if 'audio' in x]
        self.assertEqual(heard, ['wav:James, once upon a time. One.', 'wav:Two.', 'wav:The end.'])
        self.assertIn('audio', said[-1])

    def test_the_question_is_read_back_then_a_breath_then_the_opening(self):
        self.speech.side_effect = lambda text, timeout=30: primer.voice.wav(b'\0\0'*primer.voice.RATE)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), \
                unittest.mock.patch.object(primer.voice, 'remembered', return_value=b'RIFFopening'):
            primer.read_back('What is a raven?', 'James, once upon a time...')
        said = [json.loads(x) for x in printed.getvalue().splitlines()]
        self.assertEqual([x['say'] for x in said], ['What is a raven?', 'James, once upon a time...'])
        seconds = (len(base64.b64decode(said[0]['audio']))-44)/2/primer.voice.RATE
        self.assertAlmostEqual(seconds, 1+primer.voice.PAUSE, places=2)
        self.speech.side_effect = OSError('402 Payment Required')  # Piper reads it back; an errand has no opening
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            primer.read_back('Text Day that I am late', None)
        self.assertEqual([json.loads(x) for x in printed.getvalue().splitlines()], [{'say': 'Text Day that I am late'}])

    def test_one_voice_failure_leaves_every_line_to_piper_without_waiting(self):
        self.reply(dict(mode='lesson', steps=[dict(caption=f'Step {i}.') for i in range(6)]))
        self.speech.side_effect = OSError('402 Payment Required')
        Path(self.trace).write_text(line('rendered')+line('state', 'writing')+line('acknowledged'))
        printed, start = io.StringIO(), time.time()
        with contextlib.redirect_stdout(printed):
            self.assertTrue(primer.follow(REQUEST, 0))
        said = [json.loads(x) for x in printed.getvalue().splitlines()]
        self.assertEqual(len([x for x in said if 'say' in x]), 6)
        self.assertFalse([x for x in said if 'audio' in x])
        self.assertLess(time.time()-start, primer.VOICE_WAIT)
        self.assertLessEqual(self.speech.call_count, 3)

    def test_the_narration_is_a_wav_r1_sayd_can_stream_after_its_44_byte_header(self):
        import wave
        tone = (np.sin(np.arange(24000)/24000*2*np.pi*440)*8000).astype('<i2').tobytes()
        clip = primer.voice.wav(primer.voice.resample(tone))
        with wave.open(io.BytesIO(clip)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 22050))
            self.assertAlmostEqual(w.getnframes(), 22050, delta=2)
        self.assertEqual(len(clip)-44, 2*w.getnframes())

    def test_the_voice_is_sent_only_the_line_and_a_clip_too_long_for_its_words_is_left_to_piper(self):
        # 2026-11-01 07:26: a style paragraph above the line was read aloud; "James, once upon a time..." came back 22 s.
        import base64
        from unittest import mock
        def clip(seconds):
            pcm = base64.b64encode(b'\0\0'*int(24000*seconds)).decode()
            return {'candidates': [{'content': {'parts': [{'inlineData': {'data': pcm}}]}}]}
        with mock.patch.object(primer.voice.gm, '_held', return_value=False), \
                mock.patch.object(primer.voice.gm, '_post', return_value=clip(22)) as post:
            self.assertIsNone(SPEECH('James, once upon a time...'))
            sent = json.loads(post.call_args[0][1])['contents'][0]['parts'][0]['text']
            self.assertEqual(sent, 'James, once upon a time...', 'only the words to be spoken')
            post.return_value = clip(3.7)  # the length it is spoken at, measured
            self.assertTrue(SPEECH('James, once upon a time...').startswith(b'RIFF'))

    def test_a_lesson_question_hears_the_opening_at_once_and_an_errand_does_not(self):
        for question in ('What is a raven?', 'Tell me about levers', 'why is the ocean blue'):
            self.assertEqual(primer.opening(question), 'James, once upon a time...', question)
        for question in ('Text Day that I am late', 'Tell My Dude to add pictures', 'yes', 'Send it'):
            self.assertIsNone(primer.opening(question), question)
        self.reply(dict(mode='lesson', steps=[dict(caption='... a robot.'), dict(caption='Two.')], takeaway='So.'))
        self.assertEqual(primer.narration(REQUEST, opened=True), ['... a robot.', 'Two.', 'So.'])

    def test_the_tale_is_told_from_its_first_beat_before_the_reply_is_drawn_and_keeps_to_the_pen_after(self):
        page = 'd'*36+'/'+'e'*36+'.rm'
        asked = time.time()
        tale = dict(steps=[dict(caption='... a robot.', see='a robot'), dict(caption='Two.', see='x'),
                           dict(caption='Three.', see='y')], takeaway='So.')
        Path(self.tmp.name, page.replace('/', '_')+'.json').write_text(json.dumps(dict(tale, t=asked-60)))
        self.assertEqual(primer.tale(page, asked), [], 'an older question on the page is not this one')
        Path(self.tmp.name, page.replace('/', '_')+'.json').write_text(json.dumps(dict(tale, t=asked+1)))
        self.assertEqual(primer.tale(page, asked), ['James, once upon a time a robot.', 'Two.', 'Three.', 'So.'])
        self.reply(dict(mode='lesson', steps=[dict(caption='Other words.')]))  # the tale, not the reply, is told
        primer.STEP = 0.3
        printed = io.StringIO()

        def write(text):
            with open(self.trace, 'a') as f:
                f.write(text)
        threading.Timer(.3, write, [line('page_read')+line('submitted')+line('rendered')+line('state', 'writing')]).start()
        threading.Timer(.7, write, [line('acknowledged')]).start()
        with contextlib.redirect_stdout(printed):
            self.assertTrue(primer.follow(REQUEST, 0, page, asked, opened=True))
        said = [json.loads(x) for x in printed.getvalue().splitlines()]
        self.assertEqual(said[0], {'say': '... a robot.'}, 'the first beat comes before the page is even read')
        self.assertEqual([x['say'] for x in said if 'say' in x], ['... a robot.', 'Two.', 'Three.', 'So.'])
        self.assertLess(said.index({'say': 'Two.'}), said.index({'stage': 'done'}))
        self.assertGreater(said.index({'say': 'Two.'}), said.index({'stage': 'drawing'}), 'later beats keep to the pen')

    def test_the_openings_voice_is_made_once_and_then_kept(self):
        self.speech.side_effect = lambda text: b'RIFF'+text.encode()
        with unittest.mock.patch.object(primer.voice, 'CACHE', self.tmp.name):
            self.assertIsNone(primer.voice.remembered('James, once upon a time...'), 'Piper says it the first time')
            for _ in range(50):
                if primer.voice.remembered('James, once upon a time...'):
                    break
                time.sleep(.02)
            self.assertEqual(primer.voice.remembered('James, once upon a time...'), b'RIFFJames, once upon a time...')
        self.assertEqual(self.speech.call_count, 1)

    def test_a_failed_request_is_reported_with_its_reason(self):
        Path(self.trace).write_text(line('submitted')+line('held', 'failed', reason='Notebook model invalid_json'))
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertFalse(primer.follow(REQUEST, 0))
        self.assertEqual(json.loads(printed.getvalue().splitlines()[-1]),
                         dict(stage='failed', note='Notebook model invalid_json'))

    def test_only_a_recent_unfinished_request_counts_as_in_flight(self):
        Path(self.trace).write_text(line('press')+line('press', request='notebook-'+'e'*32)
                                    + line('acknowledged', request='notebook-'+'e'*32))
        self.assertEqual(primer.in_flight(), [REQUEST])
        with open(self.trace, 'a') as f:
            f.write(line('cleared', 'no answer'))
        self.assertEqual(primer.in_flight(), [])

    def test_the_lowest_ink_is_found_below_the_toolbar_and_inside_the_paper(self):
        grey = np.full((1872, 1404), 255, np.uint8)
        self.assertEqual(ink_bottom(grey), 0)
        grey[150, 300:400] = 0   # the Respond button's row: above the paper
        grey[1500, 1350:1400] = 0  # outside the safe columns
        grey[640:700, 300:302] = 0
        self.assertEqual(ink_bottom(grey), 699)

    def test_the_r1_is_shown_the_newest_ink_filling_its_screen_and_nothing_when_nothing_changed(self):
        page = np.full((1872, 1404), 255, np.uint8)
        page[800:802, 300:900] = 0
        drawn = page.copy()
        drawn[1000:1300, 400:700] = 0  # new ink
        drawn[50:150, 1240:1320] = 0   # Respond lit: the toolbar, not the page
        drawn[500:900, 40:70] = 0      # the side toolbar
        shown, looks = [], iter([drawn, drawn])
        mirror = primer.Mirror(page)
        with unittest.mock.patch.object(primer.tablet, 'screen', lambda: next(looks)), \
                unittest.mock.patch.object(primer, 'out', lambda **line: shown.append(line)):
            mirror.look()
            self.assertEqual(mirror.boxes, [(400, 1000, 699, 1299)])
            mirror.look()  # the same screen: the same picture is not sent again
        self.assertEqual(len(shown), 1)
        from PIL import Image
        picture = Image.open(io.BytesIO(base64.b64decode(shown[0]['show'])))
        self.assertEqual(picture.size, primer.VIEW)
        dark = np.array(picture) < 128
        rows = np.nonzero(dark.any(axis=1))[0]
        self.assertGreater(dark.mean(), .1)  # the new ink is large on the R1
        self.assertGreater(rows[-1], primer.VIEW[1]*.6)  # near the foot, what came before above it


if __name__ == '__main__':
    unittest.main()
