import unittest
import copy
import json
import uuid
from unittest.mock import Mock
from notebook_equation_ink import equation_plan, fraction, glyph, Equation, RENDERER
from notebook_ink_playback import playback_assets, validate_playback
from notebook_drawing import preview_svg
from notebook_media import render_equation
from notebook_lesson_native import (prepare_semantic_reply, _bundle_from_compiled_lesson,
                                    lesson_source_archive, inspect_source_archive)
from notebook_semantic_examples import examples
from notebook_stroke_asset import validate_native_ink_budget


class EquationInkTests(unittest.TestCase):
    def test_fraction_inequality_is_ordered_native_ink(self):
        plan=equation_plan(r'\frac{2}{3}>\frac{3}{5}')
        asset=playback_assets(plan)[0]
        self.assertEqual(asset['stroke_count'],7)  # 2, bar, 3, >, 3, bar, 5
        self.assertLess(asset['point_count'],3000)
        self.assertLess(asset['playback']['duration_ms'],30000)
        validate_playback(asset,asset['data'])
        svg=preview_svg(plan)
        self.assertNotIn('<image',svg)
        self.assertNotIn('<text',svg)
        self.assertEqual(svg.count('<polyline'),7)

    def test_greek_letters_are_written_by_the_pen_and_drawn_in_the_typed_equation(self):
        for source in (r'\lambda = c/f', r'A = \pi r^2', 'α + β = γ', r'\frac{\Delta\theta}{\Delta t} = \omega'):
            asset=playback_assets(equation_plan(source))[0]
            validate_playback(asset,asset['data'])
            image=render_equation(source)
            self.assertLess(image.getextrema()[0],128)
        self.assertNotEqual(render_equation(r'\alpha').tobytes(),render_equation(r'\beta').tobytes())
        with self.assertRaisesRegex(ValueError,'unsupported equation command'):
            equation_plan(r'\aleph')

    def test_fraction_layout_does_not_flatten_or_drop_grouping(self):
        n,d=glyph('2',30),glyph('3',30)
        f=fraction(n,d,36)
        numerator,bar,denominator=f.paths
        self.assertLess(max(y for _,y in numerator),bar[0][1])
        self.assertGreater(min(y for _,y in denominator),bar[0][1])
        self.assertEqual(bar[0][1],bar[1][1])

    def test_existing_bounded_math_grammar(self):
        for source in (r'\int_0^1 x^2\,dx=\frac{1}{3}',r'1+3+5+7=4^2=16',
                       r'\sqrt{x^2+1}',r'\sum_{i=1}^n i',r'2\times3\approx6',
                       r'x\Rightarrow y',r'1+2+\cdots+n',r'\text{Area}=\frac{1}{3}'):
            with self.subTest(source=source):
                asset=playback_assets(equation_plan(source))[0]
                validate_playback(asset,asset['data'])
                self.assertLessEqual(asset['stroke_count'],64)
                self.assertLessEqual(asset['point_count'],3000)
                # The legacy raster backend continues to support the same input.
                self.assertGreater(render_equation(source).width,0)

    def test_fail_closed_before_any_asset_or_device_io(self):
        for source in ('',r'\input{/tmp/a}',r'\frac{1}',r'x^2^3',r'\unknown',
                       'x'*401,'x'*40,'ℵ','@',r'\frac{'*18+'1'+'}{2}'*18):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):equation_plan(source)

    def test_deterministic_geometry(self):
        self.assertEqual(equation_plan(r'\frac{2}{3}>\frac{3}{5}'),
                         equation_plan(r'\frac{2}{3}>\frac{3}{5}'))

    def test_equation_after_captions_before_takeaway_without_raster_store(self):
        store=Mock()
        bundle=prepare_semantic_reply(json.dumps(examples()['fractions-variant']),store,
                                      playback=True,pen_equations=True)
        self.assertEqual(len(bundle['sources']),6)
        blocks=bundle['blocks']
        self.assertEqual([b['kind'] for b in blocks],['text']+['text','ink']*5+['ink','text'])
        equation=blocks[-2]
        self.assertEqual(equation['role'],'equation')
        self.assertNotEqual(equation['scene'],blocks[2]['scene'])
        self.assertEqual((equation['stage_index'],equation['stage_count']),(0,1))
        self.assertTrue(blocks[-1]['text'].startswith('Takeaway:'))
        store.equation.assert_not_called()
        validate_playback(equation,bundle['sources'][-1]['data'])

    def six_step_plan(self, points=2):
        plan=equation_plan(r'1=1')
        plan.update(scene='six-steps',equation=r'\frac{2}{3}>\frac{3}{5}',takeaway='Compare the amounts.')
        plan['stages']=[dict(id=f'step-{i}',title='Step',text='Add one mark.',annotations=[],
                             paths=[[(10+i,20)]*points]) for i in range(6)]
        return plan

    def test_six_steps_plus_math_archive_keeps_whole_lesson_limits(self):
        bundle=_bundle_from_compiled_lesson(self.six_step_plan(),playback=True,pen_equations=True)
        self.assertEqual(len(bundle['sources']),7)
        parent=str(uuid.uuid4())
        doc,data=lesson_source_archive(bundle,{'cPages':{},'fileType':'notebook'},parent)
        equation=bundle['blocks'][-2]
        self.assertEqual(inspect_source_archive(data,doc,parent,equation['source_page'],equation['stroke_count']),
                         equation['sha256'])
        with self.assertRaisesRegex(ValueError,'whole-lesson'):
            _bundle_from_compiled_lesson(self.six_step_plan(2000),playback=True,pen_equations=True)
        for mutation in ('unmarked','extra','early','role'):
            bad=copy.deepcopy(bundle['blocks'])
            if mutation=='unmarked':bad[-2].pop('role')
            if mutation=='extra':bad.append(copy.deepcopy(bad[-2]))
            if mutation=='early':bad.insert(0,bad.pop(-2))
            if mutation=='role':next(b for b in bad if b['kind']=='ink')['role']='anything'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_native_ink_budget(bad)

    def test_no_pen_equations_without_playback(self):
        with self.assertRaisesRegex(ValueError,'playback'):
            _bundle_from_compiled_lesson(self.six_step_plan(),pen_equations=True)


if __name__=='__main__':unittest.main()
