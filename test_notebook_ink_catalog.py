import copy
import tempfile
import unittest

from notebook_drawing import compile_storyboard
from notebook_ink_catalog import InkCatalog
from notebook_media import AssetStore, notebook_blocks, notebook_content
from notebook_storyboard import integral_storyboard
from notebook_stroke_asset import storyboard_assets


def manifest(author=None):
    plan = integral_storyboard()
    assets = storyboard_assets(plan, author=author, ink_labels=True)
    return {'version': 1, 'scenes': {plan['scene']: {
        'digest': compile_storyboard(plan)['digest'], 'stages': {
            a['stage']: dict(source_doc='4a48e85d-40e3-437a-92c5-c411a8bff83e',
                source_page=['ef846d65-f19a-4870-af4e-f13435f7b5c1',
                             '5cbfac00-92bd-4491-89d2-071c040d5f37',
                             'add00534-8265-43b9-9b06-10c8cdb6aeb8'][i],
                sha256=a['sha256'], stroke_count=a['stroke_count'], point_count=a['point_count'],
                bounds=a['bounds'], labels=a['annotations_rendered_as']) for i,a in enumerate(assets)}}}}


class InkCatalogTest(unittest.TestCase):
    def test_catalog_is_immutable_and_selects_only_authored_registered_stages(self):
        raw = manifest()
        catalog = InkCatalog(raw)
        raw['scenes'].clear()
        first = catalog.get('unit-square-integral','see')
        self.assertEqual(first['stage_index'],0)
        self.assertEqual(first['stage_count'],3)
        first['bounds'][0] = -500
        self.assertGreaterEqual(catalog.get('unit-square-integral','see')['bounds'][0],0)
        for scene,stage in (('file:///private','see'),('unit-square-integral','../../page'),('unit-square-integral','conclude')):
            with self.assertRaises(ValueError):
                catalog.get(scene,stage)

    def test_invalid_manifest_program_or_geometry_cannot_be_registered(self):
        raw = manifest()
        for mutate in (lambda m:m.update(version=True),
                       lambda m:m['scenes']['unit-square-integral'].update(digest='0'*64),
                       lambda m:m['scenes']['unit-square-integral']['stages']['see'].update(bounds=[0,0,10000,10000]),
                       lambda m:m['scenes']['unit-square-integral']['stages']['see'].update(labels='silent-raster'),
                       lambda m:m['scenes']['unit-square-integral']['stages']['see'].update(source_page='../../page')):
            changed = copy.deepcopy(raw)
            mutate(changed)
            with self.assertRaises(ValueError):
                InkCatalog(changed)

    def test_ordered_native_prose_ink_math_sequence_strips_markers_only_when_provisioned(self):
        catalog = InkCatalog(manifest())
        raw = ('## See the area\nThe graph is y = x².\n[[notebook-ink:unit-square-integral:see]]\n'
               '## Measure it\nAdd left rectangles.\n[[notebook-ink:unit-square-integral:measure]]\n'
               '## Notice the gaps\nFiner slices improve the estimate.\n[[notebook-ink:unit-square-integral:notice]]\n'
               '```math\n\\int_0^1 x^2\\,dx=\\frac{1}{3}\n```\nThe exact area is one third.')
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            blocks = notebook_blocks(raw,store,catalog)
            self.assertEqual([b['kind'] for b in blocks],['text','ink','text','ink','text','ink','media','text'])
            self.assertTrue(all('[[notebook-' not in b.get('text','') for b in blocks))
            self.assertEqual([b['stage_index'] for b in blocks if b['kind']=='ink'],[0,1,2])
            plain,media = notebook_content(raw,store,catalog)
            self.assertNotIn('[[notebook-',plain)
            self.assertEqual(len(media),1)
            with self.assertRaises(ValueError):
                notebook_blocks(raw,store)  # no raw marker fallback on old/unprovisioned clients
            for invalid in ('[[notebook-ink:unit-square-integral:measure]]',
                            '[[notebook-ink:unit-square-integral:see]]\n[[notebook-ink:unit-square-integral:see]]',
                            '[[notebook-ink:file:///private:see]]'):
                with self.assertRaises(ValueError):
                    notebook_blocks(invalid,store,catalog)


if __name__ == '__main__':
    unittest.main()
