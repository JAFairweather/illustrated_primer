import base64
import io
import json
import math
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image, ImageDraw

import notebook_image_model as model
from notebook_raster_ink import raster_plan, budget, linemerge, order, new_ink, vectorize, hatch, solids, dilate, _points


def frame(steps, shift=0, size=(1024, 768)):
    im = Image.new('L', size, 255)
    d = ImageDraw.Draw(im)
    d.line([(60+shift, 600), (960+shift, 600)], fill=0, width=6)
    d.ellipse([(300+shift, 440), (460+shift, 600)], outline=0, width=6)
    if steps >= 2:
        d.ellipse([(760, 90), (880, 210)], outline=0, width=6)
    if steps >= 3:
        d.line([(480, 520), (700, 520)], fill=0, width=6)
    f = io.BytesIO()
    im.save(f, 'PNG')
    return f.getvalue()


class RasterInkTests(unittest.TestCase):
    def test_each_stage_draws_only_what_its_frame_added(self):
        plan, report = raster_plan([frame(1), frame(2, 1), frame(3, 2)], ['Ground and ball.', 'The sun.', 'A push.'])
        self.assertEqual([s['id'] for s in plan['stages']], ['step-1', 'step-2', 'step-3'])
        self.assertEqual([r['kept'] for r in report], [2, 1, 1], 'a redrawn line one or two pixels off is not new')
        self.assertEqual([r['removed'] for r in report], [0, 0, 0])
        _, moved = raster_plan([frame(1), frame(1, 40)], ['A ball.', 'The ball, somewhere else.'])
        self.assertGreater(moved[1]['removed'], .2, 'an edit that moved the picture is reported, since ink stays')
        ys = lambda stage: [y for p in stage['paths'] for _, y in p]
        self.assertLess(max(ys(plan['stages'][1])), min(ys(plan['stages'][0])), 'the sun sits above the ground')
        for stage in plan['stages']:
            for path in stage['paths']:
                self.assertTrue(all(math.dist(a, b) <= 8.01 for a, b in zip(path, path[1:])))
                self.assertTrue(all(type(v) is float for point in path for v in point))

    def test_the_picture_fits_the_region_and_the_whole_lesson_budget(self):
        plan, report = raster_plan([frame(3)], ['All at once.'], width=600, height=300)
        xs = [x for s in plan['stages'] for p in s['paths'] for x, _ in p]
        self.assertTrue(0 <= min(xs) and max(xs) <= 600)
        self.assertLessEqual(sum(r['points'] for r in report), 12000)

    def test_budget_keeps_the_longest_paths_within_strokes_points_and_pen_time(self):
        paths = [[(0.0, float(i)), (float(10+i), float(i))] for i in range(100)]
        kept = budget(paths, points=3000, strokes=64)
        self.assertEqual(len(kept), 64)
        self.assertEqual(kept[0], paths[36], 'the shortest are dropped and order is kept')
        long = [[(0.0, float(i)), (2000.0, float(i))] for i in range(5)]
        kept = budget(long)
        self.assertLessEqual(sum(map(_points, kept)), 3000)
        self.assertLessEqual(sum(map(_points, kept))*.009+len(kept)*.070, 30)

    def test_lines_that_meet_are_merged_and_the_pen_travels_to_the_nearest_end(self):
        merged = linemerge([[(0, 0), (10, 0)], [(20, 0), (11, 0)], [(50, 50), (60, 60)]])
        self.assertEqual(len(merged), 2)
        self.assertIn(20, [x for p in merged for x, _ in p])
        ordered = order([[(100, 0), (90, 0)], [(10, 0), (0, 0)]])
        self.assertEqual(ordered[0], [(0, 0), (10, 0)], 'reversed so it starts nearest the pen')

    def test_solid_dots_become_small_circles_not_lost_pixels(self):
        mask = np.zeros((60, 60), bool)
        mask[20:25, 30:35] = True
        paths = vectorize(mask)
        self.assertEqual(len(paths), 1)
        cx = sum(x for x, _ in paths[0])/len(paths[0])
        self.assertAlmostEqual(cx, 32, delta=1)

    def test_a_filled_shape_is_outlined_round_its_white_detail_and_hatched_not_thinned(self):
        mask = np.zeros((120, 160), bool)
        mask[20:100, 30:130] = True
        mask[50:70, 60:80] = False  # a white eye
        paths = vectorize(mask)
        ends = [p for p in paths if math.dist(p[0], p[-1]) <= 3]
        self.assertGreaterEqual(len(ends), 2, 'the outside and the eye are both closed outlines')
        deep = ~dilate(~mask, 4)
        self.assertFalse(any(deep[round(y), round(x)] for p in paths for x, y in p), 'no scrawl down its middle')
        shade = hatch(solids(mask))
        self.assertLessEqual(len(shade), 3, 'a few zigzags shade it')
        inked = [(x, y) for p in shade for x, y in p]
        self.assertTrue(all(mask[round(y), round(x)] for x, y in inked))
        self.assertFalse(any(60 <= x < 80 and 50 <= y < 70 for x, y in inked), 'the eye stays white')

    def test_a_bold_line_stays_one_line(self):
        mask = np.zeros((60, 200), bool)
        mask[26:34, 20:180] = True  # 8 px wide, as the boldest explainer lines come out
        self.assertFalse(solids(mask).any())
        paths = vectorize(mask)
        self.assertEqual(len(paths), 1)

    def test_a_sliver_left_by_a_redrawn_line_is_not_made_a_dot(self):
        mask = np.zeros((60, 60), bool)
        mask[20:26, 10:34] = True  # 24 x 6: a piece of a plank the edit moved
        paths = vectorize(mask)
        self.assertEqual(len(paths), 1)
        self.assertLess(len(paths[0]), 12, 'a line along it, not a spiral filling it')

    def test_an_edit_that_erases_adds_nothing(self):
        a = np.zeros((50, 50), bool)
        a[10, 5:45] = True
        self.assertFalse(new_ink(a, np.zeros_like(a)).any())

    def test_blank_or_mismatched_frames_are_refused(self):
        blank = io.BytesIO()
        Image.new('L', (64, 64), 255).save(blank, 'PNG')
        for frames, captions in (([blank.getvalue()], ['x']), ([frame(1), frame(2, size=(800, 600))], ['a', 'b']),
                                 ([frame(1)], []), ([frame(1)]*7, ['x']*7)):
            with self.subTest(n=len(frames)), self.assertRaises(ValueError):
                raster_plan(frames, captions)


class PictureReplyTests(unittest.TestCase):
    def reply(self, picture):
        import copy
        from notebook_semantic_examples import examples
        spec = copy.deepcopy(examples()['lever'])
        spec['picture'] = picture
        return json.dumps(spec)

    def bundle(self, picture, frames):
        from notebook_lesson_native import prepare_semantic_reply
        return prepare_semantic_reply(self.reply(picture), Mock(), playback=True, pen_equations=True, hand='primer',
                                      picture=lambda p: frames)

    def test_a_picture_is_validated_and_a_bad_one_never_refuses_the_lesson(self):
        from notebook_semantic_reply import parse_semantic_reply
        good = parse_semantic_reply(self.reply({'base': 'a seesaw', 'edits': ['a robot', 'an arrow']}))
        self.assertEqual(good['picture']['edits'], ['a robot', 'an arrow'])
        for bad in ({'base': 'a seesaw', 'edits': ['a robot']}, {'base': 'a seesaw'}, 'a seesaw',
                    {'base': 'x', 'edits': ['a robot', 'an arrow']}, {'base': 'a\nb c', 'edits': ['abc', 'abc']}):
            with self.subTest(bad=bad):
                parsed = parse_semantic_reply(self.reply(bad))
                self.assertNotIn('picture', parsed)
                self.assertTrue(parsed['picture_refused'])

    def test_frames_replace_the_drawing_and_keep_every_caption(self):
        bundle = self.bundle({'base': 'ground', 'edits': ['sun', 'push']}, [frame(1), frame(2, 1), frame(3, 2)])
        self.assertTrue(bundle['picture']['used'])
        drawn = [b for b in bundle['blocks'] if b['kind'] == 'ink' and b.get('role') is None]
        self.assertEqual(len(drawn), 3)
        plain = self.bundle({'base': 'ground', 'edits': ['sun', 'push']}, [])
        hand = lambda b: [x['scene'] for x in b['blocks'] if x.get('role') == 'hand']
        self.assertEqual(hand(bundle), hand(plain), 'every caption is written as before')
        from notebook_lesson_native import lesson_source_archive, inspect_source_archive
        import uuid
        parent = str(uuid.uuid4())
        doc, data = lesson_source_archive(bundle, {'cPages': {}, 'fileType': 'notebook'}, parent)
        self.assertEqual(inspect_source_archive(data, doc, parent, drawn[1]['source_page'], drawn[1]['stroke_count']),
                         drawn[1]['sha256'])

    def test_an_edit_never_drawn_keeps_the_frames_before_it_and_every_caption(self):
        bundle = self.bundle({'base': 'ground', 'edits': ['sun', 'push']}, [frame(1), frame(2, 1)])
        self.assertTrue(bundle['picture']['used'])
        self.assertEqual(bundle['picture']['frames'], '2 of 3')
        drawn = [b for b in bundle['blocks'] if b['kind'] == 'ink' and b.get('role') is None]
        self.assertEqual(len(drawn), 2)
        plain = self.bundle({'base': 'ground', 'edits': ['sun', 'push']}, [])
        hand = lambda b: len([x for x in b['blocks'] if x.get('role') == 'hand'])
        self.assertEqual(hand(bundle), hand(plain)-1, 'the last two captions are written as one')

    def test_a_rich_first_frame_keeps_its_longest_lines_in_one_block(self):
        busy = Image.new('L', (1024, 768), 255)
        d = ImageDraw.Draw(busy)
        for i in range(150):
            x, y = 40+(i % 15)*64, 60+(i//15)*64
            d.arc([(x, y), (x+40, y+40)], 0, 270, fill=0, width=5)
        pngs = []
        for extra in (None, [(400, 700), (700, 700)], [(400, 740), (700, 740)]):
            if extra:
                ImageDraw.Draw(busy).line(extra, fill=0, width=6)
            f = io.BytesIO()
            busy.save(f, 'PNG')
            pngs.append(f.getvalue())
        bundle = self.bundle({'base': 'ground', 'edits': ['sun', 'push']}, pngs)
        self.assertTrue(bundle['picture']['used'])
        blocks = bundle['blocks']
        drawn = [i for i, b in enumerate(blocks) if b['kind'] == 'ink' and b.get('role') is None]
        self.assertEqual(len(drawn), 3, 'the 150 arcs keep their 48 longest lines, one block, then one per edit')
        self.assertEqual([blocks[i]['stage_index'] for i in drawn], [0, 1, 2])
        self.assertEqual(len({blocks[i]['scene'] for i in drawn}), 1)
        self.assertEqual(sum(b.get('role') == 'hand' for b in blocks[:drawn[0]]), 1, 'one caption for the first step')
        self.assertTrue(all(blocks[i]['playback']['velocity'] == 1800 for i in drawn))

    def test_pictures_of_their_own_go_below_their_captions_and_a_step_without_one_follows_the_one_above(self):
        from notebook_semantic_reply import parse_semantic_reply
        picture = {'base': 'ground', 'edits': ['', 'a robot pushes']}
        self.assertEqual(parse_semantic_reply(self.reply(picture))['picture'], picture)
        class Frames(list):
            scenes, steps, labels = True, [0, 2], None
        bundle = self.bundle(picture, Frames([frame(1), frame(3)]))
        self.assertTrue(bundle['picture']['used'], bundle['picture'])
        self.assertEqual(bundle['picture']['pictures'], '2 for 3 steps')
        blocks = [b for b in bundle['blocks'] if b['kind'] == 'ink' and b.get('role') != 'equation']
        scenes = list(dict.fromkeys(b['scene'] for b in blocks if b.get('role') is None))
        self.assertEqual(len(scenes), 2)
        for scene in scenes:
            drawn = [b for b in blocks if b['scene'] == scene]
            self.assertEqual([b['stage_index'] for b in drawn], list(range(len(drawn))))
            self.assertTrue(all(b['stage_count'] == len(drawn) for b in drawn))
        where = [scenes.index(b['scene']) if b.get('role') is None else 'hand' for b in blocks]
        first, second = where.index(0), where.index(1)
        self.assertEqual(set(where[:first]), {'hand'}, 'the first caption, then its picture')
        between = where[first:second]
        self.assertGreaterEqual(between.count('hand'), 2, 'the second and third captions, then the second picture')
        self.assertEqual(between[-1], 'hand')

    def test_a_picture_of_its_own_is_drawn_whole_in_a_scene_of_its_own(self):
        from notebook_raster_ink import raster_plan
        width = lambda st: (max(x for p in st['paths'] for x, _ in p)-min(x for p in st['paths'] for x, _ in p))
        grown, _ = raster_plan([frame(1), frame(2)], ['a ball', 'a sun'])
        whole, report = raster_plan([frame(1), frame(2)], ['a ball', 'a sun'], scenes=True)
        self.assertLess(width(grown['stages'][-1]), 300, 'growing: only the sun is added')
        self.assertGreater(width(whole['stages'][-1]), 600, 'its own: the ground again, with the sun')
        self.assertNotIn('scene', grown['stages'][0])
        self.assertEqual(len({st['scene'] for st in whole['stages']}), 2)
        self.assertTrue(all(st['scene'].startswith('lesson-') for st in whole['stages']))
        self.assertEqual([r['removed'] for r in report], [0, 0])

    def test_a_composite_draws_the_story_picture_with_its_own_captions_above_the_figure(self):
        from notebook_semantic_reply import parse_semantic_reply
        story = {'base': 'ground', 'edits': ['sun'], 'captions': ['... there was a robot named Nix.', 'Nix saw the sun.']}
        self.assertEqual(parse_semantic_reply(self.reply(story))['picture'], story)
        for bad in (dict(story, captions=['one']), dict(story, captions=['a b c']*4, edits=['sun']*3),
                    dict(story, captions='one'), dict(story, extra=1)):
            with self.subTest(bad=bad):
                self.assertTrue(parse_semantic_reply(self.reply(bad))['picture_refused'])
        bundle = self.bundle(story, [frame(1), frame(2, 1)])
        self.assertEqual(bundle['picture'].get('composite'), True, bundle['picture'])
        plain = self.bundle({'base': 'ground', 'edits': ['sun', 'push']}, [])
        ink = lambda b: [x for x in b['blocks'] if x['kind'] == 'ink' and x.get('role') is None]
        self.assertEqual(len(ink(bundle)), len(ink(plain))+2, 'the story picture, then the whole figure')
        self.assertEqual([x['scene'] for x in ink(bundle)[2:]], [x['scene'] for x in ink(plain)])
        self.assertNotEqual(ink(bundle)[0]['scene'], ink(plain)[0]['scene'])
        hand = lambda b: [x for x in b['blocks'] if x.get('role') == 'hand']
        self.assertEqual(len(hand(bundle)), len(hand(plain))+2, 'each story caption is written with its frame')
        order = [x.get('role') or 'ink' for x in bundle['blocks'] if x['kind'] == 'ink']
        self.assertEqual(order[:4], ['hand', 'ink', 'hand', 'ink'])
        # Frames past what the figure leaves are folded: the finished picture is kept, the captions joined.
        from unittest.mock import patch as mock_patch
        import notebook_raster_ink
        with mock_patch.object(notebook_raster_ink, 'BLOCKS', len(ink(plain))+1):
            three = dict(story, edits=['sun', 'push'], captions=story['captions']+['And it rolled.'])
            folded = self.bundle(three, [frame(1), frame(2, 1), frame(3, 2)])
        self.assertTrue(folded['picture'].get('composite'), folded['picture'])
        self.assertEqual(len(ink(folded)), len(ink(plain))+1)

    def test_any_picture_failure_falls_back_to_the_procedural_drawing(self):
        def missing(p): raise LookupError('frame not rendered')
        from notebook_lesson_native import prepare_semantic_reply
        cases = {'missing': None, 'count': [frame(1), frame(2), frame(3), frame(3, 4)]}
        for name, frames in cases.items():
            with self.subTest(name=name):
                bundle = prepare_semantic_reply(self.reply({'base': 'ground', 'edits': ['sun', 'push']}), Mock(),
                                                playback=True, pen_equations=True, hand='primer',
                                                picture=missing if frames is None else (lambda p, f=frames: f))
                self.assertFalse(bundle['picture']['used'])
                self.assertIn({'missing': 'not rendered', 'count': '4 frames'}[name], bundle['picture']['reason'])
                self.assertTrue(any(b['kind'] == 'ink' and b.get('role') is None for b in bundle['blocks']))

    def test_an_edit_that_redraws_the_picture_keeps_the_frames_before_it(self):
        from notebook_lesson_native import prepare_semantic_reply
        bundle = prepare_semantic_reply(self.reply({'base': 'ground', 'edits': ['sun', 'push']}), Mock(),
                                        playback=True, pen_equations=True, hand='primer',
                                        picture=lambda p: [frame(1), frame(1, 40), frame(1, 80)])
        self.assertTrue(bundle['picture']['used'], bundle['picture'])
        self.assertEqual((bundle['picture']['redrawn'], bundle['picture']['frames']), (1, '1 of 3'))


    def test_labels_are_lettered_in_clear_space_with_a_pointer_and_one_name_per_thing(self):
        ground, sun = [770, 59, 792, 937], [117, 742, 273, 859]
        captions = ['Ground and ball.', 'The sun.']
        plan, report = raster_plan([frame(1), frame(2, 1)], captions,
                                   labels=[[('ground', ground), ('floor', ground)], [('sun', sun)]])
        self.assertEqual([(r['labels'], r['lettered']) for r in report], [(1, 1), (1, 1)],
                         'two names located on the same thing keep only the first')
        self.assertEqual([r['kept'] for r in report], [2, 1], 'labels are not counted as picture lines')
        bare, _ = raster_plan([frame(1), frame(2, 1)], captions)
        added = [len(a['paths'])-len(b['paths']) for a, b in zip(plan['stages'], bare['stages'])]
        self.assertTrue(all(n >= len('ground') for n in added[:1]) and added[1] >= len('sun'))
        self.assertEqual(len(plan['stages']), len(bare['stages']), 'labels ride in the frame\'s own block')

    def test_a_closed_loop_keeps_its_shape_when_thinned(self):
        from notebook_storyboard import sparse
        loop = sparse([[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]])[0]
        self.assertIn((10.0, 10.0), loop, 'a letter o or a wheel is not a dot')


class ImageModelTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        key = os.path.join(self.dir, 'key')
        with open(key, 'w') as f:
            f.write('test-key\n')
        self.patches = [patch.object(model, 'GEMINI', self.dir), patch.object(model, 'KEYF', key),
                        patch.object(model, 'CACHE', os.path.join(self.dir, 'frames')),
                        patch.object(model, 'KEPT', os.path.join(self.dir, 'frames', 'kept'))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def reply(self, png):
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        body = {'candidates': [{'content': {'parts': [{'inlineData': {'mimeType': 'image/png',
                                                                       'data': base64.b64encode(png).decode()}}]}}],
                'usageMetadata': {'promptTokenCount': 9, 'candidatesTokenCount': 1300}}
        return R(json.dumps(body).encode())

    def test_a_replay_draws_the_frames_its_reply_drew_though_the_style_changed(self):
        base, edit = frame(1), frame(2)
        model.keep('notebook-old', [base, edit])
        with patch.object(model, 'STYLE', 'a newer style'), patch.object(model, '_post') as post:
            self.assertRaises(LookupError, model.frame, 'a lever', cached=True)
            self.assertEqual(model.replayed('notebook-old', 'a lever', ['a push']), 2)
            self.assertEqual(model.frames('a lever', ['a push'], cached=True), [base, edit])
            self.assertEqual(model.frames('a lever', ['a push']), [base, edit])
        post.assert_not_called()
        self.assertEqual(model.replayed('notebook-never-kept', 'a lever', []), 0)
        self.assertIsNone(model.kept_picture('notebook-old'))
        drawn = {'base': 'a lever', 'edits': ['a push'], 'labels': [['rock'], ['push']]}
        model.keep('notebook-directed', [base, edit], drawn)
        self.assertEqual(model.kept_picture('notebook-directed'), drawn)

    def test_only_the_newest_requests_keep_their_frames(self):
        with patch.object(model, 'KEEP', 2):
            for n, t in (('a', 1), ('b', 2), ('c', 3)):
                model.keep(n, [frame(1)])
                os.utime(os.path.join(model.KEPT, n), (t, t))
            model.keep('d', [frame(1)])
        self.assertEqual(sorted(os.listdir(model.KEPT)), ['c', 'd'])

    def test_a_story_is_written_from_the_page_and_never_repeats_the_opening(self):
        def answer(tale):
            return {'candidates': [{'content': {'parts': [{'text': json.dumps(tale)}]}}]}
        beat = {'caption': '... a mouse pushed.', 'see': 'a log'}
        tale = {'intent': 'Levers', 'takeaway': 'A lever trades distance for force. Could you lift a bear?',
                'steps': [{'caption': 'James, once upon a time... a mouse wanted an apple.', 'see': 'an apple'}] + [beat]*3}
        with patch.object(model, 'WRITER', 'gemini-3.8-flash'), patch.object(model, '_post', return_value=answer(tale)) as post:
            told = model.story(b'png', None, '', opening='James, once upon a time...')
        self.assertEqual(told['steps'][0]['caption'], '... a mouse wanted an apple.')
        parts = json.loads(post.call_args.args[1])['contents'][0]['parts']
        self.assertEqual(base64.b64decode(parts[0]['inline_data']['data']), b'png')
        self.assertIn('handwriting in the image', parts[1]['text'])
        with patch.object(model, 'WRITER', 'gemini-3.8-flash'), patch.object(model, '_post', return_value=answer({'steps': []})):
            self.assertIsNone(model.story(b'png', 'Send Neil a note'))
        with patch.object(model, 'WRITER', 'gemini-3.8-flash'), patch.object(model, '_post', return_value=answer(dict(tale, steps=[beat]))):
            with self.assertRaises(ValueError):
                model.story(b'png', 'How do levers work?')

    def test_a_claude_writer_gets_the_prompt_as_its_system_and_the_page_only_when_the_question_is_unknown(self):
        beat = {'caption': '... a raven slid down a roof.', 'see': 'a roof'}
        tale = {'intent': 'Ravens', 'takeaway': 'A raven is a clever bird. What would you teach one?', 'steps': [beat]*3}
        def run(cmd, input, **kw):
            run.cmd, run.message = cmd, json.loads(input)
            return SimpleNamespace(stdout='{"type":"system"}\n'+json.dumps(
                {'type': 'result', 'is_error': False, 'result': 'Here it is: '+json.dumps(tale)})+'\n', stderr='')
        with patch.object(model, 'WRITER', 'claude-opus-5-5'), patch.object(model.subprocess, 'run', run), \
                patch.object(model, '_post') as post, patch.object(model, '_held', return_value=True):
            self.assertEqual(model.story(b'png', None, '')['steps'][0]['caption'], '... a raven slid down a roof.')
            content = run.message['message']['content']
            self.assertEqual(base64.b64decode(content[0]['source']['data']), b'png')
            self.assertIn('handwriting in the image', content[1]['text'])
            self.assertIn('claude-opus-5-5', run.cmd)
            self.assertIn('once upon a time', run.cmd[run.cmd.index('--system-prompt')+1])
            model.story(b'png', 'What is a raven?', 'Ravens play.')
            self.assertEqual([c['type'] for c in run.message['message']['content']], ['text'])
            self.assertIn('FACTS: Ravens play.', run.message['message']['content'][0]['text'])
            post.assert_not_called()

    def test_frames_edit_the_frame_before_are_cached_and_logged(self):
        sent = []
        def urlopen(req, timeout):
            sent.append(json.loads(req.data))
            return self.reply(frame(len(sent)))
        with patch('urllib.request.urlopen', urlopen):
            with self.assertRaises(LookupError):
                model.frames('a ball', ['a sun'], cached=True)
            first = model.frames('a ball', ['a sun', 'an arrow'])
            again = model.frames('a ball', ['a sun', 'an arrow'])
        self.assertEqual(first, again)
        self.assertEqual(len(sent), 3, 'the replay came from the cache')
        self.assertEqual(len(sent[0]['contents'][0]['parts']), 1)
        edit = sent[2]['contents'][0]['parts']
        self.assertEqual(base64.b64decode(edit[1]['inline_data']['data']), first[1])
        self.assertIn('an arrow', edit[0]['text'])
        self.assertEqual(sent[0]['generationConfig']['responseModalities'], ['IMAGE'])
        with open(os.path.join(self.dir, 'calls.log')) as f:
            log = f.read().splitlines()
        self.assertEqual(len(log), 3)
        self.assertTrue(all(' herd-board-image ' in line and ' 200 ' in line for line in log))
        self.assertNotIn('test-key', ''.join(log))

    def test_pictures_of_their_own_take_the_frame_before_as_the_model_sheet_and_skip_empty_edits(self):
        sent = []
        def urlopen(req, timeout):
            sent.append(json.loads(req.data))
            return self.reply(frame(len(sent)))
        with patch('urllib.request.urlopen', urlopen):
            drawn = model.frames('a ball', ['', 'a sun'], scenes=True)
            self.assertEqual(model.frames('a ball', ['', 'a sun'], scenes=True, cached=True), drawn)
            self.assertRaises(LookupError, model.frames, 'a ball', ['', 'a sun'], cached=True)
        self.assertEqual(len(drawn), 2)
        self.assertEqual(model.drawn_steps(['', 'a sun'], len(drawn)), [0, 2])
        self.assertEqual(model.drawn_steps(['a moon', 'a sun'], 2), [0, 1], 'a picture that ended early')
        self.assertNotIn('strip of panels', sent[0]['contents'][0]['parts'][0]['text'])
        scene = sent[1]['contents'][0]['parts']
        self.assertIn('Draw a new picture', scene[0]['text'])
        self.assertEqual(base64.b64decode(scene[1]['inline_data']['data']), drawn[0])

    def test_an_empty_image_is_asked_for_again_and_its_reason_kept(self):
        sent = []
        def urlopen(req, timeout):
            sent.append(1)
            if len(sent) == 1:
                return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': []}}]}).encode())
            return self.reply(frame(1))
        with patch('urllib.request.urlopen', urlopen):
            self.assertEqual(model.frame('a ball'), frame(1))
        self.assertEqual(len(sent), 2)
        tries = []
        def empty(req, timeout):
            tries.append(1)
            return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'OTHER'}]}).encode())
        with patch('urllib.request.urlopen', empty), self.assertRaisesRegex(ValueError, r'reason: OTHER'):
            model.frame('a kite')
        self.assertEqual(len(tries), model.EMPTY_TRIES)
        def edit_empty(req, timeout):
            if len(json.loads(req.data)['contents'][0]['parts']) > 1:
                return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'OTHER'}]}).encode())
            return self.reply(frame(1))
        with patch('urllib.request.urlopen', edit_empty):
            self.assertEqual(model.frames('a ball', ['a sun', 'an arrow']), [frame(1)], 'the base is kept')
            self.assertEqual(model.frames('a ball', ['a sun'], cached=True), [frame(1)])

    def text(self, value):
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R(json.dumps({'candidates': [{'content': {'parts': [{'text': value}]}}]}).encode())

    def test_a_missing_picture_is_directed_from_the_captions_and_current_facts_are_searched(self):
        sent = []
        def urlopen(req, timeout):
            sent.append(json.loads(req.data))
            return self.text(json.dumps({'base': 'a robot on a line', 'edits': ['a star above it']}))
        with patch('urllib.request.urlopen', urlopen):
            picture = model.direct('\n\nPicture: draw it.', 'zeros', ['... a robot.', 'A star.'], 'Stars guide.')
        self.assertEqual(picture, {'base': 'a robot on a line', 'edits': ['a star above it']})
        asked = sent[0]['contents'][0]['parts'][0]['text']
        self.assertIn('2. A star.', asked)
        self.assertIn('exactly 1 edits', asked)
        self.assertEqual(sent[0]['generationConfig']['responseMimeType'], 'application/json')
        answers = iter(['In **October 2026** a proof ruled out zeros past 7/8.', 'NONE'])
        def search(req, timeout):
            sent.append(json.loads(req.data))
            return self.text(next(answers))
        with patch('urllib.request.urlopen', search):
            self.assertEqual(model.facts('The latest on the Riemann hypothesis?'),
                             'In October 2026 a proof ruled out zeros past 7/8.')
            self.assertEqual(model.facts('What is a raven?'), '', 'nothing recent matters')
        self.assertEqual(sent[1]['tools'], [{'google_search': {}}])
        with open(os.path.join(self.dir, 'calls.log')) as f:
            log = f.read()
        self.assertIn(' herd-board-director ', log)
        self.assertEqual(log.count(' herd-board-facts '), 2)
        self.assertNotIn('test-key', log)

    def test_labels_are_located_cached_and_bad_boxes_left_out(self):
        sent = []
        boxes = [{'label': 'sun', 'box_2d': [100, 700, 300, 900]}, {'label': 'moon', 'box_2d': [1, 2, 3, 4]},
                 {'label': 'ball', 'box_2d': [500, 400, 400, 600]}]
        def urlopen(req, timeout):
            sent.append(json.loads(req.data))
            return self.text(json.dumps(boxes))
        png = frame(2)
        with patch('urllib.request.urlopen', urlopen):
            with self.assertRaises(LookupError):
                model.locate(png, ['sun', 'ball'], cached=True)
            self.assertEqual(model.locate(png, ['sun', 'ball']), {'sun': [100.0, 700.0, 300.0, 900.0]})
            self.assertEqual(model.locate(png, ['ball', 'sun'], cached=True), {'sun': [100.0, 700.0, 300.0, 900.0]})
        self.assertEqual(len(sent), 1)
        with open(os.path.join(self.dir, 'calls.log')) as f:
            self.assertIn(model.LOCATOR, f.read())

    def test_an_edit_that_redraws_the_picture_is_asked_for_once_more(self):
        drawn = iter([frame(1), frame(1, 40), frame(2)])
        seeds = []
        def urlopen(req, timeout):
            seeds.append(json.loads(req.data)['generationConfig'].get('seed'))
            return self.reply(next(drawn))
        with patch('urllib.request.urlopen', urlopen):
            out = model.frames('a ball', ['a sun'])
        self.assertEqual(out[1], frame(2), 'the cleaner edit is kept')
        self.assertEqual(len(seeds), 3)
        self.assertNotEqual(seeds[1], seeds[2])

    def test_a_picture_never_asks_for_dashed_or_dotted_lines(self):
        from notebook_semantic_reply import _picture
        kept = _picture({'base': 'A robot beside a Dotted path', 'edits': ['A curved dashed motion arrow over the plank']}, 2)
        self.assertEqual(kept, {'base': 'A robot beside a path', 'edits': ['A curved motion arrow over the plank']})

    def test_picture_labels_keep_three_letterable_words_per_frame_and_never_cost_the_picture(self):
        from notebook_semantic_reply import _picture
        picture = {'base': 'a lever', 'edits': ['a push arrow']}
        kept = _picture(dict(picture, labels=[['fulcrum', 'load', 'plank', 'robot'], ['push', '', 7]]), 2)
        self.assertEqual(kept['labels'], [['fulcrum', 'load', 'plank'], ['push']])
        self.assertEqual(_picture(dict(picture, labels=[['fulcrum']]), 2), picture, 'one list per frame, or none')
        self.assertEqual(_picture(dict(picture, labels=[[], []]), 2), picture)

    def test_a_frame_drawn_by_the_fallback_is_drawn_again_once_the_primary_is_back(self):
        hold = os.path.join(self.dir, 'hold-until-image')
        with open(hold, 'w') as f:
            f.write(str(time.time()+60))
        asked = []
        def urlopen(req, timeout):
            asked.append(req.full_url)
            return self.reply(frame(1, 40 if model.FALLBACK in req.full_url else 0))
        with patch('urllib.request.urlopen', urlopen):
            self.assertEqual(model.frame('a ball'), frame(1, 40))
            self.assertEqual(model.frame('a ball'), frame(1, 40), 'reused while the primary is held')
            os.remove(hold)
            self.assertEqual(model.frame('a ball', cached=True), frame(1, 40), 'the tablet reads back what was rendered')
            self.assertEqual(model.frame('a ball'), frame(1), 'the primary draws it again')
            self.assertEqual(model.frame('a ball', cached=True), frame(1))
        self.assertEqual([model.FALLBACK in u for u in asked], [True, False])

    def test_a_rate_limit_holds_images_only_and_any_hold_is_respected(self):
        import urllib.error
        def limited(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 429, 'limit', {}, io.BytesIO(json.dumps(
                {'error': {'details': [{'retryDelay': '30s'}]}}).encode()))
        with patch('urllib.request.urlopen', limited), self.assertRaises(urllib.error.HTTPError):
            model.frame('a ball')
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'hold-until-image')))
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'hold-until')), 'text callers keep going')
        asked = []
        def fallback(req, timeout):
            asked.append(req.full_url)
            return limited(req, timeout)
        with patch('urllib.request.urlopen', fallback), self.assertRaises(urllib.error.HTTPError):
            model.frame('a ball')
        self.assertIn(model.FALLBACK, asked[0], 'the held model hands pictures to the fallback')
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'hold-until-image-fallback')))
        with patch('urllib.request.urlopen', side_effect=AssertionError('no call while held')), \
                self.assertRaises(RuntimeError):
            model.frame('a ball')


if __name__ == '__main__':
    unittest.main()
