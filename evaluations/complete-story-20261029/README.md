# Fresh single-call lesson evaluation — 2026-10-29

Fourteen fixed questions, **one attempt each**, actual responder identity
`gpt-6-luna`, minimal reasoning, 2,400 output-token limit. Every answer requested
the complete story and all its drawings in one response. No repairs, retries,
tablet insertion, production restart or notebook edits.

**6/14** passed whole-answer validation and native preparation. Successful
preparation took **5.968–15.024 seconds**, median **9.5825 seconds**. Three were
under ten seconds **before any tablet delivery**. This is not Respond-to-visible
latency, teaching-quality acceptance, or evidence for general rollout.

| Question | Result | Preparation (s) / reason |
|---|---|---|
| Fractions | Schema/native pass; quality weak | 13.148; only two stages, extraneous axes |
| Integral | Schema/native pass | 5.968; correct final area diagram |
| Inverse mapping | Rejected | Caption exceeds 12 words |
| Gravity | Rejected | Unsupported label glyph |
| Odd squares | Schema/native pass; visual FAIL | 15.024; inner-square label lands inside later border |
| Compound interest | Schema/native pass; quality weak | 7.359; correct samples/endpoints, ambiguous line labels |
| Transistor | Declined to draw | Claims vocabulary cannot honestly depict circuit |
| Blue sky | Declined to draw | Claims vocabulary cannot depict scattering |
| Bayes | Rejected | Over 64 strokes before label placement |
| Water cycle | Schema/native pass | 10.620; final symbolic cycle inspected |
| Pythagoras | Rejected | Caption exceeds 12 words |
| Sensor/alarm | Schema/native pass | 8.545; final shared-output diagram inspected; only two stages |
| Proof dependency | Rejected | Incomplete/mismatched panel-map contract |
| Dependency failure | Rejected | Wrong top-level mode |

All six final drawings were visually inspected. Whole stage-by-stage playback
and tablet persistence remain unverified. The odd-square failure is a general
label-ownership defect: collision-free lettering can acquire a wrong apparent
owner when a later region grows around it. The renderer must reason about
regions and future additions, not merely line intersections. Do not special-case
this mathematical question or count algebraic correctness as a good picture.

## Evidence and reproduction

`answers.json` preserves every exact returned response string and its SHA-256,
the actual model metrics, rejection/clarification, native result and review.
Do not edit failed answers to make replay green. The originating artifacts are
under `~/.buzz/OUTBOX/complete-story-luna-20261029/`; `reviewed-index.html` presents
all fourteen results beside historical serial-model previews, with stage and
offline-playback links for valid answers. Exact response wire and input PNGs
remain in those case directories.

The fixed question packet hash is
`8fa20650898f1fdd06b3fde340b14426d561ac20e0c535e4075db075dd5c1090`.
The complete-prompt hash is
`2e94ec7974801d83f880e3108022e384725af0062417bb42f7bfd74b7b978bd4`.
The owner configuration was read before each invocation; configured prompt
bytes matched. Runtime prompt attestation is not implemented, so the results
do not claim it. Clean compiler export: `OUTBOX/vc-FmFDTH`; commit `3fb2600`.

From `tools/herd-board`:

```sh
python3 evaluations/complete-story-20261029/replay.py NEW_OUTPUT_DIRECTORY
```

Replay makes zero model calls. It verifies response hashes and revalidates
unchanged answers against the current compiler, recording failures rather than
silently omitting them. New generation still uses `notebook_complete_story_eval`
on an independently owner-configured isolated evaluation endpoint.

Clean export `OUTBOX/oc-3SKNvv` replayed all fourteen exact responses into
`OUTBOX/complete-story-clean-replay-20261029`, reproducing the same six valid and
eight nonpassing outcomes. This is reproducibility evidence, not fourteen new
model calls or fourteen successful lessons.

## Comparison caveats and next decisions

The historical serial results identify **`gpt-5.6-luna`**, not this run's
`gpt-6-luna`. Compiler versions and timing scope also differ. The side-by-side
page is a quality/history reference, **not a controlled latency experiment**.
A same-model/current-compiler serial control is still needed before attributing
differences to the one-call design. Six valid answers are fewer than the earlier
ten; the new path must not replace production on the strength of its fast cases.

Next generic work: distinguish stylistic caption guidance from genuine resource
safety; support mathematical lettering without replacement boxes; preserve
label ownership across later regions; and simplify complete-answer structure
without replacing general drawing with question-specific templates. Keep the
existing point, stroke, pen-time and page-change protections. Fixed first-pass
failures remain the baseline for measuring improvements.
