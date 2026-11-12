# B3 handwriting accuracy: preparation and private-data protocol

Status: scorer and sampler prepared; no real pages, references, model calls or
accuracy results have been collected. Frontier PLAN.md B3 requires 100 of
James's real tablet pages, transcribed by him, and character and word error
rates per model. Pi Dog reviews this method before live collection.

## Model list and frozen task

The current letter reader's source default is `gemini-3.5-flash-lite` in
`herd-board-serve` (`MODEL`, `READ_SYS`, `read_letter`). It can be overridden by
`HERD_BOARD_MODEL`; verify the effective live value before collecting. Its
number-check second read uses the same model with a different prompt and is a
production policy, not an independent model. The Primer's Pi/GPT-5.6 Luna
medium baseline in `DOODLE_ARCHITECTURE.md` is for lesson roles, not letter OCR.

| Arm | Source/status | Configuration to freeze before calls |
| --- | --- | --- |
| `gemini-3.5-flash-lite` | Current source default; live setting unverified | Direct Gemini image call; first OCR read, JSON `text`; record effective model and generation settings |
| `gpt-5.6-luna` | Planned comparator, no B3 calls yet | Pi/OpenAI-Codex image input, medium effort; verify model availability and a transcription-only adapter |
| `gpt-6-astra` | Optional third arm, no B3 calls yet | Pi/OpenAI-Codex image input, high effort; verify availability and the same adapter |

Use one frozen, verbatim-transcription instruction for all active arms and the
same exact PNG bytes per page. Preserve written case, punctuation, numbers and
math; do not solve or answer the question. Return one text string, with an
explicit unreadable marker for uncertain symbols. Save the exact prompt bytes,
digest, model ID, effort, output cap and adapter version privately with the run.
The existing lesson responder produces teaching JSON and cannot stand in for a
B3 OCR call. The production `read_letter` numeric double-read is a separate
policy check after the per-model comparison. Make at most one successful
response per page/arm in the primary comparison; preserve failures rather than
quietly retrying or replacing them.

## Read-only page selection

1. On the authorized tablet connection, enumerate saved notebook IDs and page
   order from xochitl `.metadata`/`.content` files. Read `.rm` page files using
   `cat` or bounded `dd` only. The existing `herd-board-serve` has examples of
   these reads and local `render_page`; avoid its Respond, reply, notebook-edit,
   and touchscreen paths. Do not navigate the tablet or request an unsaved
   screen frame. Ask the tablet operator to perform this step if this seat
   cannot reach it.
2. In private local storage outside every checkout, render page images and
   inspect them **before** any model output or reference transcription. Mark a
   page eligible only if it contains unambiguous human handwriting to
   transcribe. Exclude blank, agent-only, drawing-only and inseparably mixed
   human/agent pages. When a human region can be isolated, freeze one crop per
   physical page; log its coordinates privately and use the same PNG for every
   model and for James. Do not silently change crops after scoring.
3. Hash each read source file before and after collection; exclude a page if
   its saved bytes changed during the read. Hash the frozen PNG. Give each
   physical page an opaque ID. Keep notebook IDs, page IDs, crop coordinates,
   file paths, PNGs and hashes in the private manifest, never in git or Buzz.
4. Create candidate JSONL rows with `page`, `image_sha256`, `notebook`, and
   `eligible` (Boolean). Reject duplicate eligible PNGs so cloned pages do not
   count twice. Run `handwriting_sample.py --candidates ... --seed ...
   --output ...` with private paths outside the checkout. Freeze the seed
   before model calls. The script ranks eligible pages by SHA-256 of seed plus
   opaque page ID, selects 100 and lists up to 20 reserves in deterministic
   order. It stops if fewer than 100 are eligible. Record exclusion/replacement
   reasons privately; use reserves in rank order only when James marks a page
   untranscribable, and never because a model did poorly. Record notebook mix
   and date range as aggregate metadata in the final method report.

No raw handwriting, reference text, verbatim model output, page-linked score,
device path or private manifest is committed. Keep all private inputs outside
the checkout, access limited to James and the authorized runner. The CLI
rejects private inputs under the checkout and prints only aggregate data or a
generic error. Commit synthetic tests and final aggregate numeric results with
the model/prompt/config digests and sample method. A green local test does not
establish tablet access, page eligibility or model accuracy.

## References and score

Give James ten private batches of about ten frozen page PNGs each. Each entry
has an opaque page number and a text box for exactly the visible human words,
numbers and symbols in reading order. Ask him to preserve spelling, case and
punctuation; use `[unclear]` for uncertain spans, and mark a whole page
`untranscribable` rather than guessing. A page with any `[unclear]` span does
not enter the primary score; use the next ranked reserve and report this
exclusion count. Budget one sitting per batch, with a
pause or handoff between sittings. Do not present model output beside the image
before he transcribes it. A later second pass can resolve disputed references
without showing model output. Dead Rabbit will place this bounded request on
James's desk page when the private batch is ready.

Private reference JSONL: one `{"page":"opaque", "image_sha256":"...",
"text":"..."}` per sampled page. Private output JSONL: one
`{"page":"opaque", "image_sha256":"...", "model":"...",
"text":"..."}` per successful page/model; use `"error":"timeout"` (or
another allowed error code) instead of `text` for failed calls. The scorer
refuses duplicate page/model rows and mismatched PNG hashes. It normalizes
Unicode to NFC, collapses whitespace runs, trims ends, and retains case and
punctuation. Character error rate is total Levenshtein character edits divided
by total reference characters; word error rate uses whitespace-delimited words
with the same corpus-weighted formula. Report `scored`, `errors`, and `missing`
beside each rate, because a rate over successful calls alone hides failures.
`--require-complete` requires 100 reference pages and a scored output from
every selected arm on every page. Report math and uncertain-page exclusions
separately if they materially affect interpretation; the primary score remains
literal.

Example private run, after both files exist outside the checkout:

```sh
python3 handwriting_accuracy.py --references /private/b3/references.jsonl \
  --outputs /private/b3/outputs.jsonl \
  --model gemini-3.5-flash-lite --model gpt-5.6-luna --require-complete
```

The command writes only an aggregate JSON summary to stdout. Inspect it for
private identifiers or text before committing the results. Pi Dog's method
review, authorized read-only tablet access, available model adapters, 100
eligible pages and James's references remain live gates.
