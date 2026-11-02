import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from notebook_lesson_eval import compare
from notebook_model_eval import prepare_images, load_images, collect, prompt_variant, digest, identity
from notebook_model_transport import validate_model_result, ModelTransportError
from notebook_semantic_examples import examples


class ImageEvalTests(unittest.TestCase):
    def test_explicit_deadline_continuation_never_retries_and_still_stops_on_busy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prepare_images(root/'packet');calls=[]
            def fake(endpoint,rid,png,context,**kw):
                calls.append(rid)
                if len(calls)==1:raise ModelTransportError('deadline')
                if len(calls)==3:raise ModelTransportError('busy')
                raw=json.dumps(dict(request_id=rid,response_format='semantic-v1',
                    text=json.dumps({'v':1,'mode':'answer','text':'A text answer.'}),
                    metrics=dict(elapsed_ms=2,first_text_ms=1,provider='openai-codex',model='FAKE',
                        reasoning_requested='medium',requested_output_tokens=8192,usage={}))).encode()
                return validate_model_result(raw,rid,observe_response=kw['observe_response'])
            result=collect(root/'packet/packet.json',root/'run','unused',
                           continue_on_deadline=True,call=fake)
            self.assertEqual(len(calls),3);self.assertEqual(len(set(calls)),3)
            self.assertTrue(result['stopped']);self.assertTrue(result['continue_on_deadline'])
            self.assertEqual([r['id'] for r in result['rows']],['integral','gravity','odd-squares'])
            self.assertEqual([r['attempts'] for r in result['rows']],[1,1,1])
            self.assertEqual(result['rows'][0]['error'],'deadline')
            self.assertTrue(result['rows'][1]['transport_valid'])
            self.assertEqual(result['rows'][2]['error'],'busy')
            saved=json.loads((root/'run/answers.json').read_text())
            self.assertEqual([a['id'] for a in saved['answers']],['gravity'])

    def test_all_deadlines_remain_failures_and_each_question_is_attempted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);packet=prepare_images(root/'packet');calls=[]
            def timeout(*args,**kwargs):
                calls.append(args[1]);raise ModelTransportError('deadline')
            result=collect(root/'packet/packet.json',root/'run','unused',
                           continue_on_deadline=True,call=timeout)
            self.assertEqual(len(calls),len(packet['questions']))
            self.assertEqual(len(set(calls)),len(calls))
            self.assertFalse(result['stopped'])  # Whole trial completed, not successful.
            self.assertTrue(all(not r['transport_valid'] and r['error']=='deadline'
                                and r['attempts']==1 for r in result['rows']))
            self.assertEqual(json.loads((root/'run/answers.json').read_text())['answers'],[])

    def test_actual_deadline_is_recorded_even_when_no_reply_arrives(self):
        for limit in (15000, 30000):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);prepare_images(root/'packet');calls=[]
                def timeout(*args, **kwargs):
                    calls.append(kwargs['deadline_ms'])
                    raise ModelTransportError('deadline')
                result=collect(root/'packet/packet.json',root/'run','unused',
                               deadline_ms=limit,call=timeout)
                self.assertEqual(calls,[limit])
                self.assertEqual(result['request_deadline_ms'],limit)
                self.assertEqual(result['rows'][0]['request_deadline_ms'],limit)
                manifest=json.loads((root/'run/rendered/manifest.json').read_text())
                self.assertEqual(manifest['request_deadline_ms'],limit)
                self.assertEqual(manifest['rows'][0]['model_call']['request_deadline_ms'],limit)
                compare(root/'run/rendered',None,root/'review.html')
                self.assertIn(f'Request deadline: {limit} ms',(root/'review.html').read_text())

    def test_comparison_discloses_different_or_legacy_time_budgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prepare_images(root/'packet')
            def timeout(*a,**kw):raise ModelTransportError('deadline')
            for label,limit in (('a',15000),('b',30000)):
                collect(root/'packet/packet.json',root/label,'unused',deadline_ms=limit,call=timeout)
            compare(root/'a/rendered',root/'b/rendered',root/'different.html')
            text=(root/'different.html').read_text()
            self.assertIn('Unequal or unrecorded time budgets',text)
            self.assertIn('15000 ms',text);self.assertIn('30000 ms',text)
            path=root/'a/rendered/manifest.json';legacy=json.loads(path.read_text())
            del legacy['request_deadline_ms'];path.write_text(json.dumps(legacy))
            compare(root/'a/rendered',root/'b/rendered',root/'legacy.html')
            self.assertIn('Not recorded (legacy run)',(root/'legacy.html').read_text())
            self.assertIn('Unequal or unrecorded time budgets',(root/'legacy.html').read_text())
            compare(root/'b/rendered',root/'b/rendered',root/'equal.html')
            self.assertNotIn('Unequal or unrecorded time budgets',(root/'equal.html').read_text())

    def test_invalid_deadline_is_rejected_before_any_call_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prepare_images(root/'packet');calls=[]
            for limit in (0,30001,True,15000.0):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    collect(root/'packet/packet.json',root/'run','unused',deadline_ms=limit,
                            call=lambda *a,**kw:calls.append(a))
            self.assertEqual(calls,[])
            self.assertFalse((root/'run').exists())

    def test_prompt_comparison_requires_explicit_verified_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); base=prepare_images(root/'base')
            prompt=root/'candidate.txt';prompt.write_text('Different instructions')
            variant=prompt_variant(root/'base/packet.json',root/'variant',prompt)
            packets=(root/'base/packet.json',root/'variant/packet.json')
            directories=(root/'left',root/'right')
            for directory,path,packet in zip(directories,packets,(base,variant)):
                directory.mkdir()
                (directory/'manifest.json').write_text(json.dumps(dict(model='FAKE',
                    packet_sha256=digest(path.read_bytes()),rows=[dict(id=q['id'],
                    question=q['question'],valid=False,error='No model answer supplied.')
                    for q in packet['questions']])))
            dest=root/'compare.html'
            with self.assertRaisesRegex(ValueError,'different evaluation packets'):
                compare(*directories,dest)
            self.assertFalse(dest.exists())
            compare(*directories,dest,prompt_packets=packets)
            html=dest.read_text()
            self.assertIn('Prompt-only comparison',html)
            self.assertIn('different system prompts',html)
            self.assertNotIn('Identical base question packets',html)
            self.assertIn(variant['expected_system_prompt_sha256'],html)
            with self.assertRaisesRegex(ValueError,'does not match'):
                compare(*directories,root/'reversed.html',prompt_packets=packets[::-1])
            self.assertFalse((root/'reversed.html').exists())
            # Even valid hashes cannot relabel changed question context as a
            # prompt-only experiment. Verify the actual inputs, not provenance alone.
            q=variant['questions'][0];q['context']='Changed context'
            q['prompt_sha256']=identity(variant['expected_system_prompt_sha256'],q['image_sha256'],q['context'])
            packets[1].write_text(json.dumps(variant))
            manifest=json.loads((directories[1]/'manifest.json').read_text())
            manifest['packet_sha256']=digest(packets[1].read_bytes())
            (directories[1]/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'unchanged question inputs'):
                compare(*directories,root/'changed.html',prompt_packets=packets)
            self.assertFalse((root/'changed.html').exists())

    def test_prompt_variant_preserves_all_inputs_without_mutating_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=prepare_images(root/'base')
            before={p.name:p.read_bytes() for p in (root/'base').iterdir()}
            prompt=root/'candidate.txt'; prompt.write_text('A different test instruction.')
            variant=prompt_variant(root/'base/packet.json',root/'variant',prompt)
            loaded,images=load_images(root/'variant/packet.json')
            self.assertEqual(loaded,variant)
            self.assertEqual(variant['expected_system_prompt_sha256'],digest(prompt.read_bytes()))
            self.assertEqual(variant['prompt_variant']['parent_packet_sha256'],digest(before['packet.json']))
            self.assertIn('PROMPT-ONLY',variant['conditions'])
            for a,b,png in zip(original['questions'],variant['questions'],images):
                self.assertNotEqual(a['prompt_sha256'],b['prompt_sha256'])
                self.assertEqual({k:v for k,v in a.items() if k!='prompt_sha256'},
                                 {k:v for k,v in b.items() if k!='prompt_sha256'})
                self.assertEqual(png,before[a['image']])
                self.assertEqual((root/'variant'/b['image']).stat().st_mode & 0o777,0o600)
            self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'base').iterdir()})
            self.assertFalse((root/'variant/answers.json').exists())
            for existing in ('base','variant'):
                with self.assertRaises(FileExistsError):
                    prompt_variant(root/'base/packet.json',root/existing,prompt)
            self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'base').iterdir()})

    def test_prompt_variant_preflights_prompt_and_original_before_writes(self):
        for content in (b'',b'  \n',b'\0hello',b'x'*64001,b'\xff',None):
            with self.subTest(content=repr(content)[:30]), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);prepare_images(root/'base')
                prompt=root/'candidate.txt'
                prompt.write_bytes(content if content is not None else (root/'base/system-prompt.txt').read_bytes())
                with self.assertRaises(ValueError):
                    prompt_variant(root/'base/packet.json',root/'variant',prompt)
                self.assertFalse((root/'variant').exists())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prepare_images(root/'base')
            (root/'base/integral.png').write_bytes(b'tampered')
            prompt=root/'candidate.txt';prompt.write_text('New instruction')
            with self.assertRaises(ValueError):
                prompt_variant(root/'base/packet.json',root/'variant',prompt)
            self.assertFalse((root/'variant').exists())

    def test_clear_variant_changes_only_image_and_declared_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            old=prepare_images(root/'old')
            clear=prepare_images(root/'clear',image_style='clear')
            repeated=prepare_images(root/'repeated',image_style='clear')
            self.assertEqual(clear,repeated)
            self.assertEqual(old['expected_system_prompt_sha256'],clear['expected_system_prompt_sha256'])
            self.assertIn('CLEAR input variant',clear['conditions'])
            for a,b in zip(old['questions'],clear['questions']):
                self.assertEqual(a['id'],b['id'])
                self.assertEqual(a['question'],b['question'])
                self.assertEqual(a['context'],b['context'])
                self.assertNotEqual(a['image_sha256'],b['image_sha256'])
                self.assertNotEqual(a['prompt_sha256'],b['prompt_sha256'])
            self.assertEqual(len(load_images(root/'clear/packet.json')[1]),10)
            with self.assertRaises(ValueError):prepare_images(root/'bad',image_style='invented')
            self.assertFalse((root/'bad').exists())

    def test_ten_image_questions_are_reproducible_and_do_not_leak_question_as_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            a=prepare_images(root/'a'); b=prepare_images(root/'b')
            self.assertEqual(a,b)
            packet,images=load_images(root/'a/packet.json')
            self.assertEqual(len(images),10)
            self.assertEqual(len({q['prompt_sha256'] for q in packet['questions']}),10)
            self.assertEqual(len({q['context'] for q in packet['questions']}),1)
            self.assertIn('NOT attested',packet['conditions'])
            with Image.open(root/'a/integral.png') as image:
                self.assertEqual(image.size,(960,720))
            for q in packet['questions']:
                self.assertNotIn(q['question'],q['context'])

    def test_preflight_rejects_changed_image_context_prompt_before_any_call(self):
        for change in ('image','context','prompt','duplicate','path'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); packet=prepare_images(root/'packet')
                if change=='image': (root/'packet/integral.png').write_bytes(b'bad')
                elif change=='prompt': (root/'packet/system-prompt.txt').write_text('changed')
                elif change=='context': packet['questions'][0]['context']='changed'
                elif change=='duplicate': packet['questions'][1]=packet['questions'][0]
                else: packet['questions'][0]['image']='../outside.png'
                (root/'packet/packet.json').write_text(json.dumps(packet))
                calls=[]
                with self.assertRaises(ValueError):
                    collect(root/'packet/packet.json',root/'run','unused',call=lambda *a,**kw:calls.append(a))
                self.assertEqual(calls,[])
                self.assertFalse((root/'run').exists())

    def test_unedited_rejected_answers_are_saved_and_previewed_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prepare_images(root/'packet');calls=[]
            valid=examples()['integral']; invalid=examples()['integral']
            invalid['claims'][-1]['value']['numerator']=99
            def fake(endpoint,rid,png,context,**kwargs):
                calls.append(rid)
                response=json.dumps(valid if len(calls)==1 else invalid if len(calls)==2
                                    else {'v':1,'mode':'answer','text':'Unsupported visual fixture.'})
                raw=json.dumps(dict(request_id=rid,response_format='semantic-v1',text=response,
                    metrics=dict(elapsed_ms=2,first_text_ms=1,provider='openai-codex',model='FAKE',
                    reasoning_requested='medium',requested_output_tokens=8192,usage={}))).encode()
                return validate_model_result(raw,rid,observe_response=kwargs['observe_response'])
            result=collect(root/'packet/packet.json',root/'run','unused',call=fake)
            self.assertEqual(len(calls),10)
            self.assertEqual(len(set(calls)),10)
            self.assertFalse(result['host_prompt_verified'])
            self.assertFalse(result['tablet_proven'])
            self.assertFalse(result['handwriting_proven'])
            self.assertFalse(result['stopped'])
            self.assertEqual(result['rows'][1]['error'],'invalid_response')
            saved=json.loads((root/'run/answers.json').read_text())
            self.assertEqual(json.loads(saved['answers'][1]['response']),invalid)
            rows=json.loads((root/'run/rendered/manifest.json').read_text())['rows']
            self.assertTrue(rows[0]['valid']);self.assertFalse(rows[1]['valid'])
            self.assertEqual(rows[1]['stages'],[])
            self.assertFalse(rows[2]['visual_lesson'])
            self.assertFalse(list((root/'run/rendered').glob('gravity-*.rm')))
            compare(root/'run/rendered',root/'run/rendered',root/'comparison.html')
            self.assertIn('NOT attested',(root/'comparison.html').read_text())
            compare(root/'run/rendered',None,root/'report.html')
            html=(root/'report.html').read_text()
            self.assertIn('Chalkboard lesson review',html)
            self.assertNotIn('One question, two',html)
            self.assertEqual(html.count('<h3>'),10)
            self.assertIn('Held by compiler',html)
            with self.assertRaises(FileExistsError):
                collect(root/'packet/packet.json',root/'run','unused',call=fake)
            self.assertEqual(len(calls),10)

    def test_failure_stops_without_retry_and_records_missing_raw_honestly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prepare_images(root/'packet');calls=[]
            packet_path=root/'packet/packet.json'
            packet=json.loads(packet_path.read_text())
            packet['conditions']='ASSISTED diagnostic with additional typed context; not a first pass.'
            packet_path.write_text(json.dumps(packet))
            def unavailable(*args,**kwargs):
                calls.append(args);raise ModelTransportError('deadline')
            result=collect(root/'packet/packet.json',root/'run','unused',call=unavailable)
            self.assertEqual(result['conditions'],packet['conditions'])
            self.assertTrue(result['stopped']);self.assertEqual(len(calls),1)
            self.assertFalse(result['rows'][0]['raw_available'])
            self.assertEqual(json.loads((root/'run/answers.json').read_text())['answers'],[])
            rows=json.loads((root/'run/rendered/manifest.json').read_text())['rows']
            self.assertEqual(len(rows),10)
            self.assertEqual(rows[0]['failure_stage'],'transport')
            compare(root/'run/rendered',root/'run/rendered',root/'comparison.html')
            self.assertIn('No answer released by host: deadline',(root/'comparison.html').read_text())


if __name__=='__main__':unittest.main()
