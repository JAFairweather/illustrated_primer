"""Offline suite tests; all model replies below are authored fake fixtures."""
import json
from pathlib import Path
import tempfile
import unittest

from notebook_model_eval import prepare_images
from notebook_model_transport import ModelTransportError
from notebook_panel_examples import graph_reuse_example
from notebook_story_suite import prepare, load_packet, collect, compare


class StorySuiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=prepare_images(self.root/'source',image_style='clear')
        self.packet=prepare(self.root/'source/packet.json',self.root/'packet')
        self.packet_path=self.root/'packet/packet.json'
        self.sent=[]

    def fake(self,endpoint,identity,png,context,*,deadline_ms,observe_response):
        packet=json.loads(context);self.sent.append(packet)
        story,shapes=graph_reuse_example()
        if packet['task']=='story':
            story['question']=packet['context']['question']
            text=json.dumps(story)
        else:text=json.dumps(shapes[packet['context']['panel']['id']])
        result=dict(request_id=identity,response_format='story-panel-v1',text=text,
            metrics=dict(model='fake',provider='openai-codex',elapsed_ms=3,first_text_ms=1,
                         reasoning_requested='minimal',requested_output_tokens=2400,usage={'output':10}))
        observe_response(json.dumps(result).encode())
        return result

    def test_prepare_preserves_all_questions_images_and_order(self):
        packet,images=load_packet(self.packet_path)
        self.assertEqual(len(images),10)
        for new,old,png in zip(packet['questions'],self.source['questions'],images):
            self.assertEqual(new['question'],old['question'])
            self.assertEqual(new['id'],old['id'])
            self.assertEqual(png,(self.root/'source'/old['image']).read_bytes())
        self.assertEqual((self.root/'packet/system-prompt.txt').stat().st_mode&0o777,0o600)
        with self.assertRaises(FileExistsError):prepare(self.root/'source/packet.json',self.root/'packet')

    def test_tampered_late_image_prevents_every_call(self):
        late=self.root/'packet'/self.packet['questions'][-1]['image']
        late.write_bytes(b'bad png')
        with self.assertRaises(ValueError):
            collect(self.packet_path,self.root/'run','unused',expected_model='fake',call=self.fake)
        self.assertEqual(self.sent,[])
        self.assertFalse((self.root/'run').exists())

    def test_changed_prompt_rejected_without_replacing_or_calling(self):
        prompt=self.root/'packet/system-prompt.txt';prompt.write_text('changed')
        with self.assertRaisesRegex(ValueError,'frozen prompt'):
            collect(self.packet_path,self.root/'run','unused',expected_model='fake',call=self.fake)
        self.assertEqual(prompt.read_text(),'changed')
        self.assertEqual(self.sent,[])

    def test_deadline_halts_suite_without_a_second_question(self):
        attempts=[]
        def timeout(*args,**kwargs):
            attempts.append(args[1]);raise ModelTransportError('deadline')
        result=collect(self.packet_path,self.root/'run','unused',expected_model='fake',call=timeout)
        self.assertTrue(result['stopped'])
        self.assertEqual(result['stop_reason'],'deadline')
        self.assertEqual(len(attempts),1)
        self.assertEqual(len(result['rows']),1)
        self.assertFalse(result['rows'][0]['valid'])

    def test_comparison_contains_actual_panels_captions_and_missing_markers(self):
        for label in ('a','b'):
            collect(self.packet_path,self.root/label,'unused',expected_model='fake',max_questions=1,call=self.fake)
        result=compare(self.root/'a',self.root/'b',self.root/'view')
        page=Path(result['index']).read_text()
        self.assertEqual(result['questions'],10)
        self.assertEqual(len(list((self.root/'view').glob('*.png'))),8)
        self.assertIn('Start with two axes',page)
        self.assertIn('Not attempted — no model result.',page)
        self.assertIn('Full pipeline:',page)
        self.assertIn('Complete native preparation: validated offline',page)
        self.assertIn('Play caption-before-drawing sequence',page)
        self.assertEqual(len(list((self.root/'view').glob('*-playback.html'))),2)
        self.assertIn('No handwriting recognition',page)
        self.assertNotIn('Unequal per-call',page)
        self.assertEqual(len(self.sent),10)
        with self.assertRaises(FileExistsError):compare(self.root/'a',self.root/'b',self.root/'view')
        # Historical reports remain viewable after the current prompt evolves.
        from unittest.mock import patch
        with patch('notebook_story_suite.story_panel_instructions',return_value='future prompt'):
            compare(self.root/'a',self.root/'b',self.root/'historical-view')
            with self.assertRaisesRegex(ValueError,'frozen prompt'):
                collect(self.packet_path,self.root/'new-run','unused',expected_model='fake',call=self.fake)

    def test_invalid_answer_continues_next_question_without_repair(self):
        def malformed(*args,**kwargs):
            result=self.fake(*args,**kwargs)
            result['text']='```json\n{}\n```'
            return result
        summary=collect(self.packet_path,self.root/'a','unused',expected_model='fake',max_questions=2,call=malformed)
        self.assertEqual(len(self.sent),2)
        self.assertFalse(summary['stopped'])
        self.assertTrue(all(not row['valid'] for row in summary['rows']))
        collect(self.packet_path,self.root/'b','unused',expected_model='fake',max_questions=1,call=self.fake,deadline_ms=15000)
        compare(self.root/'a',self.root/'b',self.root/'view')
        page=(self.root/'view/index.html').read_text()
        self.assertIn('Held at story:',page)
        self.assertIn('Unequal per-call time budgets',page)

    def test_comparison_rejects_changed_question_packet(self):
        for label in ('a','b'):
            collect(self.packet_path,self.root/label,'unused',expected_model='fake',max_questions=1,call=self.fake)
        path=self.root/'b/packet.json';data=json.loads(path.read_text())
        data['questions'][0]['question']='A different question'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'identical fixed'):
            compare(self.root/'a',self.root/'b',self.root/'view')
        self.assertFalse((self.root/'view').exists())

    def test_comparison_rejects_unexpected_native_playback_path(self):
        for label in ('a','b'):
            collect(self.packet_path,self.root/label,'unused',expected_model='fake',max_questions=1,call=self.fake)
        path=self.root/'a/integral/result.json'
        result=json.loads(path.read_text());result['playback_file']='../outside.html'
        path.write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError,'unexpected native playback path'):
            compare(self.root/'a',self.root/'b',self.root/'view')

    def test_changed_model_stops_suite_with_raw_answer_retained(self):
        result=collect(self.packet_path,self.root/'run','unused',expected_model='different',call=self.fake)
        self.assertTrue(result['stopped'])
        self.assertEqual(result['stop_reason'],'model_changed')
        self.assertEqual(len(self.sent),1)
        self.assertTrue((self.root/'run/integral/call-00-story-response.txt').exists())

    def test_optional_correction_is_reported_separately_from_first_pass(self):
        def missing_base(endpoint,identity,png,context,**kwargs):
            packet=json.loads(context)
            reply=self.fake(endpoint,identity,png,context,**kwargs)
            if packet['task']=='story' and 'correction' not in packet['context']:
                draft=json.loads(reply['text']);del draft['panels'][0]['base']
                reply['text']=json.dumps(draft)
                kwargs['observe_response'](json.dumps(reply).encode())
            return reply
        baseline=collect(self.packet_path,self.root/'baseline','unused',expected_model='fake',
                         max_questions=1,call=missing_base)
        corrected=collect(self.packet_path,self.root/'corrected','unused',expected_model='fake',
                          max_questions=1,call=missing_base,max_corrections=1)
        self.assertFalse(baseline['rows'][0]['valid'])
        self.assertTrue(corrected['rows'][0]['valid'])
        self.assertFalse(corrected['rows'][0]['first_pass_valid'])
        self.assertEqual(corrected['rows'][0]['corrections_used'],1)
        compare(self.root/'baseline',self.root/'corrected',self.root/'comparison')
        page=(self.root/'comparison/index.html').read_text()
        self.assertIn('Unequal correction budgets',page)
        self.assertIn('First-pass valid: False; corrections used: 1.',page)
        self.assertIn('Original validation failure',page)
        self.assertEqual(len(self.sent),7)

    def test_deadline_during_correction_still_halts_suite(self):
        attempts=[]
        def timeout_on_correction(endpoint,identity,png,context,**kwargs):
            attempts.append(identity)
            if len(attempts)>1:raise ModelTransportError('deadline')
            reply=self.fake(endpoint,identity,png,context,**kwargs)
            reply['text']='{"v":'
            kwargs['observe_response'](json.dumps(reply).encode())
            return reply
        summary=collect(self.packet_path,self.root/'run','unused',expected_model='fake',
                        call=timeout_on_correction,max_corrections=1)
        self.assertTrue(summary['stopped'])
        self.assertEqual(summary['stop_reason'],'deadline')
        self.assertEqual(len(summary['rows']),1)
        self.assertEqual(len(attempts),2)
        self.assertEqual(summary['rows'][0]['corrections_used'],1)


if __name__=='__main__':unittest.main()
