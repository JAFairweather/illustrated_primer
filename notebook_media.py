"""Bounded notebook images and a small, non-executing equation renderer.

No TeX process, network fetch, arbitrary local-path attachment, or new dependency.
Equation rendering is deliberately a subset, not a general LaTeX implementation.
"""
import hashlib
import io
import math
import os
import re
import warnings
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont, ImageOps

MAX_BYTES, MAX_PIXELS = 12_000_000, 20_000_000
KINDS = {"photo", "illustration", "diagram", "equation"}
MATH_PATTERN = r"```(?:math|latex)\s*\n?(.*?)```|\\\[(.*?)\\\]|\$\$(.*?)\$\$|\\\((.*?)\\\)"


def native_inline_math(text):
    """Keep unambiguous elementary inline terms in editable native prose.

    Complex notation stays in the bounded equation renderer. Never approximate
    a fraction, remove grouping, evaluate, or substitute a mathematical value.
    """
    atom = r'[A-Za-z0-9Δ]+(?:\^(?:[0-9]+|\{[0-9]+\})|_(?:[0-9]+|\{[0-9]+\}|[ijkn]|\{[ijkn]\})){0,2}'
    superscript = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')
    subscript = str.maketrans('0123456789ijkn', '₀₁₂₃₄₅₆₇₈₉ᵢⱼₖₙ')
    def convert(match):
        source = match[1].strip()
        # Ordinary quantities belong in native prose, not little equation images.
        # Restrict this to literal whitelisted units; never evaluate or guess.
        quantity = re.fullmatch(r'([+-]?[0-9]+(?:\.[0-9]+)?)\s*(?:\\[,; ]\s*)?'
                                r'\\(?:text|mathrm)\{([A-Za-z]+(?:/[A-Za-z]+)?)\}'
                                r'(?:\^(\d|\{[0-9]+\}))?', source)
        units = {'m', 's', 'ms', 'kg', 'g', 'N', 'J', 'W', 'Hz', 'cm', 'mm', 'km', 'm/s', 'km/s', 'km/h'}
        if quantity and quantity[2] in units:
            exponent = (quantity[3] or '').strip('{}')
            if len(exponent) <= 3:
                return quantity[1] + ' ' + quantity[2] + exponent.translate(superscript)
        source = re.sub(r'\\Delta\b\s*', 'Δ', source)
        term = atom + r'(?:/' + atom + r')?'
        if len(source) > 80 or not re.fullmatch(term + r'(?:\s*=\s*' + term + r')?', source):
            return match[0]
        # Do not flatten invalid repeated scripts into a different expression.
        for part in re.split(r'[/=]', source):
            if part.count('^') > 1 or part.count('_') > 1:
                return match[0]
        source = re.sub(r'\^\{?([0-9]+)\}?', lambda m: m[1].translate(superscript), source)
        return re.sub(r'_\{?([0-9]+|[ijkn])\}?', lambda m: m[1].translate(subscript), source)
    # Display/fenced math is deliberately left untouched, including any literal
    # inline-looking delimiter within such a block (which the parser will reject).
    pattern = r'```(?:math|latex)\s*\n?.*?```|\\\[.*?\\\]|\$\$.*?\$\$|\\\((.*?)\\\)'
    return re.sub(pattern, lambda m: convert(m) if m[1] is not None else m[0], text, flags=re.S)


def clean_notebook_prose(text):
    """Remove supported presentation markup without losing paragraph boundaries."""
    original = text
    text = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]+", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.S)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"(?m)^```[^\n]*\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # The native heading paragraph already supplies vertical separation.
    # Markdown's empty paragraphs on either side double that space. Compact
    # only unambiguous headings that will actually receive a native style;
    # retain ordinary prose paragraph boundaries and all words unchanged.
    headings = {item['paragraph'] for item in notebook_paragraph_styles(original, text)}
    lines = text.split('\n')
    return '\n'.join(line for index, line in enumerate(lines)
                     if line.strip() or not ({index-1, index+1} & headings))


def notebook_blocks(text, store, ink_catalog=None):
    """Prepare ordered native prose and registered media, never raw file paths.

    Each equation is its own scene item, surrounded by the prose that actually
    preceded/followed it. Preparation validates the entire reply before returning
    any insertion plan. The tablet must not render a partially prepared reply.
    This is a block layout, not inline mathematical typography within a sentence.
    """
    if re.search(r'```\s*board-step\b', text):
        raise ValueError('board-step lessons require the native lesson adapter; reply remains held')
    text = native_inline_math(text.replace('\r\n', '\n').replace('\r', '\n'))
    token = re.compile(r"\[\[notebook-asset:(?P<asset>[0-9a-f]{64})\]\]|"
                       r"\[\[notebook-ink:(?P<scene>[a-z0-9-]{1,80}):(?P<stage>[a-z0-9-]{1,80})\]\]|" + MATH_PATTERN, re.S)
    blocks, referenced, media_count, ink_count = [], set(), 0, 0
    seen_ink = set()
    scene_progress = {}

    def prose(raw):
        if '[[notebook-asset:' in raw or '[[notebook-media-pending]]' in raw or '[[notebook-ink:' in raw:
            raise ValueError("notebook media reference is invalid or not ready")
        plain = clean_notebook_prose(raw)
        if plain:
            blocks.append({'kind': 'text', 'text': plain,
                           'styles': notebook_paragraph_styles(raw, plain)})

    end = 0
    for match in token.finditer(text):
        prose(text[end:match.start()])
        if match['scene'] is not None:
            identity = (match['scene'], match['stage'])
            if ink_catalog is None:
                raise ValueError('native ink renderer is not provisioned; reply remains held')
            if identity in seen_ink or ink_count >= 6:
                raise ValueError('duplicate or excessive native ink stage')
            block = dict(kind='ink', **ink_catalog.get(*identity))
            if block['stage_index'] != scene_progress.get(block['scene'], 0):
                raise ValueError('native drawing stages must follow their authored order')
            scene_progress[block['scene']] = block['stage_index']+1
            blocks.append(block)
            seen_ink.add(identity)
            ink_count += 1
            end = match.end()
            continue
        asset = match['asset']
        if asset is not None:
            store.get(asset)
            # Preserve the existing registered-attachment deduplication contract.
            if asset in referenced:
                end = match.end()
                continue
            referenced.add(asset)
        if media_count >= 6:
            raise ValueError("at most six media blocks fit one notebook reply")
        if asset is None:
            # Three named marker captures precede the existing math captures.
            source = next(value for value in match.groups()[3:] if value is not None).strip()
            asset = store.equation(source)['asset']
        blocks.append({'kind': 'media', 'asset': asset})
        media_count += 1
        end = match.end()
    prose(text[end:])
    return blocks


def notebook_paragraph_styles(original, plain):
    """Mark only explicit, unambiguous short headings in the cleaned prose.

    Paragraph numbers avoid Python code-point versus Qt UTF-16 offset errors.
    Never infer a heading from capitalization or a sentence's visual length.
    """
    headings, fenced = set(), False
    for line in original.splitlines():
        if line.lstrip().startswith('```'):
            fenced = not fenced
            continue
        match = re.fullmatch(r'\s*#{1,3}\s+(.+?)\s*', line) if not fenced else None
        if match:
            heading = re.sub(r'\*\*|`', '', match[1]).strip()
            if 1 <= len(heading) <= 100:
                headings.add(heading)
    lines = plain.split('\n')
    return [{'paragraph': i, 'style': 'subheading'} for i, line in enumerate(lines)
            if line in headings and lines.count(line) == 1][:8]


def notebook_content(text, store, ink_catalog=None):
    """Turn explicit math blocks into real assets, never literal TeX on paper.

    Original agent text remains in the durable pending job/transcript. Unsupported
    math raises before insertion, rather than silently dropping or mis-typesetting it.
    """
    if re.search(r'```\s*board-step\b', text):
        raise ValueError('board-step lessons require the native lesson adapter; reply remains held')
    text = native_inline_math(text.replace('\r\n', '\n').replace('\r', '\n'))
    if '[[notebook-ink:' in text:
        # Full ordered validation precedes stripping the legacy prose field.
        notebook_blocks(text, store, ink_catalog)
        text = re.sub(r'\[\[notebook-ink:[a-z0-9-]{1,80}:[a-z0-9-]{1,80}\]\]', '', text)
    assets = []
    def attachment(match):
        asset = match.group(1)
        store.get(asset)  # Registered, integrity-checked image only; no paths/URLs.
        if asset not in assets:
            if len(assets) >= 6:
                raise ValueError("at most six images fit one notebook reply")
            assets.append(asset)
        return ""
    text = re.sub(r"\[\[notebook-asset:([0-9a-f]{64})\]\]", attachment, text)
    if "[[notebook-asset:" in text or "[[notebook-media-pending]]" in text:
        raise ValueError("notebook media reference is invalid or not ready")
    def equation(match):
        if len(assets) >= 6:
            raise ValueError("at most six equations fit one notebook reply")
        source = next(value for value in match.groups() if value is not None).strip()
        assets.append(store.equation(source)["asset"])
        return ""
    plain = clean_notebook_prose(re.sub(MATH_PATTERN, equation, text, flags=re.S))
    return plain, assets


@dataclass
class Box:
    image: Image.Image
    baseline: int
    limits: bool = False


def canvas(width, height, baseline):
    if width > 16000 or height > 8000:
        raise ValueError("equation layout too large")
    return Box(Image.new("L", (max(1, int(width)), max(1, int(height))), 255), int(baseline))


def glyph(text, size):
    # The bundled Pillow font is available even inside the agent's sandbox.
    font = ImageFont.load_default(size=max(10, int(size)))
    ascent, descent = font.getmetrics()
    out = canvas(math.ceil(font.getlength(text)) + 4, ascent + descent + 4, ascent + 2)
    ImageDraw.Draw(out.image).text((2, out.baseline), text, font=font, fill=0, anchor="ls")
    return out


def math_symbol(symbol, size):
    """Draw explicit geometric glyphs; no font-dependent missing-glyph box."""
    if symbol == 'times':
        metrics = glyph(' ', size)
        out = canvas(size*.8, metrics.image.height, metrics.baseline)
        draw = ImageDraw.Draw(out.image)
        width = max(2, round(size/22))
        center = out.baseline-size*.30
        for direction in (-1, 1):
            draw.line([(size*.18, center+direction*size*.22),
                       (size*.62, center-direction*size*.22)], fill=0, width=width)
        return out
    if symbol in ('approx', 'Rightarrow'):
        metrics = glyph(' ', size)
        out = canvas(size*1.2, metrics.image.height, metrics.baseline)
        draw = ImageDraw.Draw(out.image)
        width = max(2, round(size/22))
        center = out.baseline-size*.30
        if symbol == 'approx':
            for offset in (-.11, .11):
                points = [(size*(.12+.96*i/24),
                           center+size*(offset+.06*math.sin(2*math.pi*i/24)))
                          for i in range(25)]
                draw.line(points, fill=0, width=width, joint='curve')
        else:
            for offset in (-.10, .10):
                draw.line([(size*.12, center+size*offset),
                           (size*.84, center+size*offset)], fill=0, width=width)
            draw.line([(size*.76, center-size*.27), (size*1.08, center),
                       (size*.76, center+size*.27)], fill=0, width=width, joint='curve')
        return out
    if symbol in ('cdots', 'ldots'):
        metrics = glyph(' ', size)
        out = canvas(size*.9, metrics.image.height, metrics.baseline)
        y = out.baseline-size*(.28 if symbol == 'cdots' else .05)
        radius = max(1.5, size*.035)
        draw = ImageDraw.Draw(out.image)
        for x in (.15,.45,.75):
            x *= size
            draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=0)
        return out
    if symbol == 'Delta':
        out = canvas(size*.85, size*1.12, size*.95)
        points = [(.08, .95), (.42, .12), (.77, .95), (.08, .95)]
    elif symbol == 'sum':
        out = canvas(size*.9, size*1.85, size*1.4)
        out.limits = True
        points = [(.78, .12), (.12, .12), (.48, .9), (.12, 1.68), (.78, 1.68)]
    else:
        raise ValueError('unsupported geometric math symbol')
    ImageDraw.Draw(out.image).line([(x*size, y*size) for x, y in points],
                                  fill=0, width=max(2, round(size/22)), joint='curve')
    return out


def row(parts):
    if not parts:
        return glyph(" ", 20)
    baseline = max(part.baseline for part in parts)
    descent = max(part.image.height - part.baseline for part in parts)
    out = canvas(sum(part.image.width for part in parts), baseline + descent, baseline)
    x = 0
    for part in parts:
        out.image.paste(part.image, (x, baseline - part.baseline))
        x += part.image.width
    return out


def fraction(numerator, denominator, size):
    gap = max(5, int(size * .13))
    width = max(numerator.image.width, denominator.image.width) + gap * 2
    bar = numerator.image.height + gap
    out = canvas(width, bar + gap + denominator.image.height + 3, bar + size * .27)
    out.image.paste(numerator.image, ((width - numerator.image.width) // 2, 0))
    out.image.paste(denominator.image, ((width - denominator.image.width) // 2, bar + gap + 3))
    ImageDraw.Draw(out.image).line((2, bar, width - 3, bar), fill=0, width=max(2, int(size / 25)))
    return out


def scripts(base, upper, lower):
    up_y = (-int(upper.image.height * .2) if base.limits else
            base.baseline - upper.image.height - 5) if upper else 0
    low_y = (base.image.height - int(lower.image.height * .2)
             if base.limits and lower else base.baseline + 6)
    shift = max(0, -up_y) if upper else 0
    extra = max([part.image.width for part in (upper, lower) if part] or [0])
    height = max(base.image.height, low_y + (lower.image.height if lower else 0)) + shift
    out = canvas(base.image.width + extra, height, base.baseline + shift)
    out.image.paste(base.image, (0, shift))
    if upper:
        out.image.paste(upper.image, (base.image.width, up_y + shift))
    if lower:
        out.image.paste(lower.image, (base.image.width, low_y + shift))
    return out


def integral(size):
    out = canvas(size * .65, size * 2.2, size * 1.65)
    out.limits = True
    segments = [((.57, .12), (.12, -.15), (.40, 1.0), (.25, 1.35)),
                ((.25, 1.35), (.12, 2.14), (.15, 2.3), (.02, 2.05))]
    points = []
    for p0, p1, p2, p3 in segments:
        for step in range(81):
            t = step / 80
            points.append(tuple(size * ((1-t)**3*p0[i] + 3*(1-t)**2*t*p1[i]
                                       + 3*(1-t)*t*t*p2[i] + t**3*p3[i]) for i in (0, 1)))
    ImageDraw.Draw(out.image).line(points, fill=0, width=max(3, int(size / 18)), joint="curve")
    return out


def radical(body, size):
    left, top = int(size * .6), 9
    height = max(body.image.height + top + 5, int(size))
    out = canvas(left + body.image.width + 7, height, body.baseline + top)
    out.image.paste(body.image, (left, top))
    ImageDraw.Draw(out.image).line([(1, height * .53), (left * .25, height * .48),
        (left * .48, height - 4), (left - 2, 3), (out.image.width - 2, 3)],
        fill=0, width=max(2, int(size / 25)), joint="curve")
    return out


class Equation:
    def __init__(self, source, renderer=None):
        if not isinstance(source, str) or not source.strip() or len(source) > 2000:
            raise ValueError("equation must contain 1 to 2000 characters")
        # Ordinary TeX whitespace does not start another equation. Keep a
        # separator so line-wrapped commands never concatenate accidentally.
        source = re.sub(r"\s+", " ", source).replace("∫", r"\int ")
        # Treat a contiguous Unicode numeric script as ONE grouped argument.
        # Replacing digits individually would turn x¹² into x^1^2 and reject
        # or misinterpret a perfectly ordinary exponent. No expression eval.
        for alphabet, marker in (('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻', '^'), ('₀₁₂₃₄₅₆₇₈₉₊₋', '_')):
            translation = str.maketrans(alphabet, '0123456789+-')
            source = re.sub('['+alphabet+']+',
                            lambda m: marker+'{'+m[0].translate(translation)+'}', source)
        self.source = source
        self.pos = 0
        # Internal rendering backend only; never accepted from equation input.
        # The bounded grammar is shared by raster math and native pen math.
        self.render = renderer if renderer is not None else dict(
            glyph=glyph, canvas=canvas, row=row, fraction=fraction,
            scripts=scripts, integral=integral, radical=radical, math_symbol=math_symbol)

    def argument(self, size, depth):
        while self.pos < len(self.source) and self.source[self.pos] == " ":
            self.pos += 1
        return self.atom(size, depth)

    def parse(self, size=64, grouped=False, depth=0):
        if depth > 16:
            raise ValueError("equation nesting too deep")
        parts = []
        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char == "}":
                if not grouped:
                    raise ValueError("unexpected closing equation brace")
                self.pos += 1
                return self.render['row'](parts)
            if char in "^_":
                if not parts:
                    raise ValueError("equation script has no base")
                upper = lower = None
                while self.pos < len(self.source) and self.source[self.pos] in "^_":
                    kind = self.source[self.pos]
                    self.pos += 1
                    value = self.argument(size * .62, depth + 1)
                    if kind == "^":
                        if upper:
                            raise ValueError("duplicate superscript")
                        upper = value
                    else:
                        if lower:
                            raise ValueError("duplicate subscript")
                        lower = value
                parts[-1] = self.render['scripts'](parts[-1], upper, lower)
            else:
                parts.append(self.atom(size, depth + 1))
        if grouped:
            raise ValueError("unclosed equation brace")
        return self.render['row'](parts)

    def atom(self, size, depth):
        if depth > 16 or self.pos >= len(self.source):
            raise ValueError("incomplete or deeply nested equation")
        char = self.source[self.pos]
        self.pos += 1
        if char == "{":
            return self.parse(size, True, depth)
        if char == "\\":
            match = re.match(r"[A-Za-z]+|.", self.source[self.pos:])
            if not match:
                raise ValueError("incomplete equation command")
            command = match.group()
            self.pos += len(command)
            if command in (",", ";", " "):
                return self.render['glyph'](" ", size * .5)
            if command in ('quad', 'qquad'):
                metrics = self.render['glyph'](' ', size)
                return self.render['canvas'](size*(2 if command == 'qquad' else 1),
                              metrics.height if hasattr(metrics, 'height') else metrics.image.height, metrics.baseline)
            if command in ('%', '$'):
                return self.render['glyph'](command, size)
            if command in ("left", "right"):
                return self.atom(size, depth + 1)
            if command in ("frac", "dfrac"):
                numerator = self.argument(size * .85, depth + 1)
                denominator = self.argument(size * .85, depth + 1)
                return self.render['fraction'](numerator, denominator, size)
            if command == "sqrt":
                return self.render['radical'](self.argument(size, depth + 1), size)
            if command == "int":
                return self.render['integral'](size)
            if command in ('Delta', 'sum', 'cdots', 'ldots', 'approx', 'Rightarrow'):
                return self.render['math_symbol'](command, size)
            if command in ("sin", "cos", "tan", "ln", "log", "exp"):
                return self.render['glyph'](command, size)
            if command in ('text', 'mathrm'):
                # Literal ASCII annotation, not a TeX interpreter. Nested groups,
                # escapes and commands are intentionally not supported here.
                match = re.match(r'\s*\{([A-Za-z0-9 /().,+-]{1,120})\}', self.source[self.pos:])
                if not match:
                    raise ValueError('equation text must be bounded literal ASCII')
                self.pos += len(match.group())
                return self.render['glyph'](match[1], size)
            if command == "times":
                return self.render['math_symbol']('times', size)
            if command == "cdot":
                return self.render['glyph'](" . ", size)
            raise ValueError("unsupported equation command: \\" + command)
        if char in ('Δ', 'Σ'):
            return self.render['math_symbol']('Delta' if char == 'Δ' else 'sum', size)
        if char == '×':
            return self.render['math_symbol']('times', size)
        if char in ('⋯', '…'):
            return self.render['math_symbol']('cdots' if char == '⋯' else 'ldots', size)
        if char in ('≈', '⇒'):
            return self.render['math_symbol']('approx' if char == '≈' else 'Rightarrow', size)
        if not char.isascii() or char in "}^_\n\r\t":
            raise ValueError("unsupported equation character")
        return self.render['glyph'](char, size)


def render_equation(source):
    box = Equation(source).parse()
    out = ImageOps.expand(box.image, border=24, fill=255)
    if out.width > 2200:
        raise ValueError("equation too wide; split it into separate steps")
    if out.width > 1100:
        out = out.resize((1100, round(out.height * 1100 / out.width)), Image.Resampling.LANCZOS)
    return out


class AssetStore:
    def __init__(self, directory):
        self.directory = directory

    def put(self, data, kind="photo"):
        if kind not in KINDS:
            raise ValueError("unsupported notebook image kind")
        if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
            raise ValueError("notebook image exceeds byte limit")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.width * original.height > MAX_PIXELS:
                    raise ValueError("notebook image exceeds pixel limit")
                image = ImageOps.exif_transpose(original).convert("RGBA")
                flat = Image.new("RGBA", image.size, "white")
                flat.alpha_composite(image)
                image = flat.convert("L")
        image.thumbnail((1100, 1400), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, "PNG")  # no source EXIF, GPS, or other metadata
        normalized = output.getvalue()
        asset = hashlib.sha256(normalized).hexdigest()
        os.makedirs(self.directory, exist_ok=True)
        target = os.path.join(self.directory, asset + ".png")
        if not os.path.exists(target):
            with open(target + ".new", "wb") as stream:
                stream.write(normalized)
            os.replace(target + ".new", target)
        return {"asset": asset, "kind": kind, "width": image.width, "height": image.height}

    def equation(self, source):
        output = io.BytesIO()
        render_equation(source).save(output, "PNG")
        return self.put(output.getvalue(), "equation")

    def get(self, asset):
        if not isinstance(asset, str) or not re.fullmatch(r"[0-9a-f]{64}", asset):
            raise ValueError("not a notebook asset ID")
        with open(os.path.join(self.directory, asset + ".png"), "rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != asset:
            raise ValueError("notebook image integrity check failed")
        return data
