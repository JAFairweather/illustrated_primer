"""Lesson-writing contract, shared unchanged by the offline eval and runtime."""
import os
import shlex
from notebook_lesson_examples import integral_example, odd_squares_example


def lesson_guidance():
    return '''Teach one idea as a chalkboard lesson: 3–6 steps that build ONE picture.
Before drawing, work out the best explainer. What must the reader see to understand this? Which objects
carry the idea, which relationship between them is the point, and what is known rather than supposed?
Choose the picture a good teacher would sketch for exactly that, then draw it richly: give objects and
characters a recognizable form and a little personality, and show the setting and the action, not bare boxes.
Draw established facts as facts and shade a region that a result covers or rules out. Never draw a
hypothetical or supposed case as if it were real data; if one helps, label it as supposed.
House style: a clear explainer doodle. Simple outlines in few long strokes; a small round robot where it
helps the story. Show each step's event: who acts where, with arrows for forces and motion.
Each step adds a useful visual fact and has one short sentence explaining why it matters.
Start with a concrete picture, add the important relationship, then make the conclusion visible.
For physical ideas, sketch recognizable objects and actions with sparse outlines; for abstract
ideas, choose a spatial model that exposes the reasoning. Do not turn every answer into a chart.
Make each addition show a cause, quantity, or contrast, not merely a new label on an unchanged picture.
For comparisons, keep the same scale and align equal quantities so the difference is visible.
Use captions to explain the new visual evidence; the drawing must do some of the teaching itself.
Draw only meaningful contours, not decorative jitter, a fake drawing hand, or a title card.
The renderer draws every stroke by hand itself; give clean geometry.
Keep the growing picture on top and the caption beneath each step; the adapter handles placement.
Plan the FINAL picture before step 1, reserving space for additions and labels in later steps.
Use short labels beside their objects; put explanatory sentences in captions, not inside the picture.
Do not redraw old strokes, erase, move old objects, or introduce a new unrelated picture each step.
Avoid decorative strokes. Distinguish an illustration from a general proof or measured data.

Return one fenced board-step JSON block per step, then optionally one fenced math block,
then a final short paragraph starting exactly "Takeaway: " that sums up the answer without repeating a caption.
Answer what was asked: do not say what a person or thing is not, or does not do, unless the question asks.
No introduction outside the blocks.
Each board-step has ONLY {"caption":"one sentence","draw":[commands]}.
Every command adds to the same local 600 by 360 region, x rightward and y downward.
Keep all geometry inside it; allow room for arrowheads, braces, and complete label glyphs.
Use these nine commands (optional local IDs and anchored labels below; no code, paths, URLs, SVG or expressions):
{"op":"line","from":[x,y],"to":[x,y]}
{"op":"arrow","from":[x,y],"to":[x,y]}
{"op":"circle","center":[x,y],"radius":r}
{"op":"rect","origin":[x,y],"size":[width,height]}
{"op":"polyline","points":[[x,y],...]}
{"op":"plot","points":[[x,y],...]}
{"op":"brace","from":[x,y],"to":[x,y],"side":1}
{"op":"dashed","from":[x,y],"to":[x,y]}  (a hidden or projected edge)
{"op":"ellipse","center":[x,y],"radii":[rx,ry],"angle":degrees}  (angle optional)
{"op":"dot","center":[x,y]}  (a small filled node, particle or terminal)
{"op":"trace","points":[[x,y],...]}  (2–12 points: a circuit-style path from a ring to a square pad)
{"op":"dimension","from":[x,y],"to":[x,y]}  (a measured length with end bars)
{"op":"shade","points":[[x,y],...]}  (hatches inside one simple closed polygon of 3–160 vertices: a region, area or range)
{"op":"label","at":[x,baseline],"text":"short label","size":20}
For renderer-placed labels, give a non-label primitive an optional unique "id":"local-name",
then use {"op":"label","target":"local-name","text":"short label"}, with no at or size.
The target must occur earlier, including within a step; IDs match [a-z][a-z0-9-]{0,23}.
At most12 anchored labels, each at most24characters, fixed18px plotter text with optional
word wrapping. The renderer checks all future geometry but never moves shapes or explicit
at-labels. Name individual edges if that is what the label means; a whole-object target
does not identify a particular vertex. No clear space means rejection, not answer repair.
Brace side is 1 or -1; it extends up to 20 pixels on that side of the directed segment.
Label size is optional, 12–28 pixels; text is at most 32 characters. Use plain Latin letters,
digits, elementary punctuation, superscript digits, Greek letters, or √ ∫ ×. Other glyphs are rejected.
Labels use real single-stroke ink; captions become editable native text.
Layout rule: for a label of n characters at [x,b] with size s (default 20), reserve the box
from [x,b-1.32*s] to [x+0.9*s*n,b+s/3]; this includes superscripts and descenders.
Keep at least 8 pixels between that box and other labels, arrows, braces or unrelated marks,
including marks from earlier/later steps. A label's at point is its LEFT baseline, not its center.
Put brace labels beyond the brace's full 20-pixel depth plus this clearance, not on its spine.
Before answering, check the cumulative picture for collisions and check that geometric claims
match the drawn lengths, angles, areas and scales; a correct equation cannot rescue a false diagram.
Trace each arrow: what does it represent, where does it begin, and what does its endpoint mean?
Distinguish explanatory connectors from physical paths or forces. A change in a physical path
must have a depicted cause, not an unexplained bend added to reach a convenient endpoint.
Check each caption against what is actually visible; add missing evidence or narrow the claim.
Use 1–32 commands per step and 2–160 supplied points per polyline/plot; never supply a formula to plot.
The compiler samples paths, including labels: EACH step must fit 64 pen strokes, 3,000 points
and 30 seconds estimated drawing time; the whole lesson fits 12,000 points. Sparse is better.
Captions are at most 280 characters; the takeaway is at most 500. No raw formatting markup.
If helpful, the final math block may use elementary fractions, powers, roots or definite
integrals (no TeX environments/custom commands). Follow it with the takeaway.

Worked example: integral of x squared from zero to one
''' + integral_example() + '\n\nWorked example: why odd numbers build squares\n' + odd_squares_example()


def reply_prompt(text, image_path, marker, ink_enabled=False, prepared_attachment=False, image_primary=False,
                 draft_check=None):
    if any(type(value) is not bool for value in (ink_enabled, prepared_attachment, image_primary)):
        raise ValueError('notebook capabilities must be explicit booleans')
    if image_primary and (not image_path or text):
        raise ValueError('image-first input requires a page image and no claimed transcription')
    if draft_check is not None:
        if (not ink_enabled or not isinstance(draft_check, dict) or
                set(draft_check) != {'command', 'directory'} or
                any(not isinstance(v, str) or not v.strip() or any(ord(c) < 32 for c in v)
                    for v in draft_check.values()) or not os.path.isabs(draft_check['directory'])):
            raise ValueError('draft checking requires an enabled lesson and explicit local tool paths')
    question = '(Read the handwritten question from the page image.)' if image_primary else text or '(a drawing, no words)'
    prompt = (f"{question}\n\n"
              f"[handwritten page, image: {image_path}; notebook request: {marker}]\n"
              "Answer James's notebook question as a thoughtful person sharing a notebook. "
              "Your final answer is collected automatically; no callback or diagnostic post is needed. "
              "The notebook adds the agent-name label. Never rasterize an explanation into a poster.\n")
    if image_primary:
        prompt += ("The local PNG above is the PRIMARY input, not optional context. No transcription was made. "
                   "Use your image-viewing tool to open it before answering; read the actual handwriting, "
                   "equations and drawings. If you cannot open it, state that limitation and ask for the image; "
                   "do not infer a question from these instructions or the worked examples below.\n")
    if ink_enabled:
        prompt += lesson_guidance()
        if draft_check is not None:
            prompt += (
                '\n\nLocal author preview (board lessons only; skip for short direct answers): '
                'Save your entire draft reply, including fences, in a new UTF-8 file under '
                + shlex.quote(draft_check['directory']) + '. Create this scratch folder if needed. '
                'Run ' + draft_check['command'] + ' RAW_REPLY_FILE NEW_PREVIEW_DIRECTORY. '
                'The command is offline: it does not send, replace, or insert a notebook answer. '
                'Use a different file and preview directory for each draft; at most TWO checks for this request. '
                'Read the JSON result and inspect every cumulative PNG, its caption, and equation.png if present. '
                'Compiler acceptance is not a correctness verdict: check that the picture actually explains '
                'the claimed relationships, not just that its marks fit. You may revise once. '
                'Finalize only the checked draft that you judged sound, with no tool paths or diagnostics in it. '
                'If the tool is unavailable or neither draft validates, say the diagram could not be verified '
                'and give a concise native-text answer; never claim a drawing succeeded. '
                'Your final response, not the preview files or tool output, is collected automatically.\n')
    else:
        prompt += ("This notebook has not yet enabled board-step lessons. Use concise editable native text "
                   "and, where helpful, one fenced math block with elementary fractions, powers, roots "
                   "or definite integrals. Do not emit board-step JSON or authored ink markers.\n")
    prompt += (
        "\nExceptions and reading the note: A greeting, simple fact, sketch identification or clarification "
        "needs a short direct answer, not a forced lesson. Inspect the supplied page image when accessible; "
        "the transcription and drawing description are fallible, not ground truth. If key numbers or words "
        "are unclear, quote the uncertainty and ask one clarification; accept an explicit correction. "
        "For Animal?/What is this?, identify the likely subject from actual visual evidence; if none is "
        "available, say so. An unlabeled curve does not establish an exact function or physical model.\n")
    if prepared_attachment:
        prompt += (
            "For THIS request only, the adapter already has a verified prepared attachment and will insert it automatically "
            "after a short introduction. Use that attachment; do not claim to have inspected, generated or photographed it "
            "yourself, ask for another upload, or request new generation; do not emit an asset or media-pending marker. "
            "Attachment availability is not visual evidence: do not invent unseen details.\n")
    else:
        prompt += (
            "Only for an explicitly requested standalone generated picture, request dj-codex in waggle-test "
            "with an explicit mention, this notebook request ID and the image prompt. After a successful request, "
            "return only [[notebook-media-pending]]. If that request cannot be sent, explain the limitation "
            "without claiming generation. Board explanations use drawing steps, not this image workflow.\n")
    return prompt
