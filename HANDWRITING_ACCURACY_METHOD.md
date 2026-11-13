# B3 handwriting accuracy: preparation and private-data protocol

Status: scorer and sampler prepared; no real pages, references, model calls or
accuracy results have been collected. Frontier PLAN.md B3 requires 100 of
James's real tablet pages, transcribed by him, and character and word error
rates per model. Pi Dog reviews this method before live collection.

## Model list and frozen task

The public snapshot's letter reader defaults to `gemini-3.5-flash-lite` in
`herd-board-serve` (`MODEL`, `READ_SYS`, `read_letter`) and reads
`HERD_BOARD_MODEL`. The installed Primer reader, checked at
`/opt/primer/current/herd-board-serve:69` on 2026-11-13, reads
`PRIMER_MODEL` first, then `HERD_BOARD_MODEL`, then that default. Before model
calls, have the authorized operator check both override names in the service
environment, resolve that precedence, reject an empty effective model ID, and
freeze the effective ID with the run configuration privately. Do not infer the
live ID from this public snapshot or print the service's full environment. The
number-check second read uses the same model with a different prompt and is a
production policy, not an independent model. The Primer's Pi/GPT-5.6 Luna
medium baseline in `DOODLE_ARCHITECTURE.md` is for lesson roles, not letter OCR.

| Arm | Source/status | Configuration to freeze before calls |
| --- | --- | --- |
| `gemini-3.5-flash-lite` | Public and installed source default; effective live setting unverified | Direct Gemini image call under the shared transcription prompt; record effective model and generation settings |
| `gpt-5.6-luna` | Planned comparator, no B3 calls yet | Pi/OpenAI-Codex image input, medium effort; verify model availability and a transcription-only adapter |
| `gpt-6-astra` | Optional third arm, no B3 calls yet | Pi/OpenAI-Codex image input, high effort; verify availability and the same adapter |

Use one frozen, verbatim-transcription instruction for all active arms and the
same exact PNG bytes per page. Preserve written case, punctuation, numbers and
math; do not solve or answer the question. Return one text string, with an
explicit unreadable marker for uncertain symbols. Save the exact prompt bytes,
digest, model ID, effort, output cap and adapter version privately with the run.
The existing lesson responder produces teaching JSON and cannot stand in for a
B3 OCR call. The direct Gemini arm measures model-level OCR under the same
frozen prompt and image as the comparator arms. It does not measure production
`read_letter` end-to-end accuracy: that path uses `READ_SYS` and may make a
second number-check read with `NUMBER_READ_SYS`. Evaluate that production path
separately if needed; do not call its result the B3 Gemini arm. Make at most one
successful response per page/arm in the primary comparison; preserve failures
rather than quietly retrying or replacing them.

## Read-only page selection

1. On the authorized tablet connection, enumerate saved notebook IDs and page
   order from xochitl `.metadata`/`.content` files. Read `.rm` page files using
   `cat` or bounded `dd` only. The existing `herd-board-serve` has examples of
   these reads and local `render_page`; avoid its Respond, reply, notebook-edit,
   and touchscreen paths. Do not navigate the tablet or request an unsaved
   screen frame. Ask the tablet operator to perform this step if this seat
   cannot reach it.
2. In private local storage outside every checkout, render page images and
   inspect them **before** any model output or reference transcription. Before
   sampling, have James confirm authorship of each candidate page in a private
   page-linked provenance record; record who confirmed it, when, and the basis
   for the confirmation. Notebook ownership, handwriting appearance, and a
   generic "human handwriting" label are insufficient. Mark a page eligible
   only when James's authorship is confirmed and it contains unambiguous
   handwriting to transcribe. Exclude uncertain authorship, blank, agent-only,
   drawing-only and inseparably mixed human/agent pages. When a James-written
   region can be isolated, freeze one crop per physical page; log its coordinates
   privately and use the same PNG for every model and for James. Do not silently
   change crops after scoring.
3. Hash each read source file before and after collection; exclude a page if
   its saved bytes changed during the read. Hash the frozen PNG. Give each
   physical page an opaque ID. Keep notebook IDs, page IDs, crop coordinates,
   file paths, PNGs, hashes and James-authorship evidence in the private
   manifest, never in git or Buzz.
4. Create candidate JSONL rows with `page`, `image_sha256`, `notebook`, and
   `eligible` (Boolean). Set `eligible` true only after the James-authorship and
   content checks in step 2; the sampler does not verify provenance itself.
   Reject duplicate eligible PNGs so cloned pages do not count twice. Run
   `handwriting_sample.py --candidates ... --seed ...
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

## Run sheet once the reviewed export route is installed

1. **Prepare before James's confirmations.** Pi Dog records the installed
   export action's reviewed commit and checks its read-only tablet access,
   Dennis-only private drop and counts-only stdout. The runner prepares a
   private manifest/worksheet outside git, freezes the sample seed and OCR
   prompt, verifies the Gemini and Luna adapters, and records their model IDs,
   settings and prompt/config digests. Stop if access, image handling or an arm
   is unavailable; do not substitute the production `read_letter` path.
2. **Confirm authorship.** Pi Dog freezes the candidate metadata snapshot with
   stable opaque page IDs and a private mapping to tablet IDs. James sees the
   enumerated list on his private desk page and affirms all listed pages in a
   notebook except named IDs, or marks uncertain pages. Expand his answer into
   a private page-linked yes/no/uncertain record with attester, time and basis.
   Notebook ownership alone is not proof. Use James-only thumbnails only when
   metadata cannot support a confident answer; uncertain pages are ineligible.
3. **Check content, then sample.** Rank confirmed candidate IDs by the frozen
   seed and the sampler's SHA-256 seed-plus-ID rule. Pi Dog exports saved pages
   read-only in that order; Dennis checks stable source hashes, renders/crops
   each page privately, and excludes blank, agent-only, drawing-only, mixed or
   duplicate images. Continue until 100 eligible pages and up to 20 ranked
   reserves are ready. Run `handwriting_sample.py` on the checked manifest and
   freeze its output, PNG hashes and crop coordinates before model calls. The
   reported eligible count covers checked candidates, not an uninspected tablet
   population. Stop if fewer than 100 qualify.
4. **Run frozen model arms.** Feed the exact frozen PNG and prompt to each
   configured arm, once per page/arm; keep outputs and errors bound to opaque
   ID and image hash in private JSONL. Never choose replacements using model
   results. Freeze the effective live Gemini override before calls, while
   reporting the direct Gemini arm as model-level OCR only.
5. **Collect James's references last.** Dead Rabbit sends one private worksheet
   batch of about ten images at a time, with no model text shown. Bind each
   saved transcription to its opaque ID and frozen image hash. For `[unclear]`
   or untranscribable pages, take the next ranked reserve; run its model arms
   before asking James for that reserve's transcription. Do not lower the
   100-usable-page target or choose a reserve by model performance.
6. **Score and report.** Run `handwriting_accuracy.py --require-complete` only
   after 100 usable references and complete Gemini/Luna outputs (plus Astra if
   enabled) exist. If an arm is missing or errored, report the failure counts
   and pause the comparison; incomplete-arm CER/WER are not a B3 result.

Private only: tablet identifiers and paths, candidate list, attestation,
source/page/image hashes, crops, PNGs, sample seed and manifest, exact prompt,
model outputs/errors, James's text, per-page edits and worksheet. Buzz, Hive and
the public repo may receive **aggregate counts and non-page-linked SHA-256
digests** of the frozen manifest, prompt/config and code, never individual page
hashes or a private path. After a complete run, publish only aggregate CER/WER
and scored/error/missing counts per model, with the method and exclusions;
inspect the scorer's JSON for private fields first. A digest proves which
private artifact was used, not that its contents or James's authorship are valid.

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
both the Gemini baseline and GPT-5.6 Luna comparator on every page; GPT-6 Astra
may be added as a third arm and is then required on every page too. Without
`--require-complete`, each model's CER and WER cover only its answered pages;
the same model object prints `scored`, `errors`, and `missing` beside its rates.
Do not compare incomplete-arm rates as a B3 result, because failures can hide
hard pages. Report math and uncertain-page exclusions
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
James-authored eligible pages and James's references remain live gates.
