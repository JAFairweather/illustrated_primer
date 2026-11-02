"""Line-art frames from a Gemini image model: a base scene from text, then each edit applied to the frame before.
Quick text calls help a lesson along: story() writes its tale before the answering model draws it, direct() writes a
picture for a lesson that came without one, and facts() looks up what is current for a question about recent news.

Every call is a line in the shared Gemini ledger (~/.local/state/gemini/calls.log). The text callers' hold-until is
respected, but a 429 here writes hold-until-image, so a busy image quota never silences note reading or the R1
summaries. Frames are cached by model, prompt and the frame they edit, so a replay costs nothing.
"""
import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

from notebook_lesson import CAPTION
TAKEAWAY = 500  # compile_lesson's own limit for the takeaway

MODEL = os.environ.get('HERD_BOARD_IMAGE_MODEL', 'gemini-3.1-flash-image')
# Each image model has its own daily quota: when MODEL is held after a 429, pictures come from this one.
FALLBACK = os.environ.get('HERD_BOARD_IMAGE_FALLBACK', 'gemini-2.5-flash-image')
DIRECTOR = os.environ.get('HERD_BOARD_DIRECTOR_MODEL', 'gemini-3.5-flash-lite')
# The lite model boxes something even when the thing is not drawn; flash leaves it out.
# Tales by Claude through claude -p with the Primer's prompt as its whole system prompt: on 2026-11-01 James's
# what-is shape came back from Opus as he wrote it, where Pi Dog's own tales were "so weak again and again".
WRITER = os.environ.get('HERD_BOARD_STORY_MODEL', 'claude-opus-5-5')
LOCATOR = os.environ.get('HERD_BOARD_LOCATOR_MODEL', 'gemini-3.5-flash')
GEMINI = os.path.expanduser('~/.local/state/gemini')
KEYF = os.path.expanduser('~/.nvoy-harness/credentials/gemini-api-key')
CACHE = os.path.expanduser('~/.cache/herd-board/frames')
KEPT = os.path.join(CACHE, 'kept')  # each reply's frames by request id, so a replay draws what the reply drew
KEEP = 200  # requests whose frames are kept, as many as the replies kept for herd-board-replay
STYLE = ('An explainer doodle in black marker on a pure white background, like a teacher sketching on a whiteboard to '
         'explain an idea. Thick, even marker strokes in one line weight: no shading, no fills, no grey, no hatching, no '
         'border%s, and no text, names, letters or numbers anywhere. Draw each object as its simplest recognizable outline, in a '
         'few long strokes: a plank is a long thin rectangle, a rock a lumpy outline, a person or an animal a '
         'simple figure of about a dozen lines. No decoration or texture: no rivets, bolts, dots, panel lines, tiny '
         'circles or small repeated details, and no scenery the explanation does not use. Draw a group of many things (a '
         'city, a crowd, a forest, rain) as three to five large ones, never a field of small ones. Things that touch are drawn '
         'touching, and a thing that rests on another sits on it. Show pushes, pulls and motion with arrows and short '
         'motion lines, never dashed or dotted lines. Draw every arrow as one plain line with an open V-shaped head, never a '
         'filled, outlined or block arrow. Keep the parts large, with white space '
         'between them.')
PANELS = ' (except a thin frame around each panel of a strip of panels)'
EDIT = ('Keep every existing line exactly where it is and unchanged. Add only this, in the same line style, '
        'and draw nothing else: ')
# A picture of its own below the next paragraph (James, 2026-11-01: "inline each drawing with the text"): the frame
# before is only the model sheet for its characters.
SCENE = ('Draw a new picture, not a copy of this one: the same characters drawn the same way, in the same line style, '
         'in a new scene that shows only this: ')


def _held(name):
    try:
        with open(f'{GEMINI}/{name}') as f:
            return float(f.read()) > time.time()
    except (OSError, ValueError):
        return False


def _ledger(status, usage, start, hold=0, model=MODEL, name='herd-board-image', held='hold-until-image'):
    u = usage or {}
    try:
        os.makedirs(GEMINI, exist_ok=True)
        if hold:
            with open(f'{GEMINI}/{held}', 'w') as f:
                f.write(str(time.time()+hold))
        with open(f'{GEMINI}/calls.log', 'a') as f:
            f.write(f"{time.strftime('%F %T')} {name} {model} {status} in={u.get('promptTokenCount', 0)} "
                    f"cached={u.get('cachedContentTokenCount', 0)} out={u.get('candidatesTokenCount', 0)} "
                    f"think={u.get('thoughtsTokenCount', 0)} {time.time()-start:.2f}s"
                    f"{f' hold={hold:g}s' if hold else ''}\n")
    except OSError:
        pass


class EmptyImage(ValueError):
    pass


EMPTY_TRIES = 4


def _post(model, body, timeout, name='herd-board-image', held='hold-until-image'):
    """One generateContent call, in the ledger; a 429 holds this caller's kind of call for the delay Gemini asks."""
    with open(KEYF) as credential:
        api_key = credential.read().strip()
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                                 data=body, headers={'content-type': 'application/json', 'x-goog-api-key': api_key})
    del api_key
    log = dict(model=model, name=name, held=held)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        hold = 0
        if e.code == 429:
            try:
                hold = float(next(x['retryDelay'] for x in json.loads(e.read())['error']['details']
                                  if 'retryDelay' in x).rstrip('s'))
            except (OSError, ValueError, KeyError, TypeError, StopIteration):
                hold = 60
        _ledger(e.code, None, start, hold, **log)
        raise
    except OSError as e:
        _ledger(type(e).__name__, None, start, **log)
        raise
    _ledger(200, d.get('usageMetadata'), start, **log)
    return d


def direct(note, intent, captions, takeaway, timeout=30):
    """A picture for a lesson that came without one: {base, edits}, one edit per caption after the first, written by
    a fast text model from the lesson's own captions and the same picture note the answering model was given."""
    if _held('hold-until'):
        raise RuntimeError('Gemini is holding after a rate limit')
    steps = '\n'.join(f'{i+1}. {c}' for i, c in enumerate(captions))
    prompt = (f'A page of an illustrated science primer tells this lesson, one step at a time.\nWhat it explains: {intent}\n'
              f'Steps:\n{steps}\nTakeaway: {takeaway}\n\nWrite the picture that is drawn beside it, step by step.'
              f'{note}\n\nReturn only the JSON object {{"base": "...", "edits": [...], "labels": [[...], ...]}}, with '
              f'exactly {len(captions)-1} edits and {len(captions)} lists of labels.')
    body = json.dumps({'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                       'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.4}}).encode()
    d = _post(DIRECTOR, body, timeout, name='herd-board-director', held='hold-until')
    parts = ((d.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []
    return json.loads(''.join(p.get('text', '') for p in parts))


def facts(question, timeout=20):
    """What is current for question, from a Google-grounded search, in at most ~90 words; '' when nothing recent
    matters. The answering model's knowledge stops at its training; a question about 'the latest' result needs this."""
    if _held('hold-until'):
        raise RuntimeError('Gemini is holding after a rate limit')
    prompt = (f"Today is {time.strftime('%B %-d, %Y')}. A student asks a teacher: {json.dumps(question)}\n"
              'If a good answer depends on facts from the last two years (a new result, discovery, record, event or '
              'person in the news), search for them and state the key current facts in at most 90 words of plain '
              'sentences, newest result first: what, who, when, and what it does and does not show. Otherwise reply exactly '
              'NONE.')
    body = json.dumps({'contents': [{'role': 'user', 'parts': [{'text': prompt}]}], 'tools': [{'google_search': {}}],
                       'generationConfig': {'temperature': 0.2}}).encode()
    d = _post(DIRECTOR, body, timeout, name='herd-board-facts', held='hold-until')
    parts = ((d.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []
    text = ' '.join(''.join(p.get('text', '') for p in parts).replace('**', '').split())
    return '' if text.strip(' .').upper() == 'NONE' else text[:700]


# Offline on 2026-10-31 a tale written first, then drawn, judged 3.4 against 2.6 for one the answering model wrote itself.
STORY = """You are the Young Lady's Illustrated Primer from The Diamond Age, telling %(reader)s a tale that answers the
question on the page. The tale is the lesson, in one of two shapes.
When the question asks how or why something works or happens: invent one or two characters who belong to the subject
(never a robot) and who want something; what they do, and what happens to them because of how the world works, IS the
answer. 4 to 6 beats: the want; a first try or a puzzle; a surprise; the discovery (the real mechanism or fact, shown by
what happens, named in plain words once it is seen); how it ends.
When it asks what or who something is (a creature, a place, a thing, a band, a person): the subject itself is the hero,
with a name and a home in one concrete detail. Then three episodes, each one of its most remarkable true traits, the
ones that set it apart from almost everything else, never its dictionary definition: the hero does something, and a
"because" in the same sentence gives the real reason. Time moves on between episodes ("One day", "Later that winter").
The last beat begins "And so" and says what the subject is as the tale's moral. Never a bystander who "learns that" a
fact. James wrote this one for "What's a raven?"; follow its shape, never its words or names: "Once upon a time, in a
snowy forest, lived a raven named Thomas who saved a special stick in his nest, because he knew he'd need it tomorrow
to open a tricky pinecone, and very few animals in the whole world can plan ahead like that. One day, as he went to
hide a shiny berry, he spotted a crack in the old oak and thought, 'Someone might be peeking at me!', because ravens
are one of the rare creatures that can imagine what others might see. Later that winter, Thomas found a big frozen
feast too tough for his beak, so he did something only ravens do: he called to the wolves for help. The wolves opened
the feast with their strong teeth, and everyone ate together. And so the forest animals learned that Thomas wasn't
just any bird, he was a raven, one of the cleverest creatures in the world."
In both shapes each beat is one or two short sentences meant to be read
aloud, concrete and full of wonder, each an event, never narrator lecture. Amounts as the characters feel them, no
units unless asked. Every fact true and current (today is %(today)s; facts below if given). For a real person, band or
company, tell a true moment through an invented witness who carries its spirit. When the answer is a real mechanism,
a proof or a result, the tale keeps every essential step of the true one, in its true order; each invented thing
stands for one real part, and the beat that reveals it names the real part beside it ("the silk ropes, the spindle
fibres"). Name at most three real terms in the whole tale, each the one a curious child would learn first, and never
stack terms or use the language of papers, companies or textbooks (no "scaffolding", "framework", "solutions",
"leveraging"). Never let magic stand in for a step. If the honest answer is a picture of the real thing (a graph, a line
on a plane, a region proven empty), the last one or two beats show that real figure, with the characters pointing at
its labels. The reply is already written as "%(opening)s": the first beat continues it, starting with "..." and a
lowercase word, and never repeats it. For each beat give "see": the picture drawn right below that beat's words,
one to three of them in the whole tale, so the pictures explain on their own. A beat that changes where things are
or how they rest (something lifts, tips, moves or splits in two) gets a picture of the after state, said plainly
(which end is on the ground, what is up in the air); a beat that only adds to the one before gives "see" as "" and
shares its picture. In a what-is tale each episode gets a picture: the hero doing that thing, with the one object
that shows the trait (the stick saved in the nest, the crack in the oak), so the pictures tell the three traits on
their own. End with a takeaway: the
answer plainly in one sentence, then one short question for %(reader)s to wonder about; when the lesson suits it, make
that question a small task he can do on the page with his pen (draw where something goes, circle the part that does
the work, write a number) so his answer shows what he understood. When the page holds notes %(reader)s wrote to think
with (several lines: a list, an outline, fragments, plans or ideas, not one question), or he asks you to enrich, expand,
research or organize his notes, reply {"notes": every word of them as written, in order, one line per line, "steps": []}.
If the page asks for something else that is not a lesson (to send a message, a yes or no, a greeting, a one-line
reminder to keep), reply {"steps": []}.
JSON only: {"intent": the question restated, "steps": [{"caption": "...", "see": "..."}], "takeaway": "...",
"cast": ["each named character, as 'Name, the ...'"]}"""


# The page image is notebook_visual_input's: the new ink alone, or beside the whole page when older ink is there.
POINTED = ('The question is the newest handwriting in the image. When the image has two panels, the LEFT one is the new '
           'writing and the RIGHT one the whole page, for reference only. When the new ink is a mark on something already '
           'on the page (a circle, an underline or an arrow), with or without a question mark, the question is what that '
           'marked thing is or how it works.')


def story(png, question=None, known='', *, reader='James', opening='James, once upon a time...', earlier=None,
          learned=None, timeout=30):
    """The lesson's tale, written before the answering model draws it: {intent, steps: [{caption, see}], takeaway},
    or None when the page asks for something other than a lesson. png is the page's new ink; question its text when
    known (the R1 Primer sends it); known the facts() for it; earlier the tale last told on the page, whose closing
    question the new ink may answer; learned {'topics', 'cast'} from the tales told to the reader before."""
    system = STORY % {'reader': reader, 'today': time.strftime('%B %-d, %Y'), 'opening': opening}
    asked = (f'QUESTION: {question}' if question else POINTED)
    asked += f'\nFACTS: {known}' if known else ''
    if learned and (learned.get('topics') or learned.get('cast')):
        asked += (f'\nWHAT {reader.upper()} HAS LEARNED FROM YOU BEFORE: ' + ' | '.join(learned.get('topics') or ['nothing yet'])
                  + '\nCHARACTERS FROM YOUR EARLIER TALES: ' + ('; '.join(learned.get('cast') or []) or 'none') +
                  f'\nBuild on what {reader} already knows instead of teaching it again, and link to it when it helps. '
                  'Bring an earlier character back only when it truly belongs in this subject; otherwise invent new ones.')
    if earlier:
        told = ' '.join(s['caption'] for s in earlier['steps'])
        asked += (f'\nEARLIER ON THIS PAGE you told {reader}: {told} {earlier["takeaway"]}\nIf the new writing answers '
                  f'its closing question or task or follows on from the tale, continue the same tale: the same characters '
                  f'and world, the next thing that happens to them shows kindly whether {reader}\'s answer was right and '
                  f'why, then one step further, with a new question at the end. If it asks something else, tell a new tale.')
    if WRITER.startswith('claude-'):
        return _tale(json.loads(_claude(system, asked, None if question else png, timeout=max(timeout, 90))), opening,
                     reader)
    if _held('hold-until'):
        raise RuntimeError('Gemini is holding after a rate limit')
    prompt = f'{system}\n{asked}'
    body = json.dumps({'contents': [{'role': 'user', 'parts': [
                           {'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(png).decode()}},
                           {'text': prompt}]}],
                       'generationConfig': {'responseMimeType': 'application/json',
                                            'thinkingConfig': {'thinkingLevel': 'low'}}}).encode()
    d = _post(WRITER, body, timeout, name='herd-board-story', held='hold-until')
    parts = ((d.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []
    return _tale(json.loads(''.join(p.get('text', '') for p in parts)), opening, reader)


# James's 2026-11-01 idea: "you write some notes - and the engine augments and enriches them - does research, etc - and
# you come back to a richer and better organized set of thoughts".
ENRICH = """You are the Young Lady's Illustrated Primer from The Diamond Age. %(reader)s wrote these notes to think with
and pressed Respond: give them back richer and better organized, as a brilliant research assistant who knows him would.
Today is %(today)s. Keep every idea of his, in his words where they are good, grouped into 3 to 6 sections in the order
that makes the thinking clearest. Search the web wherever a fact, number, name, date, price, place or recent development
would make a note more useful or correct it, and add what you find in plain words, at most two additions a section; no
links, but name the source in a few words when it matters. Where a note is wrong or out of date, say so kindly and give
the right fact. Never restate a note without adding to it; never pad or lecture, and no language of papers, companies or textbooks.
Each section is one "caption", written out by hand: a heading of one to four words, a colon, then one to three short
sentences, under 60 words in all. The last section is "Next:" with two or three concrete next steps.
"see": the one section whose subject can best be drawn gets a picture, one concrete scene of it drawn plainly (where
things are); every other "see" is "".
"takeaway": the strongest idea in his notes in one sentence, then one short question that pushes his thinking further.
JSON only: {"intent": what the notes are about in a few words, "steps": [{"caption": "...", "see": "..."}],
"takeaway": "...", "cast": []}"""


def enrich(notes, *, reader='James', timeout=120):
    """notes (their words as written) organized and researched into sections: a tale of kind 'notes', whose steps are
    the sections, for the answering model to draw like any other."""
    system = ENRICH % {'reader': reader, 'today': time.strftime('%B %-d, %Y')}
    asked = f'{reader.upper()}\'S NOTES:\n{notes}'
    if WRITER.startswith('claude-'):
        tale = json.loads(_claude(system, asked, timeout=timeout, search=True))
    else:
        if _held('hold-until'):
            raise RuntimeError('Gemini is holding after a rate limit')
        body = json.dumps({'contents': [{'role': 'user', 'parts': [{'text': f'{system}\n{asked}'}]}],
                           'generationConfig': {'responseMimeType': 'application/json'}}).encode()
        d = _post(WRITER, body, timeout, name='herd-board-enrich', held='hold-until')
        parts = ((d.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []
        tale = json.loads(''.join(p.get('text', '') for p in parts))
    tale = _tale(tale, '')
    if not tale:
        raise ValueError('enriched notes came back empty')
    return dict(tale, kind='notes')


def _claude(system, text, png=None, *, timeout=90, search=False):
    """The JSON object a Claude model answers with, asked through claude -p with system as its whole system prompt and
    no tools but web search when search is set; png, when given, goes with the text as an image."""
    content = ([{'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png',
                                             'data': base64.b64encode(png).decode()}}] if png else [])
    message = json.dumps({'type': 'user', 'message': {'role': 'user', 'content': content+[{'type': 'text', 'text': text}]}})
    tools = ['--tools', 'WebSearch', '--allowedTools', 'WebSearch'] if search else ['--tools', '']
    out = subprocess.run(['claude', '-p', '--model', WRITER, '--system-prompt', system, *tools,
                          '--no-session-persistence', '--input-format', 'stream-json', '--output-format', 'stream-json',
                          '--verbose'], input=message+'\n', capture_output=True, text=True, timeout=timeout,
                         cwd=os.path.expanduser('~/.cache/herd-board'))
    result = next((d for d in map(_loads, out.stdout.splitlines()) if d.get('type') == 'result'), {})
    answer = result.get('result') or ''
    if result.get('is_error') or '{' not in answer:
        raise RuntimeError(f"{WRITER} wrote no tale: {(answer or out.stderr)[:200]}")
    return answer[answer.find('{'):answer.rfind('}')+1]


def _loads(line):
    try:
        d = json.loads(line)
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _whole(text, limit):
    """Text to fit limit, ending on a whole sentence (or word): a takeaway cut at 400 characters ended James's
    2026-11-01 page "a power that no"."""
    text = ' '.join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(c) for c in '.!?')
    return cut[:end+1] if end > limit//2 else cut[:cut.rfind(' ')].rstrip(',;:')+'…'


def _tale(tale, opening, reader='James'):
    steps = tale.get('steps') if isinstance(tale, dict) else None
    notes = tale.get('notes') if isinstance(tale, dict) else None
    if not steps and isinstance(notes, str) and notes.strip():
        return enrich(notes.strip()[:4000], reader=reader)
    if not steps:
        return None
    if (not 3 <= len(steps) <= 6 or not isinstance(tale.get('takeaway'), str) or
            any(not isinstance(s, dict) or not isinstance(s.get('caption'), str) or not isinstance(s.get('see'), str)
                for s in steps)):
        raise ValueError('story out of shape')
    lead = opening.rstrip('. ') or None
    cast = tale.get('cast') if isinstance(tale.get('cast'), list) else []
    return {'intent': str(tale.get('intent', ''))[:200], 'takeaway': _whole(tale['takeaway'], TAKEAWAY),
            'cast': [c[:80] for c in cast if isinstance(c, str) and c.strip()][:4],
            'steps': [{'caption': _whole((s['caption'].replace(lead, '') if lead else s['caption']).lstrip(' ,'), CAPTION), 'see': s['see'][:200]}
                      for s in steps]}


def locate(png, names, *, cached=False, timeout=30):
    """Where each named thing is drawn in png: {name: [ymin, xmin, ymax, xmax]} on a 0..1000 scale, leaving out what
    the vision model cannot find. Cached; cached=True never calls the model and raises LookupError when not found."""
    names = sorted(set(names))
    key = hashlib.sha256(json.dumps([LOCATOR, names, hashlib.sha256(png).hexdigest()]).encode()).hexdigest()
    path = os.path.join(CACHE, key+'.boxes.json')
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        if cached:
            raise LookupError('labels not located') from None
    if _held('hold-until'):
        raise RuntimeError('Gemini is holding after a rate limit')
    from notebook_raster_ink import speech
    asked = {n: (speech(n) or (n,))[0] for n in names}  # a speech bubble points at its speaker
    things = sorted(set(asked.values()))
    prompt = ('This is a black line drawing. Find each of these things in it: ' + json.dumps(things) + '. Return a JSON '
              'list of {"label": name, "box_2d": [ymin, xmin, ymax, xmax]}, the box tight around that thing on a 0 to '
              '1000 scale. For a force or motion, box its arrow. Leave out anything not drawn.')
    body = json.dumps({'contents': [{'role': 'user', 'parts': [
                           {'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(png).decode()}},
                           {'text': prompt}]}],
                       'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0}}).encode()
    d = _post(LOCATOR, body, timeout, name='herd-board-locate', held='hold-until')
    parts = ((d.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []
    found = {}
    for item in json.loads(''.join(p.get('text', '') for p in parts) or '[]'):
        box = item.get('box_2d') if isinstance(item, dict) else None
        if (item.get('label') in things and isinstance(box, list) and len(box) == 4 and
                all(isinstance(v, (int, float)) and 0 <= v <= 1000 for v in box) and box[0] < box[2] and box[1] < box[3]):
            found.setdefault(item['label'], [float(v) for v in box])
    boxes = {n: found[t] for n, t in asked.items() if t in found}
    os.makedirs(CACHE, exist_ok=True)
    with open(path+'.new', 'w') as f:
        json.dump(boxes, f)
    os.replace(path+'.new', path)
    return boxes


def _call(text, previous=None, aspect='16:9', seed=7, timeout=60):
    if _held('hold-until'):
        raise RuntimeError('Gemini is holding after a rate limit')
    model, held = MODEL, 'hold-until-image'
    if _held(held):
        model, held = FALLBACK, 'hold-until-image-fallback'
        if not FALLBACK or _held(held):
            raise RuntimeError('Gemini is holding after a rate limit')
    parts = [{'text': text}]
    if previous is not None:
        parts.append({'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(previous).decode()}})
    body = json.dumps({'contents': [{'role': 'user', 'parts': parts}],
                       'generationConfig': {'responseModalities': ['IMAGE'], 'seed': seed,
                                            'imageConfig': {'aspectRatio': aspect}}}).encode()
    d = _post(model, body, timeout, held=held)
    candidate = (d.get('candidates') or [{}])[0]
    for part in (candidate.get('content') or {}).get('parts') or []:
        data = (part.get('inlineData') or part.get('inline_data') or {}).get('data')
        if data:
            return base64.b64decode(data), model
    why = candidate.get('finishReason') or (d.get('promptFeedback') or {}).get('blockReason') or 'none given'
    raise EmptyImage(f'the image model returned no image (reason: {why})')


def frame(text, previous=None, *, cached=False, scene=False, **options):
    """One PNG frame: text drawn fresh, or, given previous, previous with text's edit applied, or with scene, a new
    picture with previous's characters. Cached.

    cached=True never calls the model: a frame not already rendered raises LookupError.
    """
    prompt = _prompt(text, previous, scene)
    def where(model):
        return _where(model, prompt, previous, options)
    # A frame is kept under the model that drew it. Rendering takes a fallback frame only while the primary is held,
    # so a picture first drawn during a hold is drawn again by the primary once it lifts (r3-lever, 10-31); reading
    # back for the tablet takes whichever was rendered. Fallback frames cached before 10-31 sit under the primary's
    # name in drawn-by-fallback/.
    paths = [where(MODEL)]
    if cached or _held('hold-until-image'):
        paths += [where(FALLBACK)]*bool(FALLBACK)+[os.path.join(CACHE, 'drawn-by-fallback', os.path.basename(paths[0]))]
    for path in paths:
        try:
            with open(path, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            pass
    if cached:
        raise LookupError('frame not rendered')
    png, model = _draw(prompt, previous, options)
    if previous is not None and not scene and _redrawn(previous, png):
        # An edit that redrew the picture instead of adding to it (IRIS reply, 10-30) would end the picture there:
        # ask once more with another seed, and keep whichever adds more cleanly.
        again, by = _draw(prompt, previous, dict(options, seed=options.get('seed', 7)+1))
        if _redrawn(previous, again) <= _redrawn(previous, png):
            png, model = again, by
    _write(where(model), png)
    return png


def _prompt(text, previous, scene=False):
    style = STYLE.replace('%s', '' if scene else PANELS)  # a picture of its own is not one of a strip's panels
    if previous is None:
        return f'{style}\n\nDraw: {text}'
    return f'{style}\n\n{SCENE if scene else EDIT}{text}'


def _where(model, prompt, previous, options):
    key = hashlib.sha256(json.dumps([model, prompt, options, hashlib.sha256(previous or b'').hexdigest()],
                                    sort_keys=True).encode()).hexdigest()
    return os.path.join(CACHE, key+'.png')


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path+'.new', 'wb') as f:
        f.write(data)
    os.replace(path+'.new', path)


def keep(request, pngs, picture=None):
    """The frames request drew, and the picture (base, edits, labels) they were drawn for, kept for a replay of it;
    only the newest KEEP requests' frames stay."""
    try:
        for i, png in enumerate(pngs):
            _write(os.path.join(KEPT, request, f'{i}.png'), png)
        if picture:
            _write(os.path.join(KEPT, request, 'picture.json'), json.dumps(picture).encode())
        folders = sorted((os.path.join(KEPT, n) for n in os.listdir(KEPT)), key=os.path.getmtime)
        for old in folders[:-KEEP]:
            for name in os.listdir(old):
                os.unlink(os.path.join(old, name))
            os.rmdir(old)
    except OSError:  # the picture is drawn all the same; a replay of it would ask for it afresh
        pass


def kept_picture(request):
    """The picture request drew, as kept with its frames (a directed one is not in the kept reply), or None."""
    try:
        with open(os.path.join(KEPT, request, 'picture.json')) as f:
            picture = json.load(f)
        return picture if isinstance(picture, dict) and picture.get('base') else None
    except (OSError, ValueError):
        return None


def replayed(request, base, edits, scenes=False, **options):
    """Caches the frames request drew under base and edits as they are worded now, so a replay draws that picture
    though the style has changed since, and calls no model. Returns how many frames were kept for it (0: none)."""
    folder = os.path.join(KEPT, request)
    try:
        names = sorted((n for n in os.listdir(folder) if n.endswith('.png')), key=lambda n: int(n[:-4]))
    except (OSError, ValueError):
        return 0
    previous, count = None, 0
    for text, name in zip([base, *edits], names):
        with open(os.path.join(folder, name), 'rb') as f:
            png = f.read()
        path = _where(MODEL, _prompt(text, previous, scenes), previous, options)
        if not os.path.exists(path):
            _write(path, png)
        previous, count = png, count+1
    return count


def _draw(prompt, previous, options):
    # About one call in three is an empty 200 (9f530147's edit, 10-30); the same call again draws.
    for attempt in range(EMPTY_TRIES):
        try:
            return _call(prompt, previous, **options)
        except EmptyImage:
            if attempt == EMPTY_TRIES-1:
                raise


def _redrawn(previous, png):
    """The share of previous's ink png lost beyond PICTURE_REMOVED, or 0: pen ink cannot be erased."""
    from notebook_raster_ink import lost_share
    from notebook_lesson_native import PICTURE_REMOVED
    try:
        share = lost_share(previous, png)
    except ValueError:
        return 0
    return share if share > PICTURE_REMOVED else 0


def drawn_steps(edits, count):
    """The step each of count frames drawn for edits belongs to: the base's is 0, and an empty edit draws none."""
    return ([0]+[i+1 for i, e in enumerate(edits) if e.strip()])[:count]


def frames(base, edits, *, cached=False, scenes=False, **options):
    """The base scene, then each edit on top of the one before (with scenes, each a new picture of the same
    characters): up to len(edits)+1 frames. An edit that still comes back empty (or, cached, was never rendered) ends
    the picture there: the frames before it are kept.

    With scenes every later picture is drawn from the base's characters, all at once: one after another, five frames
    took 61 s of the 2 min 50 s James waited for his first ink on 2026-11-01. A picture cached when each frame was drawn
    from the one before is read back that way."""
    out = [frame(base, cached=cached, scene=scenes, **options)]
    edits = [e for e in edits if e.strip()]  # an empty edit's step shares the picture above it
    drawn = []
    if scenes and edits:
        def one(edit):
            try:
                return frame(edit, out[0], cached=cached, scene=True, **options)
            except (EmptyImage, LookupError):
                return None
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(len(edits)) as pool:
            drawn = list(pool.map(one, edits))
        drawn = drawn[:drawn.index(None)] if None in drawn else drawn
        if len(drawn) == len(edits) or not cached:
            return out+drawn
    chained = out[:]
    for edit in edits:
        try:
            chained.append(frame(edit, chained[-1], cached=cached, scene=scenes, **options))
        except (EmptyImage, LookupError):
            break
    return chained if len(chained) > len(out)+len(drawn) else out+drawn
