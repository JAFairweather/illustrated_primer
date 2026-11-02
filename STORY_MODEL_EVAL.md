# Story/panel first-pass evaluation

## Completed eleven-question role comparison (2026-10-29)

`~/.buzz/OUTBOX/role-next-XmP5BE/full-cross/index.html` is now
complete: eleven questions, 56 first-attempt calls, no repair/retry/fallback.
All inputs and six bindings stayed frozen throughout. The `46bfaa5` prompt
candidate was used; neither the later hidden-frame option nor streaming prompt
was installed into this run. Historical raw outputs remain unchanged.

| Role candidate | Calls | Complete provider replies | Median call wall time |
| --- | ---: | ---: | ---: |
| p0 Luna medium | 11 | 11 | 12.420 s |
| p1 Astra high | 11 | 1 | 30.012 s |
| d0 Luna medium | 12 | 11 | 15.140 s |
| d1 Astra medium | 12 | 9 | 23.092 s |
| c0 Luna medium | 5 | 5 | 10.220 s |
| c1 Astra high | 5 | 4 | 25.727 s |

These medians include failed calls. "Complete" means a provider response,
not a valid lesson. Ten p1 planner calls hit the 30-second per-call bound;
therefore this run does not establish its teaching quality on those questions.
Planner JSON was valid for all eleven p0 calls, but several plans requested
unsupported combinations of pictures; structural validity is not quality.

Of 24 drawer attempts: **5 passed geometry/native preparation**, 7 returned
invalid JSON, 4 timed out, 4 explicitly lacked a planned capability, 2 exceeded
ink budgets and 2 failed label layout. Only two of eleven questions produced
any complete renderable candidate. The Riemann hard case did not pass. Its
planner requested a quantitative graph inside an inherited symbolic picture,
which the drawer correctly refused rather than pretending to draw it.

Successful preparation totals (planner + drawer, NOT first-visible time):

| Question/pair | Model completion time | Quality evidence |
| --- | ---: | --- |
| Odd squares p0-d0 | 21.491 s | c0 flags unclear transition from the concrete 3×3 example to general n; c1 deadline |
| Fractions p0-d0 | 29.634 s | Both critics report no critical issue; axes/label economy still only 3/4 |
| Fractions p0-d1 | 33.983 s | c0 flags distracting coordinate markings |
| Fractions p1-d0 | 20.327 s | Both flag the 2/4 label's misleading attachment to unshaded space |
| Fractions p1-d1 | 21.785 s | Critics disagree about labels/axes; not independently calibrated |

The side-by-side page includes all original stories, accepted picture stages,
equations and separate story/picture scores. The fraction outputs are new
model generations, not the older renderer-only replay. Human inspection of
p0-d0's final fraction picture confirms the correct half-shaded quartered bar,
but the remaining coordinate markings are unnecessary. Critic scores are
uncalibrated and do not certify mathematical teaching quality.

Recommendation: **do not promote a general production pairing from this run**.
Luna medium is the practical baseline for the next planner/critic experiment,
not a quality winner. Astra high is unsuitable under this particular 30-second
batch deadline, not proven generally incapable. Test a smaller incremental
composition contract and improve generic representation/layout, preserving
the corpus and source qualifications. Do not make question-specific repairs.

Reported usage on completed calls: 181,566 input, 43,116 output, 11,904 cache-read,
zero cache-write tokens. Timed-out provider usage is unavailable, so these are
not full-run cost totals. Actual subscription charges are unknown. No dollar
cost, first-visible latency, handwriting-recognition or tablet-success claim
is supported by this offline batch.

## Coordinate-only frames and controlled role collection (2026-10-29)

The reviewed prompts from `46bfaa5` are now installed in six isolated evaluator
bindings under `~/.buzz/OUTBOX/role-next-XmP5BE`. Exact prompt bytes
were checked before the PiDog harness restart; production Respond was not
reconfigured. The earlier "not installed" section below describes its earlier
checkpoint, not current evaluator state. Fresh Pythagoras attempts produced a
valid Luna outline followed by an Astra drawer deadline, and an Astra planner
deadline. Neither is a successful lesson or a first-visible-time measurement.

`notebook_role_suite.py` now runs the frozen eleven-question corpus as a full
planner × drawer comparison: both planners see identical inputs, both drawers
see each accepted plan, and both critics see each accepted rendered output.
It preserves malformed output, unavailable results, timeouts, original response
bytes, usage and timings without repair or fallback. Upstream failures skip
dependent branches, not unrelated candidates. The default stops on transport
failure. The explicit `--continue-after-confirmed-deadline` option continues
only after one empty-request check proves the installed Pi responder is idle;
it never retries the failed call. Actual responder tests verify that check
cannot invoke a provider and reports busy while cancellation is still pending.

The baseline comparison is running from frozen `46bfaa5` source plus the
collector, at `OUTBOX/role-next-XmP5BE/full-cross/index.html`. It deliberately
does NOT include the new frame option below. Do not change its inputs or prompts
mid-run. Three worked-example topics are not held-out generalization evidence.
Its batch completion timings are secondary metrics: **Respond to first visible
answer character/pen motion is unknown in this offline run**. Provider first
text may be JSON syntax. True incremental answer delivery is specified in
`DOODLE_ARCHITECTURE.md`; it is not implemented by typewriter playback.

New renderer candidate: `axes.visible` is an optional strict boolean, default
true. False omits axes and numeric endpoints without changing coordinate
mapping or non-label geometry. Hidden frames cannot own labels or create an
empty step; inherited frames remain immutable. Labels reflow through the same
general solver. No question text or named-scene dispatch is involved.

Inspectable replay: `~/.buzz/OUTBOX/frame-visibility-1sPW4L/index.html`.
It changes only the earlier generated fraction diagram's frame visibility;
there are **zero new model calls**, no device writes, and no claim of improved
model reasoning. Snapshot points fall from 5,040 to 3,640. The bars, partitions,
hatching, comparison lines and brace retain exactly the same geometry. The
extra axes disappear and the second fraction label fits below its bar. The
brace and mathematical-label arrangement still need teaching-quality work.

Clean candidate snapshot at the same directory excludes unrelated worktree
changes. All **870 Python and 54 Node tests pass**, including five new frame tests and ten
collector tests. Device/provider behavior in unit tests is mocked, not tablet
evidence. The drawer prompt changes to
`784dec7cd3ba9082b3f9b56beeb60893bffa54393c3664755fb090e6c8cda60e`;
the serial prompt changes to
`5493c6cbfe36ae0a54ba63439be73626f728bcc350cb94e98c29978c460e2e86`.
Planner/critic prompts are unchanged. The new frame prompt is NOT installed.
Source review and a separate fixed-input comparison precede deployment.

## Capability-aware lessons and final ink equation (2026-10-29, source only)

The first role comparison below exposed a contract mismatch, not just a model
choice problem: the planner requested mathematical typography and mixed symbolic
objects into an inherited quantitative graph. The new candidate addresses these
as general capabilities, without routing questions to particular answers.

- A story may carry one optional final `equation`. The existing bounded pen-math
  parser renders it after all pictures and before the takeaway. It shares the
  whole-story 12,000-point limit and existing per-stage stroke/point/time limits.
  All pictures and the equation validate before any native asset is encoded.
- Planner instructions distinguish quantitative pictures from symbolic
  relationships and explain when to start another picture or return to an exact
  earlier snapshot. The drawer does not construct equation glyphs itself.
- Three authored worked examples use the same contracts: integral, odd squares,
  and the supplied unreviewed Riemann claim. Planner examples omit geometry;
  drawer examples contain the identical stories with validated typed shapes.
  These are prompt examples, not runtime question matching or generated answers.
- Offline HTML and the critic's contact sheet include the actual final equation
  strokes. The critic is not asked to judge only the equation's source string.

Clean snapshot: `~/.buzz/OUTBOX/story-math-orpVTJ` (HEAD `9ab9a07`
plus only the twelve intended source/test files). **855 Python tests and 54 Node
tests pass, none skipped.** The new seven tests cover whole-lesson rejection,
equation ordering/limits, unchanged diagram ink, actual equation preview pixels,
and all three examples through both static and animated native preparation.
Device-related suite output is mocked; no device was used for this evidence.

Authored previews under that snapshot:

| Example | Preview | Snapshot / delivery points |
| --- | --- | ---: |
| Integral | `previews/integral/index.html` | 4,610 / 3,872 |
| Odd squares | `previews/odd-squares/index.html` | 3,593 / 2,112 |
| Riemann claim | `previews/riemann-claim/index.html` | 11,234 / 9,998 |

Visual inspection covered the integral equation, final odd-square grid, and
Riemann machine, claimed band and remaining gap. Known presentation gaps remain:
the Riemann band lacks a numeric boundary label in the picture (its caption names
seven eighths), and comparison frames still carry unnecessary axes. The ten-panel
Riemann example is schematic and explicitly preserves the unreviewed-claim
qualification. It is not a proof, a complete mathematical source explanation,
or proof that a model can generate such a lesson. Arbitrary LaTeX and equations
inside intermediate diagrams remain unsupported; pagination remains separate.

New source prompt SHA-256 values:

| Role | Digest |
| --- | --- |
| Planner | `25ce3237e41f60ee19b0527ee60c6071fcbd33ccc35a936fe732bf70e1c86d3f` |
| Drawer | `f4465d4c809ce3f49616595488357133cd74c85875d0d7859d32a2b99ece482f` |
| Critic | `6fb2ccf0acdd995e062f1ae1f85c3b282be16a9e04fcbb60dd077c684de1a63a` |
| Shared serial control | `4c2a43c5e7b0de31ccf5d4e95cd667eae4db86d301f0e9fcd28b591f6a1c710a` |

These new prompts are **not installed**. The six live evaluator bindings and
historical records still use their frozen prior prompts; production Respond is
unchanged. Before new comparisons, prepare new prompt files/config digests for
all six bindings and verify the fixed host identity. Do not overwrite or relabel
the old trials. Next: independent source review, then fresh controlled model
comparisons and the remaining corpus. No improved model-quality, latency or
tablet-success claim is made from these authored examples or unit tests.

## First live six-role comparison (2026-10-29)

The reviewed host integration is installed, not merely queued for review. See
`integrations/pi-role-host/README.md` for exact configuration, rollback location,
source checks and the one PiDog-harness restart. No tablet/server restart or
production prompt change occurred. All six bindings completed real model calls.

Artifacts: `~/.buzz/OUTBOX/role-live-CtvuMd`.
Prompts and expected hashes are frozen there. Calls use the original frozen
question PNG/context, no tools, no repair/retry and a 30-second per-call deadline.
Offline compilation uses the clean `OUTBOX/general-primitives-A49RjW` snapshot,
not the older unrelated dirty procedural/semantic edits in the worktree.

First case: one half versus two fourths. Both planners produced structurally
valid stories. Both drawers received the **identical Luna plan**; both critics
received the **identical successful Astra drawing** and original story. This
controls the upstream input for each role comparison; it is not two end-to-end
model pipelines or an estimate of general success rate.

| Role | Luna result / wall time | Astra result / wall time |
| --- | --- | --- |
| Planner | Valid 4-step plan / 11.212 s | Valid 3-step plan / 29.674 s |
| Drawer | Malformed JSON rejected / 11.459 s | Whole-lesson ink and preview valid / 12.851 s |
| Critic | Valid separate scorecard / 11.612 s | Valid separate scorecard / 15.742 s |

Luna uses GPT-5.6 Luna medium throughout. Astra uses GPT-6 Astra high for
planner/critic and medium for drawer. Output caps are 4,096 except drawer 8,192.
Each `call.json` records input/output/cache tokens and first text timing. These
are subscription model calls; token counts are not an actual billed-dollar cost.

The successful pairing's planner plus drawer took **24.063 s**, excluding
preview work, capture, reading and tablet delivery. This is **not** a measured
Respond-to-first-visible latency, and it does not meet the under-10-second aim.
No critic runs belong in the live answer latency. No fallback or repaired JSON
was published for the failed candidate.

The final image was visually inspected: equal bars, equal shading, partitions,
brace, fraction labels and equality are present. The axes and duplicate origin
labels are unnecessary for this explanation. Both critics scored story and
picture separately (all dimensions 3 or 4, no critical issues), but these are
uncalibrated model opinions, not acceptance. Astra's planner instead describes
subdividing one unchanged shaded whole, a more economical teaching approach;
that alternative has not yet been drawn in this comparison.

The Riemann hard-case planners were also tested on identical source packets:
Luna returned a valid seven-step story in 14.789 s; Astra high hit the 30-second
deadline. The Luna plan retains the unreviewed-claim qualification, but uses
several unexplained technical terms and puts many additions in one base chain.
Structural validity does not establish high-school comprehension or drawability.
Both drawers received that same plan. Luna returned malformed JSON (25.077 s).
Astra returned a valid `unavailable` capability refusal (8.900 s): the plan asks
for series/product/equation relationships and mixes symbolic objects into an
inherited quantitative picture. No hard-case ink was produced. The ad-hoc probe
stored a generic missing-`panels` diagnostic for this refusal; the raw response
is authoritative, and the reusable `generate()` already handles unavailable.

Open `OUTBOX/role-live-CtvuMd/index.html` for the side-by-side failure/success
display, four cumulative stage images and links to all original role outputs.

This is initial installed-host evidence, not the completed 11-question corpus,
model selection, calibrated critique, full latency target or tablet rollout.

## General drawing vocabulary completion (2026-10-29, offline candidate)

The typed drawer can now use sampled-point `plot`, `brace`, and polygon
`shade`, as well as the existing shapes. Plot accepts either ordered data
points or polynomial coefficients/domain, never a mixed or executable form.
Brace endpoints and side describe the grouping; the engine computes its pen
profile. Shade takes one simple polygon and produces sparse diagonal strokes,
including concave regions, without drawing an extra outline or filling its
empty corners. Geometry, hatch density and pen timing are renderer-owned.
An optional closing vertex is accepted; crossed/touching edges, degenerate
regions and invisible subpixel fills are rejected instead of guessed or enlarged.

`notebook_hatching.py` shares the existing even-odd sampled-area fill algorithm;
polynomial area/baseline-crossing behavior remains covered by regression tests.
New shade labels attach to actual hatch ink, not an empty bounding-box corner.
All shapes still go through whole-story validation and the existing native
64-stroke, 3,000-point and 30-second per-stage caps plus total-story limits.
This is not a new device writer and does not modify the native safety guards.

Ten new tests cover concave and deterministic randomized polygon containment,
winding/closure, small-region cues, invalid input, exact sample order, brace
orientation, area compatibility, immutable inherited ink, real v6 preparation,
resource caps and rejection of a bad final polygon before asset generation.
Clean snapshot `OUTBOX/general-primitives-A49RjW` passes **848 Python and 54
Node tests**. Device messages printed by those tests are mocks.

The four-stage authored fixture is reproducible with:

```sh
python3.11 notebook_panel_eval.py example NEW_DIRECTORY --scene general-primitives
```

Inspected preview: `~/.buzz/OUTBOX/general-primitives-A49RjW/preview/index.html`.
Its four materialized snapshots total 4,661 points. The final picture has clear
concave shading, a separate sampled curve, and a visible brace with plotter
labels. This establishes renderer behavior only: zero model calls, no critic
calibration, no mathematical-teaching quality score, and no tablet proof.

The shared drawing prompt has a new capability version; the current serial
prompt SHA-256 is `b812b65f7e95d91b0da6eb774eefd774b68cea4ba72ac92ffce282f84adf6c33`.
Historical comparison artifacts retain their old prompts/results; do not report
them as evaluations of this vocabulary. Recompute the drawer prompt digest when
preparing the six-role host configuration. Live prompts were not installed.

## Independent role runner (2026-10-29, offline candidate)

`notebook_role_prompts.py` now separates the geometry-free planner, batched
shape generator and visual critic. `notebook_role_eval.py` makes **one planner
call and one drawer call**, rather than one model call per panel. Each role
has its own fixed host configuration and prompt digest. The drawer receives
the validated plan and cannot rewrite it. A whole-lesson native compilation
must pass before any stage preview is emitted. No production route imports it.

```sh
python3.11 notebook_role_eval.py prompt planner
python3.11 notebook_role_eval.py prompt drawer
python3.11 notebook_role_eval.py prompt critic
python3.11 notebook_role_eval.py generate INPUT_CONTEXT.json QUESTION.png \
  ROLE_CONFIGS.json NEW_OUTPUT_DIRECTORY
python3.11 notebook_role_eval.py critique NEW_OUTPUT_DIRECTORY/story.json \
  INPUT_CONTEXT.json NEW_OUTPUT_DIRECTORY/preview CRITIC_CONFIG.json NEW_CRITIC_OUTPUT
```

`ROLE_CONFIGS.json` has exactly `planner` and `drawer`; each value contains
`endpoint` and `expected`, using the candidate fields documented below.
`CRITIC_CONFIG.json` contains one such value. These assert already installed
settings; requests cannot install prompts or select models. Role prompts are
versioned code, following the [OpenAI prompting guidance](https://developers.openai.com/api/docs/guides/prompting).

Each call saves the input, prompt, candidate metadata, raw response, metrics
and failures. Deadlines are **per call**, not the entire lesson; total native
preparation time is reported separately. There is no retry, fallback, repair,
or delivery. Compare independent roles using `invoke()` with identical frozen
inputs before interpreting end-to-end pairings. In particular, drawer rankings
need the same plan, and critic rankings need the same rendered lesson.

Critique is a separate offline call, outside answer preparation latency. It
uses a contact sheet of actual stage PNGs at original resolution, plus captions
and source notes, without producer identity or timing metadata. Oversize sheets
are refused rather than reduced until labels cannot be read. Per-page critic
collection is still needed for larger lessons. Scores require specific panel
evidence, remain separated by story/picture, and may be null for insufficient
evidence. Invalid critique is retained. No automatic quality pass or model
selection is inferred from an uncalibrated critic's opinion.

Thirteen fake-response tests cover role isolation, two-call generation, actual
offline previews, whole-lesson failure, unchanged questions, prompt/model
binding, timeout/no-retry, blinded critic input and strict evidence scoring.
These are integration tests, not real candidate evaluations. The legacy Pi
loader still needs role registration support before these variants can run.
Three full worked examples in the new prompts, multipage delivery and broader
drawing vocabulary remain unfinished goal items; this change does not claim
to complete them or alter live notebook behavior.

Clean staged export `OUTBOX/role-runner-V2FrYY` passed **838 Python tests and
54 Node tests**. All new role outputs in these tests are authored fakes.
MyDude integration review was requested on Buzz; the broker queued request
`aab84676462c80d6ada52f12ff9a87d6`. Queue acceptance is not review approval or
proof of delivery. No PiDog restart, host install or tablet write occurred.

## Fixed role-comparison corpus (2026-10-29)

`evaluations/role-selection-20261029/corpus.json` freezes the ten original
questions verbatim and appends the Riemann 7/8 hard case. It does not remove
difficult circuit, probability or science questions to improve the pass rate.
Research notes are supplied context, so this measures source-assisted teaching,
not autonomous retrieval. The Riemann manuscript's abstract/introduction and
the repository's formalization-scope note were inspected, not its proof audited.
The linked 49-page `papers/6.pdf` is the October 5 **11/12 companion**; the
September 30 **7/8 manuscript** is the 199-page `papers/5.pdf`. The corpus keeps
their identities distinct, and retains James's unreviewed-claim requirement.

```sh
python3.11 notebook_role_corpus.py /absolute/new/input-packet
```

This creates identical typeset question PNGs, per-question planner contexts,
SHA256 bindings and a separately named reviewer corpus. Never send the reviewer
corpus to an answering model. Question checks are evaluation expectations, not
renderer rules or per-question production tuning. The preparer does not choose
a model, install a host, make requests, or manufacture answer previews.

Story and picture each have four 0–4 dimensions. Each reviewed dimension must
reach 3, with no critical contradiction; a missing preview is **unreviewed**,
not a visual pass. Every score requires specific evidence. Native compilation
is a separate gate. Critics must be calibrated against independently reviewed
good and deliberately flawed lessons before their judgments select a model;
those calibration artifacts and real role comparisons are still pending.
Producer identity/cost/latency must be hidden during quality scoring. Swap pair
order to check position bias. This follows the separation of task-specific
evaluation and calibrated model judgment in the
[OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

Six offline preparation tests pass: unchanged questions, reviewer-data
separation, deterministic inputs/hashes, refusal to overwrite, source-reference
preflight and image-fit checks. This is **zero new model-quality evidence** and
does not change the live tablet. Independent role prompts, candidate host
registration and actual runs remain the next integration work.

Prepared input packet: `OUTBOX/role-selection-inputs-20261029/packet.json`;
corpus SHA256 `4f2f090156c30ed010650503d618b84af990f94962fbeba3d6cce922f8dd07c3`.
Clean staged snapshot `OUTBOX/role-corpus-kPo4J0` passed **825 Python tests and
54 Node tests**. Device-related messages in those tests are mocks. The only
real device operation during preparation was a read-only context query, which
reported a fresh active test notebook; no page or production setting changed.

## Role-specific evaluation candidate (2026-10-29, not installed)

The revised goal compares planner, drawer and critic independently. The
existing collectors below retain their original minimal-effort contract for
historical comparisons. They must not be pointed at the new role endpoint.

The local adapter now accepts an explicit `role-eval-v1` registration:

```js
registerNotebookResponder(pi, {
  socketPath: '/absolute/private/planner-luna/notebook-eval.sock',
  systemPrompt: fixedPlannerPrompt,
  fixedModel: {provider: 'openai-codex', id: 'gpt-5.6-luna'},
  responseFormat: 'role-eval-v1',
  evaluation: {role: 'planner', reasoning: 'medium', outputTokens: 4096},
});
```

This is an integration example, not a running listener. Each variant needs a
distinct private directory/socket and its own fixed prompt, role, model and
effort. The allowed roles are `planner`, `drawer`, `critic`. Effort names here
are adapter syntax, not proof that a particular account/model supports them.
Unknown settings fail; do not silently downshift. No channel participant,
identity, grant, new Nvoy consumer or model tool is needed for an evaluator.

The Python caller supplies *expectations*, not configuration overrides:

```python
from hashlib import sha256
from notebook_role_eval_transport import call_role_eval

expected = dict(role='planner', harness='pi', provider='openai-codex',
                model='gpt-5.6-luna', reasoning_requested='medium',
                requested_output_tokens=4096,
                prompt_sha256=sha256(fixed_planner_prompt.encode('utf-8')).hexdigest())
reply = call_role_eval(endpoint, request_id, captured_png, question_context,
                       expected=expected, observe_response=retain_raw_reply)
```

The wire request still contains only request identity, image bytes, context
and deadline. Its response reports the host's role, harness and prompt digest
plus actual returned model identity, requested effort/budget and token usage.
The caller rejects mismatches before returning text. This is self-reported
configuration, not cryptographic attestation; still verify the installed host
and prompt before a real benchmark. Production paths refuse this wire format.

The external Pi loader currently accepts only its old two formats and does
not forward the new `evaluation` options. It has not been changed or restarted.
James has authorized additional harness/model variants, so prefer isolated
evaluation integrations over repeatedly switching live PiDog. Never copy or
symlink an OAuth credential store between concurrent runtimes: the existing
Pi harness documentation warns that competing refreshes can invalidate it.
Use a supported in-process registry integration, or a separately authorized
login for a standalone harness. A read-only configuration probe is not a paid
model call and does not establish a candidate's availability or performance.

Next collection must preserve role-level input hashes and measure story and
picture quality separately. The candidate matrix and cost/billing caveats are
in `DOODLE_ARCHITECTURE.md` under "Model selection amendment". No real role
comparison or recommended pairing is claimed by the transport tests.

Offline evidence: clean staged export `OUTBOX/role-eval-fKXAqy` passed
819 Python tests and 54 Node tests. Six new Python tests cover exact candidate
binding, refusal by production contracts, invalid configuration preflight,
no caller overrides, strict JSON/errors and a real Node/socket/Python round
trip with a fake provider. Three new Node tests cover fixed per-role effort,
unchanged production defaults, invalid settings and lifecycle/model isolation.
No API calls, credentials, live sessions or tablet content were changed.

The default is still first-pass only. For an explicitly labeled correction
experiment, `run` and `collect` now accept `--max-corrections 1`: at most one
additional model call for the entire lesson, limited to JSON syntax, required
fields and the caption word limit. It does not retry refusals, geometry/layout
failures, native resource limits, changed model identity or transport failures.
Results retain the failed output and distinguish `first_pass_valid` from final
`valid` and `corrections_used`. A correction is never counted as a first-pass
success. Use a freshly frozen packet with the corresponding prompt; do not
overwrite an older packet or compare different prompt hashes as the same trial.

This is the offline connection between the story planner, per-panel model
calls and the typed panel compiler. It is **not installed in the live Respond
route**. Its fixtures test plumbing, not model quality or tablet behavior.

## Boundary

The operator configures the existing isolated responder with a fixed
`systemPrompt=story_panel_instructions()` and
`responseFormat='story-panel-v1'`. Both `registerNotebookResponder` and
`createNotebookResponder` accept that opt-in. Their default remains
`semantic-v1`. The notebook request cannot select or change either value.
No provider, credentials, model, reasoning effort or token limits change.

The production Python client still requires semantic-v1 and compiles the
semantic reply before returning. The new `call_story_panel_eval` accepts only
story-panel-v1 on an owner-only `notebook-eval.sock`. It returns bounded raw
text, not a native-delivery object. It shares the existing bounded socket
exchange, cancellation and envelope/metrics validation. There is no fallback.

## Run

Print the fixed system prompt for host configuration:

```sh
python3.11 notebook_story_model_eval.py prompt
```

After independently confirming the isolated host's prompt, response format
and fixed model, run one question:

```sh
python3.11 notebook_story_model_eval.py run question.txt question.png \
  /absolute/owner/state/notebook-eval.sock NEW_OUTPUT_DIRECTORY \
  --expected-model EXACT_CONFIGURED_MODEL_ID
```

The PNG and text are both supplied to the model. Typeset questions test answer
generation, not handwriting recognition. Reuse the existing ten fixed
`notebook_lesson_eval.QUESTIONS` and identical images for each model; don't
change the questions to fit the new renderer. The CLI runs one question, not
an unattended suite, so an unavailable or still-busy host does not trigger
further paid requests. The expected model is a check, not a selection command.

1. One story call, with only the question and image. Preserve its raw output.
2. Validate narrative structure and exact question identity.
3. One call per panel, with its narrative context, base ancestry and the
   **validated typed items from its exact base snapshot**. No unrelated panels,
   session history, pixel layout or previously generated text transcript.
4. Compile each prefix before giving its items to a subsequent call. Stop on
   the first invalid, unsupported or over-budget panel. No repair or retry.
5. Compile the complete lesson and exercise the real v6 encoder before
   producing any previews. Reuse the existing SVG/PNG preview path.

The model may explicitly return `{v:1,mode:"unavailable",reason:"..."}`.
That is retained as a nonvisual result, never counted as a successful lesson.
The renderer currently supports data-space geometry, not all semantic visual
kinds. This evaluation exposes those gaps rather than claiming completeness.

## Evidence and limitations

Each exclusive output directory contains the intended fixed prompt, original
PNG/question, each request, unchanged response text and request-bound wire
envelope, per-call timing/usage, and the final result. A rejected shape remains
in its response file. Successful runs also contain all stage previews.

`call_attempts` counts transport invocations; `completed_model_responses`
counts returned envelopes, including invalid answers. Neither field treats a
busy/deadline error as proof of a completed model response. `wall_ms` covers
the full sequential pipeline. First-text metrics belong to individual calls;
they are **not Respond-to-first-visible-response latency**.

The intended prompt hash does not attest what the external host loaded:
`host_prompt_attested` remains false. Record the separate host inspection
alongside any real model comparison. Preview validity means geometry and ink
encoding passed, not mathematical correctness, teaching quality, or delivery.

The automated integration test uses a real Node responder and owner-only Unix
socket, with a deliberately fake model returning the authored graph fixture.
It tests immutable branch inheritance, no unrelated context, bounded replies,
no retries, fail-before-preview, and separation from the production parser.
It cannot establish live model reliability. The tablet is not contacted.

Next gate: MyDude review and isolated-host configuration, then one unchanged
first pass per fixed question on PiDog and the comparison model. Retain every
failure and total latency. No live rollout is authorized by a passing mock.

### Verification, 2026-10-28

Clean staged export `OUTBOX/se-QCJWFn/tools/herd-board` passes all **613 Python
tests and 51 Node tests**, including nine new pipeline tests and two new
host-format tests. The dirty working copy also passes, but its unrelated
procedural drafts were excluded from this clean export. The socket integration
uses a fake provider; **zero real model calls and zero tablet operations** were
made for this change. Host installation and real model quality remain unproven.

## Fixed suite and side-by-side report

`notebook_story_suite.py` preserves every question and image byte from an
existing image-evaluation packet, including additional held-out questions.
It changes the task protocol and fixed prompt, not the questions. It does not
claim a prompt-only comparison with the old one-call semantic evaluator.

```sh
python3.11 notebook_story_suite.py prepare ORIGINAL_IMAGE_PACKET/packet.json NEW_PACKET
python3.11 notebook_story_suite.py collect NEW_PACKET/packet.json NEW_MODEL_RUN \
  /absolute/owner/state/notebook-eval.sock --expected-model EXACT_CONFIGURED_MODEL_ID \
  --max-questions 1
python3.11 notebook_story_suite.py compare MODEL_A_RUN MODEL_B_RUN NEW_COMPARISON
```

Omit `--max-questions` for the whole fixed packet. Each question gets one
first-pass pipeline; invalid output stops that lesson but permits the next
question. **Any transport error or changed model stops the entire suite.** A
deadline does not prove the provider has stopped; independently establish
termination before any later run. There is no retry/resume mechanism that
overwrites a failed trial. An unexpected collector interruption is recorded.

Both model runs must use byte-identical packets. The comparison copies PNG
previews into a self-contained directory and displays cumulative pictures,
captions, takeaway, total pipeline time and per-call metrics side by side.
Held lessons and unattempted questions remain visibly distinct. Different
time budgets are flagged. Historical comparisons do not require the current
code's prompt; new collection does, preventing silent prompt substitution.

Prepared packet: `OUTBOX/story-panel-eval-20261028/packet/packet.json`, all
fourteen original questions/images/order from
`OUTBOX/general-relations-eval-20261028/packet/packet.json`.
Fixed story/panel prompt SHA256:
`47ec41022a91892535e84680d5477f218f1f1602e863e113246e2c51de9ca49a`.
The owner-only `system-prompt.txt` in that new packet is ready for isolated
host configuration. No model calls are made by preparation or comparison.

Read-only host verification found PID87400 owning `notebook-eval.sock`, still
configured for `gpt-5.6-luna` and old prompt SHA256
`3374ea2c9d7984f676155510027464e12b77e4916cd003c0aa453a69a84d7b14`.
`nvoy-pi-harness/mcp/tools/pi_notebook_host.mjs` does not yet accept/forward an
evaluation response-format option. MyDude was given this exact integration
gap; do not spend model calls against the mismatched configuration. Neither
the host nor production settings were changed by these offline tools.

Suite verification: clean export `OUTBOX/ss-zkHjqE/tools/herd-board` passes
**621 Python tests and 51 Node tests**. Eight new suite tests cover byte-identical
inputs, whole-packet preflight, deadline/model-change stops, first-pass failures,
missing-result display, prompt changes and historical comparisons. Model
fixtures in those tests are explicitly fake. The prepared fourteen-question
packet SHA256 is
`5945614e84d81e28d78c43549e88340a72d8a02a242dcba1f0c566fa9ddf8e23`.

## First real story/panel baseline, 2026-10-28

The evaluator-only host patch from `OUTBOX/hf-WK3Sa7` is now installed.
Eight real-adapter/fake-provider host tests pass; the broader harness test
reports all checks passed. James's existing installation/restart authorization
was used. Owner configuration changed only the evaluation prompt/format;
the comparison temporarily selected Astra on the evaluation socket. Production
configuration was compared against a private pre-change backup and is unchanged.
After comparison the evaluator was restored to Luna; listener PID60414 was
verified owning `notebook-eval.sock`. MyDude review was requested; a queued
request is not an approval. Existing host worktree edits were preserved.

Both models used the exact frozen packet and prompt above, minimal reasoning,
2400 output tokens, no tools, no repair, and a 30-second **per-call** deadline.
The code was the clean `OUTBOX/sp-or5UBs/tools/herd-board` export, not the
working copy while layout fixes were being developed.

| First-pass result | Luna | Astra |
| --- | ---: | ---: |
| Complete accepted lessons | 0/14 | 0/14 |
| Completed model calls | 17 | 32 |
| Median time until rejection | 5.936 s | 27.318 s |
| Range until rejection | 4.333–27.180 s | 8.699–41.106 s |

These are rejection times, **not successful-answer latency or tablet timing**.
The pipeline makes sequential story/panel calls, so total time can exceed a
single call's deadline. All processes finished; there were no transport stops.
The initial integral smoke result was copied byte-for-byte into Luna's full
baseline and its provenance recorded, not called a second time.

Evidence under `OUTBOX/story-panel-eval-20261028/`:

- `luna-firstpass-01/`, `astra-firstpass-01/`: original requests, answers,
  envelopes, metrics and rejection results for all fourteen questions.
- `comparison-firstpass-01/index.html`: side-by-side results. No complete
  previews exist for this baseline; the report does not disguise that fact.
- `renderer-replay-01/index.html`: subsequent deterministic replay of the
  available raw panel outputs through layout changes. Nine of sixteen
  available prefixes render. They are **incomplete prefixes**, not nine new
  successful lessons. Missing later panels were not generated or authored.

Luna's dominant failure was an unnecessary invariant equating narrative
`visual_kind` with immutable drawing identity (8/14). Astra's dominant failure
was label layout (11/14); two answers used unsupported mathematical glyphs,
and one explicitly declined an unsupported circuit schematic.

The candidate removes only the same-kind reuse restriction, measures initial
axis titles before mapping data, and treats label sides as preferences with
bounded nearby collision-checked alternatives. It never moves inherited ink,
silently changes labels, clips geometry, or raises native budgets. The font
also gains actual stroke glyphs for Unicode minus and comparison operators.
The prompt revision is separate from the frozen baseline and is **not yet
installed**. Further fresh evaluation must use a new packet, not overwrite
these baseline artifacts. No tablet testing or rollout occurred here.

Verification of the final candidate in clean staged export
`OUTBOX/panel-layout-TsQGkb/tools/herd-board`: **636 Python tests and 51 Node
tests pass**. Tablet-related messages printed by these suites are mocks, not
device observations. The nine-prefix replay predates the additional Unicode
glyph change; no improved full-lesson success rate is claimed from it.
