# Label/layout probes — 2026-10-28

## Decision

Do **not** promote a larger label cap or the tested content-sized-box fallback.
Neither produced an additional accepted lesson. The production server, tablet,
model configuration and prompt were not changed. No model calls were made.

The fixed-input probes used the clean `161265f` + `9a00dd9` source snapshot at
`~/.buzz/OUTBOX/rt-mIdFtA6v/tools/herd-board`, excluding unrelated
worktree drafts. The preceding capacity experiment and compiler-only route
replay remain separate; these probes are not new model first-pass results.

## Experiments executed

Three candidates replayed the same six saved answer sets: capacity ordinary and
research, Luna/Astra prompt-contract, and Luna/Astra baseline. Each candidate
preserved all **221 previously accepted SVG stages byte for byte** and yielded
**zero additional accepted lessons**.

1. Raise only the procedural/anchored label validators from 24 to 32 characters,
   matching explicit-position labels. Keep actual glyph size, wrapping,
   collision checks, finite placement search and native budgets unchanged.
2. Keep the original label cap. After existing spatial compositions fail, size
   schematic boxes around their complete labels and place those labels inside.
   Physical motifs remain unchanged. Reserve label footprints, reroute against
   the new outlines, and try only the existing finite arrangements.
3. Combine those two candidates.

The hat response's 25-character label passed the candidate text cap, but the
complete graph still failed placement (`no clear label location for groups`).
Content-sized boxes did not make that graph fit. These negative results do not
prove every content-aware layout strategy will fail; they reject these bounded
implementations on the saved corpus. No wording was shortened, dropped or
replaced, and no failed answer was rerolled.

## Why the Langlands response is held

A separate read-only direct-primitive diagnostic counted its expanded glyph
paths and the same two-pixel densification formula used by `_dense`. It did not
accept the response, bypass a cap or produce native ink. The result isolates the
binding constraint rather than relying on the generic error message:

| Step | Continuous-font strokes | Points | Estimated pen seconds | Label strokes |
| --- | ---: | ---: | ---: | ---: |
| Shared curve and two categories | 90 | 2,412 | 28.008 | 88 |
| Equivalence | 16 | 421 | 4.909 | 12 |
| Whittaker route | 21 | 674 | 7.536 | 16 |
| Localization route | 42 | 924 | 11.256 | 39 |

The first step contains only two rectangles; lettering consumes 88 of its 90
strokes. It exceeds the **64-stroke** cap even though its point and estimated
time totals fit. The existing original-font alternative is worse here: 143
strokes, 2,232 points, 30.098 seconds in the first step. Increasing playback
speed, enlarging boxes or using that font alternative does not resolve the
stroke-count violation.

For comparison, the accepted Kakeya steps use 25/28/3 strokes and
797/1,199/623 points with the continuous font. All these timings are compiler
estimates, not physical tablet measurements or Respond latency.

## Architectural implication / next work

The compiler must account for text and geometry together. A primitive-count
limit alone cannot tell a planner that five short label commands expand to 88
strokes. This supports a measured composition contract between the semantic
lesson plan and renderer, with per-step lettering/geometry costs available
before native playback. It does **not** authorize silently rewriting model
claims, splitting user-requested steps, shrinking fonts or increasing caps.

The next design/test should address that complete composition contract, not add
another topic-specific renderer or another unbounded layout fallback. A good
lesson must still demonstrate the idea, not merely render a valid flowchart.
The hat logic outline's weak illustration and Langlands' mathematical accuracy
remain separate quality questions from compiler acceptance.

## Reproduction artifacts

All local scripts, unchanged-answer hashes, manifests and previews are in:

`~/.buzz/OUTBOX/label-capacity-FVVVWQ6l/`

- `probe.py`, `results.json`: label-cap-only replay.
- `content_boxes.py`, `content-boxes-24/results.json`,
  `content-boxes-32/results.json`: finite content-sized-box candidates.
- `stage_costs.py`, `stage-costs.json`: direct-primitive resource diagnostic.
- `research-comparison.html`: original versus label-cap candidate, including
  held results rather than hiding them.

Run scripts with `PYTHONPATH` pointing to the clean snapshot above. Replays
deliberately refuse an existing output directory; use a fresh copy of the
experiment directory when reproducing them. No tablet access is needed.

Status: offline evidence only. No new device behavior, reliability claim,
source-retrieval capability or full-proof verification is established here.
