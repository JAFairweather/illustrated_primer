"""herd-board-primer offline: wrapping, what it narrates, and how it follows a request through the trace."""
import base64
import contextlib
import fcntl
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

    def test_each_paragraph_is_said_as_its_handwriting_starts_not_on_a_timer(self):
        self.reply(dict(mode='lesson', steps=[dict(caption='One.'), dict(caption='Two.'), dict(caption='Three.')],
                        takeaway='So.'))
        primer.STEP = 0.05  # would say every line within the first claim's wait if the timer still ran
        heard, began = [], time.time()
        claim = lambda scene: line('ink_claimed', scene=scene, block_stage='hand' if scene[:5] == 'hand-' else 's1')

        def write(text):
            with open(self.trace, 'a') as f:
                f.write(text)
        write(line('rendered')+line('state', 'writing')+claim('hand-a')+claim('hand-b'))
        threading.Timer(.4, write, [claim('picture-1')+claim('hand-c')]).start()
        threading.Timer(.8, write, [claim('picture-2')+line('ink_claimed', 'refused', scene='hand-x')
                                    + claim('hand-d')]).start()
        threading.Timer(1.2, write, [line('acknowledged')]).start()
        with unittest.mock.patch.object(primer, 'out', lambda **x: heard.append((time.time()-began, x))):
            self.assertTrue(primer.follow(REQUEST, 0))
        said = [(t, x['say']) for t, x in heard if 'say' in x]
        self.assertEqual([s for _, s in said], ['James, once upon a time. One.', 'Two.', 'Three.', 'So.'])
        self.assertLess(said[0][0], .4)
        self.assertTrue(.4 <= said[1][0] < .8 and .8 <= said[2][0] < 1.2 and said[3][0] >= 1.2, said)

    def test_a_passage_is_said_when_the_block_that_opens_it_is_claimed(self):
        # Two passages in one run of handwriting, no picture between: run counting would hold the second to the end.
        self.reply(dict(mode='lesson', steps=[dict(caption='Pip was born in a basket of wool.'),
                                              dict(caption='Weeks later, Pip got a thorn in her paw.'),
                                              dict(caption='Years later, Pip had kittens of her own.')],
                        takeaway='Cats purr to say I am here.'))
        heard, began = [], time.time()
        claim = lambda scene, opens=None: line('ink_claimed', scene=scene, block_stage='hand', opens=opens)

        def write(text):
            with open(self.trace, 'a') as f:
                f.write(text)
        write(line('rendered')+line('state', 'writing')+claim('hand-o', 'James, once upon a time...')
              + claim('hand-a', 'Pip was born in a basket of wool.')+claim('hand-a2'))
        threading.Timer(.4, write, [claim('picture-1', None)+claim('hand-b', 'Weeks later, Pip got a thorn in her p')]).start()
        threading.Timer(.8, write, [claim('hand-c', 'Years later, Pip had kittens of her own.')]).start()
        threading.Timer(1.2, write, [line('acknowledged')]).start()
        with unittest.mock.patch.object(primer, 'out', lambda **x: heard.append((time.time()-began, x))):
            self.assertTrue(primer.follow(REQUEST, 0))
        said = [(t, x['say']) for t, x in heard if 'say' in x]
        self.assertEqual([s for _, s in said], ['James, once upon a time. Pip was born in a basket of wool.',
                                                'Weeks later, Pip got a thorn in her paw.',
                                                'Years later, Pip had kittens of her own.', 'Cats purr to say I am here.'])
        self.assertLess(said[0][0], .4)
        self.assertTrue(.4 <= said[1][0] < .8 and .8 <= said[2][0] < 1.2 and said[3][0] >= 1.2, said)

    def test_a_typed_caption_is_said_as_its_drawing_starts(self):
        # 11:27 on 2026-11-01: only the opening was handwritten; every claim carried "opens": null, and all was said at the end.
        # The server names a typed caption on its drawing's claim; a drawing under a handwritten caption names nothing.
        self.reply(dict(mode='lesson', steps=[dict(caption='One.'), dict(caption='Two.')], takeaway='So.'))
        heard, began = [], time.time()
        claim = lambda scene, stage, opens=None: line('ink_claimed', scene=scene, block_stage=stage, opens=opens)

        def write(text):
            with open(self.trace, 'a') as f:
                f.write(text)
        write(line('rendered')+line('state', 'writing')+claim('hand-o', 'hand', 'James, once upon a time...'))
        threading.Timer(.6, write, [claim('lesson-1', 'step-1', 'One.')+claim('lesson-1', 'step-1-2')]).start()
        threading.Timer(1.6, write, [claim('lesson-2', 'step-2', 'Two.')+claim('lesson-3', 'step-3')]).start()
        threading.Timer(2.6, write, [line('acknowledged')]).start()
        with unittest.mock.patch.object(primer, 'out', lambda **x: heard.append((time.time()-began, x))):
            self.assertTrue(primer.follow(REQUEST, 0, opened='James, once upon a time...'))
        said = [(t, x['say']) for t, x in heard if 'say' in x]
        self.assertEqual([s for _, s in said], ['James, once upon a time...', 'One.', 'Two.', 'So.'])
        self.assertTrue(said[0][0] < .6 and .6 <= said[1][0] < 1.6 and 1.6 <= said[2][0] < 2.6 <= said[3][0], said)

    def test_a_storys_head_then_its_rest_are_one_telling(self):
        # The head (opening and first caption) is written as its own request; its done names the rest's request.
        self.reply(dict(mode='lesson', steps=[dict(caption='One.'), dict(caption='Two.')], takeaway='So.'))
        rest = 'notebook-'+'f'*32
        claim = lambda scene, opens=None, request=REQUEST: line('ink_claimed', request=request, scene=scene, opens=opens)
        heard = []
        Path(self.trace).write_text(line('head', opens='One.')+line('rendered', mode='answer')+line('state', 'writing')
                                    + claim('hand-o', 'James, once upon a time...')+claim('hand-1', 'One.')
                                    + line('acknowledged')+line('state', 'written')+line('continued', next=rest)
                                    + line('acknowledged')  # the head's post, traced after it answered
                                    + line('state', 'writing', request=rest)+claim('lesson-2', 'Two.', rest)
                                    + line('acknowledged', request=rest))
        with unittest.mock.patch.object(primer, 'out', lambda **x: heard.append(x)):
            self.assertTrue(primer.follow(REQUEST, 0, opened='James, once upon a time...'))
        self.assertEqual([x['say'] for x in heard if 'say' in x], ['James, once upon a time...', 'One.', 'Two.', 'So.'])
        self.assertEqual([x['stage'] for x in heard if x.get('stage') == 'done'], ['done'])
        Path(self.trace).write_text(line('head', opens='One.')+line('acknowledged')+line('continued', next=rest)
                                    + line('held', 'failed', request=rest,
                                           reason='Rest of the story timed out after 180 s; its start is on the page'))
        heard.clear()
        with unittest.mock.patch.object(primer, 'out', lambda **x: heard.append(x)):
            self.assertFalse(primer.follow(REQUEST, 0))
        self.assertEqual(heard[-1], dict(stage='failed', note="I wrote the start of the story, but the rest didn't come. Ask again."))

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

    def test_an_r1_that_lost_its_connection_reattaches_and_hears_the_lines_it_missed(self):
        # 2026-11-02 12:30: the R1's Wi-Fi gave out after the question's read-back; the tablet got the whole story.
        live, lock = os.path.join(self.tmp.name, 'live.jsonl'), os.path.join(self.tmp.name, 'primer.lock')
        with unittest.mock.patch.multiple(primer, LIVE=live, LOCK=lock, RUNS=os.path.join(self.tmp.name, 'runs')), \
                contextlib.redirect_stdout(io.StringIO()):
            self.addCleanup(setattr, primer, 'live', None)
            self.addCleanup(setattr, primer, 'run_log', None)
            primer.start_run('Seven friends go rafting on the Rio Pacuare. How does the trip go?')
            primer.out(stage='writing')
            primer.out(say='Seven friends go rafting.')
            primer.out(show='old picture')
            primer.out(say='James, once upon a time...')
            primer.out(show='new picture')
            primer.out(say='The raft finds the smooth V.')
            primer.out(stage='done', say='The end.')
            for start, heard in ((2, ['James, once upon a time...', 'The raft finds the smooth V.', 'new picture',
                                      'The end.']), (6, ['The end.'])):
                printed = io.StringIO()
                with contextlib.redirect_stdout(printed):
                    self.assertEqual(primer.attach(start), 0)
                self.assertEqual([x.get('say') or x.get('show') for x in map(json.loads, printed.getvalue().splitlines())],
                                 heard)
            self.assertTrue(primer.same_question('Seven friends go rafting together on the Rio Pacuare. How does that '
                                                 'trip go?', primer.told_question()))
            self.assertFalse(primer.same_question('Why is the sky blue?', primer.told_question()))

    def test_a_reattached_r1_follows_the_story_as_it_goes_on(self):
        live, lock = os.path.join(self.tmp.name, 'live.jsonl'), os.path.join(self.tmp.name, 'primer.lock')
        Path(live).write_text(''.join(json.dumps(x)+'\n' for x in ({'question': 'q'}, {'say': 'One.'}, {'show': 'a'},
                                                                      {'show': 'b'})))
        held = open(lock, 'w')
        fcntl.flock(held, fcntl.LOCK_EX)

        def tell():
            time.sleep(0.5)
            with open(live, 'a') as f:
                f.write(json.dumps({'say': 'Two.'})+'\n')
                f.flush()
                time.sleep(0.5)
                f.write(json.dumps({'stage': 'done', 'say': 'The end.'})+'\n')
            held.close()
        teller = threading.Thread(target=tell)
        teller.start()
        printed = io.StringIO()
        with unittest.mock.patch.multiple(primer, LIVE=live, LOCK=lock), contextlib.redirect_stdout(printed):
            self.assertEqual(primer.attach(1), 0)
        teller.join()
        self.assertEqual([x.get('say') or x.get('show') for x in map(json.loads, printed.getvalue().splitlines())],
                         ['b', 'Two.', 'The end.'])

    def test_a_story_that_stopped_without_an_end_tells_the_reattached_r1_so(self):
        live, lock = os.path.join(self.tmp.name, 'live.jsonl'), os.path.join(self.tmp.name, 'primer.lock')
        Path(live).write_text(json.dumps({'question': 'q'})+'\n'+json.dumps({'say': 'One.'})+'\n')
        printed = io.StringIO()
        with unittest.mock.patch.multiple(primer, LIVE=live, LOCK=lock), contextlib.redirect_stdout(printed):
            self.assertEqual(primer.attach(0), 1)
        said = [json.loads(x) for x in printed.getvalue().splitlines()]
        self.assertEqual(said[0], {'say': 'One.'})
        self.assertEqual(said[-1]['stage'], 'failed')

    def test_the_question_is_read_back_then_a_breath_then_the_opening(self):
        self.speech.side_effect = lambda text, timeout=30: primer.voice.wav(b'\0\0'*primer.voice.RATE)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), \
                unittest.mock.patch.object(primer.voice, 'remembered', return_value=b'RIFFopening'):
            primer.read_back('What is a raven?', 'James, once upon a time...')
        said = [json.loads(x) for x in printed.getvalue().splitlines()]
        self.assertEqual([x['say'] for x in said], ['What is a raven?'], 'the opening waits for its handwriting')
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

    def test_a_page_that_took_a_plain_answer_is_said_as_the_page_says_it_not_as_the_tale(self):
        # 12:08 on 2026-11-01: the voice told the tale while the page showed Pi Dog's own short answer.
        page = 'doc/page.rm'
        tale = dict(steps=[dict(caption='... a mapmaker named Odile.', see='x')], takeaway='Tale takeaway.')
        Path(self.tmp.name, page.replace('/', '_')+'.json').write_text(json.dumps(dict(tale, t=time.time())))
        self.reply(dict(mode='answer', text='The page answer.'))
        Path(self.trace).write_text(line('rendered', mode='answer')+line('state', 'writing')+line('acknowledged'))
        heard = []
        with unittest.mock.patch.object(primer, 'out', lambda **x: heard.append(x)):
            self.assertTrue(primer.follow(REQUEST, 0, path=page, asked=time.time()-5))
        said = [x['say'] for x in heard if 'say' in x]
        self.assertIn('The page answer.', said)
        self.assertFalse(any('Odile' in s or 'Tale takeaway' in s for s in said), said)

    def test_the_tale_waits_for_the_pen_and_the_opening_is_said_as_its_handwriting_starts(self):
        page = 'd'*36+'/'+'e'*36+'.rm'
        asked = time.time()
        tale = dict(steps=[dict(caption='... a robot.', see='a robot'), dict(caption='Two.', see='x'),
                           dict(caption='Three.', see='y')], takeaway='So.')
        Path(self.tmp.name, page.replace('/', '_')+'.json').write_text(json.dumps(dict(tale, t=asked-60)))
        self.assertEqual(primer.tale(page, asked), [], 'an older question on the page is not this one')
        Path(self.tmp.name, page.replace('/', '_')+'.json').write_text(json.dumps(dict(tale, t=asked+1)))
        self.assertEqual(primer.tale(page, asked), ['James, once upon a time a robot.', 'Two.', 'Three.', 'So.'])
        self.reply(dict(mode='lesson', steps=[dict(caption='Other words.')]))  # the tale, not the reply, is told
        primer.STEP = 0.05
        heard, began = [], time.time()
        claim = lambda scene, opens=None: line('ink_claimed', scene=scene, block_stage='hand',
                                               **({'opens': opens} if opens else {}))

        def write(text):
            with open(self.trace, 'a') as f:
                f.write(text)
        threading.Timer(.3, write, [line('page_read')+line('submitted')+line('rendered')+line('state', 'writing')]).start()
        threading.Timer(.6, write, [claim('hand-o', 'James, once upon a time...')+claim('hand-a', '... a robot.')]).start()
        threading.Timer(1.6, write, [claim('picture-1')+claim('hand-b', 'Two.')]).start()  # follow() looks twice a second
        threading.Timer(2.6, write, [line('acknowledged')]).start()
        with unittest.mock.patch.object(primer, 'out', lambda **x: heard.append((time.time()-began, x))):
            self.assertTrue(primer.follow(REQUEST, 0, page, asked, opened='James, once upon a time...'))
        said = [(t, x['say']) for t, x in heard if 'say' in x]
        self.assertEqual([s for _, s in said], ['James, once upon a time...', '... a robot.', 'Two.', 'Three.', 'So.'])
        self.assertTrue(.6 <= said[0][0] < 1.6 and .6 <= said[1][0] < 1.6, 'nothing is said before its ink: %s' % said)
        self.assertTrue(1.6 <= said[2][0] < 2.6 and said[3][0] >= 2.6, said)

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

    def test_a_failed_request_is_reported_in_words_the_r1_can_say(self):
        Path(self.trace).write_text(line('submitted')+line('held', 'failed', reason='Notebook model invalid_json'))
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertFalse(primer.follow(REQUEST, 0))
        self.assertEqual(json.loads(printed.getvalue().splitlines()[-1]),
                         dict(stage='failed', note="My drawing didn't come out right, so nothing was written. Ask again."))

    def test_each_failure_reason_is_said_plainly(self):
        for reason, words in [('Notebook page_changed', 'keep your ink safe'), ('Timed out after 309 s', 'too long'),
                              ('Notebook model busy', 'busy'), ('', 'Something went wrong')]:
            with self.subTest(reason=reason):
                self.assertIn(words, primer.plain_words(reason))

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
