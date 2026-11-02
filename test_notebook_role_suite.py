"""Offline collector tests with fake provider results, never model evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from notebook_model_transport import ModelTransportError
from notebook_panel_examples import graph_reuse_example
from notebook_role_corpus import prepare
from notebook_role_prompts import role_prompt, STORY_DIMENSIONS, PICTURE_DIMENSIONS
from notebook_role_suite import collect, confirm_idle, KEYS


class RoleSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.story,self.shapes = graph_reuse_example()
        corpus = {'version':1,'audience':'Test student','sources':[], 'questions':[
            {'id':identity,'question':self.story['question'],'source_ids':[],
             'reviewer_only':'Never send this string to the model.'} for identity in ('first','second')]}
        (self.root/'corpus.json').write_text(json.dumps(corpus))
        prepare(self.root/'packet',corpus_path=self.root/'corpus.json')
        self.packet = self.root/'packet/packet.json'
        self.configs = {key:{'endpoint':f'/unused/{key}/notebook-eval.sock','expected':{
            'role':role,'harness':'pi','provider':'openai-codex','model':'fixture-'+key,
            'reasoning_requested':'medium','requested_output_tokens':4096,
            'prompt_sha256':hashlib.sha256(role_prompt(role).encode()).hexdigest()}}
            for key,role in KEYS.items()}
        self.review = dict(v=1,mode='lesson-review',critical_issues=[])
        for category,dims in [('story',STORY_DIMENSIONS),('picture',PICTURE_DIMENSIONS)]:
            self.review[category] = {key:dict(score=3,panel='axes',evidence='Fake test evidence.') for key in dims}
        self.sent = []
        self.overrides = {}
        self.time = 0

    def call(self, endpoint, identity, png, context, *, expected, deadline_ms, observe_response):
        key = expected['model'].removeprefix('fixture-')
        packet = json.loads(context)
        self.sent.append((key,packet,png))
        self.assertNotIn('reviewer_only',context)
        self.assertNotIn('Never send this string',context)
        self.time += .1
        value = deepcopy(self.story if key.startswith('p') else
                         dict(v=1,mode='story-shapes',panels=self.shapes) if key.startswith('d') else self.review)
        if key == 'p1': value['takeaway'] = 'The second planner has a different takeaway.'
        value = self.overrides.get(key,value)
        if isinstance(value,Exception): raise value
        reply = dict(request_id=identity,response_format='role-eval-v1',
            text=value if isinstance(value,str) else json.dumps(value),
            evaluation={k:expected[k] for k in ('role','harness','prompt_sha256')},
            metrics={k:expected[k] for k in ('provider','model','reasoning_requested','requested_output_tokens')})
        reply['metrics'].update(elapsed_ms=100,first_text_ms=10,usage={'input':100,'output':50})
        observe_response(json.dumps(reply).encode())
        return reply

    def run_suite(self):
        return collect(self.packet,self.configs,self.root/'run',call=self.call,clock=lambda:self.time)

    def test_full_cross_uses_identical_inputs_and_blind_critics(self):
        result = self.run_suite()
        self.assertTrue(result['complete']); self.assertFalse(result['stopped'])
        self.assertEqual(len(self.sent),28)
        for offset in (0,14):
            sent = self.sent[offset:offset+14]
            self.assertEqual([s[0] for s in sent],['p0','p1','d0','c0','c1','d1','c0','c1','d0','c0','c1','d1','c0','c1'])
            self.assertEqual(sent[0][1:],sent[1][1:])
            self.assertEqual(sent[2][1:],sent[5][1:])
            self.assertEqual(sent[8][1:],sent[11][1:])
            self.assertEqual(sent[3][1:],sent[4][1:])
            self.assertEqual(sent[9][1:],sent[10][1:])
            self.assertNotEqual(sent[2][1],sent[8][1])
            self.assertNotIn('fixture-',json.dumps(sent[3][1]))
        self.assertFalse(result['tablet_proven']); self.assertIsNone(result['dollar_cost'])
        for row in result['rows']:
            self.assertEqual(len(row['drawings']),4)
            for drawing in row['drawings'].values():
                self.assertTrue(drawing['native_preparation_valid'])
                self.assertEqual(drawing['model_wall_ms'],200)
                self.assertEqual(len(drawing['critics']),2)
        page=(self.root/'run/index.html').read_text()
        self.assertIn('p1-d1/preview/panel-branch.png',page)
        self.assertIn('in-context examples',page)
        self.assertNotIn('<img src="http',page)
        self.assertFalse(list((self.root/'run').rglob('*.rm')))
        self.assertEqual((self.root/'run/first.png').read_bytes(),(self.root/'packet/first.png').read_bytes())

    def test_bad_final_input_and_bad_sixth_binding_prevent_any_calls(self):
        original=(self.root/'packet/second.png').read_bytes()
        (self.root/'packet/second.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'): self.run_suite()
        self.assertEqual(self.sent,[]); self.assertFalse((self.root/'run').exists())
        (self.root/'packet/second.png').write_bytes(original)
        self.configs['c1']['expected']['prompt_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'fixed prompt'): self.run_suite()
        self.assertEqual(self.sent,[])

    def test_reject_duplicate_endpoints_and_identical_candidates(self):
        saved=deepcopy(self.configs)
        self.configs['p1']['endpoint']=self.configs['p0']['endpoint']
        with self.assertRaisesRegex(ValueError,'distinct fixed'): self.run_suite()
        self.configs=saved
        self.configs['p1']['expected']=deepcopy(self.configs['p0']['expected'])
        with self.assertRaisesRegex(ValueError,'distinct candidates'): self.run_suite()
        self.assertEqual(self.sent,[])

    def test_content_failure_is_not_repaired_or_replaced_by_authored_example(self):
        self.overrides['p0']='{"unfinished":'
        self.overrides['d0']=dict(v=1,mode='unavailable',reason='Missing essential capability.')
        result=self.run_suite()
        self.assertTrue(result['complete'])
        self.assertEqual([s[0] for s in self.sent],['p0','p1','d0','d1','c0','c1']*2)
        row=result['rows'][0]
        self.assertFalse(row['planners']['p0']['valid'])
        self.assertNotIn('p0-d0',row['drawings'])
        self.assertEqual(row['drawings']['p1-d0']['unavailable'],'Missing essential capability.')
        self.assertIn('metrics',row['planners']['p0'])
        self.assertEqual((self.root/'run/first/p0/response.txt').read_text(),'{"unfinished":')

    def test_transport_stop_preserves_terminal_call_and_leaves_remainder_unattempted(self):
        self.overrides['p1']=ModelTransportError('deadline')
        result=self.run_suite()
        self.assertFalse(result['complete']); self.assertTrue(result['stopped'])
        self.assertEqual(result['stopped_at'],'first/p1')
        self.assertEqual([s[0] for s in self.sent],['p0','p1'])
        self.assertFalse((self.root/'run/second').exists())
        failure=json.loads((self.root/'run/first/p1/result.json').read_text())
        self.assertEqual(failure['transport_error'],'deadline')
        self.assertEqual(failure['metrics']['transport_error'],'deadline')
        self.assertIn('Not attempted.',(self.root/'run/index.html').read_text())

    def test_failed_critic_does_not_repair_drawing_and_all_attempts_remain(self):
        self.overrides['c0']='not JSON'
        result=self.run_suite()
        self.assertTrue(result['complete'])
        self.assertEqual(len(self.sent),28)
        for row in result['rows']:
            for drawing in row['drawings'].values():
                self.assertTrue(drawing['valid'])
                self.assertFalse(drawing['critics']['c0']['valid'])
                self.assertTrue(drawing['critics']['c1']['valid'])
                self.assertFalse(drawing['critics']['c1']['tablet_proven'])

    def test_existing_run_cannot_be_overwritten(self):
        (self.root/'run').mkdir()
        (self.root/'run/keep').write_text('old evidence')
        with self.assertRaises(FileExistsError): self.run_suite()
        self.assertEqual(self.sent,[])
        self.assertEqual((self.root/'run/keep').read_text(),'old evidence')

    def test_confirmed_deadline_is_failure_not_retry_but_other_trials_continue(self):
        self.overrides['p1']=ModelTransportError('deadline')
        checks=[]
        result=collect(self.packet,self.configs,self.root/'run',call=self.call,clock=lambda:self.time,
            idle_check=lambda endpoint: checks.append(endpoint) or True)
        self.assertTrue(result['complete']); self.assertFalse(result['stopped'])
        self.assertEqual(checks,[self.configs['p1']['endpoint']]*2)
        self.assertEqual([s[0] for s in self.sent].count('p1'),2) # once per distinct question
        self.assertEqual(len(self.sent),16)
        for row in result['rows']:
            self.assertTrue(row['planners']['p1']['provider_idle_after_deadline'])
            self.assertFalse(row['planners']['p1']['valid'])
            self.assertNotIn('p1-d0',row['drawings'])

    def test_busy_after_deadline_or_other_transport_error_still_stops(self):
        self.overrides['p1']=ModelTransportError('deadline')
        result=collect(self.packet,self.configs,self.root/'run',call=self.call,clock=lambda:self.time,
            idle_check=lambda endpoint:False)
        self.assertTrue(result['stopped']); self.assertEqual(len(self.sent),2)
        self.overrides['p0']=ModelTransportError('candidate_mismatch')
        probe=MagicMock(return_value=True)
        result=collect(self.packet,self.configs,self.root/'run2',call=self.call,clock=lambda:self.time,
            idle_check=probe)
        probe.assert_not_called(); self.assertTrue(result['stopped'])

    def test_idle_probe_sends_only_invalid_empty_object_never_valid_model_request(self):
        for error,expected in [('invalid_request',True),('busy',False),('closed',False),('provider_error',False)]:
            with self.subTest(error=error), patch('notebook_role_suite.socket.socket') as create:
                stream=create.return_value.__enter__.return_value
                stream.recv.return_value=json.dumps(dict(request_id=None,error=error)).encode()+b'\n'
                self.assertEqual(confirm_idle('/unused/notebook-eval.sock'),expected)
                stream.sendall.assert_called_once_with(b'{}\n')
        with patch('notebook_role_suite.socket.socket',side_effect=OSError):
            self.assertFalse(confirm_idle('/unused/notebook-eval.sock'))


if __name__=='__main__': unittest.main()
