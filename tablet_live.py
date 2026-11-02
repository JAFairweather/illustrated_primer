"""Live reMarkable 2 display capture without a signal, save, or document close.

Framebuffer location/format follows goMarkableStream and smart_remarkable's
documented RM2 firmware-3.24+ layout. Read only the validated pixel allocation.
No third-party program is installed on the tablet.
"""
import io
import gzip
import math
import re
import struct
import subprocess
import time
from PIL import Image, ImageFilter
import numpy as np

WIDTH, HEIGHT = 1404, 1872
RESPOND_TOP, RESPOND_HEIGHT, RESPOND_RIGHT = 112, 84, 40
RESPOND_TAP = (1270, RESPOND_TOP + RESPOND_HEIGHT // 2)
# xochitl's screen image is malloc'd memory of its own: W*H*4 bytes after malloc's 8-byte header, in whole pages. Its
# mapping can merge with neighbours: after one restart it stood alone (2026-11-01 08:55), after others it followed a
# quarter-screen buffer (1404x468x4 bytes and a header, in pages) in one mapping. It is found by its header (a zero,
# then its size with malloc's own-mapping bit), walking from each mapping's start over any of malloc's own chunks in
# front of it by their sizes, and at the quarter-screen buffer's end when the walk cannot start.
PIXEL_OFFSET = 8
ALLOCATION = -(-(WIDTH * HEIGHT * 4 + PIXEL_OFFSET) // 4096) * 4096
PLACES = (0, -(-(WIDTH * HEIGHT // 4 * 4 + PIXEL_OFFSET) // 4096) * 4096)
CHUNKS = 16  # the most chunks walked in one mapping
# Sets fb_image to the address of the image's header in xochitl ($fb_pid), or to nothing.
IMAGE_FIND = f'''fb_image=$(while read fb_r fb_p fb_x fb_d fb_i fb_n; do
  [ "$fb_p" = rw-p ] && [ -z "$fb_n" ] || continue
  case "$fb_r" in (*[!0-9a-f-]*) continue;; esac
  fb_s=$((0x${{fb_r%-*}})); fb_e=$((0x${{fb_r#*-}})); fb_k=0; fb_t=0
  while [ $fb_t -lt {CHUNKS} ] && [ $((fb_s + fb_k + {ALLOCATION})) -le $fb_e ]; do
    fb_t=$((fb_t + 1)); fb_z=0
    set -- $(dd if=/proc/$fb_pid/mem bs=8 skip=$(((fb_s + fb_k) / 8)) count=1 2>/dev/null | od -x)
    [ "$2$3" = 00000000 ] && [ ${{#4}} -eq 4 ] && [ ${{#5}} -eq 4 ] && fb_z=$((0x$5$4))
    [ $((fb_z & 2)) -ne 0 ] && [ $((fb_z & ~7)) -ge {WIDTH * HEIGHT * 4} ] && [ $((fb_z & ~7)) -le {ALLOCATION} ] &&
      echo $((fb_s + fb_k)) && break 2
    if [ $((fb_z & 2)) -ne 0 ] && [ $((fb_z & ~7)) -ge 4088 ] && [ $((fb_k + (fb_z & ~7))) -lt $((fb_e - fb_s)) ]; then
      fb_k=$((fb_k + ((fb_z & ~7) + 4095) / 4096 * 4096))
    elif [ $fb_k -eq 0 ]; then fb_k={PLACES[1]}
    else break; fi
  done
done < /proc/$fb_pid/maps; true)'''


def framebuffer_region(maps):
    lines = maps.splitlines()
    if len(lines) != 2 or lines[0].split()[-1:] != ["/dev/fb0"]:
        raise ValueError("no supported RM2 framebuffer mapping")
    allocation = lines[1].split()
    if len(allocation) != 5 or allocation[1] != "rw-p":
        raise ValueError("unexpected framebuffer allocation mapping")
    start, end = [int(part, 16) for part in allocation[0].split("-")]
    if end - start != ALLOCATION:
        raise ValueError("framebuffer allocation is not the screen image's size")
    return start + PIXEL_OFFSET, WIDTH * HEIGHT * 4


def capture(tablet):
    return _capture(tablet)


def capture_region(tablet, box):
    """Read only rows covering an exact screen rectangle, including its edges.

    This is the same framebuffer source as capture(), not a reduced-resolution
    or sampled blank-space check. The caller must still guard page/view/input.
    """
    return _capture(tablet, _capture_box(box))


def _capture_box(box):
    if (not isinstance(box, (tuple, list)) or len(box) != 4 or
            any(type(n) is not int for n in box) or
            not 0 <= box[0] < box[2] <= WIDTH or
            not 0 <= box[1] < box[3] <= HEIGHT):
        raise ValueError('capture rectangle must be integer pixels inside the display')
    return tuple(box)


def _capture(tablet, box=None):
    # Resolve AND validate the current allocation in the same SSH operation as
    # the bounded read. No cached PID/address survives a native-app restart.
    # This removes one ~0.6s SSH setup on the measured home LAN per capture.
    top, bottom = (box[1], box[3]) if box else (0, HEIGHT)
    header = 'HBFB2 %s ' + ' '.join(map(str, box)) if box else 'HBFB1 %s'
    script = f'''set -e
fb_pid=$(pidof xochitl)
case "$fb_pid" in ""|*[!0-9]*) exit 1;; esac
fb_first=$(awk '$NF == "/dev/fb0" {{ print; exit }}' /proc/$fb_pid/maps)
test -n "$fb_first"
{IMAGE_FIND}
test -n "$fb_image"
fb_line=$(printf '%x-%x rw-p 0 00:00 0' $fb_image $((fb_image + {ALLOCATION})))  # the image's own range
fb_maps=$(printf '%s\\n%s' "$fb_first" "$fb_line")
fb_range=${{fb_line%% *}}
fb_start=${{fb_range%-*}}
fb_end=${{fb_range#*-}}
fb_address=$((0x$fb_start + {PIXEL_OFFSET}))
fb_limit=$((0x$fb_end))
fb_size={WIDTH * HEIGHT * 4}
test $((fb_address + fb_size)) -le "$fb_limit"
fb_address=$((fb_address + {top * WIDTH * 4}))
fb_size={(bottom-top) * WIDTH * 4}
fb_skip=$((fb_address / 4096))
fb_offset=$((fb_address % 4096))
fb_count=$(((fb_offset + fb_size + 4095) / 4096))
printf '{header}\\n%s\\n' "$fb_pid" "$fb_maps"
dd if=/proc/$fb_pid/mem bs=4096 skip=$fb_skip count=$fb_count 2>/dev/null | gzip -1 -c
'''
    return decode_capture(tablet(script), box=box)


def decode_capture(data, *, box=None):
    if box is not None:
        box = _capture_box(box)
    try:
        header, first, allocation, packed = data.split(b"\n", 3)
    except ValueError:
        raise ValueError("incomplete live framebuffer header") from None
    expected = rb'HBFB1 [0-9]+' if box is None else (
        rb'HBFB2 [0-9]+ ' + ' '.join(map(str, box)).encode('ascii'))
    if not re.fullmatch(expected, header):
        raise ValueError("cannot identify xochitl")
    maps = (first + b"\n" + allocation).decode('ascii')
    address, size = framebuffer_region(maps)
    if box is not None:
        address += box[1] * WIDTH * 4
        size = (box[3]-box[1]) * WIDTH * 4
    offset = address % 4096
    raw = gzip.decompress(packed)
    frame = raw[offset:offset + size]
    if len(frame) != size:
        raise ValueError("incomplete live framebuffer")
    # The panel is gray; the first BGRA channel already has full 8-bit values.
    image = Image.frombytes("L", (WIDTH, box[3]-box[1] if box else HEIGHT), frame[::4])
    return image.crop((box[0], 0, box[2], image.height)) if box else image


def png_bytes(image):
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def respond_control_box(pixels, top=RESPOND_TOP):
    """Locate the known top-right button's border, including wider status labels.

    Mask its actual width rather than discarding handwritten text to its left.
    Require both a long top edge and the expected vertical right edge.
    """
    right = WIDTH - RESPOND_RIGHT
    edge = pixels[top+12:top+RESPOND_HEIGHT-12, right-4:right+1] < 110
    if edge.sum(axis=0).max() < RESPOND_HEIGHT - 30:
        return None
    lefts = []
    for row in pixels[top:top+9]:
        transitions = np.diff(np.pad((row < 110).astype(np.int8), (1, 1)))
        for left, end in zip(np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1)):
            if end-left >= 100 and abs(int(end)-right) <= 10:
                lefts.append(int(left))
    return (max(130, min(lefts)-10), top-2, min(WIDTH, right+3), top+RESPOND_HEIGHT+3) if lefts else None


def notebook_pixels(image):
    """Copy the page with known native controls replaced by white paper.

    A bounding crop alone cannot exclude a button inside its rectangle when
    handwriting spans both above and beside that button.
    """
    if image.size != (WIDTH, HEIGHT):
        raise ValueError('live page has unsupported display dimensions')
    pixels = np.array(image.convert('L'), copy=True)
    button = respond_control_box(pixels)
    pixels[:, :130] = 255
    # Native continuous-page scrollbar sits ~55 px from the right edge; a
    # 50 px exclusion still counted its black thumb as handwriting.
    pixels[:, WIDTH - 100:] = 255
    pixels[:100, :] = 255
    # Respond now sits below the close X. Preserve the old lower-right writing
    # area, and text to the left of the actual (variable-width) button.
    pixels[HEIGHT - 80:, :] = 255
    if button:
        left, top, right, bottom = button
        pixels[top:bottom, left:right] = 255
    return pixels


def settled_frame(initial, read_frame, attempts=6, stable_frames=3):
    """Require repeated stable paper pixels before saving the next OCR baseline.

    Native viewport movement/tiles can finish after the editor callback. Saving
    that transient image makes old text appear newly written at the next tap.
    This runs only at final acknowledgement, never before the first reply text.
    Known controls are excluded; notebook pixels themselves are not changed.
    """
    if (type(attempts) is not int or type(stable_frames) is not int or
            not 2 <= stable_frames <= attempts <= 8):
        raise ValueError('bounded stable-frame sample count required')
    previous = notebook_pixels(initial)
    frame, streak = initial, 1
    for _ in range(attempts-1):
        frame = read_frame()
        pixels = notebook_pixels(frame)
        streak = streak+1 if np.array_equal(previous, pixels) else 1
        if streak >= stable_frames:
            return frame
        previous = pixels
    raise ValueError('Notebook display is still changing; stable input baseline not saved')


def writing_box(image, baseline=None):
    """Visible dark ink, excluding native controls and the gray ruled template."""
    pixels = notebook_pixels(image)
    mask = pixels < 110
    if baseline is not None:
        previous = notebook_pixels(baseline)
        if previous.shape != pixels.shape:
            raise ValueError("live page baseline has different dimensions")
        # A baseline saved by the old bottom-button build must not hide new
        # handwriting in that now-free area. Normalize OLD controls only in
        # the previous image; never mask current lower-right writing.
        legacy = respond_control_box(np.asarray(baseline.convert('L')), HEIGHT-40-RESPOND_HEIGHT)
        if legacy:
            left, top, right, bottom = legacy
            previous[top:bottom, left:right] = 255
        mask &= previous > 160
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return max(130, int(xs.min()) - 30), max(100, int(ys.min()) - 30), min(WIDTH - 100, int(xs.max()) + 31), min(HEIGHT - 80, int(ys.max()) + 31)


def _scroll(before_view, after_view):
    """The whole-pixel paper offset between two native view transforms; zoom, rotation and subpixel moves refuse."""
    views = np.asarray([before_view, after_view], dtype=float)
    if views.shape != (2,6) or not np.isfinite(views).all():
        raise ValueError('native viewport proof requires two finite transforms')
    if not np.allclose(views[0,:4], views[1,:4], rtol=0, atol=1e-6):
        raise ValueError('native zoom or rotation changed; visible proof unavailable')
    a,b,c,d = views[0,:4]
    matrix = np.array([[a,c],[b,d]])
    if not .0001 <= abs(np.linalg.det(matrix)) <= 100:
        raise ValueError('native viewport proof has unsupported transform')
    offset = np.linalg.solve(matrix, views[1,4:]-views[0,4:])
    if not np.allclose(offset, np.rint(offset), rtol=0, atol=.01):
        raise ValueError('native subpixel scroll needs saved-content proof')
    return tuple(int(n) for n in np.rint(offset))


def aligned_writing_box(image, baseline, before_view, after_view):
    """New dark pixels in paper coordinates, never viewport-relative motion.

    Only compare paper visible in BOTH frames. Newly exposed page regions are
    unknown, not blank. Zoom/rotation and fractional resampling are deliberately
    unsupported: they need separate saved-content proof, not a pixel guess.
    """
    dx,dy = _scroll(before_view, after_view)
    current, previous = notebook_pixels(image), notebook_pixels(baseline)
    def paper(frame):
        mask = np.zeros((HEIGHT,WIDTH), dtype=bool)
        mask[100:HEIGHT-80,130:WIDTH-100] = True
        control = respond_control_box(np.asarray(frame.convert('L')), RESPOND_TOP)
        if control:
            left,top,right,bottom = control
            mask[top:bottom,left:right] = False
        return mask
    valid_now, valid_before = paper(image), paper(baseline)
    x0,x1,y0,y1 = max(0,-dx),min(WIDTH,WIDTH-dx),max(0,-dy),min(HEIGHT,HEIGHT-dy)
    if x0 >= x1 or y0 >= y1:
        return None
    # Allow one pixel of e-ink antialiasing around old marks, never count an
    # edge redraw as a new reply. Controls remain invalid, not erased paper.
    previous = np.asarray(Image.fromarray(previous).filter(ImageFilter.MinFilter(3)))
    now = np.s_[y0:y1,x0:x1]
    old = np.s_[y0+dy:y1+dy,x0+dx:x1+dx]
    new = (current[now] < 110) & (previous[old] > 160) & valid_now[now] & valid_before[old]
    ys,xs = np.nonzero(new)
    if len(xs) < 12:
        return None
    return (int(xs.min())+x0, int(ys.min())+y0, int(xs.max())+x0+1, int(ys.max())+y0+1)


def exposed_writing_box(image, before_view, after_view, minimum=100):
    """Dark ink on paper a long native scroll brought into view, for when too little observed paper stays visible.

    A long reply scrolls the view past everything seen before it was written, so aligned_writing_box has almost no
    shared paper to compare. Returns (box, rows): rows is the observed paper still in view, and box the new paper's
    ink, or None when at least a third of the observed paper is still visible (then the aligned check decides), or
    when the newly exposed paper holds fewer than minimum dark pixels.
    """
    dx,dy = _scroll(before_view, after_view)
    top, bottom = 100, HEIGHT-80
    seen = max(top, -dy), min(bottom, HEIGHT-dy)
    rows = max(0, seen[1]-seen[0])
    if rows*3 >= bottom-top:
        return None, rows
    ink = notebook_pixels(image) < 110
    ink[:top], ink[bottom:] = False, False
    if rows:
        ink[seen[0]:seen[1]] = False
    ys,xs = np.nonzero(ink)
    if len(xs) < minimum:
        return None, rows
    return (int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1), rows


def notebook_crop(image, baseline=None):
    box = writing_box(image, baseline)
    return Image.fromarray(notebook_pixels(image)).crop(box) if box else None


def pen_frame(events):
    # Linux input_event is two 32-bit timeval fields on this ARMv7 tablet.
    now = time.time()
    sec, usec = int(now), int((now % 1) * 1_000_000)
    return b"".join(struct.pack("<iiHHi", sec, usec, kind, code, value)
                    for kind, code, value in [*events, (0, 0, 0)])


def pen_point(x, y):
    if not 0 <= x < WIDTH or not 0 <= y < HEIGHT:
        raise ValueError("pen point outside display")
    return round((1 - y / HEIGHT) * 20966), round(x / WIDTH * 15725)


def draw_paths(paths, ssh_args, env, pace=.006, guard=None, duration=None):
    """Feed native pen input, always releasing the pen on interruption.

    Optional guard must return exactly True before opening input and before
    every pen-down/motion event. The caller owns the request/page/layout lease;
    this callback alone is NOT an atomic page-navigation lock. Never wire it
    to an automatic response without establishing that native lease first.

    Optional duration is the target seconds PER stroke's motion, apportioned
    by screen-space arc length. Monotonic deadlines avoid adding guard time to
    every interval. Slow guards/transport may exceed the target; no points or
    safety checks are skipped to catch up. Pen-down/up overhead is additional.
    """
    if type(pace) not in (int, float) or not 0 <= pace <= .05:
        raise ValueError('native pen pace must be within 0..50 ms')
    if duration is not None and (type(duration) not in (int,float) or not .1 <= duration <= 10):
        raise ValueError('native stroke duration must be within 0.1..10 seconds')
    paths=[path for path in paths if len(path)>1]
    converted = [[pen_point(x, y) for x, y in path] for path in paths]
    schedules=[]
    if duration is not None:
        for path in paths:
            distances=[0.0]
            for a,b in zip(path,path[1:]):distances.append(distances[-1]+math.dist(a,b))
            if distances[-1]<=0:
                raise ValueError('timed stroke requires nonzero length')
            schedules.append([duration*d/distances[-1] for d in distances])
    if sum(map(len, converted)) > 100000:
        raise ValueError("native ink reply too large")
    def check():
        if guard is not None and guard() is not True:
            raise RuntimeError('native pen lease changed; drawing stopped')
    check()
    if not converted:
        return
    process = subprocess.Popen([*ssh_args, "cat > /dev/input/event1"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    up = [(3, 24, 0), (3, 25, 100), (1, 330, 0), (1, 320, 0)]
    def emit(events):
        process.stdin.write(pen_frame(events))
        process.stdin.flush()
    try:
        for path_index,path in enumerate(converted):
            check()
            x, y = path[0]
            emit([(3, 0, x), (3, 1, y), (1, 320, 1), (1, 330, 0), (3, 24, 0), (3, 25, 100)])
            time.sleep(.015)
            check()
            emit([(1, 330, 1), (3, 24, 1500), (3, 25, 0)])
            time.sleep(.015)
            started=time.monotonic()
            for point_index,(x, y) in enumerate(path[1:],1):
                if duration is not None:
                    time.sleep(max(0,started+schedules[path_index][point_index]-time.monotonic()))
                check()
                emit([(3, 0, x), (3, 1, y)])
                if duration is None:time.sleep(pace)
            # Let xochitl consume the final coordinate before the tool-up event.
            time.sleep(.025)
            emit(up)
            time.sleep(.015)
    finally:
        try:
            emit(up)
        except (BrokenPipeError, OSError):
            pass
        process.stdin.close()
        process.wait(timeout=10)
    if process.returncode:
        raise RuntimeError("native pen input failed: " + process.stderr.read().decode()[:160])
