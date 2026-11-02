import importlib.machinery
import importlib.util
import json
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image


class NativeInkPreflightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader('native_ink_preflight_server',
                    str(Path(__file__).with_name('herd-board-serve')))
        cls.server = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(cls.server)

    def test_source_validation_shared_but_claim_reads_are_never_cached(self):
        from notebook_lesson_native import native_semantic_bundle
        from notebook_semantic_examples import examples
        bundle=native_semantic_bundle(json.dumps(examples()['integral']),playback=True)
        block=next(b for b in bundle['blocks'] if b['kind']=='ink'); data=bundle['sources'][0]['data']
        with patch.object(self.server,'tablet') as remote:
            self.assertEqual(self.server.validate_native_ink_source(block,data),data)
            remote.assert_not_called()
        with patch.object(self.server,'tablet',side_effect=[data,b'changed after import']) as remote:
            self.assertEqual(self.server.native_ink_source(block),data)
            with self.assertRaisesRegex(ValueError,'integrity'):
                self.server.native_ink_source(block)
            self.assertEqual(remote.call_count,2)
        for change in ('identity','hash','count','playback'):
            bad=copy.deepcopy(block)
            if change=='identity':bad['source_page']='../bad'
            elif change=='hash':bad['sha256']='0'*64
            elif change=='count':bad['stroke_count']+=1
            else:bad['playback']['duration_ms']=1
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.server.validate_native_ink_source(bad,data)

    def sample(self, folder='Storyboard tests (Codex)'):
        context = dict(doc='905df7ae-ff54-46b9-a71e-45bb02bef638',
                       page='3ad12986-0467-48fe-986d-d1bd480c4777', fresh=True, active=True,
                       available=True, size=[1404,1872], view=[1,0,0,1,-702,0],
                       text_bounds=[-468,100,936,200])
        query = dict(request='notebook-'+'a'*32, origin=[-468,330])
        metadata = [json.dumps(dict(parent='a7a7e181-7b6b-4a84-a169-3bc7e5fe35da',visibleName='To pidog')).encode(),
                    json.dumps(dict(visibleName=folder)).encode()]
        return context, query, metadata

    def test_whole_first_diagram_reservation_must_be_visibly_blank(self):
        context, query, metadata = self.sample()
        for occupied in (False, True):
            frame = Image.new('L', (1404,1872),255)
            if occupied:
                frame.putpixel((400,400),0)
            with patch.object(self.server,'native_ink_current') as current, \
                 patch.object(self.server,'native_ink_source') as source, \
                 patch.object(self.server,'tablet',side_effect=metadata), \
                 patch.object(self.server,'live_capture_region',side_effect=lambda remote,box:frame.crop(box)):
                if occupied:
                    with self.assertRaisesRegex(ValueError,'existing content'):
                        self.server.native_ink_preflight({'scene':'unit-square-integral'}, query, context, True)
                else:
                    self.server.native_ink_preflight({'scene':'unit-square-integral'}, query, context, True)
                self.assertEqual(current.call_count, 1 if occupied else 2)
                self.assertTrue(all(call.args == (query['request'],) for call in current.call_args_list))
                source.assert_called_once()

    def test_non_test_notebook_refused_before_framebuffer_capture(self):
        context, query, metadata = self.sample('Correspondence')
        with patch.object(self.server,'native_ink_current'), patch.object(self.server,'native_ink_source'), \
             patch.object(self.server,'tablet',side_effect=metadata), patch.object(self.server,'live_capture_region') as capture:
            with self.assertRaisesRegex(ValueError,'restricted'):
                self.server.native_ink_preflight({'scene':'unit-square-integral'},query,context,True)
            capture.assert_not_called()

    def test_later_stage_revalidates_source_and_folder_without_requiring_blank_plot(self):
        context, query, metadata = self.sample()
        with patch.object(self.server,'native_ink_current'), patch.object(self.server,'native_ink_source') as source, \
             patch.object(self.server,'tablet',side_effect=metadata), patch.object(self.server,'live_capture_region') as capture:
            self.server.native_ink_preflight({'scene':'unit-square-integral'},query,context,False)
            source.assert_called_once(); capture.assert_not_called()

    def test_current_writing_reply_required_before_native_io(self):
        with patch.object(self.server,'notebook_jobs',{}),patch.object(self.server,'tablet') as remote:
            with self.assertRaisesRegex(ValueError,'current writing reply'):
                self.server.claim_native_ink({'request':'notebook-'+'a'*32})
            remote.assert_not_called()

    def test_compiled_equation_uses_bounded_region_and_lesson_rollout(self):
        from notebook_lesson_native import native_semantic_bundle
        from notebook_semantic_examples import examples
        bundle = native_semantic_bundle(json.dumps(examples()['fractions']), playback=True, pen_equations=True)
        block = next(b for b in bundle['blocks'] if b.get('role') == 'equation')
        context, query, _ = self.sample()
        for enabled, occupied in [(False,False),(True,False),(True,True)]:
            with self.subTest(enabled=enabled,occupied=occupied), \
                 patch.object(self.server,'native_ink_current') as current, \
                 patch.object(self.server,'native_ink_source') as source, \
                 patch.object(self.server,'lesson_enabled',return_value=enabled), \
                 patch.object(self.server,'tablet',side_effect=AssertionError('not an authored scene')), \
                 patch.object(self.server,'live_capture_region',return_value=Image.new('L',(606,206),0 if occupied else 255)) as capture:
                if not enabled or occupied:
                    with self.assertRaisesRegex(ValueError,'not enabled|existing content'):
                        self.server.native_ink_preflight(block,query,context,True)
                else:
                    self.server.native_ink_preflight(block,query,context,True)
                    self.assertEqual(capture.call_args.args[1],(231,327,837,533))
                    self.assertEqual(current.call_count,2)
                source.assert_called_once()
                self.assertEqual(capture.call_count,1 if enabled else 0)

    def test_region_keeps_every_guard_margin_pixel_and_checks_request_after_read(self):
        context, query, metadata = self.sample()
        box = (231,327,837,633)  # authored 600x300 scene plus the existing 3px margin
        for pixel in [(231,327),(836,327),(231,632),(836,632),(234,330),(833,629),None]:
            frame = Image.new('L',(1404,1872),255)
            if pixel is not None:
                frame.putpixel(pixel,0)
            def region(remote, actual_box):
                self.assertEqual(actual_box,box)
                return frame.crop(actual_box)
            with self.subTest(pixel=pixel), \
                 patch.object(self.server,'native_ink_current') as current, \
                 patch.object(self.server,'native_ink_source'), \
                 patch.object(self.server,'tablet',side_effect=metadata), \
                 patch.object(self.server,'live_capture_region',side_effect=region) as read, \
                 patch.object(self.server,'live_capture',side_effect=AssertionError('must not read whole frame')):
                if pixel is None:
                    self.server.native_ink_preflight({'scene':'unit-square-integral'},query,context,True)
                    self.assertEqual(current.call_count,2)
                else:
                    with self.assertRaisesRegex(ValueError,'existing content'):
                        self.server.native_ink_preflight({'scene':'unit-square-integral'},query,context,True)
                read.assert_called_once()
        with patch.object(self.server,'native_ink_current',side_effect=[None,ValueError('request changed')]), \
             patch.object(self.server,'native_ink_source'), \
             patch.object(self.server,'tablet',side_effect=metadata), \
             patch.object(self.server,'live_capture_region',return_value=Image.new('L',(606,306),255)):
            with self.assertRaisesRegex(ValueError,'request changed'):
                self.server.native_ink_preflight({'scene':'unit-square-integral'},query,context,True)


if __name__ == '__main__':
    unittest.main()
