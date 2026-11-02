import math
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from notebook_glyph_paths import _graph, glyph_paths, select_paths
from notebook_plotter_font import GLYPHS, label_paths, original_glyphs, font_budget_fallback
from notebook_pen_budget import NativePenBudgetError
from notebook_lesson import compile_lesson
from notebook_storyboard import _dense


def cost(paths, scale):
    points = sum(1+sum(max(1,math.ceil(math.dist(a,b)*scale/2))
                      for a,b in zip(p,p[1:])) for p in paths)
    return points*9+len(paths)*70


class ContinuousGlyphTest(unittest.TestCase):
    def test_every_builtin_glyph_preserves_exact_segment_union(self):
        for char,encoded in GLYPHS.items():
            with self.subTest(char=char):
                _,edges,_ = _graph(encoded)
                original,candidate = glyph_paths(encoded)
                # Re-split both representations using the exact rational
                # glyph coordinates, not a tolerant screenshot comparison.
                new = ';'.join(' '.join(f'{x},{y}' for x,y in path) for path in candidate)
                _,actual,_ = _graph(new)
                self.assertEqual(actual, edges)
                self.assertLessEqual(len(candidate),len(original))
                self.assertEqual((original,candidate),glyph_paths(encoded))

    def test_fewer_lifts_only_when_no_more_estimated_pen_time(self):
        improvements = 0
        for encoded in GLYPHS.values():
            original,_ = glyph_paths(encoded)
            for size in (12,18,20,24,28):
                chosen = select_paths(encoded,size/6)
                self.assertLessEqual(cost(chosen,size/6),cost(original,size/6))
                self.assertLessEqual(len(chosen),len(original))
                if chosen != original:
                    self.assertLess(len(chosen),len(original)); improvements += 1
        self.assertGreater(improvements,0)
        # Crossed strokes should not be joined when retracing costs more.
        original,_ = glyph_paths(GLYPHS['X'])
        self.assertEqual(select_paths(GLYPHS['X'],28/6),original)

    def test_disconnected_dots_and_letters_are_not_bridged(self):
        for char in ('i','j',':','!','?'):
            original,candidate = glyph_paths(GLYPHS[char])
            self.assertEqual(len(candidate),len(original))
            self.assertEqual(select_paths(GLYPHS[char],3),original)
        single,advance = label_paths('n',18)
        pair,width = label_paths('nn',18)
        self.assertEqual(len(pair),2*len(single))
        self.assertAlmostEqual(width,2*advance)
        self.assertEqual(pair[:len(single)],single)
        self.assertEqual(pair[len(single):],
                         [[(x+advance,y) for x,y in path] for path in single])

    def test_bounds_and_advances_preserved_at_all_label_sizes(self):
        for char,encoded in GLYPHS.items():
            original,_ = glyph_paths(encoded)
            for size in (12,18,28):
                paths,width = label_paths(char,size)
                before = [(x*size/6,y*size/6) for p in original for x,y in p]
                after = [p for path in paths for p in path]
                for axis in (0,1):
                    self.assertAlmostEqual(min(p[axis] for p in before),min(p[axis] for p in after))
                    self.assertAlmostEqual(max(p[axis] for p in before),max(p[axis] for p in after))
                self.assertAlmostEqual(width,5.4*size/6)

    def test_label_heavy_stage_fits_actual_existing_native_limits(self):
        label = 'Required input'
        old_count = sum(len(GLYPHS[c].split(';')) for c in label if c != ' ')*3
        self.assertGreater(old_count,64)
        steps = [dict(caption='Start with a mark.',draw=[
            dict(op='circle',center=[30,30],radius=10)]),
            dict(caption='Add the labels.',draw=[
                dict(op='label',at=[100,y],text=label,size=18) for y in (100,180,260)]),
            dict(caption='Conclude with a mark.',draw=[
                dict(op='circle',center=[570,330],radius=10)])]
        plan = compile_lesson(steps,'The original text and geometry are preserved.')
        for stage in plan['stages']:
            self.assertLessEqual(len(stage['paths']),64)
            self.assertLessEqual(stage['points'],3000)
            self.assertLessEqual(stage['estimated_pen_seconds'],30)
        # Actual stroke count remains enforced; this is not semantic batching.
        paths,_ = label_paths(label,18)
        with self.assertRaises(ValueError): _dense(paths*10)

    def test_static_font_compiler_is_bounded(self):
        for bad in ('', '0,0', '0,0 0,0', '0,0 1,1;'*100):
            with self.assertRaises(ValueError): glyph_paths(bad)
        self.assertEqual(glyph_paths.cache_info().maxsize,128)

    def test_dense_stage_keeps_original_paths_instead_of_regressing_point_cap(self):
        steps = [dict(caption='A dense diagram with labels.',draw=[
            dict(op='polyline',points=[[20 if i%2==0 else 570,200+i*10] for i in range(10)]),
            dict(op='label',at=[20,60],text='H'*16,size=18)]),
            dict(caption='A second mark.',draw=[dict(op='circle',center=[500,40],radius=10)]),
            dict(caption='A third mark.',draw=[dict(op='circle',center=[560,40],radius=10)])]
        with original_glyphs():
            expected = compile_lesson(steps,'Keep the actual resource cap.')
        actual = compile_lesson(steps,'Keep the actual resource cap.')
        self.assertEqual(actual,expected)
        self.assertEqual(actual['stages'][0]['points'],2926)  # the hand-drawn polyline's dither
        self.assertEqual(len(actual['stages'][0]['paths']),49)
        from notebook_lesson_native import native_semantic_bundle
        spec=dict(v=1,mode='lesson',intent='Explain a dense drawing',scene={'family':'drawing'},
                  steps=steps,claims=[],takeaway='Keep the actual resource cap.')
        bundle=native_semantic_bundle(json.dumps(spec),playback=True)
        self.assertEqual(bundle['plan']['stages'],expected['stages'])

    def test_only_resource_errors_retry_and_nested_compilation_retries_once(self):
        calls=[]
        @font_budget_fallback
        def inner(error):
            calls.append(len(label_paths('H',18)[0]))
            raise error
        @font_budget_fallback
        def outer(error):
            return inner(error)
        with self.assertRaises(NativePenBudgetError):outer(NativePenBudgetError('points'))
        self.assertEqual(calls,[1,3])
        for error in (ValueError('bad schema'),ValueError('label collision')):
            calls.clear()
            with self.assertRaises(ValueError):outer(error)
            self.assertEqual(calls,[1])
        self.assertEqual(len(label_paths('H',18)[0]),1)

    def test_original_font_context_does_not_leak_to_other_requests(self):
        barrier=Barrier(2)
        def original():
            with original_glyphs():
                barrier.wait(); result=len(label_paths('H',18)[0]); barrier.wait()
            return result
        def continuous():
            barrier.wait(); result=len(label_paths('H',18)[0]); barrier.wait()
            return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(original); b=pool.submit(continuous)
            self.assertEqual((a.result(),b.result()),(3,1))


if __name__ == '__main__':
    unittest.main()
