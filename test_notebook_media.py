import io
import os
import tempfile
import unittest
from PIL import Image
from notebook_media import (AssetStore, Equation, render_equation, notebook_content,
                            notebook_paragraph_styles, notebook_blocks)


class EquationTest(unittest.TestCase):
    def test_unicode_numeric_scripts_match_explicit_grouped_equations(self):
        for unicode, explicit in (
                ('∫₀¹ x² dx = 1/3', r'\int _{0}^{1} x^{2} dx = 1/3'),
                ('x¹² + a₁₀', 'x^{12} + a_{10}'),
                ('x⁻² + y₋₁', 'x^{-2} + y_{-1}'),
                ('∫₋₁¹ x³ dx = 0', r'\int _{-1}^{1} x^{3} dx = 0')):
            with self.subTest(source=unicode):
                actual, expected = render_equation(unicode), render_equation(explicit)
                self.assertEqual(actual.size, expected.size)
                self.assertEqual(actual.tobytes(), expected.tobytes())
        for invalid in ('¹²', 'x^2³', 'x₁_2', 'xᵉ'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                render_equation(invalid)

    def test_multiplication_sign_is_geometric_and_matches_tex(self):
        literal = render_equation('20 × 2 = 40')
        self.assertEqual(literal.tobytes(), render_equation(r'20 \times 2 = 40').tobytes())
        symbol = Equation('×').parse().image
        self.assertLess(symbol.getextrema()[0], 20)
        self.assertNotEqual(symbol.tobytes(), Equation('x').parse().image.tobytes())

    def test_relations_and_spacing_from_unedited_model_evaluation(self):
        for command, literal in ((r'\approx', '≈'), (r'\Rightarrow', '⇒')):
            self.assertEqual(render_equation(command).tobytes(), render_equation(literal).tobytes())
            box = Equation(command).parse()
            self.assertLess(box.image.getextrema()[0], 20)
            self.assertNotEqual(box.image.tobytes(), Equation('=').parse().image.tobytes())
        for command, ems in ((r'\quad', 1), (r'\qquad', 2)):
            box = Equation(command).parse()
            self.assertEqual(box.image.width, 64*ems)
            self.assertEqual(box.image.getextrema(), (255,255))
        for literal in ('%', '$'):
            self.assertEqual(render_equation('\\'+literal).tobytes(), render_equation(literal).tobytes())
        for source in (r'100(1.1)^3=133.10,\qquad 100+3(10)=130',
                       r'P(condition|positive)=\frac{8}{8+9}=\frac{8}{17}\approx47\%',
                       r'3^2+4^2=c^2\Rightarrow25=c^2\Rightarrow c=5'):
            self.assertLessEqual(render_equation(source).width,1100)
        for source in (r'\qquad\input{file}', r'\approximate', r'\Rightarrow\write18{x}'):
            with self.assertRaises(ValueError):
                render_equation(source)

    def test_elementary_ellipsis_has_three_dots_without_font_fallback(self):
        centered, low = Equation(r'\cdots').parse(), Equation(r'\ldots').parse()
        for command, literal in ((r'\cdots','⋯'),(r'\ldots','…')):
            self.assertEqual(render_equation(command).tobytes(),render_equation(literal).tobytes())
            image = Equation(command).parse().image
            columns = [any(image.getpixel((x,y)) < 110 for y in range(image.height)) for x in range(image.width)]
            runs = sum(value and (i == 0 or not columns[i-1]) for i,value in enumerate(columns))
            self.assertEqual(runs,3)
        def first_dark_row(box):
            return next(y for y in range(box.image.height) if any(box.image.getpixel((x,y)) < 110 for x in range(box.image.width)))
        self.assertLess(first_dark_row(centered),first_dark_row(low))
        self.assertGreater(render_equation(r'1+3+5+\cdots+(2n-1)=n^2').width,100)

    def test_literal_units_do_not_interpret_tex_commands(self):
        self.assertGreater(render_equation(r'g=9.8\ \text{m/s}^2').width, 100)
        for source in (r'\text{\input{secret}}', r'\text{a{b}}', r'\text{'+'a'*121+'}'):
            with self.assertRaises(ValueError):
                render_equation(source)

    def test_riemann_sum_symbols_have_visible_geometry(self):
        sigma = Equation(r'\sum').parse()
        self.assertGreater(sigma.image.height, Equation('x').parse().image.height)
        for symbol, literal in ((r'\Delta', 'Δ'), (r'\sum', 'Σ')):
            self.assertEqual(render_equation(symbol).tobytes(), render_equation(literal).tobytes())
        image = render_equation(r'\sum x_i^2\,\Delta x')
        self.assertGreater(image.width, 100)
        self.assertLessEqual(image.width, 1100)

    def test_line_wrapped_integral_is_ordinary_math_whitespace(self):
        source = "\\int_0^1 x^2\\,dx\n= \\left[\\frac{x^3}{3}\\right]_0^1\n= \\frac{1}{3}"
        multiline = render_equation(source)
        single = render_equation(source.replace('\n', ' '))
        self.assertEqual(multiline.tobytes(), single.tobytes())

    def test_fraction_and_scripts_have_real_vertical_layout(self):
        flat = Equation("x+1").parse()
        fraction = Equation(r"\frac{x+1}{3}").parse()
        power = Equation("x^{2}").parse()
        self.assertGreater(fraction.image.height, flat.image.height)
        self.assertGreater(power.image.width, Equation("x").parse().image.width)
        self.assertGreater(fraction.baseline, 0)

    def test_definite_integral_and_radical(self):
        image = render_equation(r"\int_0^1 x^2\,dx = \left[\frac{x^3}{3}\right]_0^1 = \frac{1}{3}")
        self.assertLessEqual(image.width, 1100)
        self.assertGreater(image.height, 100)
        self.assertEqual(image.getpixel((0, 0)), 255)
        self.assertIsNotNone(render_equation(r"\sqrt {x^2+1}").getbbox())

    def test_rejects_unsupported_or_unbounded_notation(self):
        for text in (r"\input{secret}", r"\unknown{x}", "{x", "x}", "^2", "x^", "{"*30+"x"+"}"*30, "x"*2001):
            with self.subTest(text=text[:30]), self.assertRaises(ValueError):
                render_equation(text)


class AssetTest(unittest.TestCase):
    def test_actual_gravity_units_remain_editable_native_text(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            raw = ('## During the fall\nIgnoring air resistance, the apple accelerates at about '
                   r'\(9.8\ \text{m/s}^2\). Its speed increases by roughly '
                   r'\(9.8\ \text{m/s}\) each second.')
            blocks = notebook_blocks(raw, store)
            self.assertEqual([b['kind'] for b in blocks], ['text'])
            self.assertIn('9.8 m/s²', blocks[0]['text'])
            self.assertIn('9.8 m/s each second', blocks[0]['text'])
            self.assertEqual(notebook_content(raw, store)[1], [])
            self.assertNotIn('\\', blocks[0]['text'])

    def test_actual_rectangle_reply_prepares_before_any_insertion(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            raw = ('The rectangles approximate the area under ' + r'\(y=x^2\).' + '\n\n'
                   r'Each width is \(\Delta x\), and its height is \(x_i^2\).' '\n\n'
                   r'\[\sum x_i^2\,\Delta x\]' '\nThe sum approaches\n'
                   r'\[\int_0^1 x^2\,dx=\frac{1}{3}.\]')
            blocks = notebook_blocks(raw, store)
            self.assertEqual([b['kind'] for b in blocks], ['text', 'media', 'text', 'media'])
            self.assertIn('y=x²', blocks[0]['text'])
            self.assertIn('Δx', blocks[0]['text'])
            self.assertIn('xᵢ²', blocks[0]['text'])
            plain, assets = notebook_content(raw, store)
            self.assertEqual(len(assets), 2)
            self.assertNotIn('\\', plain)
            for raw in (r'\(x^2^3\)', r'\(x_i_j\)', r'\(\Deltaevil\)'):
                with self.assertRaises(ValueError):
                    notebook_blocks(raw, store)

    def test_small_inline_math_stays_native_between_display_equation_and_explanation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            raw = ('## Form\n' + r'\[\int_0^x t^2\,dt=\frac{x^3}{3}\]' + '\n## Why\n'
                   r'The antiderivative of \(t^2\) is \(t^3/3\). Evaluating from 0 to \(x\) gives \(x^3/3\).')
            blocks = notebook_blocks(raw, store)
            self.assertEqual([b['kind'] for b in blocks], ['text', 'media', 'text'])
            self.assertEqual(blocks[-1]['text'], 'Why\nThe antiderivative of t² is t³/3. Evaluating from 0 to x gives x³/3.')
            self.assertEqual(blocks[-1]['styles'], [{'paragraph': 0, 'style': 'subheading'}])
            plain, assets = notebook_content(raw, store)
            self.assertEqual(len(assets), 1)
            self.assertNotIn('\\(', plain)
            self.assertEqual(notebook_content(r'Terms \(x_{12}\), \(t^{23}/3\).', store), ('Terms x₁₂, t²³/3.', []))
            # Grouping-dependent expressions must not be silently flattened.
            for complex_term in (r'\frac{x+1}{2}', 'x/(y+1)', r'\sqrt{x}', 'x^{-2}'):
                _, images = notebook_content('Term ' + r'\(' + complex_term + r'\)', store)
                self.assertEqual(len(images), 1)

    def test_ordered_solution_keeps_explanation_next_to_its_equation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            raw = ('## Antiderivative\r\nUse the power rule.\r\n'
                   r'\[F(x)=\frac{x^3}{3}\]' '\r\n\r\n'
                   '## Result\r\nEvaluate at both limits.\r\n'
                   r'\[F(1)-F(0)=\frac{1}{3}\]' '\r\nThat is the area.')
            blocks = notebook_blocks(raw, store)
            self.assertEqual([block['kind'] for block in blocks],
                             ['text', 'media', 'text', 'media', 'text'])
            self.assertEqual(blocks[0], {'kind': 'text', 'text': 'Antiderivative\nUse the power rule.',
                                        'styles': [{'paragraph': 0, 'style': 'subheading'}]})
            self.assertEqual(blocks[2]['text'], 'Result\nEvaluate at both limits.')
            self.assertEqual(blocks[2]['styles'], [{'paragraph': 0, 'style': 'subheading'}])
            self.assertEqual(blocks[4]['text'], 'That is the area.')
            self.assertEqual(blocks[1]['asset'], store.equation(r'F(x)=\frac{x^3}{3}')['asset'])
            self.assertEqual(blocks[3]['asset'], store.equation(r'F(1)-F(0)=\frac{1}{3}')['asset'])

    def test_ordered_blocks_cover_adjacent_math_and_every_supported_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            raw = r'Before \(\frac{x}{2}\)' + '\n```math\n1+2\n```\n' + r'\[3\]$$4$$ After'
            blocks = notebook_blocks(raw, store)
            self.assertEqual([block['kind'] for block in blocks], ['text'] + ['media']*4 + ['text'])
            self.assertEqual(blocks[0]['text'], 'Before')
            self.assertEqual(blocks[-1]['text'], 'After')
            self.assertEqual([b['asset'] for b in blocks[1:-1]],
                             [store.equation(s)['asset'] for s in (r'\frac{x}{2}', '1+2', '3', '4')])
            self.assertEqual(notebook_blocks('  ', store), [])
            self.assertEqual(notebook_blocks('Hello 🐕.', store),
                             [{'kind': 'text', 'text': 'Hello 🐕.', 'styles': []}])

    def test_ordered_registered_images_preserve_position_and_are_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            data = io.BytesIO()
            Image.new('L', (32, 32), 180).save(data, 'PNG')
            asset = store.put(data.getvalue(), 'diagram')['asset']
            marker = '[[notebook-asset:' + asset + ']]'
            blocks = notebook_blocks('Before\n' + marker + '\nAfter\n' + marker, store)
            self.assertEqual([b['kind'] for b in blocks], ['text', 'media', 'text'])
            self.assertEqual(blocks[1], {'kind': 'media', 'asset': asset})
            for raw in ('Good prose\n[[notebook-media-pending]]',
                        'Good prose\n[[notebook-asset:/tmp/no.png]]',
                        'Good prose\n' + r'\[\input{secret}\]',
                        r'\[1\]'*7):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    notebook_blocks(raw, store)
            with self.assertRaises(FileNotFoundError):
                notebook_blocks('Good prose\n[[notebook-asset:' + '0'*64 + ']]', store)

    def test_explicit_heading_styles_follow_cleaned_paragraphs_not_character_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            raw = 'An idea 🐕.\r\n\r\n## **Why it works**\r\nBody.\r\n\r\n## Result\r\nDone.'
            plain, assets = notebook_content(raw, store)
            self.assertEqual(assets, [])
            self.assertNotIn('#', plain)
            self.assertNotIn('\r', plain)
            self.assertEqual(notebook_paragraph_styles(raw, plain),
                             [{'paragraph': 1, 'style': 'subheading'}, {'paragraph': 3, 'style': 'subheading'}])
            self.assertEqual(notebook_paragraph_styles('## Repeated\nRepeated', 'Repeated\nRepeated'), [])
            self.assertEqual(notebook_paragraph_styles('```\n## Not a heading\n```', 'Not a heading'), [])
            self.assertEqual(notebook_paragraph_styles('ALL CAPS\nShort sentence.', 'ALL CAPS\nShort sentence.'), [])

    def test_native_headings_do_not_accumulate_markdown_blank_paragraphs(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            raw = 'Opening paragraph.\n\n## Evaporation\n\nWarm water rises.\n\nAnother ordinary paragraph.\n\n## Rain\n\nDrops fall.'
            plain, assets = notebook_content(raw, store)
            self.assertEqual(plain, 'Opening paragraph.\nEvaporation\nWarm water rises.\n\nAnother ordinary paragraph.\nRain\nDrops fall.')
            self.assertEqual(notebook_blocks(raw, store)[0]['text'], plain)
            self.assertEqual(notebook_paragraph_styles(raw, plain),
                             [{'paragraph': 1, 'style': 'subheading'}, {'paragraph': 5, 'style': 'subheading'}])
            # A repeated title cannot be styled safely, so retain its spacing.
            repeated = '## Same\n\nBody.\n\nSame'
            self.assertEqual(notebook_content(repeated, store)[0], 'Same\n\nBody.\n\nSame')

    def test_registered_image_reference_is_not_raw_markup_or_a_path(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            data = io.BytesIO()
            Image.new("L", (32, 32), 180).save(data, "PNG")
            asset = store.put(data.getvalue(), "illustration")["asset"]
            plain, assets = notebook_content("A dog.\n[[notebook-asset:" + asset + "]]", store)
            self.assertEqual(plain, "A dog.")
            self.assertEqual(assets, [asset])
            for invalid in ("[[notebook-asset:/tmp/a.png]]", "[[notebook-media-pending]]"):
                with self.assertRaises(ValueError):
                    notebook_content(invalid, store)
            with self.assertRaises(FileNotFoundError):
                notebook_content("[[notebook-asset:" + "0"*64 + "]]", store)

    def test_reply_math_becomes_assets_without_literal_markup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            for wrapped in (r"\[\frac{1}{3}\]", r"$$\frac{1}{3}$$",
                            "```math\n\\frac{1}{3}\n```", r"\(\frac{1}{3}\)"):
                plain, assets = notebook_content("## Answer\n**Result:** " + wrapped, store)
                self.assertEqual(plain, "Answer\nResult:")
                self.assertEqual(len(assets), 1)
                self.assertEqual(assets[0], store.equation(r"\frac{1}{3}")["asset"])
            with self.assertRaises(ValueError):
                notebook_content(r"\[\input{file}\]", store)
            self.assertEqual(notebook_content("Hi!", store), ("Hi!", []))

    def test_image_kinds_share_bounded_integrity_checked_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            data = io.BytesIO()
            Image.new("RGBA", (1800, 900), (0, 0, 0, 0)).save(data, "PNG")
            for kind in ("photo", "illustration", "diagram"):
                asset = store.put(data.getvalue(), kind)
                self.assertEqual(asset["kind"], kind)
                self.assertEqual(asset["width"], 1100)
                with Image.open(io.BytesIO(store.get(asset["asset"]))) as image:
                    self.assertEqual(image.mode, "L")
                    self.assertEqual(image.getextrema(), (255, 255))
                    self.assertNotIn("exif", image.info)
            with self.assertRaises(ValueError):
                store.get("../../outside")
            with self.assertRaises(ValueError):
                store.put(data.getvalue(), "unrecognized")
            with open(os.path.join(directory, asset["asset"] + ".png"), "ab") as stream:
                stream.write(b"tampered")
            with self.assertRaises(ValueError):
                store.get(asset["asset"])

    def test_equation_asset_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(directory)
            first = store.equation(r"\frac{1}{3}")
            self.assertEqual(first, store.equation(r"\frac{1}{3}"))
            self.assertEqual(first["kind"], "equation")
            self.assertTrue(store.get(first["asset"]).startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
