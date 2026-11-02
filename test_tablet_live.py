import unittest
import gzip
import os
import struct
import subprocess
import tempfile
from PIL import Image, ImageDraw
from tablet_live import WIDTH, HEIGHT, PIXEL_OFFSET, ALLOCATION, PLACES, IMAGE_FIND, framebuffer_region, writing_box, aligned_writing_box, exposed_writing_box, notebook_crop, notebook_pixels, pen_point, capture, capture_region, decode_capture, RESPOND_TAP, settled_frame


class TabletLiveTest(unittest.TestCase):
    def test_paper_alignment_rejects_old_scrolled_content_and_unobserved_paper(self):
        before = Image.new('L',(WIDTH,HEIGHT),255)
        ImageDraw.Draw(before).text((250,900),'Existing user note',fill=0)
        after = Image.new('L',(WIDTH,HEIGHT),255)
        after.paste(before,(0,-500))
        # This pre-existing note was off-screen before: it is NOT new evidence.
        ImageDraw.Draw(after).text((250,1600),'Older text newly scrolled into view',fill=0)
        start,end = (1,0,0,1,0,0),(1,0,0,1,0,500)
        self.assertIsNotNone(writing_box(after,before), 'old check falsely sees new ink')
        self.assertIsNone(aligned_writing_box(after,before,start,end))
        ImageDraw.Draw(after).text((250,800),'Actually new reply on observed blank paper',fill=0)
        self.assertIsNotNone(aligned_writing_box(after,before,start,end))
        self.assertIsNone(aligned_writing_box(after,before,start,(1,0,0,1,0,4000)))
        with self.assertRaisesRegex(ValueError,'zoom'):
            aligned_writing_box(after,before,start,(2,0,0,2,0,0))
        with self.assertRaisesRegex(ValueError,'subpixel'):
            aligned_writing_box(after,before,start,(1,0,0,1,0,.5))

    def test_a_long_scroll_finds_the_reply_on_newly_exposed_paper_only(self):
        after = Image.new('L',(WIDTH,HEIGHT),255)
        ImageDraw.Draw(after).rectangle((300,120,900,150),fill=0)  # observed paper still in view: not evidence
        start = (1,0,0,1,-702,0)
        self.assertIsNone(exposed_writing_box(after,start,(1,0,0,1,-702,1705))[0])
        ImageDraw.Draw(after).rectangle((300,400,900,420),fill=0)  # the reply, below everything observed before
        box,rows = exposed_writing_box(after,start,(1,0,0,1,-702,1705))
        self.assertEqual(rows,67)
        self.assertEqual(box[1],400)
        self.assertEqual(exposed_writing_box(after,start,(1,0,0,1,-702,300)),(None,1472),
                         'a short scroll keeps the observed-paper check in charge')

    def test_baseline_waits_for_three_stable_paper_frames_after_scroll_tiles(self):
        partial = Image.new('L',(WIDTH,HEIGHT),255)
        complete = partial.copy()
        ImageDraw.Draw(complete).text((250,250),'Earlier answer must not look newly written',fill=0)
        frames = iter([partial,complete,complete,complete])
        result = settled_frame(partial,lambda:next(frames))
        self.assertEqual(result.tobytes(),complete.tobytes())
        # This baseline excludes the OLD text from the next handwritten crop.
        new = complete.copy()
        ImageDraw.Draw(new).line((250,1450,500,1450),fill=0,width=3)
        self.assertGreater(writing_box(new,result)[1],1400)

    def test_unsettled_baseline_is_refused_and_known_control_changes_are_ignored(self):
        blank = Image.new('L',(WIDTH,HEIGHT),255)
        changed = blank.copy()
        ImageDraw.Draw(changed).line((250,300,500,300),fill=0,width=3)
        frames = iter([changed,blank,changed,blank,changed])
        with self.assertRaisesRegex(ValueError,'still changing'):
            settled_frame(blank,lambda:next(frames))
        control = blank.copy()
        ImageDraw.Draw(control).rounded_rectangle((1180,112,1363,195),fill=0,radius=8)
        frames = iter([control,blank])
        self.assertEqual(settled_frame(blank,lambda:next(frames)).tobytes(),blank.tobytes())
        for kwargs in ({'attempts':True},{'attempts':9},{'stable_frames':1},{'attempts':2,'stable_frames':3}):
            with self.assertRaises(ValueError):
                settled_frame(blank,lambda:blank,**kwargs)

    def test_lower_left_handwriting_survives_without_controls_in_crop(self):
        page = Image.new('L', (WIDTH, HEIGHT), 255)
        d = ImageDraw.Draw(page)
        d.line((240, 1600, 1200, 1600), fill=0, width=3)
        d.rectangle((240, 1700, 600, 1740), fill=0)  # final handwritten word
        d.rectangle((1000, 1700, 1200, 1740), fill=0)  # lower right is writable now
        before_controls = page.copy()
        d.rounded_rectangle((1180, 112, 1363, 195), radius=8, fill=0)
        d.rectangle((600, 1820, 800, 1860), fill=0)  # page-number footer
        source = page.tobytes()
        box = writing_box(page)
        self.assertGreater(box[3], 1740)
        crop = notebook_crop(page)
        self.assertEqual(crop.getpixel((400-box[0], 1720-box[1])), 0)
        self.assertEqual(crop.getpixel((1100-box[0], 1720-box[1])), 0)
        self.assertEqual(crop.tobytes(), notebook_crop(before_controls).tobytes())
        self.assertEqual(source, page.tobytes())
        self.assertIsNone(notebook_crop(page, page))
        with self.assertRaises(ValueError):
            notebook_crop(Image.new('L', (100, 100)))

    def test_top_right_button_mask_tracks_actual_width_and_preserves_nearby_ink(self):
        self.assertEqual(RESPOND_TAP, (1270, 154))
        for left in (700, 1180):
            for fill in (None, 0):
                page = Image.new('L', (WIDTH, HEIGHT), 255)
                d = ImageDraw.Draw(page)
                d.rounded_rectangle((left, 112, 1363, 195), radius=8, fill=fill, outline=0, width=3)
                d.line((left-150, 154, left-30, 154), fill=0, width=3)
                original = page.tobytes()
                pixels = notebook_pixels(page)
                self.assertEqual(pixels[154, left-80], 0)
                self.assertTrue((pixels[112:196, left:1304] == 255).all())
                self.assertEqual(page.tobytes(), original)

    def test_old_bottom_button_baseline_cannot_hide_new_lower_right_handwriting(self):
        baseline = Image.new('L', (WIDTH, HEIGHT), 255)
        ImageDraw.Draw(baseline).rounded_rectangle((1180, 1748, 1363, 1831), radius=8, fill=0)
        page = Image.new('L', (WIDTH, HEIGHT), 255)
        ImageDraw.Draw(page).rectangle((1195, 1760, 1225, 1775), fill=0)
        crop = notebook_crop(page, baseline)
        self.assertIsNotNone(crop)
        self.assertEqual(crop.getextrema()[0], 0)

    def test_one_validated_read_not_a_cached_address_or_screenshot_signal(self):
        start = 0x1000000
        maps = f"00100000-00200000 rw-s 0 00:00 1 /dev/fb0\n{start:x}-{start+ALLOCATION:x} rw-p 0 00:00 0\n"
        prefix = b'HBFB1 123\n' + maps.encode()
        raw = b'\0' * ((start + PIXEL_OFFSET) % 4096) + bytes([127, 0, 0, 255]) * (WIDTH*HEIGHT)
        data = prefix + gzip.compress(raw, compresslevel=1)
        calls = []
        def tablet(command):
            calls.append(command)
            return data
        result = capture(tablet)
        self.assertEqual(len(calls), 1)
        self.assertIn('test $((fb_address + fb_size)) -le "$fb_limit"', calls[0])
        self.assertNotIn('kill', calls[0])
        self.assertEqual(result.size, (WIDTH, HEIGHT))
        self.assertEqual(result.getpixel((900, 1100)), 127)
        with self.assertRaises(ValueError):
            decode_capture(data.replace(b'HBFB1 123', b'HBFB1 bad', 1))
        with self.assertRaises(ValueError):
            decode_capture(prefix + gzip.compress(b'partial'))
        with self.assertRaises(ValueError):
            decode_capture(data.replace(b'rw-p', b'r--p', 1))

    def test_reads_only_a_large_enough_framebuffer_allocation(self):
        start = 0x1000000
        maps = f"00100000-00200000 rw-s 0 00:00 1 /dev/fb0\n{start:x}-{start+ALLOCATION:x} rw-p 0 00:00 0\n"
        self.assertEqual(framebuffer_region(maps), (start+PIXEL_OFFSET, WIDTH*HEIGHT*4))
        with self.assertRaises(ValueError):
            framebuffer_region(maps.replace(f"{start+ALLOCATION:x}", f"{start+ALLOCATION+4096:x}"))
        with self.assertRaises(ValueError):
            framebuffer_region(maps.replace("rw-p", "r--p"))

    def test_the_screen_image_is_found_by_its_header_alone_after_other_chunks_or_a_quarter_screen_buffer(self):
        def found(mappings, headers):
            with tempfile.TemporaryDirectory() as d:
                with open(os.path.join(d, 'maps'), 'w') as f:
                    f.write(''.join(f'{a:x}-{b:x} {perms} 0 00:00 0{name}\n' for a, b, perms, name in mappings))
                with open(os.path.join(d, 'mem'), 'wb') as f:
                    for address, word in headers:
                        f.seek(address)
                        f.write(struct.pack('<II', 0, word))
                    f.truncate(max(b for _, b, _, _ in mappings))
                script = IMAGE_FIND.replace('/proc/$fb_pid', d)+'\necho "$fb_image"'
                return subprocess.run(['/bin/sh', '-c', script], capture_output=True, text=True).stdout.strip()
        size = ALLOCATION-8 | 2  # as xochitl's malloc wrote it on 2026-11-01
        alone, merged = 0x400000, 0x2000000
        self.assertEqual(found([(alone, alone+ALLOCATION, 'rw-p', '')], [(alone, size)]), str(alone))
        self.assertEqual(found([(merged, merged+PLACES[1]+ALLOCATION+8192, 'rw-p', '')], [(merged+PLACES[1], size)]),
                         str(merged+PLACES[1]))
        # behind any of malloc's own chunks, walked over by their sizes (written either way malloc counts them)
        small, quarter = 8192, PLACES[1]
        chunks = [(merged, small-8 | 2), (merged+small, quarter | 2), (merged+small+quarter, size)]
        self.assertEqual(found([(merged, merged+small+quarter+ALLOCATION, 'rw-p', '')], chunks),
                         str(merged+small+quarter))
        # a header naming more than its mapping holds is not walked past
        self.assertEqual(found([(alone, alone+ALLOCATION+8192, 'rw-p', '')], [(alone, 0x7fff0000 | 2)]), '')
        # no header, a header without the own-mapping bit, a file's mapping or a read-only one: none of them
        self.assertEqual(found([(alone, alone+ALLOCATION, 'rw-p', '')], []), '')
        self.assertEqual(found([(alone, alone+ALLOCATION, 'rw-p', '')], [(alone, ALLOCATION-8 | 1)]), '')
        self.assertEqual(found([(alone, alone+ALLOCATION, 'rw-p', ' /usr/lib/x.so')], [(alone, size)]), '')
        self.assertEqual(found([(alone, alone+ALLOCATION, 'r--p', '')], [(alone, size)]), '')
        # a header with too little mapping after it
        self.assertEqual(found([(alone, alone+ALLOCATION-4096, 'rw-p', '')], [(alone, size)]), '')

    def test_regional_capture_matches_exact_full_frame_crop_at_every_edge(self):
        start = 0x1000000
        maps = f"00100000-00200000 rw-s 0 00:00 1 /dev/fb0\n{start:x}-{start+ALLOCATION:x} rw-p 0 00:00 0\n"
        frame = Image.new('L',(WIDTH,HEIGHT),255)
        draw = ImageDraw.Draw(frame)
        for y in range(HEIGHT):
            draw.line((0,y,WIDTH-1,y),fill=y%251)
        draw.line((0,0,WIDTH-1,HEIGHT-1),fill=0,width=3)
        pixels = frame.convert('RGBA').tobytes('raw','BGRA')
        for box in [(0,0,1,1),(WIDTH-1,HEIGHT-1,WIDTH,HEIGHT),
                    (231,327,1137,833),(0,0,WIDTH,HEIGHT)]:
            with self.subTest(box=box):
                top,bottom = box[1],box[3]
                address = start+PIXEL_OFFSET+top*WIDTH*4
                rows = pixels[top*WIDTH*4:bottom*WIDTH*4]
                prefix = (f'HBFB2 123 {" ".join(map(str,box))}\n'+maps).encode()
                data = prefix+gzip.compress(bytes(address%4096)+rows,compresslevel=1)
                commands = []
                def remote(command):
                    commands.append(command)
                    return data
                region = capture_region(remote,box)
                self.assertEqual(region.size,(box[2]-box[0],bottom-top))
                self.assertEqual(region.tobytes(),frame.crop(box).tobytes())
                self.assertEqual(len(commands),1)
                self.assertIn(f'fb_address=$((fb_address + {top*WIDTH*4}))',commands[0])
                self.assertIn(f'fb_size={(bottom-top)*WIDTH*4}',commands[0])
                self.assertIn('test $((fb_address + fb_size)) -le "$fb_limit"',commands[0])
                with self.assertRaises(ValueError):
                    decode_capture(data)  # region must not masquerade as full-screen
                with self.assertRaises(ValueError):
                    decode_capture(prefix+gzip.compress(bytes(address%4096)+rows[:-1]),box=box)
                with self.assertRaises(ValueError):
                    decode_capture(data.replace(b'rw-p',b'r--p',1),box=box)
                with self.assertRaises(ValueError):
                    decode_capture(data.replace(b'HBFB2 123',b'HBFB1 123',1),box=box)

    def test_regional_capture_rejects_bad_bounds_before_device_io(self):
        def remote(command):
            self.fail('invalid bounds must never reach the tablet')
        for box in [None,[],(0,0,0,1),(-1,0,10,10),(0,-1,10,10),
                    (0,0,WIDTH+1,HEIGHT),(0,0,WIDTH,HEIGHT+1),(True,0,10,10),
                    (0,0,10.0,10),(0,0,float('inf'),10),'0 0 10 10']:
            with self.subTest(box=box),self.assertRaises(ValueError):
                capture_region(remote,box)

    def test_ignores_controls_and_template_but_finds_new_ink(self):
        page = Image.new("L", (WIDTH, HEIGHT), 255)
        d = ImageDraw.Draw(page)
        d.rectangle((0, 120, 100, 250), fill=0)  # native toolbar
        d.rectangle((700, 112, 1363, 195), outline=0, width=3)  # wider RESPOND status
        d.rectangle((1345, 250, 1353, 1600), fill=0)  # native continuous-page scrollbar
        d.line((130, 300, 1300, 300), fill=200, width=2)
        self.assertIsNone(writing_box(page))
        before = page.copy()
        d.line((220, 160, 300, 160), fill=0, width=3)
        self.assertIsNotNone(writing_box(page, before))
        self.assertIsNone(writing_box(page, page))

    def test_screen_to_native_pen_coordinates(self):
        self.assertEqual(pen_point(0, 0), (20966, 0))
        x, y = pen_point(WIDTH/2, HEIGHT/2)
        self.assertEqual(x, 10483)
        self.assertAlmostEqual(y, 15725/2, delta=.5)
        for point in ((-1,0),(0,-1),(WIDTH,0),(0,HEIGHT)):
            with self.assertRaises(ValueError):
                pen_point(*point)


if __name__ == "__main__":
    unittest.main()
