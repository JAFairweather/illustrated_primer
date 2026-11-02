import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from ink import strokes

from notebook_lesson_native import native_semantic_bundle,prepare_semantic_reply
from notebook_media import AssetStore
from notebook_semantic import SemanticError,compile_semantic,CAPABILITIES
from notebook_semantic_examples import examples
from notebook_semantic_prompt import semantic_reply_instructions,worked_examples
from notebook_semantic_reply import parse_semantic_reply
from notebook_stroke_asset import storyboard_assets


class SemanticReplyTests(unittest.TestCase):
    def test_eval_keeps_fallbacks_distinct_and_preserves_unedited_failures(self):
        from notebook_lesson_eval import prepare,render,compare
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            packet=prepare(root/'packet',semantic=True)
            self.assertEqual(len(packet['questions']),10)
            self.assertEqual(packet['response_format'],'semantic-v1')
            responses={'integral':json.dumps(examples()['integral']),
                       'gravity':json.dumps(dict(v=1,mode='answer',text='Gravity accelerates the apple.')),
                       'odd-squares':'{"v":1,"mode":"lesson"'}
            source=root/'answers.json'
            source.write_text(json.dumps(dict(model='TEST FIXTURES, not a model',answers=[
                dict(id=q['id'],prompt_sha256=q['prompt_sha256'],response=responses[q['id']])
                for q in packet['questions'] if q['id'] in responses])))
            original=source.read_bytes()
            result=render(root/'packet/packet.json',source,root/'rendered')
            rows={row['id']:row for row in result['rows']}
            self.assertTrue(rows['integral']['visual_lesson'])
            self.assertGreater(rows['integral']['response_bytes'],0)
            self.assertGreaterEqual(rows['integral']['compile_native_ms'],0)
            self.assertEqual(len(rows['integral']['stages']),4)
            self.assertTrue(rows['gravity']['valid'])
            self.assertFalse(rows['gravity']['visual_lesson'])
            self.assertEqual(rows['gravity']['stages'],[])
            self.assertFalse(rows['odd-squares']['valid'])
            self.assertFalse(rows['odd-squares']['visual_lesson'])
            self.assertGreater(rows['odd-squares']['response_bytes'],0)
            self.assertGreaterEqual(rows['odd-squares']['compile_native_ms'],0)
            self.assertEqual(rows['transistor']['error'],'No model answer supplied.')
            self.assertEqual(source.read_bytes(),original)
            saved=json.loads((root/'rendered/odd-squares-raw.json').read_text())
            self.assertEqual(saved['response'],responses['odd-squares'])
            self.assertFalse(list((root/'rendered').glob('gravity-*.rm')))
            self.assertFalse(list((root/'rendered').glob('odd-squares-*.rm')))
            compare(root/'rendered',root/'rendered',root/'comparison.html')
            self.assertIn('not a visual lesson',(root/'comparison.html').read_text())
            with patch('notebook_lesson_eval.preview_png',side_effect=ValueError('preview failed')):
                broken=render(root/'packet/packet.json',source,root/'broken')
            failed=next(row for row in broken['rows'] if row['id']=='integral')
            self.assertFalse(failed['valid'])
            self.assertFalse(failed['visual_lesson'])
            self.assertEqual(failed['error'],'preview failed')

    def test_examples_use_the_actual_compiler_not_a_second_grammar(self):
        prompt=semantic_reply_instructions()
        self.assertIn(json.dumps(CAPABILITIES,separators=(',',':'),ensure_ascii=False),prompt)
        self.assertEqual(set(worked_examples()),{'integral','odd-squares'})
        for spec in worked_examples().values():
            raw=json.dumps(spec,separators=(',',':'),ensure_ascii=False)
            self.assertIn(raw,prompt)
            self.assertEqual(parse_semantic_reply(raw)['plan'],compile_semantic(spec))

    def test_prompt_uses_representation_rules_not_topic_routing(self):
        prompt=semantic_reply_instructions()
        self.assertIn('Choose a representation by the reasoning, not by a matching topic name',prompt)
        self.assertIn('A missing named component is not a reason by itself',prompt)
        self.assertIn('a label supplies an object\'s meaning',prompt)
        self.assertIn('Connections need two distinct existing endpoints',prompt)
        # Worked examples remain the two required lessons. New motif demos
        # are evaluation fixtures, not per-topic recipes in the agent prompt.
        self.assertEqual(set(worked_examples()),{'integral','odd-squares'})
        self.assertIn('do not supply connection coordinates',prompt)
        self.assertIn('physical ray, force, trajectory or metric measurement',prompt)

    def test_prompt_delegates_layout_and_explains_additive_step_contract(self):
        prompt=semantic_reply_instructions()
        self.assertIn('nonempty reveal groups',prompt)
        self.assertIn('each ID appears in exactly ONE step',prompt)
        self.assertIn('prose-only conclusion in takeaway',prompt)
        self.assertIn('finite numeric literals',prompt)
        self.assertIn('Use anchored labels by default',prompt)
        self.assertLess(prompt.index('"target":"local-name"'),prompt.index('"at":[x,baseline]'))
        # These assertions test the authored contract, not model adherence.
        self.assertEqual(set(worked_examples()),{'integral','odd-squares'})

    def test_all_fixtures_go_directly_to_native_sources_in_answer_order(self):
        for name,spec in examples().items():
            with self.subTest(name=name),patch('notebook_lesson_native.parse_lesson',
                    side_effect=AssertionError('coordinate text path must not be called')):
                raw=json.dumps(spec);bundle=native_semantic_bundle(raw)
                plan=compile_semantic(spec)
                self.assertEqual(bundle['plan'],plan)
                assets=storyboard_assets(plan)
                # Each encoder call owns fresh author IDs; compare saved
                # geometry, not unrelated identity bytes in the v6 header.
                self.assertEqual([strokes(s['data']) for s in bundle['sources']],
                                 [strokes(a['data']) for a in assets])
                self.assertEqual(len({s['source_page'] for s in bundle['sources']}),len(assets))
                for i,stage in enumerate(plan['stages']):
                    ink,caption=bundle['blocks'][2*i:2*i+2]
                    self.assertEqual((ink['kind'],ink['stage_index'],ink['stage_count']),
                                     ('ink',i,len(plan['stages'])))
                    self.assertEqual(caption,dict(kind='text',text=stage['text'],styles=[]))
                self.assertEqual(bundle['blocks'][-1]['text'],'Takeaway: '+spec['takeaway'])
                second=native_semantic_bundle(raw)
                self.assertNotEqual(bundle['sources'][0]['source_doc'],second['sources'][0]['source_doc'])

    def test_equation_registered_before_returning_prepared_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            store=AssetStore(directory)
            bundle=prepare_semantic_reply(json.dumps(examples()['integral']),store)
            media=[b for b in bundle['blocks'] if b['kind']=='media']
            self.assertEqual(len(media),1)
            self.assertTrue(store.get(media[0]['asset']).startswith(b'\x89PNG'))
            self.assertNotIn('equation',[b['kind'] for b in bundle['blocks']])

    def test_plain_modes_allocate_no_sources_or_media(self):
        for mode,text in [('answer','That looks like a dog: pointed ears and a long tail.'),
                          ('clarify','Is the upper limit 1 or 7?')]:
            store=Mock()
            with patch('notebook_lesson_native.uuid.uuid4') as identity:
                bundle=prepare_semantic_reply(json.dumps(dict(v=1,mode=mode,text=text)),store)
                identity.assert_not_called()
            store.equation.assert_not_called()
            self.assertEqual(bundle,dict(mode=mode,plan=None,sources=[],
                                         blocks=[dict(kind='text',text=text,styles=[])]))

    def test_answer_paragraphs_preserved_without_relaxing_caption_or_markup_rules(self):
        text='Eight true positives.\n\nNine false positives.\nThe fraction is 8/17.'
        raw=json.dumps(dict(v=1,mode='answer',text=text))
        self.assertEqual(native_semantic_bundle(raw)['blocks'][0]['text'],text)
        for bad in ('Fine.\n# Heading','Fine.\n/tmp/file','Fine.\n**bold**',
                    'Fine.\n\t','<tag\nvalue>','Fine.\n\x00'):
            with self.assertRaises(SemanticError):
                parse_semantic_reply(json.dumps(dict(v=1,mode='answer',text=bad)))
        with self.assertRaises(SemanticError):
            parse_semantic_reply(json.dumps(dict(v=1,mode='clarify',text='Which?\nWhy?')))
        spec=examples()['integral'];spec['steps'][0]['caption']='One.\nTwo.'
        with self.assertRaises(SemanticError):parse_semantic_reply(json.dumps(spec))

    def test_no_salvage_or_partial_assets_on_invalid_later_stage_or_claim(self):
        base=examples()['integral']
        bad_stage=copy.deepcopy(base);bad_stage['steps'][-1]['reveal']=['area.unknown']
        bad_claim=copy.deepcopy(base);bad_claim['claims'][-1]['value']['numerator']=2
        for spec in (bad_stage,bad_claim):
            store=Mock()
            with patch('notebook_lesson_native.storyboard_assets') as encoder, \
                    patch('notebook_lesson_native.uuid.uuid4') as identity:
                with self.assertRaises(SemanticError):prepare_semantic_reply(json.dumps(spec),store)
                encoder.assert_not_called();identity.assert_not_called()
            store.equation.assert_not_called()

    def test_markdown_table_is_held_but_probability_bar_remains_plain_text(self):
        for separator in ('|---|---:|---:|---:|', '--- | :--- | ---:', '| --- | --- |'):
            raw=json.dumps(dict(v=1,mode='answer',text='A | B\n'+separator+'\n8 | 9'))
            with patch('notebook_lesson_native.storyboard_assets') as encoder:
                with self.assertRaisesRegex(SemanticError,'Markdown tables'):
                    native_semantic_bundle(raw)
                encoder.assert_not_called()
        text='P(condition | positive) = 8/17.\nEight true positives and nine false positives.'
        self.assertEqual(parse_semantic_reply(json.dumps(dict(v=1,mode='answer',text=text)))['text'],text)

    def test_reject_malformed_truncated_wrapped_and_unbounded_json(self):
        for raw in (None,'[]','null','{}','{"v":true,"mode":"answer","text":"Hi"}',
                    '{"v":1,"v":1,"mode":"answer","text":"Hi"}',
                    '{"v":1,"mode":"answer","text":NaN}',
                    '{"v":1,"mode":"answer","text":"Hi"',
                    '```json\n{"v":1,"mode":"answer","text":"Hi"}\n```',
                    '['*1500+']'*1500,' '*24001,'\ud800'):
            with self.subTest(raw=repr(raw)[:80]),self.assertRaises(SemanticError):
                parse_semantic_reply(raw)

    def test_plain_modes_reject_markup_destinations_or_invented_media(self):
        for text in ('**bold**','```code```','/tmp/private','https://example.org',
                     '<img src="x">','[[asset:x]]','a\x00b','', 'a'*1601):
            with self.subTest(text=text[:30]),self.assertRaises(SemanticError):
                parse_semantic_reply(json.dumps(dict(v=1,mode='answer',text=text)))
        for extra in ({'page':'other'},{'request':'other'},{'url':'https://example.org'}):
            with self.assertRaises(SemanticError):
                parse_semantic_reply(json.dumps(dict(v=1,mode='answer',text='Hello',**extra)))
        with self.assertRaises(SemanticError):
            parse_semantic_reply(json.dumps(dict(v=1,mode='clarify',text='a'*281)))
        for mode in ('media_request','code','',None,[]):
            with self.assertRaises(SemanticError):
                parse_semantic_reply(json.dumps(dict(v=1,mode=mode,text='No')))

    def test_a_buzz_message_names_members_and_plain_text_and_a_confirmation_is_yes_or_no(self):
        sent=parse_semantic_reply(json.dumps(dict(v=1,mode='send',to=[' My Dude'],text='Please add a second picture.')))
        self.assertEqual(sent,dict(mode='send',to=['My Dude'],text='Please add a second picture.'))
        for to in ([],['a']*4,'My Dude',[''],['@My Dude'],['x'*41],[3]):
            with self.subTest(to=to),self.assertRaises(SemanticError):
                parse_semantic_reply(json.dumps(dict(v=1,mode='send',to=to,text='Hi')))
        for text in ('**Hi**','https://example.org','a'*601,''):
            with self.subTest(text=text[:20]),self.assertRaises(SemanticError):
                parse_semantic_reply(json.dumps(dict(v=1,mode='send',to=['Dennis'],text=text)))
        with self.assertRaises(SemanticError):
            parse_semantic_reply(json.dumps(dict(v=1,mode='send',to=['Dennis'],text='Hi',channel='other')))
        self.assertEqual(parse_semantic_reply(json.dumps(dict(v=1,mode='send',to=["Day"],text='Late.',via='sms',ink='above'))),
                         dict(mode='send',to=['Day'],text='Late.',via='sms',ink='above'))
        for bad in (dict(via='whatsapp'),dict(via='imessage',to=['Day','Mom']),dict(via='sms',ink='left')):
            with self.subTest(bad=bad),self.assertRaises(SemanticError):
                parse_semantic_reply(json.dumps({**dict(v=1,mode='send',to=['Day'],text='Hi'),**bad}))
        self.assertEqual(parse_semantic_reply('{"v":1,"mode":"confirm","send":false}'),dict(mode='confirm',send=False))
        for value in ('yes',1,None):
            with self.assertRaises(SemanticError):
                parse_semantic_reply(json.dumps(dict(v=1,mode='confirm',send=value)))


if __name__=='__main__':unittest.main()
