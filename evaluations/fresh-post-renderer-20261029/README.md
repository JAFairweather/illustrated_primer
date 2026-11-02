# Fresh post-renderer evaluation — 2026-10-29

Three newly generated Astra answers, not hand-authored scenes or replay-recovered
old failures. All three passed first-attempt geometry and native preparation;
zero corrections. This is a selected three-case check, **not** a full fourteen-case
success rate or a tablet test. Rendering acceptance does not certify mathematics
or lesson quality.

`answers.json` preserves the generated story and panel objects plus measured
timing and source/compiler hashes. It contains no host configuration or credentials.
Original request/wire artifacts remain in
`~/.buzz/OUTBOX/story-ownership-eval-20261029/fresh-post-renderer-astra/`.

| Question | Generation wall time | Provider call time, summed | Calls | Corrections |
| --- | ---: | ---: | ---: | ---: |
| One half versus two fourths | 34.360 s | 33.940 s | 5 | 0 |
| Integral of x squared, zero to one | 34.244 s | 33.467 s | 5 | 0 |
| Why a many-to-one mapping has no inverse on its original domain | 39.375 s | 38.375 s | 5 | 0 |

These used the offline evaluator's per-call deadline. **All exceed the live
generator's single 30-second whole-request deadline.** First model text arrived
in 2.8–3.0 seconds, but it was internal JSON, not visible notebook content. The
under-ten-second Respond-to-visible target remains unmet and unmeasured here.

Visual inspection: the fraction subdivision and shading agree; numeric axes add
noise. The integral's region and calculation agree, but caret exponents and slash
fractions are not polished equation typography. The inverse diagram's reversed
arrows explain the ambiguity, and its takeaway qualifies the domain restriction.

## Reproduce without a provider or tablet

From the repository root, with the existing herd-board Python dependencies:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/herd-board/evaluations/fresh-post-renderer-20261029/replay.py /tmp/fresh-answer-replay
```

Choose a new output directory. Open `index.html` there for side-by-side final
pictures, stage previews and planned native playback. The script runs the real
whole-story compiler, v6 encoder and native bundle builder; it makes no model
calls and never writes to the tablet. `replay.json` records current-compiler
counts, distinct from the original generation measurements. A future compiler
failure is an error, never a silently skipped example.

## Latency experiment to run next

Compare the present story-plus-N-panel protocol with one complete typed lesson
response. Keep the same questions, model, geometry vocabulary, caption ordering,
native caps and whole-lesson validation. Do not parallelize dependent panel calls:
each currently consumes the earlier resolved item IDs. A complete response can
declare all IDs and additive bases once; the compiler can resolve them locally.

Measure full valid native preparation, output tokens, first-pass failures, lesson
quality and total deadline failures—not first tokens. Do not assume one larger
response is faster or as reliable; run the comparison. Preserve the serial route
as a control until evidence supports replacement. Use the isolated endpoint with
its owner-configured prompt/format; no caller-provided system-prompt override.
No live deployment, streaming of unvalidated prefixes, increased safety limits
or per-question templates are part of this experiment.
