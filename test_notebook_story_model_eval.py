"""Pipeline fixtures, explicitly NOT evidence of generative model quality."""
from copy import deepcopy
import io
import json
from pathlib import Path
import select
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from notebook_model_transport import ModelTransportError, _validated_envelope, validate_model_result, call_story_panel_eval
from notebook_panel_examples import graph_reuse_example
from notebook_story_model_eval import evaluate
from notebook_story_prompt import story_panel_instructions


class StoryModelEvalTests(unittest.TestCase):
    def setUp(self):
        self.story, self.shapes = graph_reuse_example()
        self.sent = []
        self.replies = [json.dumps(self.story), *[json.dumps(self.shapes[p['id']]) for p in self.story['panels']]]
        out = io.BytesIO(); Image.new('RGB', (16,16), 'white').save(out, 'PNG'); self.png = out.getvalue()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)/'run'

    def call(self, endpoint, identity, png, context, *, deadline_ms, observe_response):
        self.sent.append(json.loads(context))
        index = len(self.sent)-1
        text = self.replies[index]
        if isinstance(text, Exception): raise text
        result = dict(request_id=identity, response_format='story-panel-v1', text=text,
            metrics=dict(elapsed_ms=2,first_text_ms=1,provider='openai-codex',model='fake',
                         reasoning_requested='medium',requested_output_tokens=8192,usage={'output':10}))
        observe_response(json.dumps(result).encode())
        return result

    def run_case(self, **kwargs):
        return evaluate(self.story['question'], self.png, '/unused/notebook-eval.sock', self.dest,
                        expected_model='fake', call=self.call, **kwargs)

    def test_full_offline_pipeline_compiles_and_previews_exact_bases(self):
        result = self.run_case()
        self.assertTrue(result['valid'])
        self.assertEqual(result['call_attempts'], 5)
        self.assertEqual(result['completed_model_responses'], 5)
        self.assertEqual(result['retries'], 0)
        self.assertFalse(result['tablet_proven'])
        self.assertFalse(result['host_prompt_attested'])
        self.assertTrue(result['native_preparation_valid'])
        self.assertFalse(result['native_delivery_supported'])
        self.assertEqual(result['picture_runs'],2)
        self.assertGreater(result['delivery_points'],0)
        self.assertTrue((self.dest/'playback.html').exists())
        self.assertFalse(result['playback']['tablet_proven'])
        self.assertTrue((self.dest/'preview/index.html').exists())
        self.assertEqual(self.sent[1]['context']['base_items'], [])
        self.assertEqual([p['id'] for p in self.sent[1]['context']['picture_plan']],
                         ['axes','curve','mark','branch'])
        self.assertEqual([x['id'] for x in self.sent[3]['context']['base_items']], ['ax','square'])
        # The branch is from axes, not the immediately preceding marked curve.
        self.assertEqual([x['id'] for x in self.sent[4]['context']['base_items']], ['ax'])
        for packet in self.sent[1:]:
            self.assertNotIn('groups', packet['context'])
            self.assertNotIn('box', json.dumps(packet['context']['base_items']))
            self.assertNotIn('panels', packet['context'])
        self.assertEqual(len(list(self.dest.glob('*-wire.json'))),5)
        self.assertEqual(len(list(self.dest.rglob('*.rm'))),0)
        self.assertEqual((self.dest/'system-prompt.txt').read_text(),story_panel_instructions())
        with self.assertRaises(FileExistsError): self.run_case()
        self.assertEqual(len(self.sent),5)

    def test_snapshot_success_cannot_hide_native_preparation_failure(self):
        with patch('notebook_story_model_eval.native_story_bundle',
                   side_effect=ValueError('native delivery budget exceeded')):
            result=self.run_case()
        self.assertTrue(result['preview']['valid'])
        self.assertFalse(result['valid'])
        self.assertFalse(result['native_preparation_valid'])
        self.assertFalse(result['first_pass_valid'])
        self.assertEqual(result['failed_phase'],'native-preparation')
        self.assertFalse((self.dest/'playback.html').exists())
        self.assertEqual(len(self.sent),5)

    def test_production_envelope_failure_prevents_native_preparation(self):
        with patch('notebook_story_model_eval.parse_semantic_reply',
                   side_effect=ValueError('reply exceeds byte cap')), \
             patch('notebook_story_model_eval.native_story_bundle') as native:
            result=self.run_case()
        native.assert_not_called()
        self.assertFalse(result['valid'])
        self.assertEqual(result['failed_phase'],'native-preparation')
        self.assertEqual(len(self.sent),5)

    def test_failed_geometry_stops_before_any_preview_or_later_call(self):
        bad = deepcopy(self.shapes['curve'])
        bad['items'][0]['coefficients'] = [0,0,100]
        self.replies[2] = json.dumps(bad)
        result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertEqual(result['failed_phase'],'panel:curve')
        self.assertEqual(len(self.sent),3)
        self.assertFalse((self.dest/'preview').exists())
        self.assertEqual((self.dest/'call-02-panel-response.txt').read_text(),self.replies[2])

    def test_explicit_unavailable_is_not_visual_success(self):
        self.replies[0] = '{"v":1,"mode":"unavailable","reason":"Need the theorem statement."}'
        result = self.run_case()
        self.assertTrue(result['unavailable'])
        self.assertFalse(result['valid'])
        self.assertEqual(len(self.sent),1)

    def test_malformed_and_duplicate_json_are_not_repaired(self):
        self.replies[0] = '{"v":1,"v":1,"mode":"story"}'
        result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertEqual(len(self.sent),1)
        self.assertEqual((self.dest/'call-00-story-response.txt').read_text(),self.replies[0])

    def test_one_story_correction_preserves_first_failure_and_raw_answer(self):
        bad=deepcopy(self.story);del bad['panels'][0]['base']
        self.replies.insert(0,json.dumps(bad))
        result=self.run_case(max_corrections=1)
        self.assertTrue(result['valid'])
        self.assertFalse(result['first_pass_valid'])
        self.assertEqual(result['corrections_used'],1)
        self.assertEqual(result['retries'],1)
        self.assertEqual(result['call_attempts'],6)
        self.assertEqual(result['first_validation_failure']['feedback']['missing_keys'],['base'])
        correction=self.sent[1]['context']['correction']
        self.assertEqual(correction['previous_output'],self.replies[0])
        self.assertEqual(correction['feedback']['path'],'/panels/0')
        self.assertEqual((self.dest/'call-00-story-response.txt').read_text(),self.replies[0])
        self.assertEqual((self.dest/'story.json').read_text(),self.replies[1])
        self.assertTrue(result['calls'][1]['correction'])
        self.assertNotIn('correction',self.sent[2]['context'])

    def test_panel_correction_keeps_exact_validated_base_context(self):
        bad=deepcopy(self.shapes['curve']);bad['items'][0]['unexpected']=1
        self.replies.insert(2,json.dumps(bad))
        result=self.run_case(max_corrections=1)
        self.assertTrue(result['valid'])
        self.assertFalse(result['first_pass_valid'])
        self.assertEqual(result['call_attempts'],6)
        corrected=deepcopy(self.sent[3]['context']);corrected.pop('correction')
        self.assertEqual(corrected,self.sent[2]['context'])
        self.assertEqual([x['id'] for x in self.sent[4]['context']['base_items']],['ax','square'])

    def test_syntax_correction_gets_one_full_replacement(self):
        self.replies.insert(0,'{"v":')
        result=self.run_case(max_corrections=1)
        self.assertTrue(result['valid'])
        self.assertEqual(self.sent[1]['context']['correction']['feedback']['code'],'json_syntax')

    def test_correction_budget_is_per_lesson_not_per_panel(self):
        bad=deepcopy(self.story);del bad['panels'][0]['base']
        self.replies.insert(0,json.dumps(bad))
        self.replies[3]='{"v":'
        result=self.run_case(max_corrections=1)
        self.assertFalse(result['valid'])
        self.assertEqual(result['call_attempts'],4)
        self.assertEqual(result['corrections_used'],1)
        self.assertFalse((self.dest/'preview').exists())

    def test_invalid_correction_is_not_retried(self):
        self.replies[:2]=['{"v":','{"v":']
        result=self.run_case(max_corrections=1)
        self.assertFalse(result['valid'])
        self.assertEqual(result['call_attempts'],2)
        self.assertEqual(result['corrections_used'],1)
        self.assertFalse((self.dest/'preview').exists())

    def test_correction_cannot_modify_inherited_item_or_bypass_geometry(self):
        self.replies.insert(2,'{"v":')
        bad=deepcopy(self.shapes['curve']);bad['items'][0]['id']='ax'
        self.replies[3]=json.dumps(bad)
        result=self.run_case(max_corrections=1)
        self.assertFalse(result['valid'])
        self.assertIn('redefine',result['error'])
        self.assertEqual(result['call_attempts'],4)
        self.assertFalse((self.dest/'preview').exists())

    def test_transport_unavailable_binding_and_geometry_failures_never_correct(self):
        for index,replacement,expected in (
                (0,ModelTransportError('deadline'),'deadline'),
                (0,'{"v":1,"mode":"unavailable","reason":"Need a statement."}','unavailable'),
                (2,json.dumps(dict(self.shapes['curve'],items=[dict(id='c',type='circle',
                    **{'in':'ax'},center=[.5,.5],radius=.2)])),'equal axis')):
            with self.subTest(expected=expected):
                self.dest=Path(self.tmp.name)/expected;self.sent.clear()
                self.replies=[json.dumps(self.story),*[json.dumps(self.shapes[p['id']]) for p in self.story['panels']]]
                self.replies[index]=replacement
                result=self.run_case(max_corrections=1)
                self.assertFalse(result['valid'])
                self.assertEqual(result['corrections_used'],0)
                self.assertEqual(len(self.sent),index+1)
        self.sent.clear();self.dest=Path(self.tmp.name)/'wrong-model'
        result=evaluate(self.story['question'],self.png,'unused',self.dest,
            expected_model='not-fake',call=self.call,max_corrections=1)
        self.assertEqual(result['corrections_used'],0)
        self.assertEqual(len(self.sent),1)

    def test_correction_context_overflow_does_not_truncate_or_dispatch(self):
        bad=deepcopy(self.story);bad['unknown']='x'*13000
        self.replies[0]=json.dumps(bad)
        result=self.run_case(max_corrections=1)
        self.assertEqual(result['transport_error'],'invalid_request')
        self.assertEqual(result['call_attempts'],1)
        self.assertEqual(result['corrections_used'],0)
        self.assertEqual((self.dest/'call-00-story-response.txt').read_text(),self.replies[0])

    def test_corrected_geometry_still_obeys_native_point_cap(self):
        self.replies.insert(2,'{"v":')
        bad=deepcopy(self.shapes['curve'])
        bad['items']=[dict(id='line-'+str(i),type='arrow',
                          **{'in':'ax','from':[i/24,0],'to':[i/24,1]}) for i in range(24)]
        self.replies[3]=json.dumps(bad)
        result=self.run_case(max_corrections=1)
        self.assertFalse(result['valid'])
        self.assertEqual(result['corrections_used'],1)
        self.assertEqual(result['call_attempts'],4)
        self.assertIn('resource_feedback',result)
        for attempt in result['resource_feedback']['attempts']:
            self.assertEqual(attempt['failure']['resource'],'points')
            self.assertEqual(attempt['failure']['limit'],3000)
            self.assertGreater(attempt['failure']['observed'],3000)
        self.assertFalse((self.dest/'preview').exists())

    def over_budget_panel(self):
        return json.dumps(dict(self.shapes['curve'], items=[
            dict(id=f'note-{i}', type='label', to='ax', text='Many letters', side='auto')
            for i in range(8)]))

    def test_resource_correction_keeps_base_and_original_failure(self):
        failed = self.over_budget_panel()
        self.replies.insert(2, failed)
        result = self.run_case(max_corrections=1)
        self.assertTrue(result['valid'])
        self.assertFalse(result['first_pass_valid'])
        self.assertEqual(result['corrections_used'], 1)
        self.assertEqual(len(self.sent), 6)
        correction = self.sent[3]['context']['correction']
        self.assertEqual(correction['previous_output'], failed)
        self.assertEqual(correction['feedback']['code'], 'native_resource_budget')
        failure = correction['feedback']['resource']['attempts'][0]['failure']
        self.assertEqual(failure['limit'], 64)
        self.assertGreater(failure['observed'], 64)
        corrected = deepcopy(self.sent[3]['context']); corrected.pop('correction')
        self.assertEqual(corrected, self.sent[2]['context'])
        self.assertEqual((self.dest/'call-02-panel-response.txt').read_text(), failed)
        self.assertEqual(result['first_validation_failure']['phase'], 'panel:curve')

    def test_resource_failure_does_not_enable_correction_by_default(self):
        self.replies[2] = self.over_budget_panel()
        result = self.run_case()
        self.assertFalse(result['valid'])
        self.assertEqual(result['corrections_used'], 0)
        self.assertEqual(len(self.sent), 3)

    def test_second_resource_failure_has_no_second_correction(self):
        self.replies[2:3] = [self.over_budget_panel()] * 2
        result = self.run_case(max_corrections=1)
        self.assertFalse(result['valid'])
        self.assertEqual(result['corrections_used'], 1)
        self.assertEqual(len(self.sent), 4)
        self.assertFalse((self.dest/'preview').exists())

    def test_resource_and_schema_corrections_share_one_lesson_allowance(self):
        self.replies.insert(2, self.over_budget_panel())
        self.replies[4] = '{"v":'
        result = self.run_case(max_corrections=1)
        self.assertFalse(result['valid'])
        self.assertEqual(result['corrections_used'], 1)
        self.assertEqual(len(self.sent), 5)
        self.assertFalse((self.dest/'preview').exists())

    def test_invalid_correction_budget_is_rejected_before_any_artifact(self):
        for value in (True,-1,2,'1'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.run_case(max_corrections=value)
        self.assertEqual(self.sent,[])
        self.assertFalse(self.dest.exists())

    def test_deadline_stops_without_retry_or_preview(self):
        self.replies[1] = ModelTransportError('deadline')
        result = self.run_case()
        self.assertEqual(result['transport_error'],'deadline')
        self.assertEqual(len(self.sent),2)
        self.assertFalse((self.dest/'preview').exists())
        self.assertFalse(json.loads((self.dest/'result.json').read_text())['valid'])

    def test_model_switch_and_changed_question_are_held(self):
        other = deepcopy(self.story); other['question'] = 'Different question'
        self.replies[0] = json.dumps(other)
        result = self.run_case()
        self.assertIn('changed the supplied question', result['error'])
        self.assertEqual(len(self.sent),1)
        self.dest = Path(self.tmp.name)/'model-change'
        self.sent.clear()
        result = evaluate(self.story['question'],self.png,'unused',self.dest,
                          expected_model='not-fake',call=self.call)
        self.assertIn('model changed',result['error'])
        self.assertEqual(len(self.sent),1)

    def test_context_overflow_never_silently_truncates_or_calls(self):
        # Max-sized valid story fields can overflow the smaller IPC context
        # when the ancestry is long; fail before dispatch, never lose ancestors.
        from unittest.mock import patch
        with patch('notebook_story_model_eval.panel_packet', return_value={'huge':'x'*12001}):
            result = self.run_case()
        self.assertEqual(result['transport_error'],'invalid_request')
        self.assertEqual(len(self.sent),1)

    def test_new_envelopes_cannot_pass_live_semantic_validation(self):
        identity = 'notebook-'+'a'*32
        raw_result = dict(request_id=identity,response_format='story-panel-v1',text=self.replies[0],
            metrics=dict(elapsed_ms=2,first_text_ms=1,provider='openai-codex',model='fake',
                         reasoning_requested='medium',requested_output_tokens=8192,usage={}))
        raw = json.dumps(raw_result).encode()
        self.assertEqual(_validated_envelope(raw,identity,'story-panel-v1')['text'],self.replies[0])
        with self.assertRaises(ModelTransportError):validate_model_result(raw,identity)
        raw_result['response_format'] = 'semantic-v1'
        with self.assertRaises(ModelTransportError):
            _validated_envelope(json.dumps(raw_result).encode(),identity,'story-panel-v1')
        for text in [None, {'v':1}, 'a'*24001]:
            raw_result.update(response_format='story-panel-v1',text=text)
            with self.assertRaises(ModelTransportError):
                _validated_envelope(json.dumps(raw_result).encode(),identity,'story-panel-v1')
        with self.assertRaisesRegex(ModelTransportError,'unavailable'):
            call_story_panel_eval('/unused/notebook.sock',identity,self.png,'question')

    def test_real_socket_with_fake_provider_runs_whole_pipeline(self):
        here = Path(__file__).resolve().parent
        # Keep AF_UNIX paths independent of checkout/export path length. Resolve
        # macOS /tmp before creating the owner-only directory: the production
        # client deliberately rejects symlink ancestors and paths over 100 bytes.
        source = '''
import fs from 'node:fs';
import {createNotebookResponder} from CORE;
import {serveNotebookSocket} from HOST;
const c=JSON.parse(fs.readFileSync(0,'utf8'));
const model={provider:'openai-codex',id:'fake',input:['image','text']};
let n=0;
const modelRegistry={isUsingOAuth:()=>true,streamSimple(m,ctx,options){
 if(ctx.systemPrompt!==c.prompt || ctx.messages.length!==1 || ctx.tools.length || options.maxRetries!==0)
   throw Error('isolation changed');
 const text=c.replies[n++];
 return {async *[Symbol.asyncIterator](){yield {type:'text_delta',delta:text};},result:async()=>({
 role:'assistant',provider:m.provider,model:m.id,stopReason:'stop',content:[{type:'text',text}],usage:{output:20}})};
}};
const responder=createNotebookResponder({modelRegistry,model,systemPrompt:c.prompt,responseFormat:'story-panel-v1'});
const host=await serveNotebookSocket({socketPath:c.endpoint,responder});
console.log('ready');
process.on('SIGTERM',async()=>{await host.close();process.exit(0);});
'''.replace('CORE',json.dumps((here/'notebook_pi_responder.mjs').as_uri())).replace('HOST',json.dumps((here/'notebook_pi_socket.mjs').as_uri()))
        with tempfile.TemporaryDirectory(prefix='story-', dir=Path(tempfile.gettempdir()).resolve()) as tmp:
            endpoint = str(Path(tmp)/'notebook-eval.sock')
            self.assertLessEqual(len(endpoint.encode()), 100)
            child = subprocess.Popen(['node','--input-type=module','-e',source],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                child.stdin.write(json.dumps(dict(endpoint=endpoint,prompt=story_panel_instructions(),replies=self.replies)).encode())
                child.stdin.close()
                self.assertTrue(select.select([child.stdout],[],[],3)[0])
                self.assertEqual(child.stdout.readline(),b'ready\n')
                result = evaluate(self.story['question'],self.png,endpoint,self.dest,expected_model='fake')
                self.assertTrue(result['valid'],result)
                self.assertEqual(result['completed_model_responses'],5)
                self.assertTrue((self.dest/'preview/index.html').exists())
            finally:
                child.terminate()
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=3)
                child.stdout.close(); child.stderr.close()


if __name__ == '__main__': unittest.main()
