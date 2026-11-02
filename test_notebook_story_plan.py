from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from notebook_story_examples import story_examples
from notebook_story_plan import MAX_BYTES, parse_story, validate_story, panel_packet, outline_html
from notebook_story_eval import check_story


class StoryPlanTests(unittest.TestCase):
    def setUp(self):
        self.story = story_examples()['odd-borders']

    def test_ten_panel_cross_act_reuse_without_geometry(self):
        story = validate_story(self.story)
        self.assertEqual(story, self.story)
        self.assertIsNot(story, self.story)
        packet = panel_packet(story, 'argument')
        self.assertEqual([p['id'] for p in packet['base_chain']],
                         ['general', 'across', 'down', 'odd', 'grow'])
        self.assertEqual(packet['act']['id'], 'distinguish')
        self.assertFalse(packet['geometry_resolved'])
        self.assertFalse(packet['native_validated'])
        self.assertNotIn('examples', packet_panel_ids(packet))
        self.assertNotIn('acts', packet)
        self.assertNotIn('panels', packet)
        packet['base_chain'][0]['caption'] = 'Changed packet only.'
        self.assertNotEqual(story['panels'][3]['caption'], 'Changed packet only.')

    def test_base_is_exact_snapshot_not_latest_panel(self):
        packet = panel_packet(self.story, 'examples')
        self.assertEqual([p['id'] for p in packet['base_chain']], ['one', 'two', 'three'])
        self.assertNotIn('grow', [p['id'] for p in packet['base_chain']])
        self.assertEqual(packet_panel_ids(panel_packet(self.story, 'one')), [])

    def test_rejects_missing_self_forward_and_cyclic_bases(self):
        for base in ('missing', 'one', 'two', 1, [], '../escape'):
            value = deepcopy(self.story)
            value['panels'][0]['base'] = base
            with self.subTest(base=base), self.assertRaises(ValueError):
                validate_story(value)

    def test_rejects_unknown_geometry_and_control_fields(self):
        for level in ('root', 'act', 'panel'):
            for key in ('draw', 'items', 'x', 'position', 'tool', 'path', 'url'):
                value = deepcopy(self.story)
                target = value if level=='root' else value['acts'][0] if level=='act' else value['panels'][0]
                target[key] = 'untrusted'
                with self.subTest(level=level, key=key), self.assertRaises(ValueError):
                    validate_story(value)

    def test_rejects_duplicate_ids_unused_or_out_of_order_acts(self):
        variants = []
        value = deepcopy(self.story); value['acts'][1]['id']='notice'; variants.append(value)
        value = deepcopy(self.story); value['panels'][1]['id']='one'; variants.append(value)
        value = deepcopy(self.story); value['panels'][0]['act']='absent'; variants.append(value)
        value = deepcopy(self.story); value['acts'].append(dict(id='unused',beat='No panels.')); variants.append(value)
        value = deepcopy(self.story); value['panels'][-1]['act']='notice'; variants.append(value)
        value = deepcopy(self.story); value['panels'][1]['visual_kind']={}; variants.append(value)
        for value in variants:
            with self.assertRaises(ValueError): validate_story(value)

    def test_intent_can_change_without_changing_the_base_snapshot(self):
        value = deepcopy(self.story)
        value['panels'][1]['visual_kind'] = 'graph'
        value['panels'][2]['visual_kind'] = 'comparison'
        self.assertEqual(validate_story(value), value)
        packet = panel_packet(value, value['panels'][2]['id'])
        self.assertEqual(packet['panel']['visual_kind'], 'comparison')
        self.assertEqual(packet['base_chain'][-1]['visual_kind'], 'graph')

    def test_descriptive_visual_kind_never_selects_a_renderer(self):
        for description in ('region', 'arrow', 'growing lattice', 'new visual metaphor'):
            value = deepcopy(self.story)
            value['panels'][0]['visual_kind'] = description
            self.assertEqual(validate_story(value), value)
        for description in ('', 'x'*49, 'https://example.org', '<script>', ['graph']):
            value = deepcopy(self.story); value['panels'][0]['visual_kind'] = description
            with self.assertRaises(ValueError): validate_story(value)

    def test_picture_lookahead_excludes_other_roots_and_contains_no_geometry(self):
        packet = panel_packet(self.story, 'one')
        self.assertEqual([p['id'] for p in packet['picture_plan']], ['one','two','three','examples'])
        self.assertNotIn('general', [p['id'] for p in packet['picture_plan']])
        self.assertEqual(set(packet['picture_plan'][0]), {'id','base','new_idea'})
        future = panel_packet(self.story, 'general')['picture_plan']
        self.assertIn('argument', [p['id'] for p in future])
        packet['picture_plan'][1]['new_idea'] = 'Changed local packet only.'
        self.assertNotEqual(self.story['panels'][1]['new_idea'], packet['picture_plan'][1]['new_idea'])

    def test_bounds_and_plain_text(self):
        for text in ('x'*181, 'https://example.org', '/private/file',
                     '```json', '<script>bad</script>', '**bold**', 'two\nlines'):
            value = deepcopy(self.story); value['panels'][0]['caption']=text
            with self.subTest(text=text), self.assertRaises(ValueError): validate_story(value)
        value = deepcopy(self.story); value['panels'][0]['caption']=' '.join(['word']*12)
        self.assertEqual(validate_story(value), value)
        for field in ('acts', 'panels'):
            value = deepcopy(self.story); value[field]=[]
            with self.assertRaises(ValueError): validate_story(value)
        value = deepcopy(self.story); value['panels']*=2
        with self.assertRaises(ValueError): validate_story(value)
        value = deepcopy(self.story); value['v']=True
        with self.assertRaises(ValueError): validate_story(value)

    def test_caption_preserves_short_sentences_independent_of_word_segmentation(self):
        for text in ('The inverse would send y to two inputs, so it is not a function.',
                     'The next border has n + (n − 1) = 2n − 1 tiles.',
                     'x'*180, '字'*180):
            value=deepcopy(self.story)
            value['panels'][0]['caption']=text
            original=deepcopy(value)
            checked=validate_story(value)
            self.assertEqual(checked,original)
            self.assertEqual(value,original)
            self.assertEqual(panel_packet(value,value['panels'][0]['id'])['panel']['caption'],text)

    def test_json_is_complete_finite_unique_and_bounded(self):
        self.assertEqual(parse_story(json.dumps(self.story)), self.story)
        for raw in ('{"v":1,"v":1}', '{"v":NaN}', '[', '[]', 'null',
                    ' '*MAX_BYTES+'{}', '\ud800', '['*1100+']'*1100):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError): parse_story(raw)
        with self.assertRaises(ValueError): panel_packet(self.story, 'missing')

    def test_context_digest_stable_but_sensitive_to_story(self):
        a = panel_packet(self.story, 'one')
        b = panel_packet(dict(reversed(list(self.story.items()))), 'one')
        self.assertEqual(a['story_sha256'], b['story_sha256'])
        value = deepcopy(self.story); value['audience']='An older student'
        self.assertNotEqual(a['story_sha256'], panel_packet(value, 'one')['story_sha256'])

    def test_outline_is_explicitly_not_drawing_or_quality_evidence(self):
        value = deepcopy(self.story); value['audience']='A & B'
        page = outline_html(value)
        self.assertIn('A &amp; B', page)
        self.assertEqual(page.count('<article '), 10)
        self.assertIn('Narrative outline only.', page)
        self.assertIn('href="#three"', page)
        self.assertNotIn('<svg', page)
        self.assertNotIn('<script', page)

    def test_checker_preserves_draft_and_never_overwrites_or_emits_ink(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); source = root/'source.json'; dest = root/'review'
            raw = json.dumps(self.story).encode(); source.write_bytes(raw)
            result = check_story(source, dest)
            self.assertTrue(result['story_valid'])
            self.assertFalse(result['native_validated'])
            self.assertFalse(result['tablet_proven'])
            self.assertEqual((dest/'story.txt').read_bytes(), raw)
            self.assertEqual(result['model_calls'], 0)
            self.assertEqual(len(result['panels']), 10)
            self.assertEqual(list(dest.glob('*.rm')), [])
            with self.assertRaises(FileExistsError): check_story(source, dest)
            source.write_text('{')
            rejected = root/'rejected'; result = check_story(source, rejected)
            self.assertFalse(result['story_valid'])
            self.assertFalse((rejected/'outline.html').exists())
            self.assertTrue((rejected/'result.json').exists())

    def test_panel_name_cannot_overwrite_report(self):
        value = deepcopy(self.story)
        value['panels'][-1]['id'] = 'result'
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)/'input.json'; source.write_text(json.dumps(value))
            dest = Path(root)/'output'; result = check_story(source, dest)
            self.assertEqual(result['panels'][-1]['context'], 'panel-result.json')
            self.assertEqual(json.loads((dest/'result.json').read_text()), result)
            self.assertEqual(json.loads((dest/'panel-result.json').read_text())['panel']['id'], 'result')


def packet_panel_ids(packet):
    return [p['id'] for p in packet['base_chain']]


if __name__ == '__main__':
    unittest.main()
