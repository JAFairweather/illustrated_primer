# Whole-picture planning: fresh two-model comparison

Open [the stage-by-stage comparison](index.html). These are generated offline
previews, not tablet screenshots. All 14 fixed questions appear in the report;
missing attempts are explicitly marked. No repair calls or authored-answer
substitutions were used. Inputs are typeset question images, not handwriting.

## Frozen experiment

- Code: `dec6c29` (clean export `OUTBOX/whole-picture-IVh2Sa`).
- Packet SHA-256: `9e5d786d038d8ebd543805eba4636bfe645742b4014e54e87e4bb9ff4248d181`.
- Prompt SHA-256: `ef13e236c807927fc665ef7cd9e47137be5747ae739e356a520b146a1c97fa1a`.
- Same question strings, order and image bytes as the preceding 14-question runs.
- One story call, then one call per panel; minimal reasoning, 2,400 requested
  output tokens, no tools, 30-second deadline per call. A provider deadline
  stops collection; it is not permission to overlap another provider call.
- Source artifacts: `OUTBOX/story-panel-eval-20261028/{packet-picture-v3,luna-picture-v3,astra-picture-v3}`.

| Model | Attempted | Complete compiler/encoder passes | Calls attempted | Unattempted |
| --- | ---: | ---: | ---: | ---: |
| PiDog / gpt-5.6-luna | 14 | 4 | 41 | 0 |
| gpt-6-astra | 5 | 1 | 20 | 9 |

Luna passes: blue sky (22.065 s), fractions (15.632 s), water cycle (19.054 s),
sensor/alarm (18.579 s). Astra passes: definite integral (36.925 s).
These times cover generation and offline validation, **not Respond-to-visible
tablet latency**. Astra stopped at a story-call deadline on the fifth question;
this is not a full 14-question model ranking. No false zero was assigned to
the nine unattempted questions.

## Visual and teaching review

DJ Codex inspected every stage PNG and story of the five compiler-valid lessons.
A compiler pass proves neither mathematical quality nor a polished explanation.

- **Blue sky:** readable, stable objects, but sunlight ends at an unlabeled box
  disconnected from the scattering objects. The picture does not establish
  wavelength-dependent scattering. Needs revision.
- **Fractions:** amount relationship is present; unnecessary numeric axes and
  vertical hatching confuse partition lines. Bottom labels are crowded.
- **Water cycle:** coherent sun/water/cloud cycle. The precipitation caption
  loosely groups frozen precipitation with falling liquid droplets; review the
  phase-change explanation before treating this as finished educational content.
- **Sensor/alarm:** clear convergence and correct either-source ambiguity in
  captions. The alarm is sun-shaped, and source identities are labeled late.
  Promising, not polished.
- **Integral:** four/eight left-endpoint rectangles correctly illustrate
  underestimation and refinement; the takeaway computes 1/3. The x-axis label
  ends up above the picture, and zero-height labels are visually distracting.
  The antiderivative is caption text, not demonstrated equation typesetting.

Luna's other failures: five missing/extra-field failures, one overlong caption,
two placement/search failures, and two explicit capability declines (circuit
symbols; representing a failed inherited dependency). Astra's other attempts:
two placement/search failures, one unsupported label glyph and one deadline.
Do not weaken validators or silently supply omitted content to improve scores.

## Separate renderer improvement

After freezing this comparison, diagonal hatching was implemented as a general
fill policy. It distinguishes shading from horizontal/vertical boundaries and
uses one aligned lattice across adjacent regions. The unchanged Luna fraction
answer now replays with clearer partitions at 10,800 materialized snapshot
points, under the existing limits. Artifact:
`OUTBOX/story-panel-eval-20261028/diagonal-fill-fractions/index.html`.
**The comparison images above retain the original fill policy.** This replay
is not counted as another model success.

## What remains

Prioritize general contract feedback and composition support, not fixes keyed
to these questions. Missing-field feedback should be specific enough for a
bounded repair experiment; preserve first-pass scores separately. Axes need
semantic title attachment, not unrestricted side fallback. Symbolic scenes need
clear annotation/change semantics and appropriate glyph coverage. Continue
checking explanation meaning independently of overlap and resource checks.

The whole-picture pipeline still has `native_delivery_supported=false`. It has
not been integrated into live Respond, tested with handwritten inputs or rolled
out to another notebook. All notebook content and production settings were left
unchanged. The goal remains incomplete.
