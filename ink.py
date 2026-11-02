"""ink: the reMarkable's v6 notebook pages (.rm) for herd-board-serve. Read a page's pen strokes and render them for
Gemini; append strokes after the last, in the same layer, as the tablet's own fineliner; and set text as such strokes
in a hand (Bradley Hand, rendered, thinned to one pen line and traced). The format: a 43-byte header, then blocks
(length, version, type); type 5 is a line, its fields tagged (index << 4 | kind); ids are CRDT (author, n)."""
import io, math, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def strokes(data):
	"""A v6 .rm page's pen strokes: [(tool, [(x, y, width), ...], ours)], x from the page's centre, y from its top;
	ours: written by append() (every point at speed 2, pressure 255, which the pen never gives)."""
	if not data.startswith(b"reMarkable .lines file, version=6"):
		raise ValueError("not a v6 page")
	out, p = [], 43
	while p + 8 <= len(data):
		n, _, _, ver, kind = struct.unpack_from("<IBBBB", data, p)
		body, p = data[p + 8:p + 8 + n], p + 8 + n
		if kind == 5:   # a scene line item
			try:
				s = line(body, ver)
			except (struct.error, IndexError):
				s = None
			if s:
				out.append(s)
	return out

def line(b, ver):
	q = [0]
	def varuint():
		v = sh = 0
		while True:
			c = b[q[0]]; q[0] += 1; v |= (c & 0x7f) << sh; sh += 7
			if not c & 0x80:
				return v
	def tag():
		t = varuint(); return t >> 4, t & 0xf
	def skip(t):
		if t == 0xf: q[0] += 1; varuint()
		elif t == 0x4: q[0] += 4
		elif t == 0x8: q[0] += 8
		elif t == 0x1: q[0] += 1
		elif t == 0xc: n = struct.unpack_from("<I", b, q[0])[0]; q[0] += 4 + n
	for _ in range(5):   # parent, item, left, right ids; deleted length
		skip(tag()[1])
	if q[0] >= len(b):
		return None   # erased: no value
	i, t = tag()
	if i != 6 or t != 0xc:
		return None
	q[0] += 4
	if b[q[0]] != 3:   # not a line
		return None
	q[0] += 1
	tool, pts, ours = None, [], True
	while q[0] < len(b):
		i, t = tag()
		if i == 1 and t == 0x4:
			tool = struct.unpack_from("<I", b, q[0])[0]; q[0] += 4
		elif i == 5 and t == 0xc:
			n = struct.unpack_from("<I", b, q[0])[0]; q[0] += 4
			size = 14 if ver >= 2 else 24
			for k in range(q[0], q[0] + n - size + 1, size):
				if size == 14:
					x, y, sp, w, _, pr = struct.unpack_from("<ffHHBB", b, k)
					pts.append((x, y, w / 4)); ours = ours and sp == 2 and pr == 255
				else:
					x, y, _, _, w, _ = struct.unpack_from("<6f", b, k)
					pts.append((x, y, w)); ours = False
			q[0] += n
			break
		else:
			skip(t)
	return (tool, pts, ours) if pts else None

ERASERS, MARKERS = {6, 8}, {5, 18}

def render_page(data, pad=40, new_only=True):
	"""The owner's ink since the last answer on the page (all of it when there is none), cropped to it, as a PNG
	(bytes); None when nothing is written there."""
	ss = strokes(data)
	if not new_only:
		ss = [s for s in ss if not s[2]]
	last = max([i for i, (_, _, ours) in enumerate(ss) if ours] or [-1])
	ss = [(t, p) for t, p, _ in ss[last + 1:] if t not in ERASERS and t not in MARKERS]
	if not ss:
		return None
	xs = [x for _, p in ss for x, _, _ in p]; ys = [y for _, p in ss for _, y, _ in p]
	x0, y0 = min(xs) - pad, min(ys) - pad
	im = Image.new("L", (int(max(xs) - x0 + pad), int(max(ys) - y0 + pad)), 255)
	d = ImageDraw.Draw(im)
	for _, p in ss:
		w = max(2, int(sum(w for _, _, w in p) / len(p)))
		d.line([(x - x0, y - y0) for x, y, _ in p], fill=0, width=w, joint="curve")
	f = io.BytesIO(); im.save(f, "PNG"); return f.getvalue()


def vu(n):
	o = b""
	while True:
		c = n & 0x7f; n >>= 7
		if n: o += bytes([c | 0x80])
		else: return o + bytes([c])
def tag(i, t): return vu(i << 4 | t)
def cid(i, a, n): return tag(i, 0xf) + bytes([a]) + vu(n)
def i4(i, v): return tag(i, 0x4) + struct.pack("<I", v)
def sub(i, b): return tag(i, 0xc) + struct.pack("<I", len(b)) + b

def blocks(d):
	p, out = 43, []
	while p + 8 <= len(d):
		n, u, mn, ver, k = struct.unpack_from("<IBBBB", d, p); out.append((k, d[p:p + 8 + n])); p += 8 + n
	return out

def blank(d):
	"""Page d without its strokes, and where its strokes went (for append's start): a fresh page of the notebook."""
	bl = [r for k, r in blocks(d) if k == 5]
	return d[:43] + b"".join(r for k, r in blocks(d) if k != 5), last_item(bl[-1])


def last_item(raw):
	b = raw[8:]; q = 1   # tag 0x1f parent id: skip author byte + varuint
	def rid(q):
		a = b[q]; q += 1; v = sh = 0
		while True:
			c = b[q]; q += 1; v |= (c & 0x7f) << sh; sh += 7
			if not c & 0x80: return (a, v), q
	parent, q = rid(q); q += 1; item, q = rid(q)
	return parent, item

def line_block(parent, item, left, pts, tool=17, color=0, width=2.0):
	# An optional fourth value is the pen's angle; speed 2 and pressure 255 always mark the stroke as ours.
	P = b"".join(struct.pack("<ffHHBB", x, y, 2, int(w * 4), d[0] if d else 0, 255) for x, y, w, *d in pts)
	val = bytes([3]) + i4(1, tool) + i4(2, color) + tag(3, 0x8) + struct.pack("<d", width) + tag(4, 0x4) + struct.pack("<f", 0) \
		+ sub(5, P) + cid(6, 0, 1)
	body = cid(1, *parent) + cid(2, *item) + cid(3, *left) + cid(4, 0, 0) + i4(5, 0) + sub(6, val)
	return struct.pack("<IBBBB", len(body), 0, 2, 2, 5) + body

def append(d, lines, start=None):
	"""d plus lines ([[(x, y, w)...]...]) as new strokes after the last, in the same layer; on a page with none,
	start = (layer, last item id) from another page of the notebook."""
	bl = [r for k, r in blocks(d) if k == 5]
	parent, item = last_item(bl[-1]) if bl else start
	out, left, n = d, item if bl else (0, 0), item[1]
	for pts in lines:
		n += 1; out += line_block(parent, (item[0], n), left, pts); left = (item[0], n)
	return out


HAND = ("/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf", 0)

def thin(a):
	"""Zhang-Suen thinning of a boolean image (True = ink)."""
	a = np.pad(a.astype(np.uint8), 1)
	while True:
		changed = False
		for step in (0, 1):
			p = [np.roll(np.roll(a, -dy, 0), -dx, 1) for dy, dx in
				((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))]   # P2..P9
			b = sum(p)
			seq = p + [p[0]]
			trans = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
			if step == 0:
				c = (p[0] * p[2] * p[4] == 0) & (p[2] * p[4] * p[6] == 0)
			else:
				c = (p[0] * p[2] * p[6] == 0) & (p[0] * p[4] * p[6] == 0)
			m = (a == 1) & (b >= 2) & (b <= 6) & (trans == 1) & c
			if m.any():
				a[m] = 0; changed = True
		if not changed:
			return a[1:-1, 1:-1].astype(bool)

N8 = ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))

def trace(sk):
	"""The skeleton as polylines [(x, y)...]: from each end, along unvisited pixels; then what loops remain."""
	pix = set(zip(*np.nonzero(sk)))
	nb = lambda p: [(p[0] + dy, p[1] + dx) for dy, dx in N8 if (p[0] + dy, p[1] + dx) in pix]
	seen, out = set(), []
	def walk(p):
		path = [p]; seen.add(p)
		while True:
			n = [q for q in nb(path[-1]) if q not in seen]
			if not n: break
			seen.add(n[0]); path.append(n[0])
		out.append([(x, y) for y, x in path] if len(path) > 1 else [(p[1], p[0]), (p[1] + 1, p[0] + 1)])   # a dot too
	for p in sorted(pix, key=lambda p: (len(nb(p)), p[1])):
		if p not in seen and len(nb(p)) <= 1:
			walk(p)
	for p in sorted(pix):
		if p not in seen:
			walk(p)
	return out

def rdp(pts, eps=0.8):
	if len(pts) < 3: return pts
	a, b = np.array(pts[0], float), np.array(pts[-1], float)
	d = b - a; L = np.hypot(*d) or 1
	dist = [abs(d[0] * (a[1] - y) - d[1] * (a[0] - x)) / L for x, y in pts[1:-1]]
	i = int(np.argmax(dist)) + 1
	if dist[i - 1] <= eps: return [pts[0], pts[-1]]
	return rdp(pts[:i + 1], eps)[:-1] + rdp(pts[i:], eps)

def wrap(text, font, width):
	lines, cur = [], ""
	for w in text.split():
		t = (cur + " " + w).strip()
		if font.getlength(t) <= width or not cur: cur = t
		else: lines.append(cur); cur = w
	return lines + ([cur] if cur else [])

def pen_text(text, width, size=44, leading=1.5, max_lines=None, face=HAND):
	"""text in a face (path, index), wrapped to width, as pen strokes [[(x, y)...]] from (0, 0), and the height used."""
	font = face if hasattr(face, "getmask") else ImageFont.truetype(face[0], size, index=face[1])
	lines = wrap(text, font, width)
	if max_lines and len(lines) > max_lines:
		lines = lines[:max_lines]; lines[-1] = lines[-1].rstrip(".,;:") + " …"
	lh = int(size * leading)
	im = Image.new("L", (int(width) + 20, lh * len(lines) + size), 0)
	d = ImageDraw.Draw(im)
	for i, l in enumerate(lines):
		d.text((0, i * lh), l, font=font, fill=255)
	paths = [rdp(p) for p in trace(thin(np.array(im) > 128))]
	return paths, lh * len(lines)


def svg_lines(svg, width, height):
	"""A line drawing in SVG (line, polyline, polygon, rect, circle, ellipse, path with M L H V C S Q Z, absolute or
	relative) as pen strokes [[(x, y)...]] scaled into width x height from (0, 0), and the height used."""
	import re, xml.etree.ElementTree as ET
	root = ET.fromstring(svg)
	vb = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox", "").strip()) if v] or \
		[0, 0, float(root.get("width", 100)), float(root.get("height", 100))]
	out = []
	def num(e, k, d=0.0):
		try: return float(re.sub(r"[a-z%]+$", "", e.get(k, d)))
		except ValueError: return d
	def bez(p0, pts, n=12):
		seg = []
		for i in range(1, n + 1):
			t = i / n
			if len(pts) == 2:
				(x1, y1), (x2, y2) = pts
				seg.append(((1-t)**2*p0[0] + 2*(1-t)*t*x1 + t*t*x2, (1-t)**2*p0[1] + 2*(1-t)*t*y1 + t*t*y2))
			else:
				(x1, y1), (x2, y2), (x3, y3) = pts
				seg.append(((1-t)**3*p0[0] + 3*(1-t)**2*t*x1 + 3*(1-t)*t*t*x2 + t**3*x3,
					(1-t)**3*p0[1] + 3*(1-t)**2*t*y1 + 3*(1-t)*t*t*y2 + t**3*y3))
		return seg
	def path(d):
		toks = re.findall(r"[MmLlHhVvCcSsQqZz]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?", d)
		i, cmd, cur, start, last_c, pl = 0, "", (0.0, 0.0), (0.0, 0.0), None, []
		def take(k):
			nonlocal i
			v = [float(t) for t in toks[i:i + k]]; i += k; return v
		while i < len(toks):
			if toks[i].isalpha():
				cmd = toks[i]; i += 1
				if cmd in "Zz":
					pl.append(start); out.append(pl); pl = [start]; cur = start; continue
			rel, c = cmd.islower(), cmd.upper()
			ox, oy = cur if rel else (0, 0)
			if c == "M":
				x, y = take(2); cur = start = (ox + x, oy + y)
				if len(pl) > 1: out.append(pl)
				pl = [cur]; cmd = "l" if rel else "L"
			elif c == "L":
				x, y = take(2); cur = (ox + x, oy + y); pl.append(cur)
			elif c == "H":
				x, = take(1); cur = ((cur[0] if rel else 0) + x, cur[1]); pl.append(cur)
			elif c == "V":
				y, = take(1); cur = (cur[0], (cur[1] if rel else 0) + y); pl.append(cur)
			elif c == "C":
				v = take(6); p = [(ox + v[0], oy + v[1]), (ox + v[2], oy + v[3]), (ox + v[4], oy + v[5])]
				pl += bez(cur, p); last_c = p[1]; cur = p[2]
			elif c == "S":
				v = take(4); r1 = (2*cur[0] - last_c[0], 2*cur[1] - last_c[1]) if last_c else cur
				p = [r1, (ox + v[0], oy + v[1]), (ox + v[2], oy + v[3])]
				pl += bez(cur, p); last_c = p[1]; cur = p[2]
			elif c == "Q":
				v = take(4); p = [(ox + v[0], oy + v[1]), (ox + v[2], oy + v[3])]
				pl += bez(cur, p); cur = p[1]
			else:
				i += 1
		if len(pl) > 1: out.append(pl)
	for e in root.iter():
		t = e.tag.split("}")[-1]
		if t == "line":
			out.append([(num(e, "x1"), num(e, "y1")), (num(e, "x2"), num(e, "y2"))])
		elif t in ("polyline", "polygon"):
			v = [float(x) for x in re.split(r"[\s,]+", e.get("points", "").strip()) if x]
			pts = list(zip(v[::2], v[1::2]))
			out.append(pts + pts[:1] if t == "polygon" else pts)
		elif t == "rect":
			x, y, w, h = num(e, "x"), num(e, "y"), num(e, "width"), num(e, "height")
			out.append([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])
		elif t in ("circle", "ellipse"):
			cx, cy = num(e, "cx"), num(e, "cy")
			rx = num(e, "r") if t == "circle" else num(e, "rx"); ry = num(e, "r") if t == "circle" else num(e, "ry")
			out.append([(cx + rx * math.cos(a * math.pi / 24), cy + ry * math.sin(a * math.pi / 24)) for a in range(49)])
		elif t == "path":
			path(e.get("d", ""))
	s = min(width / vb[2], height / vb[3])
	lines = [[((x - vb[0]) * s, (y - vb[1]) * s) for x, y in l] for l in out if len(l) > 1]
	return lines, vb[3] * s
