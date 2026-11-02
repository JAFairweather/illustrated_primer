import importlib.machinery
import importlib.util
import json
import io
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw

from notebook_replies import ReplyReader, request_answer, notebook_prompt
from notebook_media import AssetStore


def user(text, **kw):
    return dict(type="message", message={"role": "user", "content": text}, **kw)


def assistant(text, **kw):
    return dict(type="message", message={"role": "assistant", "content": [{"type": "text", "text": text}],
                                         "stopReason": "stop", **kw})


class RepliesTest(unittest.TestCase):
    def test_author_preview_is_explicit_bounded_and_not_part_of_the_final_drawing_language(self):
        tool = dict(command="'/local/tools with spaces/python' '/local/checker.py' check",
                    directory='/local/scratch/notebook-test')
        prompt = notebook_prompt('Explain torque', '/page.png', 'notebook-test', ink_enabled=True,
                                 draft_check=tool)
        self.assertIn(tool['command']+' RAW_REPLY_FILE NEW_PREVIEW_DIRECTORY',prompt)
        self.assertIn(tool['directory'],prompt)
        self.assertIn('at most TWO checks',prompt)
        self.assertIn('inspect every cumulative PNG',prompt)
        self.assertIn('does not send, replace, or insert',prompt)
        self.assertIn('final response, not the preview files or tool output',prompt)
        self.assertIn('Compiler acceptance is not a correctness verdict',prompt)
        self.assertIn('If the tool is unavailable or neither draft validates',prompt)
        self.assertIn('skip for short direct answers',prompt)
        self.assertNotIn('Local author preview',notebook_prompt('Explain torque','','test',ink_enabled=True))
        for invalid in (True, {}, {'command':'check'}, dict(tool,directory='relative'),
                        dict(tool,command='check\nother command')):
            with self.assertRaises(ValueError):
                notebook_prompt('Explain','','test',ink_enabled=True,draft_check=invalid)
        with self.assertRaises(ValueError):
            notebook_prompt('Explain','','test',draft_check=tool)

    def test_image_primary_requires_actual_image_inspection_not_example_inference(self):
        prompt = notebook_prompt('', '/local/question.png', 'notebook-test', ink_enabled=True, image_primary=True)
        self.assertTrue(prompt.startswith('(Read the handwritten question from the page image.)'))
        self.assertIn('PRIMARY input, not optional context', prompt)
        self.assertIn('No transcription was made', prompt)
        self.assertIn('Use your image-viewing tool', prompt)
        self.assertIn('If you cannot open it, state that limitation', prompt)
        self.assertIn('do not infer a question', prompt)
        self.assertNotIn('(a drawing, no words)', prompt)
        for text, image, primary in (('guessed text', '/page.png', True), ('', '', True), ('', '/page.png', 1)):
            with self.assertRaises(ValueError):
                notebook_prompt(text, image, 'notebook-test', image_primary=primary)

    def test_prepared_attachment_guidance_is_request_scoped_and_not_visual_evidence(self):
        ordinary = notebook_prompt('Add the photo', '/optional/page.png', 'notebook-test')
        self.assertNotIn('adapter already has a verified prepared attachment', ordinary)
        prepared = notebook_prompt('Add the photo', '/optional/page.png', 'notebook-test',
                                   prepared_attachment=True)
        self.assertIn('For THIS request only', prepared)
        self.assertIn('will insert it automatically', prepared)
        self.assertIn('do not claim to have inspected, generated or photographed it', prepared)
        self.assertIn('Attachment availability is not visual evidence', prepared)
        self.assertIn('do not emit an asset or media-pending marker', prepared)
        for invalid in (1, 'yes', None, []):
            with self.assertRaises(ValueError):
                notebook_prompt('Add the photo', '', 'notebook-test', prepared_attachment=invalid)

    def test_lesson_guidance_is_capability_gated_and_has_two_compilable_examples(self):
        ordinary = notebook_prompt('Explain this integral', '/optional/page.png', 'notebook-test')
        self.assertNotIn('[[notebook-ink:', ordinary)
        self.assertIn('has not yet enabled board-step lessons', ordinary)
        diagnostic = notebook_prompt('Explain this integral', '/optional/page.png', 'notebook-test', ink_enabled=True)
        self.assertNotIn('[[notebook-ink:', diagnostic)
        self.assertIn('3–6 steps that build ONE picture', diagnostic)
        self.assertIn('Plan the FINAL picture before step 1', diagnostic)
        self.assertIn('sketch recognizable objects and actions', diagnostic)
        self.assertIn('the drawing must do some of the teaching itself', diagnostic)
        self.assertIn('keep the same scale and align equal quantities', diagnostic)
        self.assertIn('Do not turn every answer into a chart', diagnostic)
        self.assertIn('Trace each arrow: what does it represent', diagnostic)
        self.assertIn('Distinguish explanatory connectors from physical paths or forces', diagnostic)
        self.assertIn('add missing evidence or narrow the claim', diagnostic)
        self.assertIn('[x+0.9*s*n,b+s/3]', diagnostic)
        self.assertIn('LEFT baseline, not its center', diagnostic)
        from notebook_lesson_examples import EXAMPLES
        from notebook_lesson import parse_lesson
        for factory in EXAMPLES.values():
            example = factory()
            self.assertIn(example, diagnostic)
            self.assertGreaterEqual(len(parse_lesson(example)['stages']), 3)
        self.assertIn('editable native text', diagnostic)

    def test_discovery_walk_is_shared_and_negative_reads_are_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'session.jsonl'
            file.write_text(json.dumps(user('other-request')) + '\n')
            reader = ReplyReader([directory])
            with patch('notebook_replies.time.monotonic', return_value=100):
                self.assertIsNone(reader.answer('notebook-new', time.time()))
            with patch('notebook_replies.time.monotonic', return_value=101), \
                 patch('notebook_replies.os.walk', side_effect=AssertionError('repeat tree walk')), \
                 patch('notebook_replies.read_events', side_effect=AssertionError('repeat negative parse')):
                self.assertIsNone(reader.answer('notebook-new', time.time()))
                self.assertEqual(reader.inventory()[0]['files'], 1)
            with patch('notebook_replies.time.monotonic', return_value=101), \
                 patch('notebook_replies.os.walk', side_effect=AssertionError('index must be shared across markers')):
                self.assertIsNone(reader.answer('different-marker', time.time()))
            # Even a previously unrelated existing file can start this request.
            with file.open('a') as stream:
                stream.write(json.dumps(user('notebook-new')) + '\n' + json.dumps(assistant('Found it')) + '\n')
            with patch('notebook_replies.time.monotonic', return_value=102), \
                 patch('notebook_replies.os.walk', side_effect=AssertionError('matched append needs no walk')):
                self.assertEqual(reader.answer('notebook-new', time.time()), 'Found it')

    def test_new_harness_and_transcript_appear_after_reader_construction(self):
        with tempfile.TemporaryDirectory() as directory, patch('notebook_replies.os.path.expanduser', return_value=directory):
            reader = ReplyReader()
            with patch('notebook_replies.time.monotonic', return_value=100):
                self.assertIsNone(reader.answer('notebook-late', time.time()))
            root = Path(directory) / '.nvoy-harness/new-agent/codex/sessions'
            root.mkdir(parents=True)
            (root / 'late.jsonl').write_text(json.dumps(user('notebook-late')) + '\n' + json.dumps(assistant('Late harness answer')) + '\n')
            with patch('notebook_replies.time.monotonic', return_value=106):
                self.assertEqual(reader.answer('notebook-late', time.time()), 'Late harness answer')
            self.assertIn(str(root), reader.roots)

    def test_index_does_not_follow_directory_or_replaced_file_symlinks(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / 'private.jsonl'
            external.write_text(json.dumps(user('notebook-link')) + '\n' + json.dumps(assistant('Outside')) + '\n')
            (Path(directory) / 'linked-dir').symlink_to(outside, target_is_directory=True)
            file = Path(directory) / 'session.jsonl'
            file.write_text(json.dumps(user('notebook-link')) + '\n')
            reader = ReplyReader([directory])
            with patch('notebook_replies.time.monotonic', return_value=100):
                self.assertIsNone(reader.answer('notebook-link', time.time()))
            file.unlink()
            file.symlink_to(external)
            with patch('notebook_replies.time.monotonic', return_value=101), \
                 patch('notebook_replies.read_events', side_effect=AssertionError('read outside transcript root')):
                self.assertIsNone(reader.answer('notebook-link', time.time()))
            self.assertNotIn('notebook-link', reader.sources)

    def test_each_format_interim_tool_final_through_reply_reader(self):
        formats = {
            'pi': [user('notebook-stream'), assistant('Working on it.', stopReason=None),
                   assistant('Checking', stopReason='toolUse'), assistant('Final answer')],
            'openclaw': [user('notebook-stream'), assistant('Working on it.', stopReason=None),
                        assistant('Checking', stopReason='toolUse'), assistant('Final answer')],
            'claude': [dict(type='user', message={'content':'notebook-stream'}),
                       dict(type='assistant', message={'content':'Working on it.', 'stop_reason':None}),
                       dict(type='assistant', message={'content':[{'type':'tool_use', 'name':'Read'}], 'stop_reason':'tool_use'}),
                       dict(type='assistant', message={'content':'Final answer', 'stop_reason':'end_turn'})],
            'codex': [dict(type='response_item', payload={'type':'message', 'role':'user', 'content':'notebook-stream'}),
                      dict(type='response_item', payload={'type':'message', 'role':'assistant', 'channel':'commentary', 'content':'Working on it.'}),
                      dict(type='response_item', payload={'type':'function_call', 'name':'read'}),
                      dict(type='event_msg', payload={'type':'task_complete', 'last_agent_message':'Final answer'})]
        }
        for name, rows in formats.items():
            with self.subTest(format=name), tempfile.TemporaryDirectory() as directory:
                file = Path(directory) / 'session.jsonl'
                reader = ReplyReader([directory])
                for index, row in enumerate(rows):
                    with file.open('a') as stream:
                        stream.write(json.dumps(row) + '\n')
                    self.assertEqual(reader.answer('notebook-stream', time.time()),
                                     'Final answer' if index == len(rows)-1 else None)

    def test_partial_transcript_append_waits_for_completed_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'session.jsonl'
            file.write_text(json.dumps(user('notebook-stream')) + '\n' +
                            json.dumps(assistant('Let me check', stopReason=None)) + '\n')
            reader = ReplyReader([directory])
            self.assertIsNone(reader.answer('notebook-stream', time.time()))
            with file.open('a') as stream:
                stream.write(json.dumps(assistant('The completed answer', stopReason='stop')) + '\n')
            self.assertEqual(reader.answer('notebook-stream', time.time()), 'The completed answer')

    def test_incomplete_and_truncated_text_is_not_a_final_reply(self):
        for finish in (None, 'length', 'max_tokens', 'toolUse', 'error', 'aborted'):
            rows = [user('notebook-test'), assistant('Still checking', stopReason=finish)]
            self.assertEqual(request_answer(rows, 'notebook-test'), (True, None))
            rows.append(assistant('Finished', stopReason='stop'))
            self.assertEqual(request_answer(rows, 'notebook-test'), (True, 'Finished'))

    def test_claude_stream_requires_end_turn_or_successful_terminal_result(self):
        rows = [dict(type='user', message={'content': 'notebook-test'}),
                dict(type='assistant', message={'content': 'Partial', 'stop_reason': None})]
        self.assertEqual(request_answer(rows, 'notebook-test'), (True, None))
        failed = rows + [dict(type='result', subtype='error_during_execution', is_error=True)]
        self.assertEqual(request_answer(failed, 'notebook-test'), (True, None))
        success = rows + [dict(type='result', subtype='success', is_error=False, result='Complete')]
        self.assertEqual(request_answer(success, 'notebook-test'), (True, 'Complete'))
        rows.append(dict(type='assistant', message={'content':'Final', 'stop_reason':'end_turn'}))
        self.assertEqual(request_answer(rows, 'notebook-test'), (True, 'Final'))

    def test_codex_unknown_channel_is_held_until_task_complete(self):
        rows = [dict(type='response_item', payload={'type':'message', 'role':'user', 'content':'notebook-test'}),
                dict(type='response_item', payload={'type':'message', 'role':'assistant', 'content':'Interim'})]
        self.assertEqual(request_answer(rows, 'notebook-test'), (True, None))
        rows.append(dict(type='event_msg', payload={'type':'task_complete', 'last_agent_message':'Done'}))
        self.assertEqual(request_answer(rows, 'notebook-test'), (True, 'Done'))

    def test_notebook_composition_is_native_and_capability_honest(self):
        prompt = notebook_prompt('Visually explain this proof', '/optional/page.png', 'notebook-test')
        self.assertTrue(prompt.startswith('Visually explain this proof\n'))
        for contract in ('notebook request: notebook-test', 'editable native text',
                         'Never rasterize an explanation',
                         'has not yet enabled board-step lessons',
                         'explicitly requested standalone', 'key numbers or words',
                         'fallible, not ground truth', 'unlabeled curve',
                         'identify the likely subject from actual visual evidence',
                         'if none is available, say so',
                         'quote the uncertainty', 'accept an explicit correction',
                         '[[notebook-media-pending]]'):
            self.assertIn(contract, prompt)
        self.assertTrue(notebook_prompt('', '/optional/page.png', 'notebook-test')
                        .startswith('(a drawing, no words)\n'))

    def test_pi_and_openclaw_final_answer(self):
        rows = [user("note notebook-test"), assistant("Using a tool", stopReason="toolUse"),
                {"type": "message", "message": {"role": "toolResult", "content": "private tool output"}},
                assistant("The answer", stopReason="stop")]
        self.assertEqual(request_answer(rows, "notebook-test"), (True, "The answer"))
        self.assertEqual(request_answer(rows, "unrelated"), (False, None))

    def test_codex_commentary_is_not_answer(self):
        rows = [dict(type="response_item", payload={"type": "message", "role": "user",
                                                   "content": [{"type": "input_text", "text": "notebook-test"}]}),
                dict(type="response_item", payload={"type": "message", "role": "assistant",
                                                    "channel": "commentary", "content": "Working"})]
        self.assertEqual(request_answer(rows, "notebook-test"), (True, None))
        rows.append(dict(type="response_item", payload={"type": "message", "role": "assistant",
                                                       "channel": "final", "content": "Done"}))
        self.assertEqual(request_answer(rows, "notebook-test"), (True, "Done"))

    def test_other_turn_does_not_answer_this_request(self):
        rows = [user("notebook-test"), user("A different question"), assistant("Wrong answer")]
        self.assertEqual(request_answer(rows, "notebook-test"), (True, None))

    def test_discovery_and_branch_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "session.jsonl"
            rows = [user("notebook-test", id="q", parentId=None),
                    dict(assistant("Old abandoned branch"), id="old", parentId="q"),
                    dict(assistant("Current answer"), id="new", parentId="q")]
            file.write_text("\n".join(map(json.dumps, rows)))
            reader = ReplyReader([directory])
            self.assertEqual(reader.answer("notebook-test", time.time()), "Current answer")
            self.assertEqual(reader.answer("different-request", time.time()), None)

    def test_claude_tool_text_is_not_final(self):
        rows = [dict(type="user", message={"content": "notebook-test"}),
                dict(type="assistant", message={"content": [{"type": "text", "text": "Checking"},
                    {"type": "tool_use", "name": "Read"}]})]
        self.assertEqual(request_answer(rows, "notebook-test"), (True, None))

    def test_unchanged_source_is_not_reparsed_but_new_reply_is(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "session.jsonl"
            file.write_text(json.dumps(user("notebook-cache")) + "\n")
            reader = ReplyReader([directory])
            self.assertIsNone(reader.answer("notebook-cache", time.time()))
            with patch("notebook_replies.read_events", side_effect=AssertionError("unchanged file reread")):
                self.assertIsNone(reader.answer("notebook-cache", time.time()))
            with file.open("a") as stream:
                stream.write(json.dumps(assistant("Done")) + "\n")
            self.assertEqual(reader.answer("notebook-cache", time.time()), "Done")


class CallbackTest(unittest.TestCase):
    def test_native_ack_context_requires_the_fresh_original_page_and_tracks_ink_and_view(self):
        s = self.server
        path = '905df7ae-ff54-46b9-a71e-45bb02bef638/3ad12986-0467-48fe-986d-d1bd480c4777.rm'
        doc,page = path[:-3].split('/')
        context = dict(available=True,fresh=True,active=True,doc=doc,page=page,
                       surface='surface',view=[1,0,0,1,-702,1000],ink_revision=10)
        with patch.object(s.device_context,'snapshot',return_value=context):
            original = s.native_ack_context(path)
        for transient in ({'fresh':False},{'active':False}):
            with patch.object(s.device_context,'snapshot',return_value=dict(context,**transient)):
                self.assertEqual(s.native_ack_context(path,settling=True),original)
        for change in ({'fresh':False},{'active':False},{'doc':page},{'page':doc}):
            with patch.object(s.device_context,'snapshot',return_value=dict(context,**change)):
                with self.assertRaisesRegex(ValueError,'original active page'):
                    s.native_ack_context(path)
                if 'doc' in change or 'page' in change:
                    with self.assertRaisesRegex(ValueError,'original active page'):
                        s.native_ack_context(path,settling=True)
        for change in ({'ink_revision':11},{'view':[1,0,0,1,-702,1200]},{'surface':'replacement'}):
            with patch.object(s.device_context,'snapshot',return_value=dict(context,**change)):
                self.assertNotEqual(s.native_ack_context(path),original)

    def check_capture_transition(self, final_context, succeeds, scroll_only=False):
        s = self.server
        path = '905df7ae-ff54-46b9-a71e-45bb02bef638/3ad12986-0467-48fe-986d-d1bd480c4777.rm'
        job = ['pane',path,int(time.time()),True,'notebook-ack-view-test',None,True]
        before = Image.new('L',(1404,1872),255)
        ImageDraw.Draw(before).text((250,900),'Existing user handwriting',fill=0)
        after = Image.new('L',before.size,255)
        after.paste(before,(0,-int(final_context[1][5])))
        if not scroll_only:
            ImageDraw.Draw(after).text((250,650),'Visible native reply',fill=0)
        original = ('surface',(1,0,0,1,0,0),10)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(s,'PENDING',directory+'/pending.json'), \
             patch.object(s,'live_baseline',return_value=directory+'/baseline.png'), \
             patch.object(s,'notebook_names',{job[4]:'pidog'}), \
             patch.object(s,'live_capture',side_effect=[before,after,after,after]), \
             patch.object(s,'native_ack_context',side_effect=[original,original,original,final_context]):
            s.start_notebook_job(job)
            s.notebook_reply(job[4],'Visible native reply')
            s.native_text(path)
            if succeeds:
                self.assertEqual(s.native_text(path,job[4],done=True)['state'],'written')
                self.assertTrue(Path(directory+'/baseline.png').exists())
            else:
                with self.assertRaisesRegex(ValueError,'not visible' if scroll_only else 'changed while confirming'):
                    s.native_text(path,job[4],done=True)
                self.assertIn(path,s.ready)
                self.assertEqual(s.answers[path],'writing')
                self.assertFalse(Path(directory+'/baseline.png').exists())

    def test_new_handwriting_during_final_capture_is_not_swallowed_by_baseline(self):
        self.check_capture_transition(('surface',(1,0,0,1,0,0),11),False)
        self.check_capture_transition(('replacement',(1,0,0,1,0,0),10),False)

    def test_automatic_viewport_settling_with_unchanged_input_is_allowed(self):
        self.check_capture_transition(('surface',(1,0,0,1,0,500),10),True)

    def test_scrolling_old_ink_without_a_reply_never_acknowledges_or_clears_it(self):
        self.check_capture_transition(('surface',(1,0,0,1,0,500),10),False,scroll_only=True)

    def test_refused_legacy_respond_preserves_previous_timings(self):
        s = self.server
        doc, page = '905df7ae-ff54-46b9-a71e-45bb02bef638', '3ad12986-0467-48fe-986d-d1bd480c4777'
        path = f'{doc}/{page}.rm'
        previous = {'respond': 10, 'written': 20}
        with patch.object(s, 'reply_timings', {path: previous}), \
             patch.object(s, 'notebook_model_route', return_value=None), \
             patch.object(s, 'tablet', return_value=b'{"visibleName": "To pidog"}'), \
             patch.object(s, 'agent_list', return_value=[{'name': 'pidog', 'pane_id': 'pane'}]), \
             patch.object(s, 'read_letter') as reader, patch.object(s, 'send') as send:
            with self.assertRaisesRegex(ValueError, 'isolated model route'):
                s.respond(doc, page)
            self.assertIs(s.reply_timings[path], previous)
            reader.assert_not_called(); send.assert_not_called()

    def test_rollout_alone_never_authorizes_shared_agent_dispatch(self):
        s = self.server
        doc, page = '905df7ae-ff54-46b9-a71e-45bb02bef638', '3ad12986-0467-48fe-986d-d1bd480c4777'
        for live, enabled in ((True, True), (True, False), (False, True)):
            with self.subTest(live=live, enabled=enabled), \
                 patch.object(s, 'lesson_enabled', return_value=enabled), \
                 patch.object(s, 'lesson_rollout_config', return_value={'notebooks':[doc],'draft_check':True}), \
                 patch.object(s, 'tablet', return_value=b'{"visibleName": "To pidog"}'), \
                 patch.object(s, 'agent_list', return_value=[{'name':'pidog','pane_id':'pane'}]), \
                 patch.object(s, 'live_capture') as capture, patch.object(s, 'render_page') as render, \
                 patch.object(s, 'read_letter') as reader, patch.object(s, 'send') as send, \
                 patch.object(s, 'start_notebook_job') as start:
                with self.assertRaisesRegex(ValueError, 'isolated model route'):
                    s.respond(doc, page, live=live)
                capture.assert_not_called(); render.assert_not_called(); reader.assert_not_called()
                send.assert_not_called(); start.assert_not_called()

    def test_draft_tool_uses_deployed_compiler_and_never_creates_state(self):
        import shlex
        s = self.server
        request = 'notebook-'+'a'*32
        with patch.object(s.os.path,'isfile',return_value=True), \
             patch.object(s,'lesson_rollout_config',return_value={'notebooks':[],'draft_check':True}), \
             patch.object(s.os,'makedirs',side_effect=AssertionError('must not create draft state')), \
             patch.object(s,'tablet',side_effect=AssertionError('must not access tablet')):
            tool = s.lesson_draft_tool(request)
        command = shlex.split(tool['command'])
        self.assertEqual(command,[s.sys.executable,str(Path(s.__file__).resolve().with_name('notebook_lesson_eval.py')),'check'])
        self.assertTrue(tool['directory'].endswith('/.buzz/OUTBOX/notebook-drafts/'+request))
        with patch.object(s.os.path,'isfile',return_value=False), \
             patch.object(s,'lesson_rollout_config',return_value={'notebooks':[],'draft_check':True}):
            self.assertIsNone(s.lesson_draft_tool(request))
        with patch.object(s,'lesson_rollout_config',return_value={'notebooks':[],'draft_check':False}):
            self.assertIsNone(s.lesson_draft_tool(request))
        for invalid in ('../elsewhere',request+'/child','notebook-test',None):
            with self.assertRaises(ValueError):
                s.lesson_draft_tool(invalid)

    def test_exact_advertised_draft_command_runs_end_to_end_offline(self):
        import shlex
        import subprocess
        from notebook_lesson_examples import integral_example
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(self.server,'lesson_rollout_config',return_value={'notebooks':[],'draft_check':True}):
            root = Path(directory)
            raw = root/'raw.txt'
            raw.write_text(integral_example())
            tool = self.server.lesson_draft_tool('notebook-'+'a'*32)
            run = subprocess.run(shlex.split(tool['command'])+[str(raw),str(root/'preview')],
                                 capture_output=True,text=True,check=False)
            self.assertEqual(run.returncode,0,run.stderr)
            result = json.loads(run.stdout)
            self.assertTrue(result['compiler_valid'])
            self.assertTrue(result['preview_complete'])
            self.assertEqual(result['quality_status'],'unreviewed')
            self.assertEqual((root/'preview/draft.txt').read_bytes(),raw.read_bytes())
            self.assertEqual(list((root/'preview').glob('*.rm')),[])


    def test_prepared_attachment_cannot_enable_legacy_agent_dispatch(self):
        s = self.server
        doc, page = '905df7ae-ff54-46b9-a71e-45bb02bef638', '3ad12986-0467-48fe-986d-d1bd480c4777'
        path = f'{doc}/{page}.rm'
        for expires in (time.time()+300, time.time()-1):
            media = {path: {'asset':'a'*64, 'expires':expires}}
            with self.subTest(expires=expires), patch.object(s, 'media_tests', media), \
                 patch.object(s, 'notebook_model_route', return_value=None), \
                 patch.object(s, 'tablet', return_value=b'{"visibleName": "To pidog"}'), \
                 patch.object(s, 'agent_list', return_value=[{'name':'pidog','pane_id':'pane'}]), \
                 patch.object(s, 'start_notebook_job') as start, patch.object(s, 'send') as send:
                with self.assertRaisesRegex(ValueError, 'isolated model route'):
                    s.respond(doc, page)
                self.assertEqual(s.media_tests, media)
                self.assertIn(path, s.media_tests)
                start.assert_not_called(); send.assert_not_called()

    def test_reader_invalid_json_escape_retries_once_before_any_agent_request(self):
        s = self.server
        def response(text):
            return io.BytesIO(json.dumps({'candidates': [{'content': {'parts': [{'text': text}]}}]}).encode())
        invalid = r'{"text":"\underbrace{x}"}'
        expected = '∫_0^x x^2 dx = ?'
        valid = json.dumps({'text': expected})
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'test-key'
            key.write_text('test-only-not-a-credential')
            with patch.object(s, 'KEYF', str(key)), patch.object(s, 'ledger'), \
                 patch.object(s.urllib.request, 'urlopen', side_effect=[response(invalid), response(valid)]) as call, \
                 patch.object(s, 'send') as send:
                self.assertEqual(s.gemini('Read this note', 'The note:', 'image'), {'text': expected})
                self.assertEqual(call.call_count, 2)
                config = json.loads(call.call_args.args[0].data)['generationConfig']
                self.assertEqual(config['responseSchema']['required'], ['text'])
                send.assert_not_called()
            with patch.object(s, 'KEYF', str(key)), patch.object(s, 'ledger'), \
                 patch.object(s.urllib.request, 'urlopen', side_effect=[response(invalid), response(invalid)]) as call:
                with self.assertRaisesRegex(ValueError, 'writing is unchanged'):
                    s.gemini('Read this note', 'The note:', 'image')
                self.assertEqual(call.call_count, 2)

    def test_explicit_retry_requires_current_renderable_never_inserted_reply(self):
        s = self.server
        marker = 'notebook-'+'a'*32
        job = ['pane','doc/page.rm',int(time.time()),True,marker,None,True]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(s, 'notebook_jobs', {marker:job}), \
                patch.object(s, 'answers', {job[1]:'ready'}), \
                patch.object(s, 'ready', {job[1]:'```math\n\\frac{1}{3}\n```'}), \
                patch.object(s, 'retry_requests', {}), \
                patch.object(s, 'media_store', AssetStore(directory+'/assets')), \
                patch.object(s, 'live_baseline', return_value=directory+'/baseline'):
            result=s.retry_notebook_response(marker)
            self.assertTrue(result['retry_armed'])
            self.assertTrue(s.answer_status(job[1])['retry_token'])
            self.assertIn(job[1],s.ready)  # never acknowledges or inserts
            attempt=Path(directory+'/baseline.native-attempt')
            attempt.write_text(marker)
            self.assertIsNone(s.answer_status(job[1])['retry_token'])
            with self.assertRaises(ValueError):
                s.retry_notebook_response(marker)
            attempt.write_text('notebook-'+'b'*32)  # older request does not block a new one
            s.ready[job[1]]=r'\[\unknown{x}\]'
            s.retry_requests.clear()
            with self.assertRaises(ValueError):
                s.retry_notebook_response(marker)
            self.assertEqual(s.retry_requests,{})

    def test_held_response_diagnostic_is_current_request_only_and_read_only(self):
        s = self.server
        first, second = 'notebook-'+'a'*32, 'notebook-'+'b'*32
        jobs = {first: ['pane','doc/page.rm',0,True,first],
                second: ['pane','doc/page.rm',0,True,second]}
        with patch.object(s, 'notebook_jobs', jobs), \
                patch.object(s, 'ready', {'doc/page.rm': 'Original held equation'}):
            self.assertEqual(s.held_notebook_response(second)['text'], 'Original held equation')
            self.assertEqual(s.ready, {'doc/page.rm': 'Original held equation'})
            with self.assertRaises(ValueError):
                s.held_notebook_response(first)
            with self.assertRaises(ValueError):
                s.held_notebook_response('../not-a-request')

    def test_numeric_read_disagreement_asks_for_clarification_not_guessed_question(self):
        s = self.server
        with patch.object(s, 'held', return_value=False), \
                patch.object(s, 'gemini', side_effect=[{'text': 'What is 18 plus 24?'},
                                                       {'text': 'What is 78 plus 24?'}]) as read:
            result = s.read_letter('image')
            self.assertTrue(result.startswith('[unclear handwriting:'))
            self.assertIn('18 plus 24', result)
            self.assertIn('78 plus 24', result)
            self.assertEqual(read.call_count, 2)
            self.assertNotIn('18', read.call_args.args[1])  # second read is not primed

    def test_numeric_read_agreement_and_non_numeric_fast_path(self):
        s = self.server
        with patch.object(s, 'held', return_value=False), \
                patch.object(s, 'gemini', side_effect=[{'text': '18 plus 24?'},
                                                       {'text': 'What is 18 plus 24?'}]):
            self.assertEqual(s.read_letter('image'), '18 plus 24?')
        with patch.object(s, 'held', return_value=False), \
                patch.object(s, 'gemini', return_value={'text': 'Hello there'}) as read:
            self.assertEqual(s.read_letter('image'), 'Hello there')
            self.assertEqual(read.call_count, 1)

    def test_numeric_read_accepts_equivalent_spelled_integral_not_identical_wording_clarification(self):
        s = self.server
        first = 'Solve ∫_0^1 x^2 dx. Use two headings with an equation after each.'
        second = 'Solve integral zero to one of x squared dx. Use two headings with an equation after each.'
        with patch.object(s, 'held', return_value=False), \
                patch.object(s, 'gemini', side_effect=[{'text': first}, {'text': second}]) as read:
            self.assertEqual(s.read_letter('image'), first)
            self.assertEqual(read.call_count, 2)
        self.assertEqual(s.numeric_read_signature('x² plus THREE cubed'), ['2', '3', '3'])
        self.assertNotEqual(s.numeric_read_signature('eighteen plus 24'), s.numeric_read_signature('78 plus 24'))
        with patch.object(s, 'held', return_value=False), \
                patch.object(s, 'gemini', side_effect=[{'text': 'eighteen plus 24'}, {'text': '78 plus 24'}]):
            self.assertTrue(s.read_letter('image').startswith('[unclear handwriting:'))

    def test_tablet_dns_fallback_is_strict_and_not_used_for_key_failure(self):
        s = self.server
        missing = SimpleNamespace(returncode=255, stderr=b'Could not resolve hostname remarkable.lan', stdout=b'')
        good = SimpleNamespace(returncode=0, stderr=b'', stdout=b'ok')
        with patch.object(s, 'TABLET', 'root@remarkable.lan'), \
                patch.object(s.subprocess, 'run', side_effect=[missing, good]) as run:
            self.assertEqual(s.tablet('true'), b'ok')
            fallback = run.call_args.args[0]
            self.assertIn('HostKeyAlias=remarkable.lan', fallback)
            self.assertIn('StrictHostKeyChecking=yes', fallback)
            self.assertEqual(fallback[-2:], ['root@remarkable.local', 'true'])
        key_error = SimpleNamespace(returncode=255, stderr=b'Host key verification failed.', stdout=b'')
        with patch.object(s, 'TABLET', 'root@remarkable.lan'), \
                patch.object(s.subprocess, 'run', return_value=key_error) as run:
            with self.assertRaises(RuntimeError):
                s.tablet('true')
            self.assertEqual(run.call_count, 1)

    def test_deferred_media_survives_resume_and_accepts_one_final_callback(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(s, "PENDING", directory + "/pending.json"), \
                patch.object(s, "ready", {}), patch.object(s, "answers", {}), \
                patch.object(s, "notebook_jobs", {}):
            job = ["pane", "doc/page.rm", int(time.time()), True, "notebook-media", None, True]
            s.start_notebook_job(job)
            token = "[[notebook-media-pending]]"
            self.assertTrue(s.notebook_reply(job[4], token)["media_pending"])
            self.assertNotIn(job[1], s.ready)
            saved = s.pend("")[job[1]]
            s.answer(*saved)
            self.assertTrue(s.answer_status(job[1])["media_pending"])
            with patch.object(s.time, "time", return_value=job[2] + s.ANSWER_WAIT + 1):
                self.assertEqual(s.answer_status(job[1])["state"], "no answer")
            s.answers[job[1]] = "waiting"
            self.assertEqual(s.notebook_reply(job[4], "A dog. [[notebook-asset:" + "a"*64 + "]]"), {"state": "ready"})
            # A late placeholder may not overwrite the generated result.
            self.assertEqual(s.notebook_reply(job[4], token), {"state": "ready"})
            with self.assertRaises(ValueError):
                s.notebook_reply(job[4], "A different result")
            s.start_notebook_job(job[:4] + ["new-request", None, True])
            with self.assertRaises(ValueError):
                s.notebook_reply(job[4], "Old generated image")

    @classmethod
    def setUpClass(cls):
        source = str(Path(__file__).with_name("herd-board-serve"))
        loader = importlib.machinery.SourceFileLoader("notebook_server_test", source)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.server = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.server)

    def test_correlated_callback_survives_restart_and_rejects_conflicts(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory:
            old = s.PENDING
            s.PENDING = os.path.join(directory, "pending.json")
            try:
                s.ready.clear(); s.answers.clear(); s.notebook_jobs.clear()
                job = ["pane", "doc/page.rm", int(time.time()), True, "notebook-test"]
                s.notebook_jobs[job[4]] = job
                s.pend(job[1], job)
                with self.assertRaises(ValueError):
                    s.notebook_reply("wrong-request", "Unrelated")
                self.assertEqual(s.notebook_reply(job[4], "Hello"), {"state": "ready"})
                self.assertEqual(s.notebook_reply(job[4], "Hello"), {"state": "ready"})
                with self.assertRaises(ValueError):
                    s.notebook_reply(job[4], "Different")
                saved = s.pend("")[job[1]]
                s.ready.clear(); s.answers.clear()
                s.answer(*saved)
                self.assertEqual(s.ready[job[1]], "Hello")

                self.assertEqual(s.answers[job[1]], "ready")
                s.pend(job[1], job[:4] + ["new-request"])
                with self.assertRaises(ValueError):
                    s.notebook_reply(job[4], "Hello")
                replacement = job[:4] + ["new-request"]
                s.start_notebook_job(replacement)
                self.assertNotIn(job[1], s.ready)
                self.assertEqual(s.notebook_reply("new-request", "New answer"), {"state": "ready"})
                self.assertEqual(s.ready[job[1]], "New answer")
            finally:
                s.PENDING = old

    def test_live_reply_stays_live_through_callback_and_writes_once(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory:
            path = "bb900052-5458-4656-9f32-df7e1455b3a4/d5bba151-25fd-49ec-b2f2-0573c39e8bea.rm"
            job = ["pane", path, int(time.time()), True, "notebook-live-test", None, True]
            before = Image.new("L", (1404, 1872), 255)
            after = before.copy()
            ImageDraw.Draw(after).line((220, 200, 350, 200), fill=0, width=3)
            with patch.object(s, "PENDING", directory + "/pending.json"), \
                 patch.object(s, "live_baseline", return_value=directory + "/baseline.png"), \
                 patch.object(s, "live_capture", side_effect=[before, after]) as capture, \
                 patch.object(s, "compose", return_value=[[(0, 200, 2), (50, 200, 2)]]), \
                 patch.object(s, "live_draw") as draw:
                s.start_notebook_job(job)
                s.notebook_reply(job[4], "A live answer")
                self.assertTrue(s.pend("")[path][6])
                self.assertEqual(s.write_live(path)["state"], "written")
                self.assertEqual(draw.call_count, 1)
                self.assertEqual(capture.call_count, 2)
                with self.assertRaises(ValueError):
                    s.write_live(path)
                self.assertEqual(draw.call_count, 1)

    def test_live_write_rejects_legacy_pending_job(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(s, "PENDING", directory + "/pending.json"), \
             patch.object(s, "live_draw") as draw:
            job = ["pane", "doc/page.rm", int(time.time()), True, "notebook-legacy-test"]
            s.start_notebook_job(job)
            s.notebook_reply(job[4], "Legacy answer")
            with self.assertRaisesRegex(ValueError, "not a live"):
                s.write_live(job[1])
            draw.assert_not_called()

    def test_native_label_uses_dispatch_identity_without_another_agent_list_process(self):
        s = self.server
        path = 'bb900052-5458-4656-9f32-df7e1455b3a4/d5bba151-25fd-49ec-b2f2-0573c39e8bea.rm'
        job = ['pane',path,int(time.time()),True,'notebook-name-cache-test',None,True]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(s,'PENDING',directory+'/pending.json'), \
             patch.object(s,'notebook_names',{job[4]:'pidog'}), \
             patch.object(s,'live_baseline',return_value=directory+'/baseline.png'), \
             patch.object(s,'agent_list',side_effect=AssertionError('display name is not a send-authority lookup')), \
             patch.object(s,'live_capture',return_value=Image.new('L',(1404,1872),255)):
            s.start_notebook_job(job)
            s.notebook_reply(job[4],'Crisp native text')
            self.assertEqual(s.native_text(path)['label'],'Agent Pi Dog:')

    def test_native_text_is_held_until_correlated_visible_acknowledgement(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory:
            path = "bb900052-5458-4656-9f32-df7e1455b3a4/d5bba151-25fd-49ec-b2f2-0573c39e8bea.rm"
            job = ["pane", path, int(time.time()), True, "notebook-native-test", None, True]
            before = Image.new("L", (1404, 1872), 255)
            after = before.copy()
            ImageDraw.Draw(after).text((250, 250), "Native text", fill=0)
            with patch.object(s, "PENDING", directory + "/pending.json"), \
                 patch.object(s, "live_baseline", return_value=directory + "/baseline.png"), \
                 patch.object(s, "agent_list", return_value=[{"pane_id": "pane", "name": "pidog"}]), \
                 patch.object(s, "native_ack_context", return_value=('surface',(1,0,0,1,0,0),10)), \
                 patch.object(s, "live_capture", side_effect=[before, before, before, before, after, after, after]):
                s.start_notebook_job(job)
                s.notebook_reply(job[4], "Crisp native text")
                prepared = s.native_text(path)
                self.assertEqual(prepared["text"], "Crisp native text")
                self.assertEqual(prepared["label"], "Agent Pi Dog:")
                self.assertEqual(prepared['blocks'], [{'kind': 'text', 'text': 'Crisp native text', 'styles': []}])
                self.assertEqual(prepared["top"], 165)  # blank-page placement is unchanged
                stages = s.reply_timings[path]
                ordered = [stages[key] for key in ('native_requested', 'native_content_ready',
                           'native_media_ready', 'native_frame_ready', 'native_identity_ready', 'write_started')]
                self.assertEqual(ordered, sorted(ordered))
                self.assertTrue(all(isinstance(value, float) for value in ordered))
                self.assertIn(path, s.ready)
                with self.assertRaisesRegex(ValueError, "already attempted"):
                    s.native_text(path)
                with self.assertRaisesRegex(ValueError, "does not match"):
                    s.native_text(path, "wrong-request", done=True)
                with self.assertRaisesRegex(ValueError, "not visible"):
                    s.native_text(path, job[4], done=True)
                self.assertIn(path, s.ready)
                self.assertEqual(s.native_text(path, job[4], done=True)["state"], "written")
                self.assertNotIn(path, s.ready)

    def test_native_text_prepares_ordered_math_with_registered_tablet_urls(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory + '/assets')
            path = 'bb900052-5458-4656-9f32-df7e1455b3a4/d5bba151-25fd-49ec-b2f2-0573c39e8bea.rm'
            job = ['pane', path, int(time.time()), True, 'notebook-ordered-test', None, True]
            with patch.object(s, 'PENDING', directory + '/pending.json'), \
                 patch.object(s, 'media_store', store), \
                 patch.object(s, 'live_baseline', return_value=directory + '/baseline.png'), \
                 patch.object(s, 'agent_list', return_value=[{'pane_id': 'pane', 'name': 'pidog'}]), \
                 patch.object(s, 'live_capture', return_value=Image.new('L', (1404, 1872), 255)), \
                 patch.object(s, 'native_image_resources', return_value=[]), \
                 patch.object(s, 'tablet') as remote:
                s.start_notebook_job(job)
                s.notebook_reply(job[4], '## First\n' + r'\[x^2\]' + '\n## Second\n' + r'\[1+2\]' + '\nDone.')
                prepared = s.native_text(path)
                self.assertEqual([b['kind'] for b in prepared['blocks']], ['text', 'media', 'text', 'media', 'text'])
                self.assertEqual([b['text'] for b in prepared['blocks'] if b['kind'] == 'text'], ['First', 'Second', 'Done.'])
                for block in prepared['blocks']:
                    if block['kind'] == 'media':
                        self.assertIn(block['asset'], s.pend('')[path][7])
                        self.assertEqual(block['url'], 'file:///home/root/.cache/herd-board/assets/' + block['asset'] + '.png')
                        self.assertGreater(block['width'], 0)
                self.assertEqual(remote.call_count, 2)

    def test_native_text_can_extend_below_a_full_viewport(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory:
            path = "bb900052-5458-4656-9f32-df7e1455b3a4/d5bba151-25fd-49ec-b2f2-0573c39e8bea.rm"
            job = ["pane", path, int(time.time()), True, "notebook-full-native-test", None, True]
            frame = Image.new("L", (1404, 1872), 255)
            ImageDraw.Draw(frame).line((200, 1640, 700, 1640), fill=0, width=3)
            with patch.object(s, "PENDING", directory + "/pending.json"), \
                 patch.object(s, "live_baseline", return_value=directory + "/baseline.png"), \
                 patch.object(s, "agent_list", return_value=[{"pane_id": "pane", "name": "LukeDog"}]), \
                 patch.object(s, "live_capture", return_value=frame):
                s.start_notebook_job(job)
                s.notebook_reply(job[4], "The page extends below this writing.")
                prepared = s.native_text(path)
                self.assertGreater(prepared["top"], 1600)
                self.assertEqual(prepared["top"], s.writing_box(frame)[3] + 20)
                self.assertEqual(prepared["inkBottom"], s.writing_box(frame)[3] - 30)
                self.assertGreater(prepared["top"], prepared["inkBottom"])
                self.assertEqual(prepared["label"], "Agent LukeDog:")

    def test_media_reference_survives_callback_and_restart(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(s, "PENDING", directory + "/pending.json"):
            job = ["pane", "doc/media-page.rm", int(time.time()), True,
                   "notebook-media-durable-test", None, True, ["a" * 64]]
            s.start_notebook_job(job)
            s.notebook_reply(job[4], "An equation follows.")
            saved = s.pend("")[job[1]]
            self.assertEqual(saved[7], ["a" * 64])
            s.ready.pop(job[1])
            s.answer(*saved)
            self.assertEqual(s.ready[job[1]], "An equation follows.")
            self.assertEqual(s.pend("")[job[1]][7], ["a" * 64])

    def test_answer_status_keeps_latest_request_after_pending_removal(self):
        s = self.server
        page = "test-page"
        jobs = {"old": ["pane", page, 1, True, "old"],
                "new": ["pane", page, 2, True, "new"]}
        with patch.object(s, "notebook_jobs", jobs), patch.object(s, "answers", {page: "written"}):
            status = s.answer_status(page)
            self.assertEqual(status["request"], "new")
            self.assertEqual(status["state"], "written")
            self.assertIsNone(s.answer_status("different")["request"])

    def test_answer_elapsed_age_is_monotonic_and_missing_age_is_not_guessed(self):
        s = self.server
        with patch.object(s, 'reply_timings', {'page': {'respond': 100.0}}), \
                patch.object(s.time, 'monotonic', return_value=101.25):
            self.assertEqual(s.answer_status('page')['respond_elapsed_ms'], 1250)
            self.assertIsNone(s.answer_status('unknown')['respond_elapsed_ms'])

    def test_media_proof_requires_new_matching_image_and_saved_page_reference(self):
        s = self.server
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory + "/assets")
            asset = store.equation(r"\frac{1}{3}")["asset"]
            path = "bb900052-5458-4656-9f32-df7e1455b3a4/d5bba151-25fd-49ec-b2f2-0573c39e8bea.rm"
            marker = "notebook-media-proof-test"
            job = ["pane", path, int(time.time()), True, marker, None, True, [asset]]
            image_id = "1e2ee615-6ff6-4f96-bff9-66ed9cbebd98"
            resource = "/native/page/" + image_id + ".jpg"
            with Image.open(io.BytesIO(store.get(asset))) as image:
                encoded = io.BytesIO(); image.save(encoded, "JPEG", quality=90)
            snapshot = directory + "/baseline.png"
            with open(snapshot + ".media-before.json", "w") as stream:
                json.dump({"request": marker, "files": []}, stream)
            saved_page = [b"no image reference yet"]
            def tablet(command):
                if command.startswith("dd "):
                    self.assertIn("bs=4096 count=2930", command)
                    return encoded.getvalue()
                self.assertNotIn("head ", command)
                return saved_page[0]
            with patch.object(s, "PENDING", directory + "/pending.json"), \
                 patch.object(s, "media_store", store), \
                 patch.object(s, "live_baseline", return_value=snapshot), \
                 patch.object(s, "native_image_resources", return_value=[resource]), \
                 patch.object(s, "tablet", side_effect=tablet):
                s.start_notebook_job(job)
                for invalid in ([], ['unregistered'], asset, [None]):
                    with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                        s.native_media_proof(path, marker, invalid)
                self.assertEqual(s.native_media_proof(path, marker)["state"], "waiting")
                saved_page[0] = image_id.encode()
                self.assertEqual(s.native_media_proof(path, marker), {"state": "persisted", "images": 1})
                self.assertEqual(s.native_media_proof(path, marker, [asset]), {"state": "persisted", "images": 1})
                with self.assertRaises(ValueError):
                    s.native_media_proof(path, "unrelated-request")


if __name__ == "__main__":
    unittest.main()
