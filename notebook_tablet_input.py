"""Screen-coordinate pen strokes and touch taps on the rM2, and a read-only look at its screen, over ssh.

Used by herd-board-primer to write a spoken question in the reader's hand and press Respond, as a person would.
Touch (event2) raw axes are inverted on both axes; pen (event1, Wacom) axes are swapped with Y inverted.
"""
import gzip
import os
import struct
import subprocess

import numpy as np

W, H = 1404, 1872
TABLET = os.environ.get('HERD_BOARD_TABLET', 'root@remarkable.lan')
WX, WY = 20967, 15725  # Wacom ABS_X (screen y, inverted) and ABS_Y (screen x)
# xochitl's screen image, read from its memory: 32-bit pixels, grey in the second byte, in a mapping of its own
# (W*H*4 bytes and malloc's 8-byte header, in whole pages). Found by its size: its place moves between restarts
# (2.6 MB past /dev/fb0 until 2026-11-01, then 4.7 MB).
PAGES = -(-(W*H*4+8)//4096)
SHOT = (f'P=$(pidof xochitl); O=$(while read r x; do [ $((0x${{r#*-}}-0x${{r%-*}})) -eq {PAGES*4096} ] && '
        f'echo $((0x${{r%-*}})) && break; done < /proc/$P/maps); '
        f'[ -n "$O" ] && dd if=/proc/$P/mem bs=4096 skip=$((O/4096)) count={PAGES} 2>/dev/null')


def _ssh(command, data=None, timeout=60):
    env = dict(os.environ, SSH_AUTH_SOCK=os.path.expanduser('~/.ssh/s/r1-agent.sock'))
    # One connection for a question's look, pen and tap: each new one costs about half a second.
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'ControlMaster=auto',
                           '-o', 'ControlPath=~/.ssh/s/rm-%C', '-o', 'ControlPersist=120', TABLET, command], input=data,
                          env=env, capture_output=True, timeout=timeout, check=True).stdout


def _ev(t, c, v):
    return struct.pack('<IIHHi', 0, 0, t, c, v)


SYN = _ev(0, 0, 0)


def _run(lines):
    """lines: ('event1'|'event2', bytes) or ('sleep', microseconds). The events go over once as a file; dd bs=16
    writes each event whole."""
    blob, script, at = b'', [], 0
    for kind, value in lines:
        if kind == 'sleep':
            script.append(f'usleep {value}')
        else:
            n = len(value)//16
            script.append(f'dd if=/tmp/herd-primer.bin of=/dev/input/{kind} bs=16 skip={at} count={n} 2>/dev/null')
            blob += value
            at += n
    _ssh('cat > /tmp/herd-primer.bin', blob)
    _ssh('sh', ('\n'.join(script)+'\nrm -f /tmp/herd-primer.bin\n').encode(), timeout=180)


def tap(x, y, hold_us=80000):
    rx, ry = x, H-1-y
    down = (_ev(3, 0x2f, 0)+_ev(3, 0x39, 4242)+_ev(3, 0x35, rx)+_ev(3, 0x36, ry)+_ev(3, 0x30, 20)+_ev(3, 0x3a, 60)
            + SYN)
    up = _ev(3, 0x2f, 0)+_ev(3, 0x39, -1)+SYN
    _run([('event2', down), ('sleep', hold_us), ('event2', up)])


def _dense(path, step=3):
    """The pen reports every few pixels; handwriting paths are thinned."""
    out = [path[0]]
    for (a, b), (c, d) in zip(path, path[1:]):
        n = max(1, int(((c-a)**2+(d-b)**2)**.5/step))
        out += [(a+(c-a)*k/n, b+(d-b)*k/n) for k in range(1, n+1)]
    return out


BURST = 24  # points per write: each dd (about 50 ms to start on the tablet) paces the next; more would overflow input


def pen(strokes):
    """Draw each stroke, a list of screen (x, y), with the pen at a steady pressure. The pen's touch and lift ride in
    the first and last write of a stroke: a dd per write is most of the time it takes."""
    lines = []
    for stroke in strokes:
        pts = [(round((H-1-min(max(y, 0), H-1))*WX/(H-1)), round(min(max(x, 0), W-1)*WY/(W-1)))
               for x, y in _dense(stroke, 5)]
        events = [_ev(1, 0x140, 1)+_ev(3, 0, pts[0][0])+_ev(3, 1, pts[0][1])+_ev(3, 0x19, 0)+SYN
                  + _ev(1, 0x14a, 1)+_ev(3, 0x18, 2000)+SYN]
        events += [_ev(3, 0, a)+_ev(3, 1, b)+_ev(3, 0x18, 2000)+SYN for a, b in pts[1:]]
        events.append(_ev(3, 0x18, 0)+_ev(1, 0x14a, 0)+SYN+_ev(1, 0x140, 0)+SYN)
        lines += [('event1', b''.join(events[i:i+BURST])) for i in range(0, len(events), BURST)]
    _run(lines)


def screen():
    """The screen as an H x W grey array (read-only), or None when the capture is not a plausible page."""
    raw = gzip.decompress(_ssh(SHOT+' | gzip -1', timeout=30))  # a page is mostly white: 10 MB in about 70 kB
    if len(raw) < W*H*4+8:
        return None
    grey = np.frombuffer(raw[8:8+W*H*4][1::4], np.uint8).reshape(H, W)
    return grey if (grey >= 200).mean() >= .6 else None


def ink_bottom(grey, left=120, right=1290, top=210):
    """The lowest screen row holding ink (or typed text) inside the paper's safe columns below the toolbar; 0 if
    none."""
    rows = np.nonzero(((grey[top:, left:right] < 110).sum(axis=1)) >= 2)[0]
    return int(top+rows[-1]) if len(rows) else 0
