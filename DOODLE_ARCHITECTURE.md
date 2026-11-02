# reMarkable doodle lesson architecture

Design proposal for James Fairweather, by DJ Codex. Updated 2026-10-28.

## General handwritten interface — revised brief, 2026-10-29

This section supersedes the doodle-only scope of the older proposal below.
Authority: James's revised goal and `~/.buzz/RESEARCH/DJ_CODEX_BRIEF.md`.
The product is a handwritten interface to agents; illustrated teaching is
the first complete use case, not the definition of the rendering engine.

### Layer contracts

| Layer | Responsibility | Must not do |
| --- | --- | --- |
| Page input | Capture latest writing plus bounded visible context and existing page/revision identity | Confuse old answers with new instructions or replace original ink |
| Intent | Distinguish an answer, explanation, private-data query, or proposed external message; clarify ambiguous recipients | Send a message or treat ink content as tool authority |
| Composition | Build a document of prose, equations, drawings and optional handwriting imagery; keep sources and claim status | Choose device pixels or execute code embedded in content |
| Rendering | Resolve layout, labels, paths, style and pacing deterministically; validate the complete result | Select recipients, retrieve private data or call an agent |
| Delivery | Append to the unchanged page, or deliver an explicitly confirmed draft through a channel adapter | Treat Respond, an agent response, or a prior confirmation as authorization for a new external send |

The shared composition document is independent of subject and destination.
An explanation and a message can both contain handwriting and an illustration.
The renderer does not need to know whether those strokes will be inserted into
a notebook or exported as an image. Channel-specific sizing/encoding belongs
to the delivery adapter, after the content is fixed. Paths, URLs and executable
code are not drawing-language operations. Source references are separate
metadata, not fetch instructions passed to the renderer.

For an informational query, a separate read-only retrieval component supplies
only the relevant authorized facts. It does not share a tool-bearing messaging
session with the answer model. Private-data access, image export and external
delivery are distinct capabilities; supporting one does not authorize another.
These retrieval and external-delivery adapters are design targets, not features
proven by the current notebook implementation.

### Teaching uses a planner, then a drawer

#### First visible answer and true streaming — James, 2026-10-29

The primary latency measure is **Respond to the first visible answer character
or first meaningful pen motion**. A spinner, agent label, "working" banner,
provider token, completed JSON response, or start of a replay timer is not this
event. Completion time remains useful but is secondary. Measure the initiating
button event and first actual answer rendering on the same device clock;
also retain the server-received time to expose capture/transport delay. Device
telemetry is a rendering acknowledgment, not optical proof of e-ink refresh;
validate it against a filmed run before claiming precise visible latency.

Current evidence: `notebook_pi_responder.mjs` consumes provider `text_delta`
events but only returns text after `stream.result()`. `notebook_model_transport`
reads one terminal JSON envelope. `generate_notebook_story` buffers the plan
and every drawing before returning. Native typewriter/draw-out playback is
therefore **not end-to-end generation streaming**. The offline comparison's
`model_wall_ms` measures completed planner plus drawer calls; `first_text_ms`
can describe the first byte of JSON syntax. Neither proves first-visible time.

Next implementation contract (not deployed):

1. Compose an independent, short answer opening before detailed geometry.
   It must answer or begin explaining the actual question, not merely announce
   work. Use a separately bounded typed record, distinct from lesson JSON,
   reasoning, tool calls and status. Do not leak arbitrary provider deltas or
   partially parsed JSON onto the page. Send complete validated text chunks
   incrementally, and let the existing typewriter consume them immediately.
2. Continue planning/drawing while that opening is being read. Keep the full
   drawing preflight: no diagram strokes before the complete picture has passed
   layout and resource checks. Reuse the existing page/job guard on every append;
   a page change stops new chunks, without replaying already appended text.
3. If the drawing fails after text has appeared, retain that text and identify
   the illustration as incomplete. Do not count it as a successful visual answer
   or silently replace it with a prepared scene. Do not emit the opening again
   when the terminal lesson arrives. External sends still require confirmation.
4. Instrument first provider text, first validated answer chunk, first device
   answer rendering, first diagram motion and final completion independently.
   Test with a deliberately stalled drawer: real answer text must appear before
   drawer completion. Also test cancellation mid-text, a late invalid diagram,
   duplicate delivery and reconnect. A fast whole-response replay is not a pass.

This adds incremental delivery of independently valid prose, not incremental
acceptance of unvalidated geometry. The complete-diagram safety constraint
below remains in force. The current batch evaluator remains a quality/model
comparison; it must leave first-visible-answer latency unknown until measured
through the actual device path. No sub-ten-second claim follows from it.

Source implementation checkpoint: an opt-in `story-stream-v1` host now forwards
complete newline-delimited assistant records during generation, rather than
waiting for `stream.result()`. It does not forward reasoning. The Python
`AnswerRecords` consumer permits at most three independently bounded, ordered
plain-text opening sentences (160 characters each, 400 total). Only those
validated sentences reach `on_answer`; the terminal story/panel is never sent
to that callback. The original terminal text must match the emitted records.
Unknown fields, duplicate sequence numbers/JSON keys, changed request identity,
markup, escaped invalid Unicode and premature termination fail closed.

`generate_notebook_story(..., on_answer=...)` uses that separately configured
format, checks its existing page-current predicate before and after delivery,
and still compiles the complete lesson before returning a visual answer. Early
text is not included again in the terminal lesson. Callback failure aborts the
provider; there is no automatic retry/replay. Existing non-streaming formats and
default prompts are unchanged. The streaming prompt is explicitly selected by
`story_panel_instructions(stream=True)`, never by handwriting or request input.

Offline proof uses the actual Node adapter/socket and Python producer with a
fake provider that cannot finish until the early-answer callback releases it.
The late-invalid-diagram and page-change-after-first-chunk cases are hard tests:
the first returns no visual success despite preserved prose; the second stops
before any drawer call. This proves IPC/producer streaming, **not native tablet
insertion or real-model latency**. `first_validated_answer_ms` is explicitly a
server callback measurement; `respond_to_first_visible_answer_ms` remains null.

Clean-snapshot regression evidence: `~/.buzz/OUTBOX/story-stream-ZapmAQ`
contains HEAD `8c48282` plus only the streaming source/tests, excluding unrelated
worktree edits. Python discovery passed 880 tests (`python-tests.log`); explicit
Node `test_*.mjs test_*.cjs` discovery passed 57 (`node-tests-final.log`). These
are offline regression results, not a deployment or a latency measurement.

Still required before enabling it: connect the callback to a guarded,
append-only native text queue in the existing pending job; preserve its exact
acknowledged insertion range while the diagram validates; continue that same
reply without duplicating the heading/opening; test page changes and failed
diagrams through the actual server/client; add device render acknowledgments
and compare with video. The host loader/route has not been configured for this
format, and no tablet/server/production PiDog settings changed. The serial
story/panel producer is a transport test path, not a new model-pairing decision.

Server bridge checkpoint, 2026-10-29 (source only): the existing pending job
now holds up to three validated opening records. Authenticated tablet reads
use `/notebook-answer-stream` with exact request/page identity and a consumed
sequence cursor. Reads are repeatable; they do not acknowledge insertion or
mark the reply written. Unknown, expired, superseded and restarted jobs cannot
recreate a stream. A stopped/changed page exposes no further records. The
existing full page/surface/view/content/ink guard is unchanged.

`respond` refuses `story-stream-v1` before capture or generation unless a client
explicitly advertises integer `answer_stream_version: 1`. The current QMD does
not advertise it. This is intentional: its own native append changes the
content revision, so merely polling the new route would cancel the producer.
The native consumer must reconcile only its acknowledged append, not adopt an
arbitrary newer revision. It also must reuse the existing durable insertion
attempt protection, retain partial text after a failed diagram, and continue
the final lesson without duplicating the opening or agent label. No new lease
or audit layer is introduced by this read bridge.

Clean snapshot `OUTBOX/answer-bridge-3tbwVl` contains HEAD `d9ed110` plus only
the four bridge files. All **887 Python and 57 Node tests pass**, none skipped.
Seven new bridge tests include a real authenticated HTTP handler serving early
prose while a gated fake provider is still running, late invalid output,
page/input changes with no revival, callback validation, duplicate reads versus
duplicate producer records, and supersession/restart refusal. Test discovery
imports the existing fixture module, not its TestCase class, so those counts
do not include duplicate discovery of the 22 model-server tests.
There was no production deployment, model call, tablet input or first-visible
latency measurement for this checkpoint.

Native writer handoff checkpoint (source only): the existing typewriter can
now return a settled append to an internal `onTextSettled` callback instead of
declaring the whole reply done. The callback includes the observed UTF-16
start/end range, character count, virtual gap, surface/ink/content revision,
completion time, and the first acknowledged non-whitespace answer character
time. The agent-label prefix is excluded. This timestamp is a native-editor
observation, **not optical first-visible proof**. No user text is read back or
included in the acknowledgement.

The optional handoff requires an exact end-of-document cursor before writing;
existing batch behavior is unchanged. A page/job/controller/surface/ink change,
intervening revision, selection, pen approach, suspension, busy editor or
changed length/cursor prevents the queued completion callback. A callback is
attempted at most once, including when it throws; already written text remains.
Tests execute the actual QMD functions with asynchronous native text and cursor
updates, virtual gaps, label-only output, Unicode, and changes between the last
append and its completion callback. The full 57-test Node suite passes.
No production caller uses this hook yet. It does not itself rebase the server's
page guard, create a stream consumer, or establish durable delivery; those
remain integration work before enabling `answer_stream_version` on the tablet.

#### Model selection amendment — James, 2026-10-29

PiDog is a host candidate, not the architecture. Each role has independently
configured harness, model, effort, prompt and output allowance. James names
Pi/GPT-5.6 Luna/medium as the baseline. A read-only check of PiDog's
`pi/settings.json` confirms its default model string is `gpt-5.6-luna`; that
file did not establish notebook effort. The existing notebook responder
explicitly requests `minimal`, independently of chat settings. Historical
minimal-effort results must not be relabelled as medium-effort evidence.

Proposed first comparison (not a selection verdict or availability claim):

| Role | Baseline candidate | Comparator | What the comparison measures |
| --- | --- | --- | --- |
| Planner | Pi / GPT-5.6 Luna / medium | Pi / GPT-6 Astra / high | Accurate teaching spine, prerequisites, qualifications, visual argument |
| Drawer | Pi / GPT-5.6 Luna / medium | Pi / GPT-6 Astra / medium | Faithful translation of the same frozen outline, reference validity, readable geometry |
| Critic | Pi / GPT-5.6 Luna / medium | Pi / GPT-6 Astra / high | Detection of seeded factual/visual faults and agreement with independent human judgments |

These are role-level comparisons, not one monolithic agent comparison. The
drawer receives identical validated planner output in each arm. The critic
receives identical rendered stages, captions and source facts, without the
producer's model name or the expected judgment. It reports story and picture
scores separately, with concrete panel-level evidence. A critic's approval
does not substitute for deterministic limits or a mathematical proof. Test
critics against a small independently labelled set containing both good and
deliberately flawed lessons before using their judgments to choose a pairing.

Select promising planner/drawer pairings using held-out questions after the
role comparisons. Record each role's actual model/effort, prompt digest,
input/output/cache token counts, model time, total preparation time and later
tablet first-visible time. Include failures and timeouts, not only successful
calls. Do not rerun earlier roles just to repair geometry; hold a failed lesson
and retain its first result. A future bounded repair policy must be a separate
reported experiment, not an invisible source of cost or latency.

Official model pages confirm medium effort for Luna and high effort for Astra:
[GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra).
Account/harness availability still needs verification. Model-specific effort
support matters; do not silently translate an unsupported setting. This
follows the [reasoning guidance](https://developers.openai.com/api/docs/guides/reasoning).

Cost reporting must distinguish measured token use from actual billing.
The published standard short-context API rates on 2026-10-29 are $0.20/$0.02/
$1.20 per million input/cached-input/output tokens for GPT-5.6 Luna and
$10/$1/$50 for GPT-6 Astra (model pages above). These are reference rates,
not measured Pi OAuth charges. Before producing a dollar estimate, verify
the harness's usage-counter semantics, applicable tier, cache-write treatment
and whether reasoning tokens are included. Report unknown billing as unknown,
never zero. Sum the actual planner, drawer and critic costs for each lesson,
and show cost per successful accepted lesson alongside cost per attempt.

Local implementation: `role-eval-v1` carries the host-reported role, Pi harness
name and exact UTF-8 prompt digest. `notebook_role_eval_transport.py` checks
these alongside the independently expected model, effort and output allowance.
The model/effort/prompt are host configuration, never fields the page can set.
This is configuration evidence, not cryptographic attestation. The first
adapter is Pi/OpenAI-Codex only; other harnesses need their own implementation
of the role interface, rather than being falsely labelled Pi-compatible.

Production `semantic-v1` and `story-panel-v1` stay minimal/2,400 tokens; they
reject role-evaluation output. The new lifecycle registration requires an
explicit fixed model and an evaluation-only socket. Role evaluation can request
up to 8,192 output tokens; the existing response-size, deadline, isolation and
native drawing budgets are unchanged. Unsupported effort errors stop the call;
there is no silent fallback. The current external Pi harness loader does not
yet forward this configuration. No installation, restart, new grant or message
to MyDude was made for this change. Actual candidate runs remain outstanding.
James subsequently authorized creating additional harness/model variants;
prepare isolated variants rather than repeatedly reconfiguring the live PiDog.
This does not authorize new credentials, grants or channel subscriptions.

The planner first states the question, why it matters, the needed background,
what is established, what remains open, and what is new. It then chooses
3–8 short caption/drawing beats per page. Its descriptions express meaning
and relationships, not pen samples or screen geometry. Longer stories keep
their substance and continue on another page; the brief's ten-panel Riemann
story must not be squeezed into eight by silently dropping its caveats.

The drawer translates the fixed outline into bounded local primitives:
line, arrow, circle, rectangle, polyline, sampled plot, brace, label and shade.
General layout and stroke generation remain procedural. Shading must count
its expanded strokes and points against the same limits as any other drawing.
Every stage retains the existing 64-stroke/3,000-point/30-second limits and
the whole lesson retains its existing point budget. Validate the complete
lesson before any insertion; never display a partially validated story.

Planner/drawer separation does not require one network request per panel.
The retained same-model comparison shows a serious latency cost for serial
panel calls (successful preparation medians about 19.8 s versus 9.6 s for
the combined one-call baseline). That is evidence to test a separate planner
followed by a batched drawer, not evidence to eliminate planning. Neither
baseline establishes the quality or latency of that proposed two-call design.
No model is asked to emit animation frames. The renderer calculates pacing
from path length and renders the fixed caption before its matching action.

Score the story and picture separately: factual status, explanatory sequence
and takeaway versus ownership, legibility, geometry and reveal order. Record
compiler acceptance independently from both. The Riemann lesson must identify
the 7/8 result as an unreviewed claim and must not imply a proof of RH. Verify
its sources before using it as a factual lesson. Keep worked examples as
examples, never as question-name dispatch branches.

### External delivery is a confirmed draft, not a model tool call

Proposed flow: compose locally → show exact recipient, channel and content
(including the actual handwriting/image export) on the page → James confirms
that exact draft → channel adapter attempts delivery → show the actual result.
Changing the recipient, content or attachment invalidates confirmation. If the
page changes, hold the draft using existing page guards. A response from an
agent cannot confirm its own send. A timeout is an uncertain result, not proof
of failure: do not automatically retry an external message and risk duplicates.
Use a connector's existing delivery receipt/idempotency facility where one
exists, without introducing a separate lease or audit subsystem.

Current evidence: `notebook_pi_responder.mjs` uses an isolated model context
with no tools and rejects tool calls. Previously, `respond()` silently fell
back to `send()` into a full agent session when that isolated route was absent.
That session could act on a handwritten outbound request without confirmation.
The local candidate now refuses such requests before image capture, OCR, job
creation or dispatch, and removes that fallback from Respond. Model-free
renderer fixtures and configured isolated model calls remain supported.
An armed media test, another agent name, or a non-live request does not bypass
the refusal. This intentionally disables legacy Respond destinations until
there is a safe supported route; it is not a completed confirmation interface.

Offline verification: clean staged snapshot `OUTBOX/route-final-WH4nq8`
passes 813 Python tests and all 51 Node tests reported by `node --test`.
Dispatch regressions cover missing/mismatched/non-live routes, untouched
previous timings and armed attachments, successful isolated image delivery,
and model-free fixtures. All device/provider interactions in these checks
are mocked; these counts are not tablet acceptance results.

Status: this is a local candidate, not deployed tablet behavior. Existing
dashboard dispatch and legacy pending-job recovery are separate surfaces and
have not been certified by this change. No claim is made that all outbound
paths are now guarded. Before rollout, review those surfaces, implement and
test the on-page confirmation interaction, then verify it on an isolated
notebook without changing James's existing ink. Production remains unchanged.

## General-purpose correction — James, 2026-10-28

This section supersedes any implication below that adding a named component
for each failed question is the product strategy. The target is an engine that
composes explanations of previously unseen questions, eventually including
new mathematical arguments. The ten fixed questions are measurements, not a
list of features to hard-code. Prepared examples are test data, never a
question-to-scene lookup table. Particle/drop drafts remain undeployed; their
existence is not evidence of general explanatory ability.

### Abstraction boundary

The model chooses meaning and pedagogy: what must be explained, the relevant
objects, relationships, assumptions, captions, equations, and reveal order.
The renderer chooses presentation: placement, attachment points, routing,
label clearance, glyph paths, stroke velocity, and stage timing. The existing
native adapter remains responsible for guarded insertion and persistence.

A **visual plan** should have stable local entity IDs, typed relationships,
dependencies, captions, and separately classified claims. It should not have
question names, references to complete authored scenes, file paths, URLs,
executable code, animation frames, or model-generated pen samples. Optional
mathematical constructions are macros that lower into the same plan, not the
only ways the system can answer. A missing macro must not imply a missing
ability to draw an explanation.

The reusable core is composition rather than an icon catalogue:

| General operation | Model owns | Renderer owns |
| --- | --- | --- |
| Introduce an entity or region | Meaning, identity, essential shape/size relationships | Shape paths, visual style, measured bounds |
| Relate entities | Endpoints and relation meaning/direction | Boundary attachments, clear routing, arrowheads |
| Label or annotate | Exact text and its target | Measured glyphs, placement, wrapping |
| Compare or group | Membership, correspondence, common scale requirement | Shared layout and aligned presentation |
| Show mathematical structure | Expressions, assumptions, logical dependencies | Typesetting, diagram layout, reveal order |
| Reveal the explanation | Which addition supports each caption | Stable final-scene layout and paced playback |

Some of these are design targets, not current features. Today the generic
drawing family has bounded geometric primitives, explicit local coordinates
and object-anchored labels in the worktree. Named quantitative components
compute limited facts; causal components own their own routing. General
object placement, compositional groups, mathematical expression trees, and
relation-driven layout are not all implemented. The deployed prompt and
compiler must be checked independently; worktree support is not live support.

### Smallest general vertical slice

Extend the existing drawing path with an ID-based schematic connection between
two already introduced closed shapes, plus the existing target-based label.
Start with circles and rectangles because their boundary attachment geometry
is explicit. Resolve endpoints and route against the final scene before
running the unchanged stroke/native compiler. Preserve given geometry and
explicit labels; do not silently repair an invalid mathematical construction.
This is a bounded first slice, not a claim of universal geometry support.
Subsequent composition work should remove coordinate/layout burdens using
groups, alignment and relative constraints, based on measured held-out needs.

Use the same operation in a mathematical mapping/dependency diagram and an
unrelated process/relationship diagram. Parameter, ID, label and reveal-order
variants must work without topic branches. Test endpoint association, all-stage
clearance, deterministic geometry, no input mutation, complete-plan rejection,
and unchanged budgets. Then test fresh model selection on unseen questions.
Fixture success alone cannot prove that the agent can generate good lessons.
The offline implementation is `notebook_relations.resolve_connections`:
`{"op":"connect","from":"a","to":"b","id":"edge"}` lowers to a shaft
and one chevron arrowhead path. The optional edge ID can receive an anchored label.
It routes against later geometry and fixed-label boxes, then the existing label
resolver places deferred labels against the complete routed picture. Up to
twelve connections are allowed; all expanded commands, points, strokes and
pen time still count against the existing limits. Circle/rectangle positions
remain model-specified in this first slice. Routing is schematic, not a metric
path or physical trajectory. Unsupported references and blocked routes fail
before native asset allocation. This code is not deployed merely by being here.

Offline evidence for commit `dd1b683`: ten focused relation tests, including
many-to-one connections, and 518 Python tests plus all 18 native Node test
files pass from an isolated staged snapshot without the particle/drop drafts.
Prepared mathematical-mapping and sensor-alarm previews use the same compiler
and were visually checked (`OUTBOX/general-relations-preview-20261028/`).
These are compiler fixtures, not fresh model answers. The frozen next model
packet retains the original ten questions and adds four held-out questions
about inverse mappings, sensor ambiguity, proof dependencies, and service
dependencies (`OUTBOX/general-relations-eval-20261028/packet/`). It uses the
clean candidate prompt, SHA256
`ece52a49101c48a666dbba9e99293fba0e4370119d442e239726f7a7b1c1dbd0`.
No model results or new tablet results are claimed for this slice. PiDog has
been asked about an isolated run using existing model access, not a live
prompt change or new credentials/grants.

My Dude independently recommended this boundary and slice in
`RESEARCH/REMARKABLE_GENERAL_ILLUSTRATION_BOUNDARY_2026_10_28.md`.

### Mathematical fidelity and response depth

A correct-looking picture is not a proof. Keep explicit separation among
an illustrative example, an intuitive mechanism, a proof sketch, a sourced
account of a proof, and a formally checked claim. Generic drawing still
records `mathematics_verified:false`; a component's checked arithmetic does
not certify its prose or the theorem. The model must not substitute a numerical
instance for a general argument. Geometric constraints asserted in a proof
must either be constructed/checked by supported operations or identified as
schematic, not merely drawn to look true.

For a recent proof, establish the exact result and source first; extract the
central idea, assumptions, dependencies, and the limits of the explanation.
Then build a concise lesson from that structure. Retrieval and deep reasoning
are a distinct measured latency class, not a reason to call a waiting banner
a substantive answer or promise every research answer in ten seconds. Keep the
fast image-to-lesson route for questions that need no research. Do not change
PiDog's model, credentials, grants, or host profile merely because this design
describes multiple response depths.

### Reuse and research

Penrose is relevant because it separates mathematical statements, visual
specification, and constrained layout rather than selecting complete diagrams
from a finite catalogue ([original project paper](https://penrose.cs.cmu.edu/siggraph20)).
Its optimizer seeks local minima, and its authors document difficulties from
competing layout goals; staged geometry/label layout is a useful precedent,
not a guarantee of a fast globally valid solution
([constraints](https://penrose.cs.cmu.edu/docs/ref/constraints),
[staged layout](https://penrose.cs.cmu.edu/blog/staged-layout)).
Penrose can export SVG, but that alone supplies neither ordered native strokes
nor safe notebook insertion ([export formats](https://penrose.cs.cmu.edu/docs/ref/using)).
Our inference: borrow its abstraction boundary; evaluate any solver offline
behind the current compiler before considering a dependency. Nothing is being
installed, and no optimizer has been benchmarked for this device workflow.

### Generalization gate

Retain the original ten questions and report their failures unchanged. Add
held-out questions selected before model execution, including mathematical
and non-mathematical relations, and variations in labels, scale, direction,
and staging. Compare the unchanged first responses of two models side by side.
Require both structural validity and a human assessment that the picture
actually explains the claim. Record exact prompt/compiler versions, tokens,
first substantive visible response, and completion separately. A change must
improve an abstraction or invariant across cases; passing one repaired example
does not justify deployment or broader rollout.

Offline compiler and model evidence remain separate from tablet evidence.
Use the tablet only after the offline boundary works, then finish the original
ten-exchange preservation/latency acceptance and staged rollout. This design
does not waive those requirements or the legacy-writer retirement requirement.

## Candidate evaluation isolation — two prompts live, second model pending

MyDude installed two fixed-prompt listeners in the actual host and committed
that integration as `ce916890`. The isolated fourteen-question run proves the
candidate listener with PiDog's current Luna model; it does not prove an
alternate model. `registerNotebookResponder` now also accepts an optional
owner-fixed model selection. This still needs reviewed host configuration
wiring before a second-model run, not a per-request prompt/model override,
new authentication path, or modification of the live prompt/model.

`test_notebook_pi_isolation.mjs` exercises two real Unix listeners with a
fake model registry. Separate fixed prompts, fresh contexts, unchanged model,
no tools, rejected request-level prompt/model overrides, independent candidate
shutdown, preserved live socket identity, and occupied candidate-path failure
all pass. This test does not establish that the actual Pi extension supports
the integration until its owner verifies the event registration/wiring and
activates it. No external inference or host configuration change occurred.
Expanded coverage also checks concurrent calls with independent busy and
cancellation state, owner model-selection events replacing both listeners
while preserving their prompts, and shutdown of both endpoints. All 31
responder/socket/lifecycle/isolation Node tests pass. The fake registry proves
adapter behavior only, not production provider behavior or rate-limit isolation.
Additional real-socket tests check a fixed alternate model independent of chat
model changes, snapshotting of owner configuration, rejection of request-level
model overrides, and unavailable/mismatched/text-only/unauthenticated registry
selections leaving the live listener usable without any fallback model call.

Host integration shape, using explicitly configured trusted values:

```javascript
const live = registerNotebookResponder(pi, {
  socketPath: liveSocketPath, systemPrompt: liveSystemPrompt,
});
const evaluation = registerNotebookResponder(pi, {
  socketPath: evaluationSocketPath, systemPrompt: frozenCandidatePrompt,
  // Optional trusted owner choice, resolved via existing ModelRegistry.find.
  // Omit this field to follow the session model, as the live listener does.
  fixedModel: {provider: 'openai-codex', id: ownerSelectedEvaluationModelId},
});
// Keep both handles. End evaluation with await evaluation.close();
// never repoint, unlink, close or rewrite the live endpoint to run a candidate.
```

The current lifecycle registers on session start. Do not assume importing a
file into an already-running session activates it; the host owner must verify
startup/reload behavior. Both endpoints use the existing trusted registry;
the optional fixed selection must resolve to an image-capable OAuth model
there. No model ID is accepted from a notebook request, no session model is
mutated, and a missing model makes only that listener unavailable. The
adapter does not establish model availability or install host configuration;
those are verified separately before collecting the second model. It also
does not isolate account rate limits, CPU or provider capacity. Run the bounded
offline batch away from live latency testing, with no retries after
infrastructure failure. Existing eval transport and immutable first-response
capture remain unchanged. Host permission or credential changes, if needed,
remain James's decision; no such change is implied by this recipe.

The official evaluation guidance supports scoped, representative tests plus
human judgment, rather than treating schema passes as answer quality
([OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)).
That informs the frozen questions and visual review; it is not evidence that
this particular host deployment or model has passed.

The candidate packet's separate `review-criteria.json` was frozen before
inference. It checks semantic accuracy, visual evidence, stage alignment,
readability, and honest claims, not only accepted geometry. In particular,
alternative sources sharing an outcome must not be confused with jointly
required premises. These criteria are not sent to the model and do not prescribe
which symbols, coordinates, or components it must choose.

## Decision and intended experience

Build a small explanation system, not an autonomous drawing agent. Pi-Dog reads the question, chooses a visual explanation, and returns a compact semantic lesson. Deterministic code composes that lesson into attractive pen strokes, native captions, and equations. The existing native notebook adapter reveals the validated result without closing the notebook.

**Model granularity clarification, James, 2026-10-28:** Keep drawing instructions
high level. For example, a fraction comparison supplies two fractions and a reveal
sequence, not rectangle edges, partition coordinates, hatch marks or pen samples.
The renderer owns geometry expansion, placement, stroke order and arc-length
timing. Slow drawing must add no model-generated frames or per-point tokens.
Reusable objects and mathematical constructions are the preferred contract;
the existing bounded geometric vocabulary is an escape hatch for sparse novel
illustrations, not a reason to make every answer a list of tiny drawing commands.
Do not claim this preference already eliminates the current prompt's detailed
coordinate-based fallback: simplifying that contract remains separate work.

The desired experience is a thoughtful person explaining beside James's handwriting: recognizable objects appear, a relationship becomes visible, a short caption explains its significance, and the picture ends with a clear takeaway. It is not a slide deck, a screenshot of prose, or a flowchart attached to every answer. Simple questions still deserve simple answers.

This proposal replaces the production author-preview-and-revise loop as the default development direction. It retains the working native insertion, validation, fonts, and preview machinery. No new runtime, agent configuration, permissions, or tablet deployment is applied by this document.

### Slow-stroke bridge prototype — 2026-10-28

**Procedural right-triangle construction, 2026-10-28:** `2b0bd8a` adds
`right_triangle(legs)` so an agent supplies two lengths and reveal order rather
than computing square corners. One uniform scale, three outward true squares,
no shared-edge redraw, area labels, exact fraction/radical result, and a checked
`hypotenuse_squared` claim. Numeric legs 0.1..10000, ratio at most 5:1; captions
and question interpretation remain unverified. This illustrates Pythagoras,
not a proof of the theorem. No native budget or safety guard was changed.

MC Claude reviewed the construction; 498 Python tests pass. Eight focused
scale/ratio cases check right angles, equal square edges, outward orientation,
correct scaled areas and native budgets; an additional 340 integer-pair sweep
compiled. Developer previews (3–4, 5–12, 1–1, 5–1) are in
OUTBOX/right-triangle-preview-20261028, not model acceptance. The 3–4 and 5–1
final frames were visually inspected. Raised area labels use measured glyph
bounds and 12..18px type, not a guessed baseline.

Scoped launchd-runtime installation adds only this component/import/contract;
it does not promote anchored labels, odd-square compaction or unrelated motif
work. Initial runtime contract test exposed the still-old prompt module; after
the matching scoped prompt update all five focused runtime tests pass. Backend
restarted; tablet surface, viewport and ink/content counters stayed unchanged.
No question was submitted or reply inserted. PiDog's host cannot override its
system prompt per request; a controlled isolated-host reload to the prepared
candidate prompt was requested, keeping model/minimal reasoning/socket fixed.
First-pass inference and tablet proof remain pending, not implied by these tests.
Official prompting guidance informed the explicit bounded contract; model and
endpoint were not changed (see the OpenAI links under visual-choice evidence).

**Interrupted reply → new human question, 2026-10-28 17:33 UTC:**
`db638ea` adds explicit page-bound next-question replacement for an exactly
identified failed PiDog request. Dismissing the warning sends nothing; the next
button reads “New question — keep previous reply”. The server retains the old
attempt/content, creates a fresh ID under pending→ink locks, rejects stale
callbacks, and restores attempted replies as failed on backend restart rather
than offering replay. MC Claude reviewed; 489 Python tests and 16 native JS
suites pass. Scoped runtime deployment loaded at 17:31:58 UTC, PID22399.

Live proof: after reopening with the triangle and James's new handwritten
integral intact, the real button dismissed the old warning and then dispatched
`notebook-d4384db1285d4658aa87594dd35b7b3b`. PiDog's adapter rejected its output
as `invalid_json` at 4.143 s server-relative / capture end 4.498 s from tap.
Nothing new was inserted; this is a model-format failure, not a successful
visual lesson. Original rejected text was discarded by the adapter, so fenced
JSON versus malformed syntax is unknown. No retry, repaired substitute, or
forced success acknowledgement. Evidence: OUTBOX/live-human-integral-20261028
input/dismissal/frame PNGs and timing.json; new-question-live-20261028 backups.
The read-only after-check proves all 46 saved page files byte-identical to the
pre-deployment backup (`new-question-live-20261028-verified.json`).
The inactive-cursor candidate was installed/loaded at 17:17:13 UTC and remains
loaded in this newer patch, but this request stopped before exercising it.
Normal reopen has now visually confirmed persistence of the triangle, takeaway
and James's subsequently added integral; full earlier current-page visual
preservation remains separate from that observation.

`998f8c5` removes duplicate JSON parsing from the isolated JS adapter, leaving
its stop/model/tool/single-text/24KB checks intact. The authoritative Python
parser still rejects malformed JSON, duplicate keys, invalid schema and unsafe
geometry before publication. Its existing explicit offline observer can now
retain rejected text. Syntax errors remain `invalid_json`; schema errors remain
`invalid_response`. No fence stripping, correction, fallback or retry. Actual
Node-socket→Python regression covers these failure cases; 24 Node host tests
and 26 targeted Python tests pass. Production has no response-retention hook;
one owner-only offline diagnostic is prepared separately. This is diagnostic
coverage, not a fix for model answer quality.

**Offline visual-choice experiment, 2026-10-28:** After PiDog's confirmed host
reload (host PID51605; fixed simple-drawing prompt and Luna/minimal unchanged),
one identical captured-integral call returned valid text only in 2.528 s.
Original `invalid_json` was not reproduced. An initial local diagnostic had
failed at filesystem sandbox access before contacting the model; its record is
kept separately and is not counted as an inference.

Adding an explicit request to honor the question's visual style in the task
context produced a valid three-stage lesson in 4.548 s, 1,238 points, with about
13.8 s estimated pen time. No output repair. Preview review found the `y=t`
label ambiguously beside the vertical boundary rather than the sloping line.
Artifacts: OUTBOX/integral-output-diagnostic-20261028-approved and
OUTBOX/integral-visual-policy-eval-20261028. This task-context candidate has
NOT been promoted into the server or installed system prompt.

Three additional first-pass offline cases with that candidate: fractions
compiled in 2.627 s; odd-squares rejected at 3.100 s wall time because grouping
three borders expanded to 69 commands/78 strokes; Pythagoras rejected at
7.770 s wall time for label collisions. Pythagoras also contained an incorrectly
constructed hypotenuse square. Raw bytes and previews are retained in
OUTBOX/visual-policy-batch-20261028. These are not three passing lessons.

The procedural candidate compacts grouped odd-square borders by omitting only
decorative hatches, retaining all unit grid edges, labels, counts and claims.
Its last stage is 42 generated commands, 51 strokes, 1,444 points and 16.566 s.
Only compacted odd-square expansion gets a 64-command ceiling; other components
and direct agent drawing remain at 32. Existing native stroke/point/time limits
are unchanged. All 493 offline Python tests pass; this change is not tablet-proven.
The original unedited model response now compiles offline, but its takeaway
misstates the next border of a k-by-k square as 2k−1 instead of 2k+1; quality
therefore still fails. See OUTBOX/odd-compaction-preview-20261028/summary.json.
This is evidence for deterministic constructions and explicit quality checks,
not permission to call arbitrary generated geometry or prose a verified proof.

The OpenAI Docs prompting check informed the explicit-style experiment and
keeping fixed-model evaluations: [prompt engineering guidance](https://developers.openai.com/api/docs/guides/prompt-engineering).
[Structured Outputs guidance](https://developers.openai.com/api/docs/guides/structured-outputs)
distinguishes output-schema reliability from answer correctness. Structured
output support in this particular Pi/OAuth transport has not been established;
no endpoint, model, reasoning or response-format setting was changed.

**Fresh dynamic triangle, 2026-10-28 17:10 UTC — visible and saved, final ACK held:**
At James's request, sent one fresh `Draw a triangle.` simulated-ink question
on page46 through actual PiDog. No canned reply, retry, patch deployment or
notebook close. Request `notebook-8fcf880be8ec484b9706adeef37ce670` generated
its answer at 2.191 s. Frame7 remained negative at 7.474 s; frame8 shows the new
Agent Pi Dog label and partial caption by 8.517 s from the tap. The caption
preceded the animated triangle; the completed takeaway is visible in frame37.
Native stage commit was 16.724 s server-relative. Final layout verification
refused at 33.422 s with `reading: pen-near`; James subsequently confirmed
getting excited during the test. Do not classify this as a clean acceptance
pass or automatically resend. Saved-file inspection finds the generated
triangle geometry and all 45 prior pages byte-identical. Of 168 prior stroke
records, 167 remain identical; full current-page absolute preservation and
post-reply reopening are not yet proven. Artifacts:
`OUTBOX/live-triangle-20261028-{timing,verified}.json`, before/after tar archives,
and input/frame/final PNGs. The notebook remains on page46 with the final
warning; no replay or forced success ACK was issued.

**Circle placement audit:** `OUTBOX/circle-input-placement-20261028.json`
registers an unchanged existing caption before text-focus against the
pre-delivery frame, independently of the handwritten input. Under that single
screen translation (+34,-404), all 3,928 human-input dark pixels and the
nearby captions, inequality and takeaway match within 2 px. This resolves
visible relative placement across the manual focus operation, not full-page
or post-reopen proof.

**Inactive-cursor candidate — OFFLINE ONLY:** `herdMeasureLayout` now accepts
exactly numeric -1 only in pen mode with the native visibility API present.
Under the existing input locks it focuses the existing root with the native
NaN-point call, waits a separate settling phase, queries exact server indices,
then parks a hidden cursor at 0. This is intentionally not restoration of the
inactive internal state. Existing valid cursors still restore exactly.
No editor entry, text creation or content insertion occurs in measurement.
All identity/input/revision/view guards remain; focus-induced scrolling fails
rather than changing the reference matrix. Node tests cover delayed focus,
invalid cursor values and interrupted capture; a real `herdText` regression
proves plain and ordered replies reacquire the below-input target before
layout. MC Claude reviewed the narrow approach and raised these addressed
handoff/focus/view concerns. All 16 native Node files passed before the final
explicit-NaN/entry-test refinement; both affected suites pass afterward.
Actual firmware's inactive value and this candidate's behavior still require
an isolated test. Installed and loaded subsequently as recorded above; offline
cursor mocks are not live proof.

**Live human circle, 2026-10-28 16:54 UTC — recovered, not clean acceptance:**
James wrote “DRAW A CIRCLE” on page46 below the fraction fixture. Original
request `notebook-d03d7675167f4fe3800e1b00e10eb74f` failed validation; its raw
invalid response was not retained, so the exact original schema error is unknown.
An independent offline reproduction returned a Unicode circle as text, not ink.
Commit b7d831e permits 1–2 step drawing-family answers (teaching lessons retain
their minimum), adds a real circle example, and raises new stroke velocity from
250 to 300 units/s. PiDog's fixed startup prompt was separately updated/reloaded;
editing the server prompt alone does not reload that host's prompt.

Actual retry found three integration gaps now fixed: failed unanswered model
requests blocked the next explicit Respond (766d151); native source/archive and
tablet import guards still required three pages (df1bcec, 051cee9); and dismissing
a send rejected before assignment of a request ID threw a QString error
(f57d269). Concurrent retry regression 93359c7 verifies exactly one new worker.
484 Python tests pass; native import, dismiss, recovery and incomplete-warning
Node tests pass. These are offline results, not device reliability claims.

Live request `notebook-3c6d7f372cb54c5797f57f3661bbe2d1` returned a valid one-step
circle from PiDog at 3.190 s after Respond (model first text 2.906 s). No fixture
or substitute response was used. It initially held at the tablet import gate;
after that fix it held at `Native layout capture unavailable: cursor` on a
reopened page. A deliberate native Edit text/open-and-hide-keyboard action,
without typing, activated the cursor. Explicit repair then delivered the SAME
held model answer: Agent Pi Dog label, caption, animated circle, takeaway, and
confirmed saved state in 33.650 s from repair arm. This is NOT Respond-to-visible
latency, NOT an unattended pass, and NOT evidence of general proof quality.
No notebook closure occurred during the successful repair delivery; two setup
save/close/interface reloads were needed while correcting the earlier gates.

Evidence: `OUTBOX/circle-live-v3-20261028-timing.json`,
`circle-held-original-response.json`, `circle-held-focus-repair-timing.json`,
`circle-live-complete-20261028.png`, and `circle-live-20261028-verified.json`.
All 45 earlier pages are byte-identical. The current page has one new circle;
133 old stroke records are unchanged. Native text activation reanchored 17
existing strokes: their shapes match under a common translation, but absolute
pre-focus layout has NOT yet been independently verified. Do not report complete
preservation proof relative to the pre-focus backup. The delivery's own native
preservation proof passed against its later baseline. Post-reply reopen remains
untested. Next: handle an inactive native cursor without manual UI preparation,
verify original input layout, then run fresh unscripted visual questions.

**First attended native text/math candidate:** eight runtime files through
`eff9b01` installed with backup `OUTBOX/native-ux-runtime-backup-cdgf8arv`;
patch loaded at 15:29:40 UTC, PID 15819, after normal save/close. The staged
candidate over actual runtime dependencies passed 115 targeted Python tests
and all 14 native Node files. Page 41 `464e98a2-1ff6-4a9e-97de-48b4d8340f55`,
request `notebook-f4066295167a4f678a766643edd3c7bb`, FAILED: first picture stage
committed at 16.940 s; one caption “S” appeared, then the client held at 17.714 s
with the combined page/input guard. No resubmission. Prior human circle notes
on page 40 were present before deployment and were not used as the test page.
Artifacts: `OUTBOX/native-ux-attended-20261028-*`.

Native QML confirms `SceneView.isLoading` includes controller work and pending
tiles. The initial typewriter put it in the fatal guard, before the busy wait,
so normal append reflow can falsely abort. The correction waits for loading
after identity/pen checks and existing deadlines, rather than treating it as
page-change proof. Regression tests cover normal editor/tile reflow, changed
page while loading, and a stuck loading state without replay or deadline
extension. This diagnosis identifies a real guard bug; the corrected physical
retest is still required, and the failed attempt remains a failure.

**Attended fraction replay, page 40, 2026-10-28:** James said the 200-unit/s
fraction comparison “looks pretty good,” asked for about 25% faster motion,
asked that the inequality draw rather than pop in, and requested typewriter-like
native prose. Request `notebook-be23dbf802ff4604b564de4143971152` on page
`a19db50c-8cff-4eeb-be69-2c3c8ce96773` completed at 64.866 s; four drawing
stages committed, all 39 earlier pages byte-identical. Artifact prefix
`OUTBOX/slower-attended-20261028`. This was a renderer fixture, not a PiDog
model-quality test. No reopen during delivery or afterward.

The 200-unit pace had been deployed before this run. The first attempt (page
36) failed before any diagram ink because a 70,046-byte valid plan exceeded
the journal reader's 64 KiB metadata limit. `cf06fb4` aligns plan-only read/write
limits at 1 MiB, rejects oversized writes before creating either journal file,
and retains 64 KiB claim/ACK limits. MC Claude found no blockers in this narrow
fix; 455 Python tests passed then. It is live; the failed attempt is retained.

**Next UX changes, offline only:** renderer velocity 200→250 (25% faster,
20% shorter movement; unchanged 70 ms pen-up gaps). Native lesson captions and
takeaway use a 40 ms character timer, append through the native editor, and
wait for asynchronous text/cursor settlement; page, pen, selection, unexpected
length/cursor and timeout changes hold the partial reply without replay. No
per-character model output. Common combining/emoji sequences stay together;
complex joining scripts conservatively reveal the whole run. Native caption
typing is not yet proven on the physical display; native text refresh cadence
and virtual paragraph behavior need an isolated test.

`notebook_equation_ink.py` now renders the existing bounded equation grammar as
ordered plotter strokes, sharing the parser with the raster backend. Offline
2/3 > 3/5 uses seven strokes / 247 points / about 2.22 s at 250 units/s; the
definite integral uses 17 strokes / 433 points / about 4.01 s. Geometry uses
the same native asset/playback validation, without bitmap tracing or model
coordinates. Previews: `OUTBOX/pen-equations-20261028-v2/index.html`. The math
renderer is now wired into semantic lesson insertion behind the explicit
`pen_equations_version: 1` client capability and the existing playback rollout
switch. This integration is OFFLINE ONLY; production still uses raster math.
The optional equation is a separate final ink region before the takeaway.
Six diagram steps plus one renderer-owned equation can use seven source pages,
but the whole lesson still has a 12,000-point budget, including math, and each
stage retains its 64-stroke/3,000-point/30-second limits. Invalid combined plans
fail before provisioning; capability loss during import holds the reply.
Regression result: 466 Python tests and all 14 native Node test files pass
offline, including the incomplete-reply context/view tests below.
No new QMD deployment/restart and no further unattended demo.

MC Claude review follow-up: the 90 s fixed typewriter deadline was too tight
for the allowed 2,000-unit ceiling with asynchronous insertion. It now has a
10 s no-progress timeout, reset only by acknowledged native text insertion,
plus a unit-count-scaled total bound. The slow-editor regression crosses 90 s
and finishes; a stuck first insertion stops without replay. Pen proximity/input
still aborts rather than automatically resuming over possible new writing.
The existing error banner explicitly says the caption is incomplete and its
partial text was kept. A read-only reopen hint now reuses the existing durable
`.native-attempt` record: an accepted active-page context report can restore
“Reply may be incomplete — tap to dismiss” for the same unconfirmed request. Dismissal
only clears the current view's warning; it does not edit text, retry insertion,
or change saved delivery state. No new journal or inline marker deletion.
Offline tests cover fresh views, a restored held reply, completed/superseded
attempts, page changes, and dismissal. Restoring the hint requires backend
connectivity. **Physical reopen indication remains unproven:** an interrupted
caption and reopening test is still required before calling this complete.
Never erase partial text on a changed page or infer authority to resume.
Velocity 250 is based on James's newer
direct-session request for 25% faster than the attended 200-unit fraction
demo, not the older complaint that 240 was too fast.

MC Claude's d12aa8f review found no integration/budget blocker and raised two
warning-lifecycle questions. The hint now says **may be incomplete**, because
a missing final acknowledgement cannot prove missing page content. The final
native endpoint `/native-text-done` has one successful return, after setting
`answers[path] = written`, removing the held/pending reply and clearing its error.
Stage `/native-ink-done` and `/notebook-ink-proof` acknowledgements deliberately
do not complete the whole reply; captions/takeaway or final visibility proof
can still be pending. An offline six-case regression exercises actual final
ACK handling for legacy text/lesson, semantic answer/clarify, and semantic
raster/pen math: every success clears the hint, leaves the attempt file intact,
and rejects demotion by a late failure callback. Device/proof inputs are mocked,
not evidence of tablet persistence. If the final response is lost after server
completion, `/answer` still reports written; if the request never reaches the
server, uncertainty remains and no automatic replay is authorized.

**Attended repeat, 10:09 EDT:** At James's request, repeated the existing
`motion-check` fixture on fresh isolated page 35
`2964227f-7830-4ddf-92aa-30ee0eec95b0`, request
`notebook-253c5a446ecc4a4fb3312b360d25d8cd`. James's direct-session verdict was
“that looked godo just a little quick.” This is positive physical-panel feedback
for the scoped Animation-mode bridge, with a speed refinement requested—not a
claim that physical pen events were used or that all lesson types are accepted.
All three new strokes match saved source geometry and all 34 preceding pages
are unchanged. Saved ACK 39.551 s; first stage claim 7.241 s is NOT a measured
first-visible time. No model call, notebook closure or restart during delivery.
Artifacts: `OUTBOX/motion-repeat-20261028-{timing,verified}.json`; the verifier's
earlier `pending human observation` field predates this verdict and is retained.
No reopen test on this repeat. The previous failed demo below remains a failure.

Earlier pace refinement: default 200 rather than 240 local units/s
(20% longer motion), with unchanged geometry, pen-up intervals, input guards
and 30-second stage cap. Existing 240-unit descriptors remain valid. Browser
preview timing uses the actual descriptor, not a separately hard-coded speed.
This refinement was subsequently deployed and attended on page 40 above.

**Physical acceptance correction, 2026-10-28 09:04 EDT:** James watched the
fresh actual PiDog integral demo on page 33 and said the final picture looks
good, but it still does not draw slowly like the earlier real-pen lines,
curves and circles test. Treat the Canvas bridge as **FAIL for the requested
physical slow-drawing experience**, not merely awaiting observation. Captured
partial frames and Qt `painted` callbacks do not override that report. We have
not established whether panel update scheduling/coalescing is the cause.
The reply path disconnects physical pen routing, paints a temporary Canvas,
and then clones a complete native stage; the successful attended primitive
test instead sends paced native pen events. These are different mechanisms.

Request `notebook-2084eb9509134b46a4fe4df97a2e74e5`, page
`540be305-ae36-46d4-9639-8b13f3a1c550`, artifact prefix
`OUTBOX/integral-live-demo-20261028`: model ready 6.994 s, first-stage claim
13.004 s, final ink commit 40.352 s, saved acknowledgement 58.831 s (all from
server receipt). All 53 new diagram strokes match saved source geometry and
all 32 preceding pages are byte-identical. The notebook stayed open during
delivery and was left open afterward; no reopen test this run. This proves
delivery/preservation, not satisfactory animation. The un-deployed source-read
optimization in `de961f7` was not part of the demo.

Next priority is the bridge from validated procedural geometry to the native
incremental drawing path that produced the accepted primitive motion. Do not
spend another end-to-end model run to test panel refresh. First use a single
bounded line in an isolated page, observed by James, then a curve/rectangle,
then connect the existing lesson geometry. Reuse existing request/stage claims;
do not bypass the current input lock or silently enable simultaneous physical
and automated pen input. A supported native scene builder or deliberately
isolated input route still needs investigation. No new lease/audit layer is
justified by this visual failure.

**Scoped display-mode experiment, 09:18 EDT:** Installed firmware resource
`native-qml.k14u9p/16568793.qml` uses an `Epaper.ScreenModeItem` with mode
`Animation` for its progress UI, and `16579338.qml` distinguishes animation
from ordinary content refresh. Our Canvas had no such item. This is a concrete
missing display hint, not proof of the physical failure's root cause.
Commit `14184ee` adds that item only inside the lazy Canvas, inheriting its
bounded dimensions and visibility, with no global mode assignment, new input
route, or change to native persistence. It is still an overlay-then-paste
implementation, not actual pen input.

After normal save/close, one setup restart loaded the patch at 13:14:04 UTC
(PID11127); the preceding integral survived reopening with unchanged hash.
Only QMD and the named fixture library were promoted; backend source-read
optimization `de961f7` remains undeployed. `motion-check` uses the existing
local-only fixture arm: one line, circle, rectangle, each a single native
stroke, with planned motion 2.083/2.224/2.917 seconds. No model call.
Request `notebook-e346767f61344819974d18816f9b77c0` on fresh page 34
`a7450821-f1ce-492f-a89d-64f4dcd684f0` completed all three claims/commits and
saved at 38.736 seconds from server receipt. The three new strokes match source
geometry; all 33 earlier pages are byte-identical. No close/restart during
delivery, no error banner. Artifact prefix `OUTBOX/animation-mode-20261028`.
The page is left open. **Physical motion remains unverified pending James's
observation**; partial framebuffer lines are not acceptance. Offline: 444 Python
tests and all 12 native Node files passed; the new Node assertion checks QMD
structure, not firmware waveform behavior. No broad rollout or completion claim.

Related read-only research: [inkling's XOVI bridge](https://github.com/nathanmarlor/inkling/blob/main/xovi-ext/README.md)
uses Qt entry points for UI/selection/tool operations and reports ARM32 hook
race risks. It does not document a safe incremental Line builder. No third-party
extension or installer was executed. MyDude has the focused native-builder
research request; the display-mode experiment must not be misreported as that
missing integration.

**Reopen and API check, 09:29 EDT:** After the same request was terminal
`written`, a normal close/reopen returned to page 34 with the line, circle,
rectangle, input and captions visible. The page remains byte-identical to its
pre-close saved file (`18d2f537649e8537f3d504e0a3b7764154d912f1733e8457221eceea3d1f53c5`),
and all 33 earlier page files remain unchanged. Evidence is
`OUTBOX/animation-mode-reopen-20261028-{before,closed,open,settled}.png` and
`-verified.json`; the first open frame was still loading, not lost ink.
No restart, model call or answer replay was used. Physical animation is still
pending human observation, separately from this successful persistence check.

Read-only inspection of the installed `/usr/bin/xochitl` (SHA256
`52c952f0adf4f5becb153544641d508026767229e0636ef69d111e10e30f538b`)
narrows the native API search: the `ScenePenInputHandler` metadata strings at
15840380 expose `setSelectionActive`, `queryIntermediateState` and
`setShapeDetection`; its `PenInputLineHandler` base at 15842568 exposes pen
style properties, and `PenInputHandler` at 15843360 exposes transforms,
main-thread locking and pen-up time. `PenInputSurface` at 16735636 exposes
`clearFramebuffer`, `setTransform`, `mapPenPositionToLocal` and
`replayLastPenPoint`, not a demonstrated arbitrary-point submission method.
The `beginStroke` string at 19787404 is next to `ToolMenuGesture` source/log
strings, not that handler's QML method table. These are search-scoped metadata
observations, not proof that a native extension is impossible. No speculative
method calls or pen-filter changes were made. In particular,
`PenInput.setFilterEvents` must not be mistaken for an isolated synthetic input
channel: its presence alone establishes no safe routing behavior.

The latest actual PiDog/tablet fraction lesson demonstrated ordered persistent
native ink, but each stage appeared in four coarse paste chunks. It did **not**
demonstrate the slow pen motion James requested. The attended physical-pen demo
and the normal response path remain different mechanisms.

`notebook_ink_playback.py` now pairs an ordinary native stage asset with a timed
descriptor decoded from those exact asset bytes. The model supplies no animation
frames or timing tokens. The procedural default is 240 local units/second,
70 ms between strokes, and a 50 ms minimum for dots/short marks. Existing
whole-plan validation, 64-stroke/3,000-point caps and 30-second stage cap remain;
actual arc-length duration must also fit 30 seconds. Reject excess duration,
do not silently accelerate or drop geometry. All stages validate before import.

The QMD prototype reuses the existing claim and native input lock. It brings the
shared picture into view before each stage, interpolates along arc length
(including corners), and draws on a transparent Canvas bounded to that diagram.
It does not unlock/inject physical pen input or create a separate drawing pad.
Only after Qt reports the final Canvas paint complete does it dispatch the
ordinary native clone once; the overlay stays through native insertion ACK.
Saved-page geometry proof still decides persistence. A displayed overlay or
insertion ACK is never proof of a saved response. A crash before native insertion
loses the transient stage; the existing attempted claim holds it for inspection,
not automatic replay. No new lease/journal layer is introduced.

Qt's [Canvas documentation](https://doc.qt.io/archives/qt-5.15/qml-qtquick-canvas.html)
documents the Image target, Immediate strategy, and painted signal; the
[Context2D API](https://doc.qt.io/archives/qt-5.15/qml-qtquick-context2d.html)
provides the transforms and path operations used. These API references are not
evidence of this firmware's e-ink refresh behavior. A Qt painted signal is not a
measurement of when a human first sees a line on the physical display.

**Offline proven:** exact descriptor/native-byte geometry; velocity and pen-up
timing; corners and dots; full-plan rejection; import capability continuity;
one claim/one native paste; final-paint gating; late timer safety; cancellation
on page, input, revision, viewport or suspend changes; no save success for missing
or partial native geometry. Regression: 399 Python tests and all 13 native Node
test files pass. JavaScript tests execute extracted QMD functions with mocked Qt
objects, not the firmware renderer.

**Deployment and tablet evidence, 2026-10-28:** The initial eager-Canvas build
caused native toolbar tools to fail loading, before playback even began. The
firmware reported `Required property toolbar was not initialized`. Restoring the
previous private QMD restored the toolbar; all 26 earlier pages remained byte
identical. Commit `d78dc01` defers Canvas creation until the first actual ink claim,
instead of constructing/reparenting it during DocumentView startup. After the
setup reload, the toolbar loaded normally and no repeat of that error occurred.
This isolates a startup interaction, not a proven diagnosis of Qt internals.

The isolated integral renderer fixture then completed four animated stages,
followed by native persistence. All 53 newly inserted strokes match the exact
source geometry. A normal close/reopen retained the same saved page SHA256;
all 26 prior pages remained unchanged. First captured partial drawing was at
9.512 seconds, final saved acknowledgement at 57.753 seconds. These are fixture
timings, **not PiDog latency**; the input was simulated ink, not fresh human writing.
No notebook close or interface restart occurred during the exchange.

Evidence: `OUTBOX/playback-integral-20261028-timing.json`, frames 00–58,
`-before-reopen.json`, `-after-reopen.json`, and `-reopened.png`. Request
`notebook-cb2e983593e5470a8c7698ba4eac1003`, isolated page
`4c7d7d27-4da8-44df-8609-99c2757b6a38`. The source/hash verifier excludes
pre-existing stroke IDs; an overlay screenshot is not its persistence evidence.

The following **actual PiDog** fraction exchange (simulated handwritten input
"Show why 1/2 equals 2/4.") also completed without closing the notebook during
delivery. The model completed at 3.965 s from server receipt (3.213 s after
submission). Captures bound the first agent label at 8.961 s and first drawn
label strokes at 11.744 s from the Respond tap; the latter misses the 10 s goal.
The two bar outlines, partitions and hatching progressively appeared; all four
stages committed by 42.852 s and saved acknowledgement completed at 61.135 s.
The per-stage programmed draw durations were 9.556, 1.177, 4.715 and 4.680 s.
This distinguishes deliberate animation time from preparation/confirmation delay;
it is not a claim that the whole remaining interval is removable overhead.

All 52 new native strokes matched; all 27 earlier pages were byte-identical.
Normal reopen retained the exact saved page hash and the complete native lesson.
Captions, hatching and equation correctly explain equal halves/quarters with no
final overlap or stale banner. Artifact prefix `OUTBOX/playback-pidog-20261028`;
request `notebook-890acbc76398405ba356b8771eae0287`, page
`51a69ff5-0f4c-45e7-910c-b9dc51ebc8d0`. The 60-frame observer ended while the
same request was still writing; a later status check confirmed `written` without
resending. This is one actual model exchange, not ten human acceptance tests.

**Still unproven:** physical-panel smoothness at the 25 Hz paint-request cadence,
native/overlay line-weight match, absence of flicker/double ink during handoff,
crash appearance, and interruption during the native-paste handoff. Pen-proximity
cancellation during the display-only portion is proven below. Mid-animation memory captures contain
horizontal gaps that disappear in the final native drawing. These may be torn
captures while reading a changing framebuffer, but that explanation is not yet
proven; do not label them either a clean animation or confirmed panel flicker.

QMD advertises `playback_version: 1`, but the server
requires an explicit operator `stroke_playback: true` in the existing rollout
configuration. Default is off; the notebook allowlist remains mandatory and
removing the option during source import holds the reply. The option is currently
enabled only for the isolated Storyboard test notebook. Review is requested, not
approved. Next checks: physical-panel animation quality, corner/dot behavior,
page-change cancellation, and reduced preparation/confirmation latency. Do not broaden rollout
until those observations pass. This prototype is not a substitute for the full
lesson-quality, latency, ten-exchange, second-notebook and broad-rollout gates.

### Leaving the page during model generation — live test, 2026-10-28

Normal navigation from a new handwritten test question to the preceding page
cancelled the in-flight model call before insertion; all 29 saved pages remained
unchanged. This was **not** a completed answer held for later insertion: the model
had not finished, and no result was published. The original test incorrectly
expected `ready` and its failed assertion is retained in the evidence.

The test exposed a misleading generic "Reply needs attention" banner. Commit
`a864c70` names locally observed `page_changed` and `page_unavailable` cancellation
reasons, retains the first reason for that call, and maps only those known reasons
to clear UI notices. Returning to the page cannot revive a stopped call. Provider
cancellation is not mislabelled as a page change. Other errors retain the existing
failure display. Dismissal is still just dismissal, not retry or resend. A completed
reply waiting on another page now says so instead of "Answer coming in".

After one saved/closed setup reload (xochitl PID8730, 12:15:43 UTC), the repeat
test on new page `697dbfd5-833f-4311-bd2a-41a307f07f29` stopped request
`notebook-b4388e3460ea4d33864e93d945f586b1` before insertion and showed
"Page changed — request stopped — tap to dismiss". All 30 saved pages were
byte-identical before/after; the notice dismissed without resending and left
the earlier fraction lesson intact. Artifacts: `OUTBOX/page-change-v2-20261028-*`;
original test: `OUTBOX/page-change-20261028-*`. No repeated start, automatic repair,
new lease, or new audit layer was added. This proves the **pre-insertion** navigation
case, not interruption halfway through animation or a completed-reply recovery.

Offline verification for this commit: 439 tests under Python unittest discovery
and all 12 `test_native_*.cjs` files pass. The Node tests cover UI reason mapping,
unknown-error filtering, matching-request polling, and original-page status;
Python tests retain no-publish/no-fallback/supersession checks and cover sticky
cancellation plus provider/local cancellation distinction.

### Pen proximity during slow playback — live test, 2026-10-28

On fresh diagnostic page `ded0162b-9f46-4d7e-b960-eeb1efd7feb2`, one integral
fixture request `notebook-c93c62b39658469fb11e20f41dfc7481` reached the first-stage
claim at 7.177 s. A capture shows partially drawn axes. At 9.096 s after the
Respond tap, the test injected **pen proximity only** for 1.5 s (tool present,
touch off, pressure zero), then released it in `finally`. It never sent pen-down.
The live client reported `Playback page or input changed`; server `native_failed`
was 9.028 s from server receipt, a different timing origin. No stage committed.
The overlay disappeared, the native controls unlocked, and no automatic replay
occurred. The already-inserted `Agent Renderer Test:` header remained deliberately.
No app restart or notebook close occurred during this test.

Independent saved-world-geometry verification against the request's original
pre-insertion baseline preserves all 40 input strokes (every point and style),
with **zero new ink strokes**. All 30 preceding pages are byte-identical. An
existing read-only hidden-source cursor probe supplied the required native text
anchor; it changed neither source bytes nor the foreground page. Dismissing the
notice and normally leaving/reopening the page restored RESPOND, no overlay,
and the same saved SHA256
`251914caa82ee172b930aff7efa3601b615347a0b463e5cc108f4ad02338c588`.

The initial helper incorrectly compared raw `(parent, item)` identities across
native text insertion. Native regrouping made all 40 records appear new; the
helper failed and its original result is retained. This was not lost handwriting
or an unsaved-input race: the pre-tap file already contained 40 records. The
separate verifier uses the existing geometry-aware preservation implementation
and the native anchor measurement, not a best-fit translation or relaxed check.

Artifacts: `OUTBOX/playback-interrupt-20261028-{result,verified}.json`,
`-partial.png`, `-after-04.png`, `-reopened.png`, and `-verified.rm`; bounded
helpers `test-playback-interruption-20261028.py` and
`verify-playback-interruption-20261028.py`. The request remains failed/stopped,
not written or recoverable by replay. This proves only pre-paste pen-proximity
interruption, not page navigation while locked, process crash, or post-paste
failure. It is a renderer fixture, not a PiDog exchange or latency benchmark.
No production code, configuration, new lease, or audit layer was added.

### Regional blank-space capture — latency change and live demo, 2026-10-28

Commit `e882a22` changes only the first native ink stage's framebuffer read:
`capture_region` transfers the rows covering the existing projected drawing
reservation and its three-pixel margin, then crops the exact horizontal extent.
It retains every pixel, the `<110` threshold, full allocation validation, current
PID resolution, source integrity checks, request checks and post-I/O page/input
validation. Full-screen capture remains the path for handwriting and saved-reply
confirmation. It adds no cache, polling loop, lease or audit layer.

Offline: all 442 Python tests and 12 native JS test files pass. New tests compare
regional decoding byte-for-byte with full-frame crops, including single pixels
at opposite display corners, non-page-aligned row offsets, all reservation margin
corners, invalid/truncated/mismatched headers and bounds, and request change after
capture. An initial new test assumed the authored integral was 900x500 rather
than its actual 600x300; that test expectation was corrected before deployment.

Read-only device measurement: eight alternating full/region pairs on the same
unchanged page gave identical crop hashes every time. For the 906x506 test region,
median capture time was 0.573 s full versus 0.222 s regional. This is approximately
0.35 s saved in **one check**, not a claim about whole-response latency. Evidence:
`OUTBOX/region-capture-20261028-benchmark.json` and its bounded helper.

Exact backend files `herd-board-serve` and `tablet_live.py` were promoted with
backups in `OUTBOX/region-capture-deploy-20261028-6y967lil`, followed by an
authenticated backend restart. QMD, model/prompt, rollout configuration and the
running tablet interface (PID8730) were unchanged. Review was requested with an
explicit MyDude mention; no approval or general rollout is claimed.

One fresh actual PiDog exchange on page32 `ec6f9dcb-4c9d-43c5-8a2e-20a826e09e11`
asked, in simulated handwriting, "Show why 1/2 equals 2/4." Request
`notebook-5193b3c182744cc9959d3c462a071ac6` completed without closing/restarting
the notebook: progressive bar outlines, partitions, hatching, captions, equation
and takeaway. Frame13 at12.006s has no drawing; frame14 at12.904s has partial
plotter text. First-stage claim11.507s, all ink committed44.063s, final written
65.459s (server-relative). **Under10s first-drawing goal still fails**; overall
latency did not improve in this run. Image preparation1.502s and model duration
4.338s were slower than the previous exchange. Write-start→first-claim was3.002s
versus3.357s previously, consistent with the microbenchmark but not a controlled
end-to-end causal estimate.

All52 new diagram strokes match native source geometry; all31 earlier pages are
byte-identical. Saved page SHA256 is
`42a949951d80f8be0949c445392df66da13205757d359cc1c9435895019373d4`.
The lesson was left open for James to inspect; no new reopen test was performed.
Physical-panel smoothness awaits his observation. Artifact prefix
`OUTBOX/region-capture-demo-20261028-` includes timing, frames, settled capture,
before archive, saved `.rm` and independent verification JSON. The frame observer
ended at54.078s while still writing; the same request later confirmed written,
without retry/resend. This is a second actual slow-playback model exchange, not
ten fresh human acceptance exchanges or completion of the full workflow goal.

### What counts as success

- A new question produces a dynamically composed explanation, not a selection from three complete canned scenes.
- The picture contributes evidence or intuition that the caption alone does not provide.
- The explanation is legible in monochrome, visually coherent, and pleasant at the tablet's actual reading size.
- First substantive response appears in under 10 seconds on the normal fast route; all actual timings and failures are reported.
- James's ink is preserved. Responses go below the latest input, carry the actual agent's name, survive reopening, and never require closing the notebook to refresh.
- A page change holds the reply. Unsupported drawing requests fail honestly rather than inserting misleading or unvalidated geometry.

## Evidence behind the change

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| Existing native lesson adapter interleaves ink stages and captions in one shared scene | We can reuse a staged notebook delivery path | Broad reliability, aesthetic quality, or arbitrary lessons |
| Recent live sky test took 47.135–48.428 seconds to first observed response and ended in native text | The current authoring loop misses the latency goal and did not produce a valid drawing | That the tablet or rendering code consumed those 48 seconds |
| That request took 44.619 seconds from agent receipt to final reply; two preview checks took 0.183 and 0.172 seconds | Repeated agent/tool transitions are a material target for removal | A precise decomposition of model inference versus scheduling time |
| New local procedural lever, water-cycle, and short-plan fixtures compile and native-encode in 4.148, 6.368, and 6.906 ms respectively | Small semantic descriptions can cheaply expand into validated native geometry | Model quality, production integration, tablet latency, or a polished doodle style |
| Procedural prototype currently supports a lever and a bounded network layout with six simple object shapes | There is a useful starting point | A general-purpose illustration engine |

Evidence files: [live sky report](../../../../OUTBOX/chalkboard-live16-author-sky-review.json), [procedural results](../../../../OUTBOX/procedural-board-demo-20261027-v1/results.json), and [stage previews](../../../../OUTBOX/procedural-board-demo-20261027-v1/index.html). These are local workspace artifacts, not portable repository assets. The live report also records preservation checks and their limits. Its text fallback is not a successful doodle demonstration.

The underlying architectural error was assigning geometric execution to the model: calculate coordinates, avoid glyph collisions, render previews, inspect them, revise, then answer. A stronger model might reduce mistakes, but it would not remove that work or make it deterministic. The new division of responsibility removes the work instead.

## System boundaries

```text
reMarkable Respond
    │ captured question image + existing request and page identity
    ▼
Notebook coordinator on the Mac
    │ self-contained input, concise relevant history, supported visual vocabulary
    ▼
Pi-Dog notebook responder
    │ one complete semantic LessonSpec; no coordinates or shell work
    ▼
Semantic validator → deterministic scene compiler → whole-lesson validation
    │                         │
    │                         └─ same compiled scene → offline previews and evals
    ▼
Native bundle adapter → existing guarded staged insertion → saved notebook

Buzz / Nvoy coordination is outside this response path.
```

The Mac remains the service boundary; the tablet remains a thin native display and input client. Keep the current localhost/tunnel transport. Do not introduce a new cloud rendering service, tablet package installation, VPN change, or general remote execution channel.

| Component | Owns | Must not own |
| --- | --- | --- |
| Tablet client | Capture, visible state, native placement, page-change checks, scrolling, persistence acknowledgments | Model reasoning or direct replacement of the open page file |
| Notebook coordinator | Request lifecycle, input packaging, identity, deadlines, collection of one answer | Scientific explanation or invisible retries of uncertain writes |
| Pi-Dog responder | Read input, reason about the subject, choose a teaching structure, write captions and semantic relationships | Pixels, fonts, routing, file management, preview commands, device access |
| Scene compiler | Layout, geometric construction, scales, anchors, labels, style, reveal schedule | Changing the answer's meaning to make an invalid diagram fit |
| Native adapter | Convert a validated scene to ordered ink/text/media blocks using existing machinery | Letting model-supplied paths or IDs select files or destinations |
| Offline evaluator | Replays, previews, quality comparisons, regression and latency reports | Posting answers to real notebooks |

These are code responsibilities, not six new services or agents. Implement initially in the existing Python process and modules.

### Alternatives and tradeoffs

| Alternative | Why it is not the default |
| --- | --- |
| Ask a stronger model for raw coordinates | Keeps layout, scale, and collision work in an expensive probabilistic loop; useful for an offline comparison, not the execution model |
| Generate a beautiful full-page image for every answer | Sacrifices native text and object-level reveal; makes revisions and persistent notebook interaction harder |
| Trace every generated image into strokes | Adds generation and conversion latency; contours alone do not recover semantic objects or teaching order |
| Select only authored complete scenes | Fast and reliable for known examples, but fails the requirement for new questions |
| Build a general animation editor first | Large scope without proving that one model response can become a useful notebook explanation |
| Stream each model drawing instruction directly | Improves apparent startup at the expense of whole-picture validation, coherent layout, and safe partial failure |

The chosen design trades unlimited immediate illustration freedom for predictable, extensible visual components. The cost is maintaining that component library and its semantic tests. The benefit is that visual improvements apply to every lesson using a component without spending additional model tokens. This tradeoff must be evaluated on unseen questions, not only the examples used to build it.

## Pi-Dog as a notebook responder

### Actual configuration and proposed configuration

Pi-Dog reported on 2026-10-27 that its session identifies itself as `gpt-5.6-luna` through `openai-codex`, with reasoning `medium`. This is self-reported provenance, not an independently authenticated runtime setting. Its seat can inspect local PNGs and has broad file, shell, and Nvoy tools. The report does not establish a dedicated notebook profile, native JSON-schema enforcement, or an isolated session. Do not describe the current route as sandboxed to a preview helper or as already running minimal reasoning.

Create a dedicated **notebook response profile** within Pi-Dog's existing identity. Keep Pi-Dog's personality and relevant notebook continuity, but exclude development conversation and Buzz coordination from each inference. The service should attach the image directly when the supported transport allows it; a local path alone is not portable image input. Until direct attachment is supported, expose a narrowly scoped image-read operation and measure its extra round trip.

The existing route invokes `herdr pane run` into the agent's pane and finds the response in session transcripts by request marker. A new profile name cannot isolate history on that route. Before production integration, choose a supported invocation that creates a distinct notebook-scoped execution context under Pi-Dog's identity, attaches the actual image, restricts tools, and returns a final result bound to the request. Verify configuration and behavior: put a development-only sentinel in a separate development context and confirm it is not supplied or recoverable by a notebook request; attempt a prohibited tool call and confirm the execution layer denies it; confirm the actual image reaches the model. A model saying it cannot see the sentinel is insufficient without checking the supplied context. If the harness cannot enforce these boundaries, label the route unisolated and keep the proposed fast profile out of production while offline work continues.

Proposed logical configuration below is a design contract, **not valid configuration for an established harness API**:

```yaml
profile: notebook-doodle-v1
identity: pi-dog
model: verified-installed-luna-alias
reasoning: lowest-supported-level-that-passes-the-quality-suite
input: question-image-plus-bounded-notebook-context
output: LessonSpec-v1
tools: none-after-input-attachment
history: notebook-scoped-summary-and-relevant-recent-exchanges
normal_model_calls: 1
automatic_geometry_revision_calls: 0
target_visible_output_tokens: 450-900
max_visible_output_tokens: 1400
target_model_wall_seconds: 5.5
interactive_request_deadline_seconds: 20
```

Resolve the actual provider/model identifier and supported reasoning values from the serving configuration before implementation. Compare the installed Luna option at its supported low setting against its current setting and one stronger available responder on identical inputs. Select the cheapest/fastest setting that passes the quality gate, not the lowest reasoning label by assumption. Do not silently change James's global Pi-Dog model or grants.

The token target is for visible lesson JSON, not a guarantee about provider reasoning tokens. The adapter must map output limits correctly for the chosen backend and record actual usage when exposed. A truncated JSON object is a failed plan, never a partially valid lesson. If the measured transport/model cannot meet the 5.5-second allocation, change the measured budget or serving path rather than presenting it as achieved.

The notebook route should enforce tool exclusion in its execution configuration. Prompt instructions alone do not remove shell or Nvoy authority. Any necessary grant change remains James's decision; MyDude reviews the route boundary. Until enforcement exists, distinguish “asked not to call tools” from “unable to call tools.” No changes to permissions are part of this design pass.

### Input and context

Each request is self-contained: current question image, enough surrounding page context to understand references, notebook-scoped recent turns, a short user preference summary, and a versioned capability list. The service owns notebook/request/page IDs outside the model-authored payload. The agent cannot select another destination.

The image is primary evidence. Do not routinely serialize image → cheap OCR → second interpretation → planner. OCR may be an auxiliary hint for routing or accessibility, but uncertainty in a number, operator, or sketch must not be silently replaced by a guess. An ambiguous integral limit should yield one targeted clarification. A drawing-recognition answer should name the evidence it actually saw, not the most likely subject from the prompt examples.

Start with a bounded context budget: the current question image, optionally one contextual crop, a short notebook summary, and at most two relevant prior exchanges. Make these limits configurable and test references to older work. Do not include the full development transcript or keepalive messages. Request content is data; handwriting that says to run commands does not grant the responder execution authority.

### Response contract

The responder chooses one mode:

- `answer`: concise native text for facts, greetings, sketch identification, or unsupported visual coverage.
- `clarify`: one specific question when the input cannot be read or a material assumption is missing.
- `lesson`: a complete semantic picture, 3–6 reveal steps, optional equation, and takeaway.
- `media_request`: an explicitly requested generated image or imported photo, handled by a separate authorized media workflow.

Prefer one model call that returns the **entire small plan**. Do not introduce a serial reader agent, pedagogy agent, artist agent, critic agent, and repair agent on the interactive path. Difficult reasoning can use a separately configured deeper route, but it must be visible as slower work, not disguised as a fast reply. Initial release uses no automatic model retry for geometry failures.

Suggested core instruction, to replace the coordinate manual in the fast route:

> Read the handwritten question and teach one useful idea. Choose a concrete picture or visual model that makes the reason visible. Return one complete LessonSpec using only advertised components. For a lesson, introduce the situation, reveal the relationship, then show the conclusion in 3–6 short steps. Each caption explains what the new visual evidence means. Use shared scales for comparisons, distinguish physical paths from explanatory connections, and state material assumptions. Give semantic objects, quantities, and relationships, never pixel coordinates. Do not call shell, preview, messaging, or device tools. If the note is unclear, ask one clarification. If the vocabulary cannot honestly represent the answer, use a short text answer rather than inventing a capability. Finish with the takeaway; do not narrate your planning.

Ship two compact worked examples, integral and odd-square growth, generated from the same versioned contract tests as the compiler. Examples teach the grammar, not an instruction to reuse those scenes regardless of the question. Keep special cases in a short final section rather than accumulating incident-specific prompt patches.

Use provider-enforced structured output where the actual route supports it, with server validation regardless. Schema validity is not mathematical or pedagogical correctness. Official documentation explicitly notes that structured responses can still contain mistakes. [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

## Semantic lesson contract

Introduce a versioned `LessonSpec` above the existing low-level geometry language. The low-level language remains the compiler's internal target and a developer fixture format. It is not the normal model interface.

### Required concepts

| Field | Meaning |
| --- | --- |
| `v`, `mode` | Schema version and response mode |
| `intent` | The single question the lesson answers |
| `scene` | Composition family, semantic objects, relationships, quantities, and explicit assumptions |
| `steps` | Ordered reveals referencing stable object or relationship IDs, each with one short caption |
| `equation` | Optional structured mathematical expression, not executable source |
| `takeaway` | One or two sentences answering the original question |
| `fallback` | Optional short, independently useful answer if the visual component is unsupported |

No paths, URLs, source code, device IDs, rendering commands, arbitrary SVG, or asset bytes are accepted. Named assets resolve through a server-owned allowlist. Quantities include units and domain constraints. Every reveal references a declared object; an arrow cannot appear before its endpoints. All geometry is planned before the first stage, even though it is revealed gradually.

Do not put grid slots, row/column indices, or label positions into LessonSpec. The earlier prototype's network `slot` field has been removed; the compiler derives layout from relationships. The responder supplies semantic grouping, sequence, comparison, and relationship type; the compiler decides placement. Reveal IDs and typed conclusion predicates must be declared by the selected component version, not invented as arbitrary strings by the model.

Keep the initial schema small: at most six main objects, eight relationships, six stages, and short labels. These are authoring limits, not promises that every combination fits the final stroke budget. Bound input bytes, nesting, string lengths, numeric magnitude, and parser work. Reject non-finite numbers and unknown fields. Richness comes from the explanatory structure and well-designed components, not unbounded scene complexity.

The service advertises only implemented component versions. Each component defines its parameters, units, named parts available for reveal, named anchors, conclusion predicates, and optional decorative detail. A typed compiler result contains the existing validated plan plus a small list of diagnostics. Distinguish `unsupported_component`, `invalid_quantity`, `contradictory_claim`, `layout_overflow`, and `native_budget_exceeded`; do not return a generic “reply needs attention” for every case. These codes serve the existing response state and tests, not a new incident system.

### A proposed lever lesson

This is the intended semantic API, not a payload accepted by today's `compile_board` prototype:

```json
{
  "v": 1,
  "mode": "lesson",
  "intent": "Explain why a longer lever arm needs less force",
  "scene": {
    "family": "mechanism",
    "objects": [{
      "id": "lever",
      "component": "lever",
      "arms": {"values": [1, 3], "unit": "m"},
      "forces": {"values": [3, 1], "unit": "N"},
      "assumptions": ["rigid beam", "negligible beam weight", "perpendicular forces"]
    }]
  },
  "steps": [
    {"reveal": ["lever.body", "lever.pivot"], "caption": "The beam turns around its support."},
    {"reveal": ["lever.forces"], "caption": "The force on the left is three times as large."},
    {"reveal": ["lever.arms", "lever.moments"], "caption": "The right arm is three times longer, so the turning effects balance."}
  ],
  "takeaway": "Turning effect is force times perpendicular distance; a longer arm can compensate for a smaller force."
}
```

The component generates lengths, arrows, dimension lines, and units from one shared numeric source. It verifies the balance claim from computed moments. It must not display “balanced” for unequal moments just because a caption says so. General prose cannot be fully verified by arithmetic, so structured conclusion predicates should cover supported component claims.

### A proposed integral lesson

The model asks for a graph component with polynomial coefficients, interval, and partition counts; it does not emit sampled coordinates:

```json
{
  "v": 1,
  "mode": "lesson",
  "intent": "Explain the integral of x squared from zero to one",
  "scene": {
    "family": "quantitative",
    "objects": [{
      "id": "area",
      "component": "riemann_area",
      "polynomial_coefficients_ascending": [0, 0, 1],
      "interval": [0, 1],
      "partitions": [4, 8],
      "sampling": "left",
      "comparison": "nested_refinement"
    }]
  },
  "steps": [
    {"reveal": ["area.axes", "area.curve"], "caption": "We want the area under the curve from zero to one."},
    {"reveal": ["area.coarse"], "caption": "Four left-endpoint rectangles underestimate this increasing curve."},
    {"reveal": ["area.refinement"], "caption": "Splitting each interval adds area and improves the approximation."},
    {"reveal": ["area.exact_value"], "caption": "The definite integral gives the exact area, one third."}
  ],
  "takeaway": "Integration is the limit of increasingly fine area sums."
}
```

Code samples the curve, constructs the rectangles, computes the finite sums and polynomial antiderivative, and produces a structured equation from those same values. A finite drawing illustrates convergence; it does not itself prove the limit. Nested refinement must add only new edges and added strips, not paste a second complete rectangle grid over the first. If this becomes visually cluttered, use one fixed partition and a small aligned comparison inset instead; do not silently change the mathematical claim.

The expressions above are typed data with explicitly implemented evaluators. No `eval`, arbitrary symbolic strings, imported model code, or unrestricted formula interpreter is required.

## Procedural rendering and visual design

### Three reusable layers

1. **Drawing parts:** curves, open contours, arrows, braces, ticks, single-line glyphs, and recognizable asset silhouettes.
2. **Semantic components:** a lever, number line, grouped counters, graph and shaded area, partitioned square, fraction bar, causal chain, cycle, comparison, timeline, and simple physical scene.
3. **Lesson compositions:** introduce → act → explain; compare → isolate difference → conclude; partition → accumulate → generalize. These arrange components and reveal order; they do not contain fixed answers.

A catalog of reusable parts is not a catalog of canned lessons. The agent can combine different parts, quantities, relationships, and captions for unseen questions. Nevertheless, coverage is bounded: a small catalog cannot draw every possible mechanism or character. Unknown subjects get a truthful text answer or an explicitly requested slower illustration path. Record missing capabilities from real questions and add reusable components rather than hard-coding the answer to each failing prompt.

### Style specification

Use dark ink on the ordinary light notebook page. Let native text carry sentences and reserve single-stroke lettering for short labels. Keep outlines open and economical, object silhouettes recognizable, and line weight consistent. Start with the existing original plotter alphabet, not an unreviewed font replacement. A future licensed single-line face can be compared with it on real device samples.

Target a dominant visual anchor with two or three supporting elements, not six equal boxes. A physical explanation should look like a physical scene: a beam resting on a triangular support, sunlight reaching water, or a person observing scattered light. Use a network layout when the subject is genuinely a process or relationship. Do not reduce every noun to a labeled rectangle.

Use 1–3 words for most labels, 12–18 words for most captions, and one visual addition per teaching beat. These are authoring targets, not rigid rules that damage clarity. Establish a visible hierarchy through size, spacing, and selective emphasis. Never depend on color to distinguish information. “Blue” and “red” in a scattering lesson need labels or distinct line patterns on this display.

Avoid random jitter as a shortcut to a hand-drawn look. First establish good proportions and contours. Optional tiny deterministic variation may affect decorative contours, but never plotted data, equal lengths, tick positions, arrow endpoints, or equations. Style transforms must run before the final collision and budget checks. Repeated rendering of the same plan must remain stable.

### Layout algorithm

Plan the complete scene before stage one. Allocate the region below the latest input; within it, choose a composition from the semantic relationships. Use named anchors such as pivot, surface, center, source, and destination rather than bounding-box guesses.

The compiler then constructs quantitative geometry on shared scales, expands assets, reserves label regions using actual glyph extents, routes explanatory connectors, and checks the final cumulative drawing. For each placement, try a small deterministic list of candidate positions. Use an explicit cost function favoring readable labels, short connections, balanced whitespace, and no crossings. Do not create a generic unbounded layout optimizer.

Component ports specify a named point or edge, outward direction, and allowed relationship types. Connecting to a cloud's bounding box is not equivalent to connecting to its visible contour. Define bounds after all transforms. Begin with 20-unit diagram labels and a minimum of 18 units in the 600-by-360 logical scene, while preserving any stricter existing validator limit. Verify the resulting physical size on tablet-scale previews and then the device; logical units alone do not guarantee legibility. Permit intended intersections inside a semantic component, such as a pivot touching its beam, but reject unrelated object overlaps and label/line collisions. Unsupported placement returns a deterministic failure, not a smaller unreadable font or an LLM repair request.

Physical paths and explanatory connectors are different types. A water-cycle arrow can route around a label because it denotes a relationship. A light ray cannot bend around a label without a depicted scattering or refraction event. Label placement must move around physical geometry, not deform the physics. Quantitative components also specify allowed clipping and aspect-ratio rules; a circle or equal-area comparison must not be stretched into a false result.

Never shrink text indefinitely to force a fit. Use a finite sequence: alternative label anchor, alternative supported composition, then reject the visual plan. Omit purely decorative details only when the component declares them optional. Do not drop evidence or silently alter captions. Fall back to validated native text when no safe composition fits.

### Reveal and notebook layout

Reserve one bounded scene above a compact caption stack. Draw only the new strokes for each stage; retain the earlier picture. Append its caption below the scene. End with the equation, when useful, and takeaway. The native label `Agent Pi Dog:` is added by the trusted adapter from actual dispatch identity, not by the model.

Initial delivery uses the existing 3–6 stage boundaries. Later, split a stage into a few semantically meaningful chunks, such as contour → relationship arrow → label, only after device tests show no loss of responsiveness or persistence. Do not imitate video with frame-by-frame refresh, repeated full-scene pastes, a fake drawing hand, or artificial multi-second waits.

The picture and current caption should fit together within the usable viewport when possible. As captions accumulate, follow the newest content only while the user is already following the answer. If James scrolls upward or starts writing, stop automatic view movement and show a small “latest response” affordance rather than fighting him. Changes to ink or destination page continue to hold insertion under the existing guard. Treat view-only movement separately from content changes only where the current native API can prove that distinction.

Append below the lowest occupied input extent using a small measured gap, not a fixed number of blank text lines. The first acceptance test is a populated, partially scrolled page, not a blank page. Preserve the most recent reading position on normal reopen using the native persistence mechanism where supported; otherwise report this as an unmet requirement instead of adding restart tricks.

## Open source reuse

| Project | Recommended use | Boundary |
| --- | --- | --- |
| OpenDoodler | Study scene composition, grouped objects, asset libraries, and ordered stroke reveal | It is a Windows WPF desktop application, not a native notebook renderer. The repository lists AGPL-3.0; treat source reuse as a separate license review before incorporating code. |
| Google Quick, Draw! | Curate a small local library of recognizable vector doodles, keeping stroke order and source metadata | Do not download random sketches at response time or treat the dataset as an answer-generation API. The data is CC BY 4.0; retain attribution and document modifications. |
| Skeleton Tracing | Optional offline centerline extraction for clean monochrome line art | A bitmap does not contain the original object semantics or drawing order; tracing cannot recover the lesson plan. |
| Rough.js | Evaluate restrained sketch styling in desktop prototypes | Not the geometry or teaching engine; extra strokes and hatching consume tablet budgets. |
| Vivus | Optional browser preview of ordered paths | A browser animation is not proof of native tablet rendering. |

Primary sources: [OpenDoodler](https://github.com/Rsverma/OpenDoodler), [Quick, Draw! dataset](https://github.com/googlecreativelab/quickdraw-dataset), [Skeleton Tracing](https://github.com/LingDong-/skeleton-tracing), [Rough.js](https://github.com/rough-stuff/rough), [Vivus](https://github.com/maxwellito/vivus).

Quick, Draw! stores actual stroke vectors; raw records include timing and simplified records provide normalized paths. Its documentation warns that moderation is not a guarantee against inappropriate content. Therefore select and inspect a small asset set offline, simplify within bounds, and attach semantic anchors manually. Begin with perhaps 20–30 useful objects, chosen for the evaluation set and everyday explanations, rather than a large uncurated library. Give each asset a source record, attribution, version, recognition review, native stroke cost, and permitted transformations. Do not transmit dataset user metadata with notebook answers. [Dataset format and limitations](https://github.com/googlecreativelab/quickdraw-dataset)

InstaDoodle, Golpo, and James's preferred second video are style references, not assumed open-source dependencies. The intended qualities are purposeful staging, recognizable doodles, and concise explanatory narration translated into captions. This design does not claim a frame-by-frame analysis of those videos. Dennis's existing [tool research](../../../../RESEARCH/REMARKABLE_STROKE_ANIMATION_TOOLS.md) remains useful for optional import/export tools; none is required on the interactive path.

### Novel drawings and photos

A doodle lesson and a generated standalone picture are distinct products. A dog component can support explanations about dogs, but a curated dog asset must never be presented as a newly generated custom dog image. For an explicit creative image request, use an authorized image-generation workflow; preserve the raster result when that is what James asked for. Converting a generated line-art image into pen strokes is an optional slower branch, with a preview and no promise of original stroke order.

An imported photo remains a photo. The service receives bytes through the authorized capture/upload path, verifies the media, and inserts it into the same request-bound native media route. It should not require the responder to write local paths into a lesson or ask another agent in Buzz to complete every ordinary notebook interaction. Unsupported camera access must be reported, not claimed.

## Validation and safe delivery

Retain the current full-plan validator, native ink encoder, and page-change guard. The existing limits are **64 strokes, 3,000 points, and 30 seconds estimated pen time per stage**, plus **12,000 points per lesson**. The 30-second value is a safety ceiling, not the desired animation length. Use substantially smaller normal scenes and measure actual paste/reveal times.

Validation has separate outcomes:

1. **Schema:** valid bounded data, known capabilities, valid IDs and dependencies.
2. **Meaning:** unit consistency and supported numerical predicates; no impossible component parameters.
3. **Geometry:** complete cumulative scene in bounds, labels legible and clear, arrows attached appropriately, scales preserved.
4. **Native preparation:** the actual encoder accepts every stage and all assets are ready before insertion.
5. **Delivery:** the original request is current, destination unchanged, and existing native insertion guards hold.
6. **Observed result:** visible response, correct position, original ink preserved, and persistence after reopening.

A compiler pass is not a teaching-quality verdict. An insertion acknowledgment is not visual proof. Keep these distinctions in the reports without creating another lease, audit, or approval framework.

### Request behavior

Use the existing request identity and journal. The intended state sequence is capture → thinking → validated → inserting → complete, with held, failed, or expired exits. Map it onto existing states instead of creating a parallel lifecycle.

| Situation | Required behavior |
| --- | --- |
| Double Respond or duplicate completion | Do not insert the same answer twice; consult the existing request state |
| Page or relevant content changes | Hold the answer; no redirect to whatever page happens to be open |
| Partial JSON, refusal, timeout, invalid scene | No ink insertion; show a concise truthful status or validated text answer |
| Agent returns unsupported objects | Use the provided safe fallback or state the capability gap; no invented assets |
| Connection lost after a possible write | Inspect existing completion evidence before retrying; do not blindly replay |
| A later stage fails after earlier stages appear | Preserve the inserted material, mark the lesson incomplete, and hold; no erasing James's page to roll back |
| User retries | Create or resume only through the explicit existing retry behavior; do not resurrect expired work silently |

When a scene fails a semantic check, do not reuse its unverified conclusion as the fallback. A geometry-only failure may allow the independently valid textual explanation. If there is no trustworthy answer, the status must say that the answer could not be completed, not pretend the failure banner is a response.

Prevalidate the entire lesson before committing the first lesson stroke. This intentionally rejects streaming unvalidated geometry for a lower first-pixel number. A small full plan should make that affordable. A local “thinking” indicator can appear immediately but does not count toward substantive-response latency. Later streaming requires a separate design that preserves global layout and claim consistency; it is not necessary for this phase.

## Latency design and measurement

The first target is fewer serial transitions, not faster coordinate reasoning. One self-contained request and one compact answer remove preview execution, repeated image inspection of the generated result, model repair turns, and Buzz handoffs. This is consistent with official latency guidance to reduce generated tokens and requests and use conventional code for deterministic work. [Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization)

Proposed normal-path allocation, to validate rather than advertise as achieved:

| Segment | Budget |
| --- | ---: |
| Capture, package, and dispatch | 1.0 s |
| Pi-Dog reading and complete semantic response | 5.5 s |
| Compile, validate, native-encode | 0.2 s |
| Transfer, native preparation, first meaningful visible stage | 2.0 s |
| Scheduling and observation margin | 0.8 s |
| Total target | 9.5 s |

Run an end-to-end monotonic clock where possible. Do not subtract unsynchronized tablet and Mac clocks. Record tap/receipt, capture ready, dispatch, model first token if exposed, final plan, compilation done, native start, first substantive visible frame, final stage, and save acknowledgment. Screen sampling gives an interval for visibility; report that interval rather than false millisecond precision.

Report per-test timing, failures, median, p90, and maximum. Distinguish first caption, first diagram, complete lesson, and persistence. A cached plan or canned fixture is not a live model latency measurement. A timeout or text fallback remains in the denominator. Use the 20-second deadline as an initial bound for the fast route; expiration produces an honest status, never an automatic duplicate attempt. Deep or media requests need separately reported latency classes.

Cache immutable assets, fonts, and compiled geometry by renderer version and plan digest. Do not reuse an old answer merely because a question image looks similar. Prefetching local renderer resources is useful; keeping an agent awake with messages is not a substitute for a responsive request service.

## Development and evaluation method

### Combined native playback preview — 2026-10-28

`native_lesson_preview` now consumes the resolved native bundle rather than
reconstructing an image-only equation. It verifies every playback descriptor
against its source bytes, applies the combined ink budget, keeps one growing
picture on top, and sequences caption characters, final equation ink and the
takeaway in block order. It uses 40 ms planned text units; a regression compares
its conservative Unicode grouping directly against `herdTypingUnits` in QMD.
Native editor acknowledgement, page placement and save delays are NOT simulated.
The evaluator prefers this player for semantic replies while retaining static
previews and separate preparation errors. No new model or tablet calls.

Artifacts: `OUTBOX/native-lesson-preview-20261028/fraction-fixture.html` and
`comparison.html`. The comparison replays unchanged count-grid-v5 answers and
retains their original quality reviews and self-reported comparator provenance.
The current renderer prepares six PiDog and five comparator visual lessons;
that is compiler acceptance, not a new teaching-quality pass. In particular,
the newly drawable PiDog water-cycle answer retains its earlier content review.
No interpretation or answer was repaired in this replay. Existing experimental
particles/drop worktree edits remain separate and are not deployed by this work.

Browser-only evidence: `OUTBOX/browser-native-lesson-Abxrr1/` contains partial
caption, partial equation, final screenshots and computed-style assertions.
At 220 ms into the first caption, only “Start” is visible; at 200 ms into math,
the first stroke is partial and later strokes remain hidden. Full completion
and checkbox reset passed. The initial browser assertion sampled exactly on
a 1 ms visibility transition and was replaced with a settled, between-tick
sample; no production timing was changed. The fraction fixture plans 24.51 s
of strokes and 40.47 s including text, not end-to-end latency. 469 Python tests
pass. Physical tablet testing of the new text/math behavior is still pending.

### Draw-order preview, 2026-10-28

The existing side-by-side evaluator now also embeds an optional **Draw lesson**
player for every accepted visual answer. `notebook_playback_preview.py` decodes
the same native assets as tablet playback, preserves path order/corners/pen
lifts, and uses the same 240 local units/second, 70 ms pen-up gaps and minimum
stroke duration. Captions appear after their stage; the equation and takeaway
follow the picture. The page uses bounded SVG/CSS with no script, network or
model calls; unchecking resets playback, and reduced-motion preferences show
the completed picture instead. Static cumulative previews remain available.

This previews **planned motion**, not observed device speed: model, network,
native insertion and save delays are excluded. A failed playback preparation
is reported independently of a valid static picture. The player does not
establish that the physical e-ink panel updates smoothly, or that lesson prose
is correct. SVG dash animation and CSS fill behavior follow the
[SVG painting specification](https://www.w3.org/TR/SVG2/painting.html#StrokeDasharrayProperty)
and [CSS Animations specification](https://www.w3.org/TR/css-animations-1/#animation-fill-mode),
not a new tablet rendering path.

`OUTBOX/notebook-draw-order-preview-20261028-final/comparison.html` replays the
unchanged count-grid-v5 answers, with the original quality reviews/provenance.
Both saved sets contain five drawable lessons out of ten questions. The
comparator's model identity/isolation remains self-reported; this is not a new
controlled model run. In particular, prior content failures and missing visual
answers remain failures. The experimental evdev motion-program budget and
current Canvas playback preparation are different checks, explicitly identified
in the report rather than conflated. No live configuration changed.

Offline regression: 449 Python tests pass. A fresh-profile headless Chrome check
confirmed a partially drawn first line at 1000 ms with later shapes hidden,
completion/caption visibility at 8000 ms, and reset. Browser screenshots and
computed-style assertions are evidence of browser playback only; they do not
replace James's pending physical-tablet verdict.

### Separate the three loops

**Renderer loop:** milliseconds to seconds, no model, no tablet. Fixed semantic inputs, variant parameters, property tests, and stage previews. Fix geometry and aesthetics here.

**Responder loop:** bounded offline model runs. The same question images, capability schema, and prompt go through Pi-Dog and one comparator. Save the first raw plan, compile it without assisted edits, and review stage previews side by side. Fix interpretation, teaching structure, and capability selection here.

**Device loop:** a reviewed candidate and a small scripted test session. Test actual native placement, scrolling, interrupted delivery, refresh, and reopen. Do not use the tablet to discover ordinary JSON, arithmetic, or label-layout bugs.

### First evaluation set

Keep ten fixed questions, with James's additions and a held-out variant set:

1. Riemann rectangles for the integral of x squared from zero to one.
2. Why successive odd numbers build a square.
3. A lever with changed forces and arm lengths.
4. Why the sky is blue, using a physical scattering scene rather than misleading routed rays.
5. Evaporation, condensation, and rain in a water cycle.
6. Compound growth compared with linear growth on shared scales.
7. Bayes' rule using counts in a population grid with explicit denominators.
8. A transistor as a switch, with the model and simplifications stated.
9. Recognition and explanation of an actual handwritten dog sketch.
10. A non-mathematical causal explanation, such as how a seed becomes a plant.

For each: a golden semantic fixture tests the renderer separately; an image-based first-pass model run tests the responder; and a changed-number or changed-wording variant tests generalization. Include illegible input, contradictory quantities, unsupported objects, long labels, unusual glyphs, malformed output, refusal, and output truncation. The generated dog picture and imported photo are additional media acceptance tests, not substitutions for the ten-question lesson comparison.

Publish capability coverage alongside quality. A correct text fallback on an unsupported question is a safe outcome but not a visual-lesson pass. Slice 1 may cover only a subset of the suite; do not mark the full ten-question comparison complete until its required components exist. Preserve held-out variants so a prompt or asset added after a failure is tested on more than that same example.

### Quality rubric

Score each dimension 0–2, with human review of every stage and the final scene:

| Dimension | A score of 2 requires |
| --- | --- |
| Correctness | Claims, quantities, and diagram agree; assumptions and approximations are explicit |
| Visual explanation | The picture shows why, rather than decorating the caption |
| Staging | Each reveal adds a meaningful fact; earlier facts remain readable |
| Composition | Recognizable subjects, useful hierarchy, balanced space, attached labels |
| Legibility | Comfortable tablet-scale text and symbols; no collisions or tiny details |
| Relevance | The answer addresses the actual handwriting, not an example it remembered |

Initial release gate: no zero in any dimension, at least 10/12 overall, and full correctness for every accepted core example. Report visual failures separately from compiler rejection. Human judgment remains necessary: geometry tests cannot establish beauty or scientific truth. Ask James to select between a small set of finished style samples before investing in a large asset catalog.

Also record recognizability separately from explanatory contribution: can a reviewer identify the central object without reading its label, and does that object's depiction explain the claimed relationship? An attractive icon can pass the former and fail the latter. Neither may be hidden inside an aggregate aesthetic score.

### Device acceptance

After the offline gate, test ten consecutive exchanges on the isolated notebook, explicitly separating fresh human handwriting from replayed test inputs. Verify placement below input, actual agent label, no notebook close, no duplication/overlap/raw markup/stale banners, and per-test visible latency. Exercise long captions, a full page, a partially scrolled page, user writing during generation, page switching, and one interrupted connection. Reopen normally and verify content and view behavior. Then promote to one additional “To DJ Codex” notebook before any broader rollout.

Maintain a small evidence index linking the raw question, raw first response, compiled preview, versions, timings, and device observations. Reuse current reports; do not build a new monitoring platform to run this suite.

Keep handwriting and notebook context in the existing local data boundary and authorized model path. Review packages should contain the selected test evidence, not whole private notebooks or agent transcripts. Do not silently publish screenshots with a PR, expand retention, or add automatic deletion of user artifacts. Use synthetic fixtures for portable repository tests.

## Implementation sequence and exit criteria

| Slice | Deliverable | Exit criterion |
| --- | --- | --- |
| 1. Contract and fixtures | Versioned semantic schema; lever, integral, odd-square, and object-scene fixtures | Parameter variants work; examples cannot drift from the schema; no model or device needed |
| 2. Visual foundation | Anchored doodle assets, consistent lettering, composition and label placement | A physical scene, a quantitative construction, and an organic/causal scene, each with changed-parameter/wording variants and tablet-scale stage previews; recognizability and explanatory contribution both pass |
| 3. Pi-Dog response profile | Supported request-bound invocation with actual image input, isolated context, and enforced tool limits; measured model/settings selection | Context-sentinel, prohibited-tool, image-input, and request-binding checks pass before production use; first-pass two-responder comparison passes the offline rubric |
| 4. Native adapter integration | Semantic plan feeds the existing compiled/native path behind the current rollout control | Regression tests pass; no second writer or permission expansion; independent review |
| 5. Device acceptance | Populated-page and interruption tests with timing and reopen evidence | Original workflow acceptance met; failures remain visible in the report |
| 6. Controlled expansion | One extra notebook, then eligible notebooks; explicit legacy retirement | Native coverage proved for text, equations, ink, and media before removing old paths |

For each slice, commit a small logical change, request a bounded review, and show an artifact. Do not batch another day of changes across runtime and worktree copies. Runtime promotion must state the exact revision and files; avoid assuming launchd runs the development checkout. Do not deploy partial semantic support while advertising the full vocabulary to Pi-Dog.

DJ Codex owns the schema, compiler, previews, tests, and integration. Pi-Dog supplies a bounded responder implementation and first-pass answers, not renderer development. MyDude owns independent review and coordination of harness changes. James supplies aesthetic feedback and any required permission decisions. Normal local implementation does not wait for repeated permission requests.

### Existing code to reuse

- `notebook_procedural.py`: early semantic-to-geometry prototype; extend after hardening finite placement, ports, validation, and contract tests. Its current `network` and `lever` formats are not the final LessonSpec.
- `notebook_lesson.py`: low-level parsing and geometry validation; keep it as the internal boundary.
- `notebook_drawing.py`: compilation, budgets, and `preview_svg`.
- `notebook_shapes.py` and `notebook_plotter_font.py`: deterministic geometry and original single-line lettering.
- `notebook_stroke_asset.py`: real native ink encoding.
- `notebook_lesson_native.py`: shared scene, ordered captions, native source preparation. Add an entry point for a validated semantic compilation; do not stringify it back into a model reply just to parse it again.
- `notebook_lesson_prompt.py`: replace the fast-route coordinate instructions with the semantic contract; retain old examples only where their supported route needs them.
- `notebook_lesson_eval.py`: raw-response capture and comparable previews; extend it rather than build a competing evaluator.
- `herd-board-serve` and `xochitl/herdRespond.qmd`: retain capture, identity, rollout, native insertion, and existing guards. Change only the adapter boundary initially.

The legacy `compose`/`write_answer` SVG path is not the home for the new engine. Retire it only after native text, equations, ink, images, failure handling, and reopen behavior are covered. Do not remove a working fallback merely to make the architecture diagram simpler.

## Coordination without interrupting development

Keep Nvoy out of the notebook critical path and out of Pi-Dog's notebook response context. Ordinary answers require no diagnostic group post, external reviewer, or acknowledgment. Development reviews should be batched around an actual artifact, with a specific question and a terminal answer.

A separate inbox handler is a useful harness-level proposal: read each admitted envelope once, preserve broker authority and reply binding, classify information versus work, handle routine messages, and escalate only actionable changes or blockers to the main development context. It must not bypass grants, silently discard tasks, or execute ambiguous requests. A subagent inside this conversation cannot prevent already-delivered envelope markers from entering it. MyDude owns evaluating routing support; James owns any grant changes. This is not a prerequisite for building the renderer offline.

During sustained work, report artifact-based progress at least every ten minutes as requested, and promptly when a real blocker appears. Say what changed, what was tested, what can be seen, and what remains. Do not substitute “still working” or repeated status pings for demonstrable progress. A bounded keepawake mechanism may support an active device session; verify it rather than assuming it persists overnight.

## Decisions deferred until evidence is available

- Exact model identifier and reasoning setting: resolve from the serving configuration, then compare quality and latency. Pi-Dog's self-report alone is insufficient.
- True tool-limited notebook execution: review the existing harness capability and enforce the boundary before claiming it; grant changes need James.
- Doodle asset source and final lettering: compare a few curated samples, confirm licensing, then scale the library.
- Chunked native reveal and scroll-follow behavior: test on the device after the semantic route works; do not redesign insertion speculatively.
- Arbitrary illustration coverage: add an explicit slower branch only when requested; do not pretend a small renderer can synthesize every scene.
- Whole-lesson versus partial streaming: begin with a fully validated compact plan; revisit only if measured latency still requires it.

The next implementation milestone is a visually convincing, parameterized lesson produced from a compact first-pass semantic answer, shown in offline stages before it is tried on the tablet. That milestone is smaller than the full goal, but it tests the architecture that the full goal needs.

## Review status

MyDude reviewed the design on 2026-10-27 and supported the single-plan/compiler/native-adapter split, with three corrections: prove notebook execution isolation rather than naming a profile; remove even coarse layout slots from the model contract; and require physical, quantitative, and organic/causal variety in the offline gate. Those corrections are incorporated above. This is a reviewed design direction, not approval of an implemented profile, runtime deployment, or completed acceptance tests.

### First offline implementation

`notebook_semantic.py` implements a strict v1 subset, with actual accepted examples in `notebook_semantic_examples.py`. The illustrative JSON earlier in this design is not the complete implemented schema: the subset requires explicit typed `claims`, uses the advertised component part names, and does not yet support every proposed mode or component parameter. There is no live prompt or server integration.

The subset supports a parameterized lever, left Riemann sums for increasing nonnegative-coefficient polynomials on nonnegative intervals, and causal networks built from six simple object motifs. It computes shared scales and exact polynomial areas, rejects contradictory or missing required component claims, and routes process connections from explicit contour ports. It does not verify unrestricted captions or takeaways. Labels use a fixed 18-unit size in the current prototype, the proposed lower bound; tablet legibility still requires device testing.

Six synthetic fixtures cover two lever configurations, two polynomial/interval/partition configurations, and a water-cycle wording variant. Twenty additional polynomial/partition combinations pass native encoding tests. These establish parameterized compilation, not aesthetic acceptance, arbitrary-domain coverage, or first-pass model quality. The organic contour/curved-route update in `8bd3e00` improves the water-cycle picture; the broader component vocabulary remains unfinished.

Generate a new offline review directory with:

```sh
python3.11 notebook_procedural_demo.py NEW_OUTPUT_DIRECTORY --semantic
```

This generates cumulative SVG/PNG previews, input JSON, equations, and timing metadata. It refuses an existing output directory. No tablet operations occur. MyDude reviewed the initial implementation and found the optional-claims loophole; the compiler now requires the relevant numeric conclusion predicates, with a regression test for the exact omitted-claim case.

### Attended native motion experiment

James praised the first slow line and requested working primitives before timing polish. The intended later timing rule is one chosen screen-space pen velocity, with each stroke's motion duration derived from its arc length. This is not yet a production reply feature.

`tablet_live.draw_paths(duration=...)` apportions a bounded target motion duration by cumulative arc length using monotonic deadlines. It retains every guard and point, and always releases the pen on failure. `notebook_pen_motion.motion_chunks` partitions a logical path into short contacts, preserving exact shared endpoints and every original corner. Pen lifts, transport and fresh-context waits add to the target duration. These helpers do not provide an atomic navigation/input lock and are not connected to the reply adapter.

The first attended 2.5-second line stopped partway when the fresh/active/page check failed; its partial ink was preserved without replay. The exact failing snapshot was not retained, so stale telemetry is a hypothesis, not a proven cause. A second diagnostic used at most 0.65 seconds per contact, required recent telemetry before contact and exactly one ink completion afterward, and recorded failure snapshots. On a new blank isolated page, line, cubic curve, circle and arrow completed: 20 native contacts, no automatic retries, no close/restart during drawing. Individual paths took 3.287–3.603 seconds including checks; the arrow has separate shaft/head paths. This is direct renderer evidence, not Respond latency or model integration.

Visual inspection and saved geometry still show native distortion: a nominal radius-140 circle has saved radii 138.841–146.542, and adjacent quarter-circle endpoints differ by about 5 pixels despite exact input joins. Native processing is changing the supplied path; the cause and remedy require a focused test. Do not label primitive fidelity finished or hide this with random jitter. Next: investigate endpoint settling and curve fidelity, then integrate paced reveal only with the native page/input protection already required above. Constant velocity across different paths follows primitive correctness.

Two subsequent paired diagnostics narrowed this down. Slowing the final 15% of each contact did not improve geometry: control/taper circle radial errors were 6.528/6.559 px, with effectively identical line endpoints. That optional timing code was removed, not promoted. Increasing sampling from 201 to 801 points at the original pacing reduced circle maximum radial error from 6.528 to 0.567 px and joins from approximately 5.1 to 1.1 px; line endpoint error fell from approximately 2.74 to 0.70 px. The denser circle took 3.717 s versus 3.526 s for control, including checks. These are single paired tests at different screen positions, not a general device calibration or proof of an internal smoothing algorithm.

The resulting pure `sample_motion_path` helper adds interpolated samples at a maximum screen-space interval (default 1.25 px), preserves original vertices/corners, and rejects expansion past 3,000 points. It changes neither the geometric polyline nor the requested duration. This helper has offline tests; the live comparison used independently generated dense fixtures, so full compiler-to-sampler-to-device fidelity remains to be tested. Keep resampling in the procedural renderer, not in model output. Do not multiply the model's coordinate/token workload or silently relax whole-lesson limits. Protected lesson insertion and request-bound model integration remain open.

James also requested using native pen types and tips for different brush effects. After geometry/pacing correctness, test a small intentional style palette: fine diagram/label lines, heavier emphasis, and restrained soft shading. The renderer should own concrete native tool/width/pressure choices; a model may request a supported semantic role, not arbitrary device settings. Verify actual tool support, legibility, saved appearance and restoration of James's selected pen before integrating. The current attended input helper uses the already-selected native pen and fixed contact pressure; it does not yet implement automatic style switching.

The exact committed sampler subsequently passed an attended live test of line, cubic curve, circle, and arrow: 2,851 sampled input points, 20 contacts, 3.402–3.580 s per logical path including checks. Saved circle maximum radial error was 0.552 px; cubic joins were at most 1.502 px. All shapes survived normal post-test reopening, and all 17 earlier page files were byte-identical. This closes the sampler-specific live/save check for those primitives, not automatic reply integration or arbitrary geometry. The native palette was inspected without changing it: Fineliner, Medium, Black were selected, with three width choices and other pen types available. Brush rendering/style restoration tests remain open.

`notebook_motion_program.compile_motion_program` now connects an entire validated storyboard to sampled motion without device I/O. It preserves caption/equation/annotation order, gives strokes a distinct `motion_stroke` operation, and derives duration from path length and a renderer-owned speed (default 240 local units/s, 0.1 s minimum for short strokes). It counts expanded contact points and contacts against the existing 3,000-point/64-stroke/30-second per-stage and 12,000-point whole-lesson limits before returning anything. Six semantic fixtures compile, including tiny plotter-font dot strokes. These are offline planning results; actual telemetry/transport time and a scene-to-display mapping still belong to the future adapter. Do not treat the planning estimate as measured response latency.

Installed QML and binary metadata expose `controller.addDrawingLine(Line)` and guarded whole-item cloning, but the inspected resources do not demonstrate a scene-owned constructor or point-injection API for `Line`. MyDude independently reached the same search-scoped finding. The present paste lock deliberately disconnects `PenInputSurface.handler` and selects `SelectionTool`; paced evdev cannot be inserted into that locked path unchanged. Keep the working locked clone/paste route for actual replies until a native incremental builder is demonstrated. This is not proof that XOVI cannot expose such a builder, and is not permission to re-enable physical pen input during automated drawing.

### Compact responder integration: offline preparation

`notebook_semantic_reply.parse_semantic_reply` accepts one complete bounded JSON object: the existing v1 semantic lesson, or strict `answer`/`clarify` objects containing only `v`, `mode`, and plain `text`. Invalid lessons remain errors; their captions/takeaway are never reused as an unverified fallback. Unsupported media requests are rejected, not treated as completed image generation. `native_semantic_bundle` and `prepare_semantic_reply` pass validated geometry directly to the existing native source/ordered-block preparation. They do not stringify thousands of drawing coordinates into a reply and parse them again. The existing board-step route shares the same private preparation helper and remains unchanged in production.

`notebook_semantic_prompt` advertises only the implemented lever, polynomial-area, odd-square growth, and bounded causal-object vocabulary. Its two accepted grammar examples come directly from tested semantic fixtures (integral and odd-squares). Clarification and plain answers are deliberate modes, not visual-lesson acceptance passes. No global Pi-Dog settings, tool permissions, live prompt, or transport changed. Prompt instructions to avoid tools do not enforce isolation. Provider structured-output configuration is also not enabled by these local changes; server validation remains necessary, including correctness checks beyond schema shape. The prompt/fixture consistency tests guard against grammar drift, following the distinction between output guidance and configured schema enforcement in the [official structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs).

### Bounded layout and odd-square growth update

Process labels now use measured word wrapping at unchanged size18, finite route-normal candidates and constrained-first joint placement (4096 attempts maximum), with at most two complete layouts. Original first-pass MC Claude water-cycle output now renders without changing words or requesting a model repair; PiDog's incorrect causal labeling remains a quality failure. This is layout evidence, not a new model benchmark.

The offline `odd_square_growth` component takes only an integer layer count3..6. It reuses the existing square-growth motif, reveals each L border once, alternates hatching, computes the numeric equation and checks required `odd_border_growth`/`final_area` claims. Contiguous new grid edges are joined within each layer to avoid unnecessary pen lifts; old edges are never redrawn. Tests expand those joined paths back into exact unit edges and verify the complete k-by-k cell set at every step. Same-step parts must also respect dependency order. Every supported size passes native asset encoding and the expanded motion budgets. Captions still need semantic review; the compiler does not prove arbitrary prose.

Previews: `OUTBOX/odd-square-growth-20261027-v2/index.html` (developer-authored quantity variants, not PiDog results). Four-layer stages and six-layer final image inspected; additional sizes tested structurally. Source changes are offline pending review; no claim of protected automatic animation or live Respond latency.

### Request-bound semantic delivery adapter (offline server integration)

`start_notebook_job(job, response_format='semantic-v1')` pins the response protocol in the existing pending job's delivery metadata before dispatch. This is an internal service entry point, not a new HTTP selector, environment switch, model-selected field, or enabled production call site. The existing `respond()` still uses its original prompt/shared-pane transport. A future reviewed image-first transport must use the returned canonical job and retain its request identity; this implementation alone supplies neither isolation nor image attachment.

`native_text()` validates semantic replies before any capture, import or device operation. Lessons use the existing immutable source import, shared diagram origin, ordered captions/equation, page/input checks, native claim and saved-ink proof. Answer/clarify modes produce plain native text blocks, without parsing their text as legacy media/ink markup. Format is preserved when equation assets are added and through backend recovery or explicit invalid-answer correction. Unknown delivery metadata, format rebinding, expired/changed semantic jobs and raw-format mismatches fail closed. Invalid payloads remain held for diagnosis; they are never salvaged as prose. An operator's existing digest-bound repair may replace an invalid semantic payload with a completely validated response, held until explicit retry.

No new lease, journal or audit store: the delivery field already carried revision holds. Old pending jobs without a format keep their old contract. Semantic jobs cannot reach the old file writer, even if durable pending state is missing. A failed pending-file write must not clear an earlier response or publish a new in-memory job. These are mocked-device server tests, not evidence that the transport or tablet integration has run live.

PiDog's read-only report (Nvoy envelope8ff02caf…, 2026-10-27) identifies `REPOS/nvoy-pi-harness/docs/RUNTIME_SUPERVISOR.md` and `mcp/tools/pi-harness.mjs` as the fixed-session runtime documentation/entry point. Independent read-only inspection of that Pi documentation and the launch/configuration fields confirms the fixed session and absence of per-request image/session/tool selectors there. This is not a claim about every underlying SDK API. No harness settings or grants were changed. Do not create another Nvoy consumer under that identity or bypass the fixed-session contract to enable this adapter; coordinate a supported transport extension before production rollout.

The existing offline evaluator accepts `prepare NEW_DIRECTORY --semantic`, preserving the same ten fixed questions and original raw answers. It reports semantic mode, raw response bytes and local compile/native-encode milliseconds, renders cumulative previews, and labels accepted text separately from visual lessons in side-by-side comparisons. Those milliseconds exclude model, network, image reading, and tablet latency. First-pass model results and visual quality must be reviewed separately from fixture/unit-test success. No automatic model revision loop is introduced.

### Protected chunk reveal (worktree, not deployed)

`native_semantic_bundle(..., reveal=True)` and `prepare_semantic_reply(..., reveal=True)` explicitly opt into up to four ordered native pieces per stage. The server selects this preparation only for request-bound semantic lessons from a client advertising integer `reveal_version: 1`; the import callback must retain that capability. Old clients receive ordinary source pages, never atlas geometry. Normal production Respond still does not opt into semantic jobs, and none of this revision is deployed. `notebook_ink_reveal` splits the existing ordered polylines by cumulative distance, preserves corners and pen lifts, and encodes the pieces in separate rows of the same immutable source page. Only shared boundary points are duplicated, never a nonzero edge. Additional points and strokes count against the existing limits; near-limit plans can be refused rather than coarsened or silently pasted whole.

The native client selects one row, clones it, and translates its bounding-box centre back into the shared diagram region. Later rows reuse the same stage claim and keep the actual native input lock held. There is one final stage acknowledgement, then its caption. Page/input/view changes stop before the next dispatch; no automatic replay or extra durable claim layer is added. The source integrity preflight and saved-ink proof both validate the row mapping. Persistence requires every piece at a common destination translation, not the atlas's separated source positions.

This is **coarse progressive native reveal**, not the smooth evdev demonstration or a verified native point-append API. Four chunks are a bounded first adapter, not a claimed aesthetic target or timing result. The native selection of off-page atlas rows, clone placement, actual visual cadence, preservation and reopen still require an isolated tablet test after review. All current evidence is offline Python/native-client mock testing. The read-only binary inspection found `beginStroke` beside `ToolMenuGesture`, and `Line` metadata with length/tool/count/bounds, but no demonstrated QML constructor/append operation; calling those symbols speculatively would not establish safe gradual drawing.

### Deterministic tablet fixture path (not deployed)

The existing local-authenticated `/notebook-test` endpoint also accepts `fixture` alongside exact `doc` and `page` UUIDs. The value names an existing developer-authored semantic example, not arbitrary response text, files, model settings or code. It is restricted to the enabled `To pidog` notebook inside `Storyboard tests (Codex)`, with fresh active telemetry and no pending job/test. This remains the existing single in-memory 30-second arm, not a new queue, lease or audit layer.

The next live Respond on that exact page consumes the arm once, captures the actual page, and rechecks page/surface/view/ink/content state before starting a normal request-bound semantic job. It holds the fixed response through the existing native import, blank-region check, placement and saved-content proof. It never calls OCR, dispatches an agent or starts an answer-wait worker. A fixture that expires or changes cannot silently become a model request. Normal requests retain their existing route; no PiDog profile is enabled by this test capability.

Fixture output is labelled `Agent Renderer Test:`. The flag is stored in the existing pending delivery metadata so restarting the backend cannot misattribute it to PiDog. The response reports `renderer_fixture`, and timing records `fixture_ready` rather than model `submitted`. Measure Respond-to-visible time here as **renderer-only latency**, never end-to-end agent latency or a model-quality pass. The route is not granted to the tablet credential; only the existing local operator credential may arm it. Named fixture execution is an explicit test, not automatic recovery of a failed real reply.

After reviewed deployment, arm with the existing client helper using a JSON body such as `{"doc":"<isolated-notebook-uuid>","page":"<fresh-test-page-uuid>","fixture":"integral"}`, then invoke the normal Respond button within 30 seconds. Use a new isolated test page with a clearly identified diagnostic input, preserve earlier page bytes, and capture every reveal transition and the final normal reopen. Do not describe these developer-authored tests as new handwritten exchanges with PiDog. This paragraph describes the original pre-deployment checkpoint; subsequent live evidence is below.

### Live renderer checkpoint and isolated model transport — 2026-10-28

QMD d233733 ran the integral08 fixture on the actual tablet: first label sampled
at 4.825 s, first ink at 7.439 s, final save acknowledgement at 44.143 s. Stable
native image geometry allowed the takeaway 0.867 s after the equation request,
versus 10.413 s in the preceding diagnostic run. This is one controlled pair,
not a latency distribution. All 65 inserted strokes matched their source;
all 24 older pages were byte-identical before and after normal reopen. The
complete new page also retained its hash. Full evidence lives in
`OUTBOX/native-reveal-integral-08-*` and the phase tracker. No model was called.
The protected reveal is still coarse chunks, not the smooth evdev demonstration.

The new transport has three opt-in parts, none enabled by importing them:

- `notebook_pi_responder.mjs`: direct `modelRegistry.streamSimple` inside the
  existing Pi process, with its configured OAuth/image-capable model. Every call
  gets the fixed lesson prompt, one user message with actual PNG bytes, no prior
  transcript, no tools, minimal requested reasoning and no automatic retry.
- `notebook_pi_socket.mjs`: one JSON-line request per owner-only Unix connection.
  The parent must already be owned by the current UID and mode 0700; the socket
  is 0600. Existing endpoints are refused, never taken over at startup. This
  authenticates the OS user, not individual processes of that same user. No
  network listener, new secret, second Nvoy consumer or separate Pi session.
- `notebook_model_transport.py`: full PNG decoding, exact request binding,
  bounded result validation and the existing complete semantic compiler before
  the answer can be published. Its cancellation callback must inspect the
  existing pending request/page; the caller must recheck under that lock before
  publishing. It does not write the tablet or own a second pending-job store.

Host integration must create the responder/socket from the current `ctx` at
`session_start`, and close it on `session_shutdown` or session replacement.
The fixed system prompt is generated from `semantic_reply_instructions()` by
the deployment owner, not supplied by a notebook request. Select the configured
model from the host registry, never from IPC input. Do not use
`sendUserMessage`, expose chat tools, read credentials into herd-board, or start
another Nvoy consumer. Host installation is coordinated with the Pi harness
owner; this repository's tests do not establish that it is installed.

Bounds: 3 MB PNG, four million pixels, 12 KB question context, 24 KB output,
30 s maximum deadline, one in-flight provider call. Disconnect/shutdown aborts
the request. If a provider ignores cancellation, the busy slot stays occupied
until that provider actually terminates. The SDK receives `maxTokens: 2400`,
but the inspected installed Codex provider does not serialize a hard output
token cap; do not describe this as a guaranteed token ceiling. Deadline and
byte limits are enforced independently. Provider diagnostics and reasoning
content are not returned; only bounded timings and whitelisted usage counts.

Offline evidence: 339 Python tests, all native JavaScript scripts and 15 new
Node tests pass. A real Python-to-Node Unix roundtrip sends PNG bytes through
the actual adapter and validates an integral lesson with the actual compiler;
only the model registry/provider is fake. This proves framing and isolation
against that test double, not live provider latency, vision quality or teaching
quality. Production Respond still uses the shared-pane route at this checkpoint.
The next gate is host integration plus a real image-first model result, then
the isolated tablet, additional notebook and broader rollout.

### Opt-in Respond connection (implemented, not deployed)

The existing operator-owned `.notebook-lessons.json` may now contain
`model_transport: {"agent":"pidog","socket":"/absolute/private/pi.sock","deadline_ms":15000}`
alongside `notebooks` and `draft_check`. The example path is illustrative, not
an installed endpoint. Only a live request to an explicitly enabled notebook
whose freshly resolved agent name is `pidog` takes this route. Missing settings
retain the existing route; a selected but unavailable endpoint fails without
falling back to shared chat. No HTTP request or model result can select it.

Respond snapshots existing native page/view/input telemetry before capture,
rechecks it afterward, pins `model_transport: pi-socket-v1` plus `semantic-v1`
in the existing pending job, and starts one image-first worker. The worker
cancels when that job is superseded or page/input telemetry changes. A final
locked recheck and full semantic parse precede `notebook_reply`. Existing
native placement, import and saved-content checks remain responsible for all
tablet writes. A model failure holds the pending request and exposes a bounded
error, never a hidden retry. Prepared media tests and named renderer fixtures
cannot accidentally enter the model path.

Restart recovery can restore a completed validated response. An interrupted
call with no completed response is held as failed; it is neither redispatched
nor looked up in PiDog's chat. This uses existing delivery metadata, not a new
job journal. `model_first_text` measures provider text availability, NOT first
visible ink; both must be reported separately in live tests.

Ten additional mocked-provider/device integration tests cover the real Respond
entry point, request replacement, changes during capture/model work, failure,
restart, media/fixture separation, and operator-only configuration. The full
Python suite passes 349 tests. These tests do not authorize a claim of a live
PiDog response. Before enabling, the Pi harness owner must install/review the
host, confirm the intended configured model and authenticated route, and
provide the actual private socket location. No host settings, grants, runtime
backend or tablet changes were made by this implementation.

### Fraction comparison: quantity-driven coverage, not an authored scene

The quantitative vocabulary now includes `fraction_comparison`, with two
`{numerator, denominator}` values. It supports positive proper fractions with
integer denominators 2..12. PiDog supplies the quantities, reveal captions and
one checked relationship (`equal`, `first_greater`, or `second_greater`); it
supplies no coordinates. Four parts reveal equal-sized wholes, their partitions,
the first selected amount and the second selected amount. The renderer generates
the fraction labels and final equation, verifies the relationship with exact
rational arithmetic, and passes the entire lesson through the existing geometry,
label-clearance, stroke, point and pen-time limits before native assets exist.

Hatching has the same angle, spacing and phase for both wholes. Equivalent
fractions therefore select equal widths AND equal hatch density, regardless of
how many pieces they have. New diagonal marks may cross the existing internal
partition lines, but they do not retrace any border edge. Captions remain model
prose, not a mathematically verified proof. This does not yet support zero,
negative, improper fractions, unlike-sized wholes or denominators above 12;
the prompt states those bounds rather than silently altering a question.

Offline evidence: tests check all 66 supported proper fractions against their
reduced forms, six comparison/extreme cases through motion and native reveal
encoding, wrong/missing claims, invalid quantities and coordinate overrides.
Full Python suite: 353 passing tests. The first visual/layout run exposed a
two-digit-denominator label collision; the corrected layout leaves clearance.
The second preview revision uses denominator-independent hatching. Both
artifacts are retained under `OUTBOX/fraction-comparison-20261028-v{1,2}`.
The v2 cumulative 1/2 versus 2/4 stages, 2/3 versus 3/5 final picture and fraction
equation were visually inspected. Local compile/native-encode was about 5–6 ms
for these two fixtures, excluding model, capture, delivery and tablet time.
These are developer-authored fixtures, not new PiDog results or tablet proof.

### Pi host lifecycle hook (ready for owner integration, not installed)

`notebook_pi_lifecycle.mjs` supplies the actual registration function, so the
host owner does not need to reconstruct startup/teardown logic from prose.
Import it into the existing `pi_harness_extension.mjs`, then call once from that
extension's default entry point, alongside `createPiHarness`:

```javascript
// Import from the owner-installed, reviewed herd-board module directory.
const notebook = registerNotebookResponder(pi, {
  socketPath: notebookSocketPath,
  systemPrompt: notebookSystemPrompt,
  onStatus: state => { /* optional bounded ready/stopped/unavailable UI */ },
});
```

The two inputs above must be explicit trusted deployment values: an existing
private parent/short Unix path and the fixed prompt generated by
`semantic_reply_instructions()`. They are not client/model fields. The
inspected Pi launcher selects only its own extension (`--no-extensions -e
pi_harness_extension.mjs`); simply dropping this module in a workspace does
not load it. The inspected `readPiClientConfig` also rejects unknown fields,
so adding notebook settings to that file without a reviewed schema change is
not an installation procedure. No live config or credentials were inspected
to create this hook, and no deployed harness file was modified.

Registration starts no resources until `session_start`. It takes only that
context's configured model and registry, not its transcript or tools.
`model_select` cancels the previous responder and reopens using the event's
selected model/current registry. `session_shutdown` closes the listener.
Pending-bind shutdown, rapid successive sessions and duplicate shutdown are
handled. Provider mismatch/no OAuth/image support fails closed; no fallback.
All Pi event handlers return immediately, so notebook cleanup cannot block
the normal chat UI. Background transitions are serialized, and replacement
waits for the old provider to actually finish even if it ignores cancellation.
The core and socket `close()` promises now expose that drain; callers must
not mistake an abort request for termination. `settled()` is optional lifecycle
observation, not evidence that a model answer or tablet write succeeded.

Tests: 23 Node tests pass across core, real Unix framing and lifecycle,
including an actual socket close/rebind between two configured test models.
The registry/provider remains fake; no external model call is claimed. All
353 Python tests still pass. Next installation step belongs to the Pi harness
owner: register this hook with explicit trusted deployment settings in the
already-running identity's supported extension, then confirm its ready state
and endpoint. Do not launch a second Pi/Nvoy consumer to exercise the code.

### Image-input evaluation through the installed host — 2026-10-28

`notebook_model_eval.py` connects the ten existing fixed questions to the
image-first transport and existing cumulative preview renderer. `prepare`
creates typeset PNG question cards and a fixed expected system prompt;
`collect` sends the actual image bytes with generic question context, never a
text transcription. It uses only an already-installed owner-only socket; no
model SDK, credentials, new consumer, tablet access or server setting.

```sh
python3 notebook_model_eval.py prepare /absolute/new/image-packet
python3 notebook_model_eval.py collect /absolute/new/image-packet/packet.json \
  /absolute/new/model-a --socket /verified/private/notebook.sock
# After a supported host model change, collect the SAME packet in model-b.
python3 notebook_lesson_eval.py compare /absolute/new/model-a/rendered \
  /absolute/new/model-b/rendered /absolute/new/comparison.html
```

The whole packet is preflighted before any model call. Images, context and
expected prompt hashes identify the packet; copies of exact inputs survive
later edits. One serial call per question, no repair/retry or automatic model
change. Infrastructure failure/deadline stops the run. Responses carry actual
provider/model metrics; a model change stops a mixed run. Each completed
question checkpoints its original wire response, metrics and result. An
interrupted run is not silently resumed or overwritten.

An optional immutable-byte observer in the Python transport retains a bounded,
request-bound, metrics-checked response before semantic validation. It cannot
replace the bytes or bypass the compiler. A mathematically false claim is
saved for diagnosis but remains rejected and generates no native ink. If the
host rejects output before releasing it, raw text is unavailable: the report
says so, and the comparison distinguishes host/transport failure from compiler
rejection or an unattempted question. The ordinary server installs no observer.

Limitations are explicit in the run and comparison: these are **typeset**, not
handwritten inputs; call timings are not Respond-to-visible latency; the
protocol does not attest the host's fixed prompt digest. The saved prompt is
an expected deployment input, not proof that the host used it. Confirm that
installation independently before treating runs as a controlled model
comparison. Text fallback is not a visual lesson pass. Neither synthetic test
answers nor preparing the ten images counts as model or tablet acceptance.

Host review: nvoy PR282 (a64d64f, based on published feat/pi-channel-post).
The actual Pi supervisor checkout at9970735 has additional unpublished changes;
local compatibility commit af6b33a preserves them and passes build/harness
tests. These are review artifacts, not proof of activation. The three adapter
modules and fixed prompt from3939bea remain compatible; this evaluation
addition changes neither their wire protocol nor the model's instructions.

### Sampled charts: reusable numerical coverage (offline, 2026-10-28)

The real image-first Luna run returned four visual lessons and six plain
answers. A new `quantitative / sampled_chart` component addresses numerical
relationships without another topic-specific authored scene. The agent sends
2–8 paired x/y quantities and short axis labels, not pixels, functions, code,
or paths. The renderer owns a linear scale, zero-inclusive y range, lettering,
markers and straight guide links. Four parts—axes, scale, samples, links—reveal
on one picture with captions below. Existing whole-lesson validation, point,
stroke and motion budgets still apply before native allocation.

Strictly increasing x values prevent ambiguous ordering. Exact short decimal
axis labels avoid silent scale rounding, and indistinguishably close markers
are refused. Links stop at marker boundaries and do not invent a smooth
function. Trend claims are checked against the supplied values; they do **not**
verify transcription, a financial assumption, a physical model, or caption
truth. Zero-valued series use the explicitly labelled range -1 to 1. A graph
of falling distance is not a picture of the object's physical trajectory.

Developer-authored growth and free-fall examples use the same compiler and
different quantities. Native encoding and motion compilation also cover
decreasing, signed, constant, irregularly spaced and eight-sample series.
Previews: `OUTBOX/sampled-chart-20261028-v1/index.html`; these are fixtures,
not fresh PiDog responses or tablet evidence. Original real model outputs
remain unchanged. The new prompt capability must be tested in a separately
identified model run after host prompt deployment; the running host still
uses its previous fixed prompt. No live backend, tablet or global agent
configuration is changed by adding this component.

### Shared-scale comparisons after the real-model diagnostic

An explicitly guided Luna answer drew the compound-growth series but left the
fixed-addition series in prose. That was a teaching-quality failure even though
the native compiler accepted the drawing. `sampled_chart` now optionally takes
`label` and `reference: {label, y}` with values at the same x samples. Distinct
labels are bounded to 12 characters. Both traces share one zero-inclusive
linear scale: primary circles/solid links and reference crosses/dashed links.
Coincident segments share the existing solid line instead of painting it twice.
Markers may coincide deliberately when values are equal; captions should say so.

After `scale`, either series may reveal its samples; each set of links requires
its own samples. `difference` requires both sets of links. This permits showing
both point sets before connecting them, as a real model requested. Combine
parts as needed to fit the six-step lesson limit. The compiler requires
one extra exact predicate, `final_above`, `final_below`, or `final_equal`, and
computes a visible final gap (primary minus reference). It does not infer that
final ordering holds at other samples, verify source data or prove the prose.
Small differences remain small on the shared scale; the numeric gap makes them
readable without distorting the graph. Existing whole-lesson label clearance,
native stroke/point and motion-time caps remain unchanged.

Offline tests cover signed/crossing/equal series, omitted or false comparison
claims, distinct labels, strict reference sizes, shared-edge preservation and
eight-point motion/native encoding. `OUTBOX/sampled-comparison-20261028-v2`
shows the developer-authored growth comparison, not a fresh model or tablet
answer. The prompt also makes the lesson preference explicit when the available
vocabulary honestly depicts the central idea; it does not force unsupported
questions into an unrelated scene. Deploy and evaluate this prompt separately
from the previous assisted probes before claiming automatic selection works.

### General drawing scene alongside procedural components

The semantic-only restriction was still preventing the requested general-purpose
lessons: a numerical chart or one of a few motifs cannot stand in for every
circuit, geometric proof or count diagram. The fast JSON route now also accepts
an explicitly selected `scene: {family: "drawing"}`. The ordinary lesson envelope
is unchanged; its 3–6 steps use `{caption, draw}` instead of `{caption, reveal}`,
with `claims: []` and an optional top-level `equation` string. Other scene families
cannot add that equation field or override their computed quantities.

This reconnects the existing eight-operation `compile_lesson` language rather
than adding another writer. All steps build the same local 600×360 picture.
Lines, arrows, circles, rectangles, sparse polylines/plots, braces and labels
expand through the existing plotter font, density/budget checks, complete-plan
validation, native source builder and unchanged request/page/ink protections.
No URLs, file paths, code, SVG or raw native ink are accepted. There is no
automatic catch-and-fallback, model repair loop, extra lease or audit system.

Prefer procedural components for supported quantitative layouts; use a few
primitives when those components cannot express the central idea. The model
still chooses meaning and sparse geometry—not thousands of sampled strokes.
Drawing validation proves bounded syntax/layout, **not** mathematical correctness
or caption truth. The returned metadata explicitly leaves those unverified.
This supersedes the earlier design's absolute no-coordinate/no-layout-escape
restriction; it retains the original user-requested drawing vocabulary under
the same strict compiler and native safety limits. Real-model/offline quality
review and tablet acceptance remain separate requirements.

### Cyclic network layout: preserve the answer, improve the composition

The second-model drawing-v4 evaluation exposed a valid four-node network whose
precipitation label could not fit between a vertical connector and a return arc.
The established three-across-top layout made the cycle unnecessarily narrow.
The renderer now tries one additional wide-triangle arrangement for four-node
networks after the two existing row-gap variants fail label placement. This is
at most four whole compositions, each with the existing 4,096-choice label
search bound. Successful prior layouts remain unchanged.

Only `LabelPlacementError` triggers this finite alternative. Invalid semantics,
unsupported fields, native budget failures and other errors are not repaired
or retried. Model words, object shapes, relationships, reveal sequence, 18px
plotter labels and collision/point/stroke/time limits remain unchanged. No model
call, extra input tokens, native write or new lease is part of layout selection.

The unchanged saved water-cycle response now compiles to three native stages;
all three offline previews were inspected. Existing non-water previews in the
same answer set remain byte-identical. This is a compiler replay of a previous
model failure, not a new first-pass model success or tablet acceptance. The
original rejection and original raw answer remain in their evaluation folders.

### Wrapped-label clearance and five-node return loops — 2026-10-28

The unchanged saved PiDog water-cycle answer exposed a concrete layout defect:
fixed label baselines could place a wrapped object's label against its own
outline. Object placement now retains the original four candidates, then offers
four additional above/below candidates derived from the full measured label
box, including descenders. Existing whole-picture collision checks still decide
acceptance; no font shrinking, wording edits or overlapping labels are allowed.

Five-node causal scenes also have one alternative return-loop layout: the entry
pair is nearer each other and the returning node occupies the opposite bottom
corner, giving parallel process arrows enough room for full labels. Like the
four-node alternative, this is deterministic, at most four full compositions
and 4096 label-search visits per composition. Only label-placement failures
try another composition; malformed inputs and native budget failures do not.

The exact original answer now renders four cumulative stages in
`OUTBOX/five-node-layout-20261028/report.html`, all visually inspected. Native
strokes per stage are 45/49/41/58; points 784/997/830/1170. Playback preparation
passes the existing per-stage limits, with 39.086 seconds total planned motion
across all four stages, not device latency. Five previously accepted answers'
SVG previews are byte-identical. All 451 Python tests pass, including full-box
clearance, determinism, bounded attempts, native encoding/playback and a
separate generic circular-node loop. A wider-box variant still rejects safely.

This is an **offline layout fix only**. The answer still uses the liquid-pool
motif for vapor and rain; its symbol semantics are not repaired or approved.
No fresh model run, tablet deployment, safety-limit change, or broad rollout
is claimed. Original failures and raw answers remain untouched.

### Two-way count grids: quantities instead of coordinate-heavy tables

`count_grid` is a quantitative component for a 2×2 table, not a canned answer
to the Bayes evaluation question. The model supplies two row labels, two column
labels, four nonnegative integer counts (each at most 999999), and a selected
cell with explicit `condition_on: "row"` or `"column"`. Labels are at most ten
characters, distinct within each axis; `Total` is reserved. Actual glyph widths
must leave at least 12 local units between column headings. The renderer does
not shrink/truncate labels or infer a missing category from prose.

Code computes every margin and the exact conditional fraction, draws the
table edges once, underlines the conditioning category, and boxes the numerator
cell and matching margin. The exact `selected_fraction` claim must agree with
those supplied counts. Zero denominators, false claims, bad quantities and
unsupported fields reject before native source allocation. Input reading,
category interpretation, mutual exclusivity/exhaustiveness and prose truth
remain unverified; arithmetic validity does not prove the source was understood.

Parts are `frame`, `columns`, `row1`, `row2`, `totals`, `selection`. The fixed
prompt recommends one part per step (six additive stages): combining frame and
headings exceeded the expanded motion budget in development. Either row may
come first; both must precede totals and the final selection. The same native
encoder, complete-plan collision checks, plotter font, motion sampling and
per-stage 64-stroke/3000-point/30-second limits apply, without a model repair
loop. The final equation displays the count ratio and its reduction when needed.

Developer fixtures cover column conditioning (8 of 17) and row conditioning in
an unrelated batch comparison (3 of 60 = 1/20). Tests exercise all four cells,
both axes, zeros and maximum counts, explicit highlight geometry, incorrect
denominators, schema rejection before allocation, and actual native/motion
encoding. This is renderer evidence only until a separately identified fresh
model run chooses the component and a real tablet exchange proves delivery.

### Optional object-anchored labels in the general drawing language

The eight operations remain unchanged. Any non-label primitive may now have
an optional unique local `id`; a label can opt into renderer placement with
`{"op":"label","target":"local-id","text":"short name"}` instead of `at`.
Targets must already have been drawn, even within a step; labels cannot target
other labels, external resources or future objects. Explicit `at` labels retain
their original coordinates and size: a rejected explicit layout is never
silently converted into this format or repaired.

The model still owns the shapes, quantities, caption meaning and label-to-object
association. The renderer owns placement only when explicitly requested. It
uses the existing constrained-first finite label search against **all** final
geometry and reserved fixed-label boxes. Open-path labels use arc-length/normal
positions; closed shapes also offer a centre candidate and nearby exterior
positions. Short word wrapping preserves text, and no shapes or stages move.
Labels are fixed18px, at most24characters, with at most12 anchored labels per
lesson. IDs match the existing short lowercase local-name convention.

The ordinary compiler processes the resolved primitives again: wrapping counts
against32commands per stage, expanded glyphs against64strokes/3000points/30s,
and the whole picture against12000points and final label clearance. Excessive
geometry is refused before the placement search; exhausted search or no clear
location holds the whole lesson before native allocation. This adds no device
API, lease, credential or answer-repair loop. Placement metadata stays in the
existing plan for offline inspection; it is not a new authorization mechanism.

Developer fixtures illustrate3-4-5 and6-8-10 side-square diagrams and a sparse
straight-ray scattering sketch using the same general primitives. Shared
triangle/square edges are drawn only once. These fixtures demonstrate optional
placement, not fresh model success or tablet delivery; original failed model
answers remain untouched. The model can still choose an inappropriate target
or false explanation, which the layout engine does not claim to verify.

### 2026-10-28 attended native typewriter failures

The initial integrated test on isolated page41 stopped after its first caption
character. `SceneView.isLoading` includes normal editor work and pending tiles;
1212d1e waits for these while retaining identity, pen and bounded-progress checks.
Reopening page41 restored the read-only incomplete warning, without resuming.

Page42 then exposed a distinct cursor assumption. A diagnostic repeat on page43
reported `lengthBefore=23,lengthNow=31,cursorBefore=23,cursorNow=30` after one
letter in a native virtual gap. The initial interpretation (terminal newline)
was WRONG: c1a427f's page44 run produced `tart...\nS`, exposing the cursor as the
start of the inserted unit, not its end. `replaceText(..., cursor=0, ...)` leaves
that start shifted by materialized preliminary breaks. The revised guard accepts
exactly this initial virtual start (`length-unitLength`), then explicitly advances
to document end. No arbitrary cursor location is adopted. The old test mock
appended every character regardless of cursor, hiding the difference; it now
also inserts at the native cursor, leaving it at the insertion start.

Page44 additionally reached the equation and held: preflight mistakenly looked
up its `equation-*` scene in the authored factory table. Compiled equation blocks
now use the same lesson rollout and bounded blank-region check as lesson scenes.
An actual compiled-equation preflight regression checks enabled, disabled, and
occupied cases. Page44 remains a failed attempt, not a completed demonstration.

These three attempts are failures, not acceptance passes. Page42 failed at17.403s
and page43 at17.625s from server Respond; prior saved pages remained byte-identical
(41 and42 pages respectively). Artifacts are `OUTBOX/native-ux-reflow-attended-20261028-*`
and `OUTBOX/native-ux-cursor-diagnostic-20261028-*`. These use a renderer fixture,
not PiDog, so they provide no new model-quality or model-latency evidence.

**First corrected complete run (49cf343):** isolated page45,
`26b45199-eff4-4579-bd0a-717cb215f3a5`, request
`notebook-e5a260281cdd41a3b4559b4f3fdd4b20`, reached `written` at89.538s.
First sampled reply label visible by5.835s after tap (frame04 still cursor only).
All four diagram stages plus the equation committed; the equation stage ran
67.831–70.581s. Captions are correctly ordered, captured partially revealed at
19.954s, and the takeaway is complete in the final capture with the viewport
following it and no error banner. This is renderer-only, not model latency.
Read-only saved-page comparison matched all67new strokes (including7equation
strokes) to validated source geometry and all44earlier pages byte-for-byte.
Artifact prefix: `OUTBOX/native-ux-advance-attended-20261028-*`.
James observed the physical animation and called it "pretty fantastic". A normal
close/reopen preserved the exact saved page SHA256 and written status, without
replaying. This one fixture is not the ten-exchange/general-model acceptance run.
Local verification:471Python tests and14native Node test files passed.

**Caption-first revision (offline):** playback now emits label-only text, then
each short caption before its matching ink addition. The introductory caption
is above the shared picture; subsequent captions remain below it. Static/legacy
clients retain draw-then-caption. Fraction comparisons optionally split upper
and lower partitions as semantic parts, not individual stroke instructions.
The replay fixture has five steps and keeps the computed pen-stroke inequality.
Typewriter timer cadence is31ms instead of40ms (~29% faster nominal rate);
native acknowledgement/reflow still determines actual throughput. All existing
page/pen/identity/timeout guards remain. The diagnostic prompt uses wrapped
single-line plotter lettering instead of skeletonized bitmap outlines.
475Python tests and the native-client suite pass; this revision still needs its
own tablet proof. Requested MC Claude review before the isolated replay.

**Caption-first tablet proof (885502a):** page46
`655fdf5f-5aec-4eb5-b5b1-65ed60c3abc4`, request
`notebook-49469e90709042a0b26b1cf70ff326d0`, completed without an error banner.
The requested question was written as input ink: "What is greater, 2/3 or 3/5?
Explain visually." Frame04 shows the reply label by5.116s; frame05 has partial
introductory caption by6.075s. Frame25 has the full upper-thirds cue BEFORE its
divider strokes. Five diagram stages and the pen equation all committed; the
equation completed at64.923s and persistence reached written at93.964s. The
whole run is NOT 30% faster than the previous fixture; the timer rate is faster,
but native editor/save waits and five rather than four steps still contribute.
Saved geometry matches all67output strokes (15,2,4,20,19,7), and all45older pages
remain byte-identical. Artifact prefix: `OUTBOX/native-caption-first-20261028-*`.
This is still a renderer fixture, not a new PiDog reasoning/latency evaluation.
Left open for James; this new page has not yet had its own reopen check. The
prompt lettering is more regular but word spacing and the introductory
label-to-caption gap still merit visual polish; do not call layout fully solved.

### 2026-10-28: live right-triangle save-confirmation diagnosis

Fresh PiDog request `notebook-381a593ab3944942be6d99643eb6129c` produced
four triangle/square stages and a pen equation on page46, without closing the
notebook during insertion. Model completion was5.204s; captured first agent
label13.869s and substantive caption14.796s. Final acknowledgement failed at
83.417s. This is **not** an end-to-end acceptance pass or the ten-exchange gate.

Read-only saved-file inspection matches all28new strokes across the five
blocks(2,2,1,8,15). All45earlier pages are byte-identical. Existing native text
retains its538-character prefix, layout and styles. The visible triangle lesson
survives navigating to page45 and returning normally to page46, at the same
saved view offset5007. The failed request remains failed; no resend or forced
acknowledgement was used. Dismissing its UI banner enabled the existing hidden
source-page diagnostic; it did not clear server state.

**Root cause isolated:** two prior strokes, item IDs1176/1179, reanchor as
1571/1574 with exact world geometry, attributes and move lineage. Their line
field6changes from(0,1)to(1,1576). The preservation checker mistakenly included
this timestamp in its style fingerprint. The upstream
[rmscene reader](https://github.com/ricklupton/rmscene/blob/main/src/rmscene/scene_stream.py)
identifies field6as timestamp and handles field7as move lineage. Actual pen,
color, thickness, starting length and optional RGBA are separate fields.

The scoped fix validates timestamp encoding but excludes it from appearance
hashes. Baselines now explicitly use style_version2; mixed old/new journals
are refused, not retroactively reinterpreted. Geometry, every non-coordinate
point byte, author, unique match, move lineage, text and image checks remain.
Two new regression tests cover timestamp-only reanchoring and rejection of
mixed legacy baselines; changed ink/lineage and malformed timestamps still fail.
All500Python tests pass. No new leases, queues or audit mechanisms were added.

Independent hidden-native measurements of all12saved anchors, combined with
an **offline-only** timestamp normalization derived from retained pre-test raw
styles, match all291pre-existing strokes with zero geometry anomalies. This
diagnostic never changes the stored baseline or the failed request. Artifacts:
`OUTBOX/live-right-triangle-20261028-save-diagnostic.json`,
`OUTBOX/right-triangle-saved-anchor-diagnostic.json`,
`OUTBOX/right-triangle-preservation-diagnostic.json`,
`OUTBOX/right-triangle-preservation-normalized-diagnostic.json`, and
`OUTBOX/right-triangle-reopened-after-diagnostic.png`.

**Remaining gate:** reviewer check, deploy the scoped comparator change, and
obtain a fresh live exchange with the new baseline format and successful final
acknowledgement. Startup latency remains over target and needs separate work.

**Fresh live gate passed (dcc40b4):** after My Dude's source review, the scoped
timestamp fix was deployed to the server without restarting the tablet UI.
Fresh simulated handwriting "Draw a circle." and one actual Respond produced
request `notebook-482bc2c74d5a4037b31f6b79f7b415ab`. Its persisted baseline uses
style_version2. Model completion2.966s, native write start12.357s, circle commit
20.778s, and final `written` acknowledgement44.035s. Captured frame13 at13.456s
does not show the new reply; frame14 by14.640s shows both the agent label and
partial caption. This misses the under10s first-visible target. Final settled
screen has the circle, caption and takeaway, RESPOND restored, and no error
banner. No resend, forced ACK, notebook closure or interface restart occurred
during this exchange.

An independent read-only archive comparison confirms all45earlier pages remain
byte-identical and the new saved circle matches its immutable source stroke.
The server's successful final proof checks old content; this independent check
does not claim a second complete anchor measurement. A normal reopen check for
this circle remains outstanding. Evidence prefix
`OUTBOX/live-timestamp-fix-circle-20261028-`, including `timing.json`,
`save-evidence.json`, `after.tar`, `terminal.png`, and frames000–047.

**Latency diagnosis, not a speedup claim:** the existing native_requested field
was overwritten at3.211,3.833,7.435,11.295s. The source-import callback accounts
for one re-entry, and layout measurements account for subsequent calls, but the
retained trace does not establish why another capture was needed. New offline
diagnostics preserve first/latest boundaries plus fixed reason-specific layout
timestamps (initial, snapshot_changed, context_changed) in the existing numeric
timing map. No new journal, validation bypass, or retry is introduced. The
current-stage names retain their old latest-pass semantics. Two regressions and
all502Python tests pass; the diagnostics still require source review and live
deployment/testing. Tablet telemetry and the configured transport remain live;
the failed bare remarkable.lan lookup was not evidence of a dead tablet.

**Circle reopen proof:** normal close to the library and reopen of the same
To pidog notebook preserved the circle, caption, takeaway and latest viewport
offset6585. Saved page SHA256 stayed exactly
`33cd40f0006a60609aea7b16a82ff8e6070892e88a796ad9fc3324ddd115d007`.
The `closed.png` and `reopened.png` captures share the circle evidence prefix.
This completes that one reopen check, not the broader ten-exchange gate.

**Live timing diagnostic (3680f69), failed before insertion:** My Dude reviewed
the concrete four-file change, then the two scoped runtime modules were updated
and the server restarted with no active insertion. No tablet UI restart.
Fresh simulated "Draw a square." request
`notebook-dda6397a3b824cc38c786e0c0a6b74b2` returned from PiDog at2.935s.
First native preparation3.156s; post-import pass3.919s; initial before-layout
query4.951s; measurement callback7.702s. At7.909s finish_capture rejected
`saved page or input changed during native layout capture`. Native page,
surface, content and ink revision checks passed, but independently read saved
bytes differed. The tablet log records focusing its inactive pen cursor during
the measurement. Autosave is a plausible cause, not a proven byte-level
explanation; the original differing raw snapshot has not been exported.

The server retains the answer as ready-with-error and the UI reports failure.
There is no registered plan or before-ids baseline for this request, no ink
claim, and no write_started timestamp. No retry or forced ACK was sent.
All45earlier pages remain byte-identical in a read-only archive comparison.
Artifacts use prefix `OUTBOX/live-latency-square-20261028-`, especially
`timing.json`, `held-evidence.json`, `before.tar`, and `held.tar`.
The observer continued sampling until its150s window because it recognizes
failed/written but not ready-with-error; that is an observer limitation, not a
live job that needs restarting.

Next: retain exact before/after saved snapshots in a controlled diagnostic to
identify whether the transition is content or non-content. My Dude's review
explicitly advises against generic discard-and-remeasure: stable telemetry is
not proof that changed saved bytes are harmless. Keep the before-phase guard
and failed request unchanged until that evidence exists. This remains a live
reliability failure; no broader rollout or ten-exchange claim is justified.

### 2026-10-28: saved-input transition isolated; native hint trial

Separate fresh page45 square `notebook-624e00e86034434bbd1f62d1333c1e4b`
completed at44.739s. A read-only concurrent recorder retained three immutable
saved `.rm` versions in `OUTBOX/native-save-transition-20261028/`:

- Initial48,232bytes, text length439: new handwriting was not yet persisted.
- First change observed by7.761s after Respond,53,356bytes, text length439:
  new question strokes plus native regrouping. This is content, not merely
  autosave metadata. Baseline hash matches this second version exactly.
- Reply-bearing60,055bytes observed by37.701s, text length588. Final saved
  confirmation followed at44.739s.

Model3.073s; first layout request5.035s, measured6.756s; register detected the
changed saved snapshot at7.837s; second layout measured9.614s; write_started
10.676s. The first measurement preceded persistence of the handwritten input.
This identifies the recapture cause in this request, not the exact unrecorded
byte transition in the earlier held page46 request. That failed request remains
held, without retry or ACK. Independent saved inspection matched the new square
source stroke and all45other page files remained byte-identical. A normal close
and reopen after setup-only UI reload showed the square/caption/takeaway at the
same view offset1993; normal-close saved bytes were identical. Evidence includes
`record.json`, SHA-named files, `block-differences.json`, `after.tar`,
`normal-close-proof.json`, `terminal.png` and `reopened.png`.

OS3.29's extracted DocumentView calls
`sceneController.requestDeferredCompleted()` when Page Overview opens, to
complete thumbnails/deferred work (`OUTBOX/native-qml.k14u9p/16610915.qml:150`).
Installed SceneController metadata confirms the method. This is not proof of
save semantics or a completion acknowledgement. The candidate QMD calls it once
before Respond dispatch only in the existing isolated storyboard notebook.
Unavailable methods/errors are a no-op; no polling, waiting, new journal,
capture bypass or replay is introduced. Existing snapshot/revision/preservation
guards are unchanged. My Dude reviewed the isolated experiment's scope; all502
Python tests and native CJS regressions pass. Device timing validation remains
pending at this entry; do not describe the hint as a fix until measured.

**Isolated hint trial, held:** request
`notebook-1c6e5f90e45c46e1b94934358a68d1b4` logged one deferred-work call before
model dispatch. Its first saved-file transition arrived by0.881s after the tap
(comparison above7.761s), and the saved bytes remained unchanged throughout the
layout measurement. PiDog completed at2.156s. The measurement began3.969s,
returned6.687s, and failed6.743s with `native layout capture requires a fresh
active page`, not a saved-byte mismatch. No registered plan, insertion or ACK.
All45other pages stayed byte-identical, and normal close left this held page's
saved bytes unchanged. Artifacts: `OUTBOX/native-save-hint-20261028/record.json`,
two SHA-named `.rm` files, `held.tar`, `held-evidence.json`, and screenshots.
The earlier run lacks per-sample server context, so do not assert whether this
failure was specifically age expiry or the last heartbeat reporting loading.

The QMD publishes context every500ms, with one report in flight; server context
expires after1.5s and requires active=true. Cursor restoration can make the
native view temporarily loading. The original measurement callback immediately
posted its result without an accepted context report as a completion barrier.
Commit `fe1f376` adds a bounded handoff before this before-layout result: await
native idle, publish the existing context, require HTTP200/accepted:true, then
recheck the frozen request/page/surface/revisions and restored pen route/idle
before sending the ORIGINAL command and samples. Three-second bound, no
recapture/rebase/server-gate relaxation. Busy/rejected/late reports and changed
input are tested; all502Python tests and native CJS regressions pass. My Dude
reviewed the concrete handoff and approved one isolated live trial, not rollout.

**Isolated handoff trial passed:** new page47 was seeded with a fresh native
`Say hello` exchange (saved6.454s), then simulated handwriting `Draw a square.`
and one Respond produced `notebook-336683abd4464e3cb362d1c294c8b837`.
PiDog completed2.519s; before-layout requested4.311s, received5.692s,
measured5.759s; write_started6.647s. Screenshot008 shows the NEW caption
`Here is a` by8.920s after the tap, below the latest handwritten input.
This is a sampled upper bound, not a precise display-refresh timestamp.
Ink committed15.203s; full saved confirmation36.697s. No repeat measurement,
error banner, manual resend or UI restart during the exchange.

Concurrent context recording shows accepted sequence449 active/fresh at
tap+5.633s (age161ms) and+5.850s (age378ms), same surface and revisions8/50.
Native log shows context publication19:35:02.146 and confirmation19:35:02.192.
The server accepted the original before-layout result; its freshness and
preservation gates remain unchanged. This supports the handoff on this run,
not a causal guarantee for every device timing pattern.

Independent saved-ink inspection matches the square's one source stroke;
all46other page files remained byte-identical. Normal close/reopen preserved
exact saved SHA256 `9fc444386aecf9c103f6e2a52627374a70d4e2d66719769762da4d3a637dbd54`
and visually retained caption, square and takeaway at view offset1556.
Evidence: `OUTBOX/native-layout-handoff-fresh-20261028/` contains `record.json`,
immutable SHA-named snapshots, before/after archives, `save-evidence.json`,
`terminal.png`, and `reopened.png`. This is one successful square trial, not
the ten-exchange acceptance target or proof of general lesson quality.

Setup also exposed an independent status-reporting limitation: page44's older
persisted pending request was absent from in-memory answer_status after restart.
Respond correctly returned400 `request already pending`; no new request or
insertion occurred. It remains untouched. Observer evidence is under
`OUTBOX/native-layout-handoff-20261028/`; request:null/observation_timeout there
reflects the recorder's inability to classify that rejected submission, not a
new model timeout. Fix status visibility separately; never clear pending state
or replay to make a test proceed.

### 2026-10-28: fraction lesson rejected by the wrong expansion allowance

Fresh simulated-handwritten `Which is greater, 3/4 or 2/3? Explain visually.`
on page47 produced `notebook-f5f7dd9a013f49acb7f1899e17e57b20`, held before
insertion with `invalid_response` by observed5.522s. No raw response was retained
by the production path, so the original cause is unknown. PiDog's read-only
recovery found no additional response or parser detail. The request remains
held; no retry or forced ACK. Evidence: `OUTBOX/live-fraction-lesson-20261028/`.

One separate offline call using the captured question image retained its exact
response in `OUTBOX/fraction-capture-offline-20261028/response.json`:
`notebook-46e53c4f00d94b0bbf676eef86c78696`, Luna/minimal,4.051s model,
4.082s wall. This NEW response correctly selected fraction_comparison, supplied
3/4 and2/3 with first_greater, and used three captioned stages. The third stage
revealed both shaded amounts together. Two semantic IDs expanded to38 commands,
which incorrectly encountered the raw-model32-command allowance. This explains
the offline failure, not necessarily the unrecovered live failure.

The compiler now applies its existing bounded procedural allowance to fraction
expansions above32commands, as it already does for compact odd-square growth.
The agent-facing drawing grammar remains32commands. Expanded native limits,
whole-picture collision checks and motion validation are unchanged; no model
repair, caption rewrite, stage split, coordinate change or native replay.

Replaying the immutable answer through this fix produces15/5/42 native strokes
and1077/150/1276 points. Expanded motion budgets are2157/295/2510points,
25/5/42contacts, and21.163/3.005/25.530estimated pen seconds, within existing
per-stage limits. All three cumulative previews were inspected: equal bars,
correct partitions, and visibly greater3/4 selected area; captions/takeaway
agree. Exact equation is3/4>2/3. Native encoding succeeds. Evidence:
`OUTBOX/fraction-expansion-replay-20261028/{index.html,summary.json,step-*.png}`.
Tests cover this unchanged grouping and rejection of a denser combined shading
that exceeds the existing motion limits. All504Python tests pass. This is an
offline compiler fix pending review/live validation, not a successful live
fraction exchange or a general reliability claim.

**Reviewed deployment and fresh live result:** fix committed as `852a949`.
The launchd copy predates the repo's odd-square and anchored-label integration.
To avoid deploying those unrelated changes, its scoped update adds only the
explicit procedural bool/32-or64command selection in notebook_lesson.py and
fraction-only activation in notebook_semantic.py. My Dude reviewed this runtime
subset separately. Six runtime fraction tests pass. One authenticated backend
restart loaded it; no tablet UI reload, model/prompt change or wider rollout.

New page48 request `notebook-36b6ae835da44c01a82e8a27cc605140` used fresh
simulated handwriting of the same question, a real Respond and a new PiDog
answer. It chose FOUR stages (the two shadings separate), not the offline
probe's three; thus it does not prove combined-shading device behavior.
Model completed3.711s after Respond; write_started5.713s. Frame006 visibly
contains the first caption by7.908s after tap. Four drawing stages committed
at23.215/32.431/45.251/59.585s; equation64.713s; saved86.333s. Caption-first
typewriter and progressive ink remained inside the open notebook. Scroll
advanced to1091 to expose the final equation and takeaway.

Independent saved-source matching found15/5/22/20strokes for the four stages
and7equation strokes. All47other page files stayed byte-identical, including
the previous failed page. Normal close/reopen retained exact SHA256
`22ff9f2e41423b2951a4defd4089348deaff1cc4317d73804c3223da8fde5633`
and view1091; the comparison equation/captions/takeaway are visibly retained.
Evidence: `OUTBOX/fraction-fix-live-20261028/record.json`, `save-evidence.json`,
`reopen-evidence.json`, archives and frame PNGs. This proves a new generated
four-step fraction lesson, not ten consecutive successes or unrestricted
general-purpose lesson quality. The failed page47 request remains held.

**Three-step combined-shading live check (2026-10-28):** after My Dude's
four-step evidence review, a separate new page49 request
`notebook-9019a503efbf43f3a869553e921ddb93` asked via simulated handwriting:
"Compare 3/4 and 2/3 visually in 3 steps: equal wholes, partitions, then shade
both together." This was a real Respond and fresh PiDog generation, not a
fixture or replay. No runtime, prompt, model, or rollout configuration changed.
It generated exactly three drawing stages: 15/5/42 strokes, with 1,276 points
in the combined shading stage, followed by the correct seven-stroke inequality.
This directly exercises the procedural fraction expansion allowance on-device.

Model completed at4.069s, write_started6.397s; label visible by8.079s and actual
first caption by9.266s after tap (frame007; frame006 has the label but no caption).
Stages committed23.547/34.012/54.369s, equation59.631s, saved87.412s.
The notebook stayed open throughout the exchange and scrolled to1136.
Independent source-to-saved geometry matching found all15/5/42+7 strokes.
All48 other pages are byte-identical, including held page47. A subsequent
normal close/reopen retained the same viewport and exact SHA256
`ffa1d52bbbc5d80786759a077737aa76ccc999d639093146d8c40b9b1b7720cc`.
Reopened captions, inequality and takeaway were visually inspected. The six
focused fraction regressions also pass. Evidence is in
`OUTBOX/combined-shading-live-20261028/` (record, save/reopen evidence, archives,
input and timestamped frames). The synthetic handwriting is rough and vertical
spacing remains generous; this is a bounded functional/persistence pass, not
finished visual polish, ten consecutive human exchanges, or broader rollout.

### 2026-10-28: current-runtime breadth evaluation and count-grid row wrapping

Ten fixed clear question PNGs were sent once each to the running PiDog host,
using the current runtime compiler rather than later worktree capabilities.
Raw replies, timings, expected startup prompt f58bf0a3 and compiler hashes are
retained under `OUTBOX/current-runtime-eval-20261028/`. The first collection
stopped before dispatch because sandbox metadata access to the private socket
was unavailable; it is retained separately. The access-verified collection
completed all ten: five visual lessons, two text-only answers, three held
replies. Median wall time was3.440s, excluding tablet capture/insertion/save.
Every accepted cumulative visual preview and caption was inspected; findings
are in `current-runtime-review.html` and the rendered quality-review.json.

Failures distinguish model and tool: blue-sky invented unsupported component
`air`; water-cycle requested a prohibited cloud-to-itself condensation arrow;
Bayes correctly supplied8/2/9/81 and8/17 but the row name `No condition` exceeded
the renderer's ten-character cap. The last is addressed without modifying the
answer: row names may have up to24characters and wrap at a word boundary into
at most two fixed-size lines in the existing154-by48 gutter. Column names keep
their original ten-character limit. Existing one-line geometry is unchanged;
the table, numbers, font and prose never move/shrink/truncate. Row-conditioning
underlines span the full wrapped label. Whole-picture and ink/motion budgets
still reject before allocation.

The unchanged Bayes reply (wire SHA256
`6bb14d15c2e769c84d8e90d71eff9145461530e79bea3106e709435ae9af1721`)
now compiles and native/motion-encodes in six stages with the patched module
and otherwise runtime dependencies. All six previews were inspected; correct
8/17 numerator/denominator highlights and readable `No condition` wrap.
All five previously accepted visual answers' SVGs are byte-identical. Evidence:
`row-label-wrap-replay/{summary.json,review.html}`. All507Python tests pass,
including three new wrapping/underline/short-label regressions. This is a
compiler replay, not a repaired model response or new first-pass success.
My Dude reviewed this scope and approved one isolated live Bayes trial.

The fresh second-model comparison is still missing: MC Claude verified the
packet but reported no isolated image-call runner and performed no inference.
PiDog has been asked for an existing offline-only alternative; live host/model
configuration is unchanged. Earlier model comparisons are not relabelled as
current-run evidence. Broader rollout remains gated.

**Live Bayes follow-up:** fresh request
`notebook-0fc5e7ebdb41497f85e18975f281420d` on new page50 completed after the
row-wrap deployment. The actual first caption is visible in frame007 by9.299s
after Respond; model completion5.490s, insertion start7.452s and saved79.368s.
Three stages (39/20/27 strokes) plus the five-stroke equation independently
match the saved ink. The table, positive-column underline, numerator8 and
denominator17 boxes, equation8/17 and47.1% takeaway were visually checked.
All49 other pages are byte-identical. Normal close/reopen preserved viewport511
and SHA256 `dc54def2273c41de4a1069ec854aa413f2563d025c159e73802262291e7f3ae8`.
Evidence: `OUTBOX/bayes-live-20261028/`. The model selected Ill/Well instead of
the requested Condition/No condition, so this is NOT wrapped-row device proof.

**First-caption spacing candidate:** commit5cad8a4 applies the existing compact
caption path when `nativeLesson` is set, before the first ink insertion. The
prior test called `herdLayout` with a manually supplied compact flag and missed
the real `herdOrdered` handoff. New tests execute that handoff and verify one
newline between the settled label and first caption, asynchronous cursor waits,
and holds on changed text/page or an unsettled cursor. This does not change
initial handwriting clearance, picture bounds, later captions or page guards.
All17 native Node test files pass. My Dude reviewed the two-file scope.

The named count-grid renderer fixture now uses Condition/No condition and
natural captions, with unchanged counts8/2/9/81. A regression verifies the
actual wrapped commands, seven native sources and8/17 result; all508 Python
tests pass. My Dude separately reviewed these fixture/test hunks. Pre-existing
phase-change/particle/drop changes remain unstaged and undeployed. Offline
runtime compilation and previews are in `OUTBOX/wrapped-grid-spacing-20261028/`;
this prepared lesson explicitly proves renderer behavior, never model quality.
One setup-only interface reload loaded the reviewed caption patch at20:32:15UTC
(PID32065), after normal close preserved page50 and an archive captured all50
pages.

**Prepared device proof completed:** page51 request
`notebook-0937c2e59690439c9f2fb28db3360cd3` used the named count-grid fixture,
labelled Agent Renderer Test, with zero model calls. Actual first caption is
visible by5.749s (frame004; frame003 has only the label/cursors). Its first glyph
row begins68pixels below the label's top, versus207pixels in the previous Bayes
run: about139pixels of introductory whitespace removed. These are framebuffer
measurements from the two captures, not a claim about identical model latency.
The first caption still precedes the drawing and clears the simulated input.

Frame052 visibly shows Condition and two-line No condition aligned to their
correct count rows with no overlap. All six stages (8/31/20/23/17/10 strokes)
and the five-stroke equation independently match saved native ink. Final save
was112.897s; no closure/restart occurred during the exchange. All50 existing
pages are byte-identical, both across the exchange and compared with the
pre-reload archive. A normal close/reopen retained viewport1112 and exact SHA256
`86e89596904f7cd69fb99b73d140325904f3380d962e13f16ab975c3bff49ddb`.
The reopened final captions, equation and takeaway were visually checked;
RESPOND is restored with no stale error. Evidence: record.json,
save-evidence.json, reopen-evidence.json, archives and timestamped screenshots
in the wrapped-grid-spacing folder above. This closes the targeted renderer
placement/wrapping/persistence check, not fresh-model selection or broad
acceptance. Equation-to-takeaway whitespace, repeated generated-question
reliability, current second-model comparison and wider rollout remain open.

**Equation whitespace follow-up (2026-10-28):** reviewed commit3377120
changes only the native post-commit layout and its extracted-JS regression.
A successful standalone equation uses the rounded-up maximum Y of its
validated playback coordinates for the following text reservation, with the
existing30-unit clearance. The original600x200 playback/clip/paste canvas,
growing-picture reservations, larger previous mediaBottom and all failure
guards are unchanged. All508 Python tests and18 native Node test files pass.
My Dude reviewed the scoped code/test diff before deployment.

One setup-only interface restart loaded the patch at20:45:07UTC (PID853),
after normal close and an archive of all51 existing pages. New page52
`a5206034-cdeb-435e-aae6-3d2d64819d38` ran the same count-grid fixture as page51,
with request `notebook-155ac4a95df74f0e9416959a4cae2e48`, simulated input and
Agent Renderer Test label: zero model calls. The first actual caption is
visible in frame004 by5.774s after Respond. Insertion began2.966s, the equation
committed84.805s, and final written status arrived104.357s. No notebook closure
or restart occurred during the exchange. These are prepared-renderer timings,
not fresh PiDog latency or a claim that spacing alone explains total duration.

All six picture stages and the equation independently match saved native
geometry. All51 previous page files are byte-identical across both setup and
the exchange. Normal close/reopen preserves viewport1112 and exact SHA256
`9ac78991c43f80d1301b6849b6a8bfaa45fb162cab5b0cfb06144afde89bbe6c`.
The reopened result is readable with RESPOND restored and no error banner.
Compared at the same viewport with the previous prepared lesson, equation ink
still ends on pixel row602; the takeaway's first dark glyph row moves from775
to636, a139-pixel reduction with no overlap. Measurements use the original
1404x1872 reopened captures, grayscale<80, x235..1100, at least8 dark pixels
per row. Native text reflow quantizes the final position; this is an observed
device measurement, not simply the98-unit equation-canvas reduction.

Evidence: `OUTBOX/equation-spacing-20261028/` contains pre-reload/before/after
archives, record.json, save-evidence.json, reopen-evidence.json and timestamped
captures. This closes this fixture's equation-gap check. The next priority is
the failed general-question cases in the current ten-question evaluation,
then repeated fresh exchanges, a current second-model comparison, and staged
rollout. None is proven complete by this prepared replay.

### 2026-10-28: isolated fourteen-question first pass and general label replay

James approved the isolated evaluation host installation and PiDog restart.
MyDude installed the actual `nvoy-pi-harness` integration (not the different
review-tree socket convention), subsequently committing it as `ce916890`.
Independent launch/config/loader inspection verified distinct fixed prompts:
production `f58bf0a3…` on `state/notebook.sock`, candidate `ece52a49…` on
`state/notebook-eval.sock`. Both owner-only sockets were held by PID12728.
The live model, production prompt and notebook dispatch were not switched.

The frozen original ten questions plus four held-out relation questions were
sent once each as clear typeset PNGs to the isolated endpoint. All fourteen
returned raw answers from `openai-codex/gpt-5.6-luna`, minimal reasoning;
there were no repair calls, retries, tools or tablet writes. Median complete
model-call wall time was3.992s (range2.631–6.561s); median first model text
was2.404s. Neither is Respond-to-first-visible tablet latency.

Nine answers compiled and encoded as visual lessons; five were held. All
four `drawing`-family answers were held. The nine accepted lessons used the
higher-level quantitative/causal builders. **This does not establish reliable
general-purpose drawing.** The rejected cases exposed fixed labels outside
the region, explicit label/geometry collisions, and missing anchored-label
space. None failed because the isolated endpoint was unavailable.

Every cumulative accepted picture was inspected with its caption and raw
answer. Five received a visual/content pass (including presentation caveats),
four need improvement, and five remain held. In particular, converging arrows
alone do not distinguish alternative causes from jointly required premises;
a diagram about failure must visually explain the failure, not leave that
work entirely to the takeaway. These are general explanatory requirements,
not reasons to add topic-specific symbols. The judgments are assistant review,
not user acceptance or machine-verified proof.

Evidence is `OUTBOX/general-relations-eval-20261028/pidog-first-pass/`:
untouched wire responses, answers, metrics, cumulative previews, quality review,
and separate host verification (the response protocol does not attest prompts).
The requested 5m20s narrated video at sibling
`video/fourteen-lessons-reviewed.mp4` replays validated native paths with
compressed timing and explicitly shows all five holds. It is NOT tablet
footage. Full decode verified3840 frames,1920x1080 H.264 and AAC narration.

The next scoped renderer improvement adds finite edge-aligned label candidates.
If centred placement extends past the reserved region, an opt-in anchored
label may slide along its owner's edge while retaining the owner's centre in
its projection. Original candidates remain first. Shapes, explicit `at`
labels, text, font size, reveal order, collision checking and ink limits do
not change. Four reflected corner fixtures test the same rule, not question
names. The clean candidate passes519 Python tests. Recompiling the untouched
fourteen answers still accepts nine, with all previously accepted SVGs byte
identical. The previously blocked observer label can now be placed, exposing
a separate fixed-label collision in that same answer; it is correctly still
held. This replay is not a new model result or an increased success rate.

The current second-model comparison, fresh handwritten reliability sequence,
expanded-notebook rollout and legacy-writer retirement remain unproven. No
new code from this label candidate has been deployed to the tablet.

### 2026-10-28: topology-derived arrangement, not question-specific geometry

After the existing finite arrangements exhaust label space, causal DAGs can
try a layered arrangement. Longest-path ranks determine left-to-right position;
siblings share a rank, with stable parent-barycentre ordering. This depends on
connections and IDs, not the topic, caption, label wording or a model-specified
grid. Cycles retain existing loop arrangements. Ranks too crowded to preserve
outline clearance have no layered fallback. At most six complete arrangements
are tried. Successful existing layouts remain first; malformed input and native
budget errors are not retried. No label is deleted, shortened or shrunk, and no
relationship, caption, claim or reveal step is rewritten.

The clean candidate passes523 Python tests. Replaying the same fourteen saved
answers, with no model calls or repair, now encodes ten lessons rather than nine.
The previously held proof-dependency graph has room for every supplied label;
its four cumulative stages were visually inspected. All37 SVGs from the nine
previously accepted lessons remain byte-identical. The full native compilation
of the recovered lesson took216ms in this replay (not a latency benchmark).
Evidence: `OUTBOX/general-relations-eval-20261028/layered-clean-replay/`.

This is a renderer replay, not an improved first-pass model result or tablet
test. The proof diagram still needs improvement: converging arrows do not
explicitly encode that both premises are required, and label-to-edge association
could be clearer. None of the four free-form drawing failures is resolved by
this causal-layout change. Those failures, the current second-model comparison,
and device rollout remain open. No production deployment was made.

### 2026-10-28: frozen two-model comparison and vertical DAG fallback

The isolated evaluation endpoint now binds `openai-codex/gpt-6-astra`; the live
PiDog model remains `gpt-5.6-luna`. The configured evaluation prompt digest is
`ece52a49101c48a666dbba9e99293fba0e4370119d442e239726f7a7b1c1dbd0`.
This was checked from owner configuration separately from returned model
identity; the wire protocol itself does not attest a system prompt.

Both models have fourteen first attempts on identical question identities,
images and prompts. Astra stopped at question11's15-second deadline; only the
three unattempted questions were collected in a separate batch. The deadline,
malformed JSON and invalid reveals remain failures; none was retried or repaired.
With the previous committed renderer, Luna encodes10/14 and Astra8/14.
Completed-response medians are3.992s and7.748s respectively; Astra's all-attempt
median including the timeout is8.201s. These are model/IPC timings, not Respond
or tablet-visible latency. This small single-sample corpus is not a broad model
ranking. Side-by-side cumulative previews and individual visual reviews are in
`OUTBOX/general-relations-eval-20261028/two-model-comparison/index.html`.

Astra supplies a useful explicit AND junction in its dependency explanation,
but the renderer prematurely stops at a failed connector arrangement. Spatial
routing failures now have a distinct exception, and may try the same bounded
layout alternatives as label-placement failures. DAG ranks may advance down
the page after existing horizontal arrangements fail: the coordinate transform
preserves ranks, sibling order, original objects, endpoints, labels and reveals.
At most eight compositions are tried, not an unbounded search or model retry.
Malformed schemas, invalid reveal sequences and native budgets still hold.

The clean staged snapshot passes525 Python tests. The new generic join tests
use mathematical, equipment and approval vocabularies and check unchanged
semantics, deterministic output, route clearance and native limits. Renderer-only
replay now encodes Astra9/14, Luna10/14; all74 previously accepted cumulative
SVGs remain byte-identical. The recovered four-stage AND lesson was visually
inspected; one full native compilation took177ms, not a benchmark. Updated
side-by-side output is `OUTBOX/general-relations-eval-20261028/`
`two-model-comparison-vertical/index.html`. Raw first attempts and baseline
comparison are retained separately. No tablet deployment or tablet proof is
claimed by this change. Cycle layout, explicit-coordinate failures, invalid
model reveals, fresh handwritten reliability and rollout remain open.

### 2026-10-28: compact cyclic layout with annotation headroom

The frozen Astra cycle answer was semantically more useful than the earlier
Luna answer: it distinguishes invisible vapor from surface liquid and returns
precipitation to the surface. It was still held by joint label placement.
Diagnostic enumeration showed that merely permuting the four outer corners
did not fit its full labels. A compact row-major grid leaves a spare column
for returning edges and annotations. This is a final bounded layout candidate
for any three-to-six-object network, derived from count and existing traversal
order, not from subject names, labels or question IDs. It also works for cycles,
where the ranked DAG fallback is unavailable. At most ten compositions are
attempted. No model calls, schema relaxation, coordinate-answer repair, label
shortening, changed endpoints or discarded ink are involved.

The clean candidate passes 527 Python tests, including a cycle entered from
outside, two unrelated workflow/equipment vocabularies, all supported object
counts, native budgets, and bounded typed-error handling. The additional
vocabularies verify that existing successful arrangements stay preferred;
the compact layout is not claimed to fit every possible label set.

Replaying exactly the saved first attempts now encodes 10/14 answers for each
model. All 78 previously accepted cumulative SVGs are byte-identical. The four
recovered cycle stages were visually inspected: distinct vapor representation,
readable labels and a closed return connection. Arrows remain explicitly
schematic process relations, not physical trajectories; a spatially realistic
illustration would still be more intuitive. One full native compilation took
334 ms (single observation, not a latency benchmark). Raw answers, initial
comparison, and intermediate renderer replays remain separate.

Evidence: `OUTBOX/general-relations-eval-20261028/`
`two-model-comparison-compact/index.html`, with all stages, failures and visual
reviews. Astra still has one malformed JSON answer, one deadline, one empty
reveal and one repeated reveal. Luna still has four explicit-coordinate/layout
failures. Neither result satisfies the live reliability goal. The read-only
device check returned reachable telemetry with `active:false`; no device input
or deployment was performed. Production rollout still lists only the isolated
test notebook. Fresh handwriting tests, the second notebook and broad rollout
remain outstanding.

### 2026-10-28: separate prompt-contract experiment

The remaining first-pass failures include fixed-label collisions, malformed
numeric JSON and empty/repeated reveal groups. The candidate prompt makes
anchored labels the default, describes component steps as nonempty disjoint
groups of IDs, places prose-only conclusions in the takeaway, and asks for
numeric literals. It does not add topic recipes, repair answers, weaken
validation or replace the integral and odd-square worked examples.

`notebook_model_eval.py prompt-variant PACKET DEST --system-prompt FILE`
creates a new packet with identical question images, question text, order and
context. It validates the complete baseline and bounded UTF-8 candidate before
creating output; existing destinations are refused. Per-question prompt
identities are recomputed, and the parent packet/prompt hashes are retained.
This is an offline input-preparation operation, not a host configuration or
model call. It leaves saved baseline answers untouched.

The clean staged snapshot passes 530 Python tests. New tests cover exact image
preservation, changed prompt identities, untouched baseline bytes, no overwrite,
tampered inputs and invalid candidate prompts. Prompt assertions verify the
instructions, not actual model adherence. The frozen 14-question variant is
`OUTBOX/general-relations-eval-20261028/prompt-contract-packet/`; its prompt SHA
is `3374ea2c9d7984f676155510027464e12b77e4916cd003c0aa453a69a84d7b14`.
Its diff against the original prompt contains only the contract changes above.
No candidate inference, live-prompt change or tablet deployment has occurred.
Next: review, install the candidate on the isolated evaluation endpoint, and
collect separate first attempts before judging its effect on lesson quality.

### 2026-10-28: Astra prompt experiment — no net acceptance gain

The owner configuration now points the isolated endpoint at the candidate
prompt; a new host process started after that configuration change, and the
endpoint returned Astra identities. The live model remains Luna. The wire
protocol still does not attest the system prompt; these are separate checks.

All fourteen candidate questions were attempted exactly once. The collector
stopped at each 15-second deadline; explicit continuations covered only
previously unattempted questions, in three disjoint batches. The two deadlines
are retained. Ten answers compile versus ten baseline answers replayed with
the same renderer. Blue-sky now has valid JSON and a clear anchored-label ray
diagram; sensor-alarm now has valid additive steps. Transistor timed out, as
did inverse-mapping. Proof-dependency and dependency-failure no longer have
reveal-grammar problems, but their expanded labels exceed 64 strokes in one
stage. They remain held, with no shortening, regrouping or model repair.

Completed-response median is 9.540s (12 complete responses), versus baseline
7.748s (13). All-attempt median including deadlines is 9.799s versus 8.201s.
These are model/IPC timings, not tablet visibility. One sample per question
does not establish a causal prompt improvement or reliable latency change.
No live prompt promotion is justified by these results.

All cumulative stages of the ten accepted lessons were visually inspected.
The growth comparison is numerically correct but weakly emphasizes its small
gap. The water-cycle graph has correct process connections yet places vapor
and clouds below surface water while describing rise/fall; it needs a more
meaningful spatial representation. Compiler acceptance alone is insufficient.
Raw responses, batch provenance, stage previews and individual reviews live
under `OUTBOX/general-relations-eval-20261028/`
`astra-prompt-contract-all-first-attempts/`.

The comparison viewer now supports explicit `--prompt-packets BASE CANDIDATE`.
It verifies both packets, exact input image bytes/context/question order,
parent provenance and each rendered run's packet hash before allowing changed
instructions. Default model comparisons still reject differing packets. The
header discloses the prompt change and both expected digests; no manifest hash
is rewritten to defeat the ordinary guard. The clean snapshot passes 531
Python tests. Side-by-side evidence is `OUTBOX/general-relations-eval-20261028/`
`astra-prompt-contract-comparison.html`.

Next: run the same candidate with Luna via an evaluation-only model switch,
then inspect how semantic stages should fit bounded native rendering work
without making the model count plotter-font strokes. Existing resource caps
remain intact. No tablet input, deployment, broader rollout or new live
acceptance result occurred in this experiment.

The matching Luna candidate run is also complete: fourteen calls, one attempt
each, no deadline or retry. Ten responses validate, but one is a text-only
gravity fallback, leaving **nine visual lessons**, versus ten in the frozen
baseline replay. Median complete response is 3.595s versus baseline 3.992s;
this single sample is not proof of a latency improvement. Four holds remain:
zero-length drawing geometry, a self-connection, unroutable reciprocal
connections, and omitted reveal IDs. All nine accepted lessons were visually
inspected. The Bayes counts are correct but three captions describe additions
one step before they appear. The sky's causal chain does not meaningfully
illustrate scattering, and the proof graph leaves conjunction in prose.
These findings rule out promoting the candidate on validation counts alone.

Luna raw answers/reviews are in `luna-prompt-contract-first-pass/`, under the
same OUTBOX evaluation root. The baseline-vs-candidate report is
`luna-prompt-contract-comparison.html`; the candidate Luna-vs-Astra report is
`candidate-two-model-comparison.html`. Neither baseline answers nor rendered
geometry were edited to obtain a pass. Live prompt and tablet remain unchanged.

Diagnostic-only expansion of the two held Astra stages counts 84 and 87
strokes, respectively, while their point/time costs are 1432/18.768s and
1636/20.814s. No native assets were created from these rejected stages. The
existing chunk encoder applies the 64-stroke cap to the whole original stage,
so merely turning chunk reveal on cannot fix them. Any future separation of
semantic steps from native batches needs explicit end-to-end tests preserving
caption order, every stroke, per-batch limits, whole-lesson limits and existing
page-change holds. Do not silently increase caps or make the model count
plotter-font segments. The reciprocal-route failure is another general
renderer issue suitable for same-answer offline diagnosis.

### Bounded connector detours (2026-10-28, offline only)

The saved Luna many-to-one/reverse-map answer exposed a missing route family:
three connectors fit, but the fourth needed to leave an occupied side and
return around the outside. No answer rewrite, additional model call, moved
object or topic rule is needed. The connector renderer now considers a finite
set of contour-normal stubs joined through outer orthogonal lanes, only after
the existing curved/straight candidates fail. At most 448 additional candidates
are generated per edge. Retracing and self-crossing candidates are rejected;
the existing final-scene obstacles, prior shafts, arrowhead clearance, region
and native-budget checks still apply.

Network layout needs a two-pass search: all existing (at most ten) arrangements
with ordinary routes first, then those arrangements with detours enabled.
An initial implementation tried detours too early and displaced a cleaner
vertical composition; a regression test caught this. The corrected ordering
preserves successful prior compositions. Spatial search is bounded to twenty
arrangements; malformed input and native-budget failures still stop, not retry.
This is renderer search, not model retries or a relaxation of ink limits.

Clean candidate snapshot: `OUTBOX/connector-detour-final-u07d4hqs/tools/herd-board`.
All 535 Python tests and 31 Node adapter tests pass from that snapshot, excluding
the unrelated in-progress motif drafts. The tests cover reciprocal directions,
mirroring, vertical layouts, circles/rectangles, collision rejection, bounded
search, native caps and unchanged clean-layout preference.
Four fixed-answer replays live under `OUTBOX/general-relations-eval-20261028/`:
`luna-detour-ordered-replay`, `astra-detour-ordered-replay`,
`luna-baseline-detour-ordered-replay`, and
`astra-baseline-detour-ordered-replay`. All **159 previously accepted stage
SVGs are byte-identical**. The candidate Luna run gains one visual answer
(nine to ten of fourteen); the other three runs retain ten visual answers.
Raw answers and packets are unchanged. This does not fix the remaining model
semantic/reveal mistakes or the excessive-label stroke-budget failures, and
does not justify promoting the experimental prompt.

All three newly accepted stages were inspected in the cumulative contact
sheet `luna-detour-review-v2/inverse-mapping.png`; review details are in
`luna-detour-ordered-replay/connector-review.json`. Original circle positions,
labels, captions and four arrow directions survive. Native assets validate
offline within the existing limits. The long outer right-angle return is
clear but less organic than the curved routes. No tablet interaction,
deployment, broader rollout or new first-visible latency result is claimed.

### Continuous plotter glyphs (2026-10-28, offline candidate)

The label-heavy stage failure did not require changing the model's answer or
splitting a semantic stage to evade the ink cap. The original alphabet lifts
the pen between connected parts of many letters. A bounded static-font compiler
now joins a glyph's connected components using only its existing segments,
occasionally retracing a short segment. Exact rational intersections and a
shortest-path pairing of branch endpoints preserve the original visible line
union. Dots and separate letters are never bridged. Already continuous glyphs
and candidates with a higher estimated drawing cost keep their original paths.
The cache is bounded to 128 glyph entries; the font has 92 glyphs. This compiler
is not exposed as an agent command and does not reorder diagram stages/arrows.

This is an actual reduction in pen-down contacts, not a renamed budget or a
larger cap. All existing stage/whole-lesson native validations still run. The
tradeoff is slightly more sampled points for retraced letters. A dense-stage
regression test exposed this: a previously valid 49-stroke/2,917-point stage
crossed the point cap with continuous labels. Pure compilation now retries
once with the original glyph paths, only after a typed native resource failure.
The complete same-input plan and all original limits are checked again; no
caption, coordinate or model response is repaired. Nested compilation shares
one outer retry, and context-local font selection isolates concurrent requests.
Schema, collision and provider errors do not trigger this fallback. The dense
regression restores the exact original plan, including its 29.683-second stage.
The candidate remains offline pending review and an observed tablet
motion/pen-weight test.

The clean snapshot `OUTBOX/gf-ot9xhfsd/tools/herd-board`
passes **544 Python tests and 49 Node tests**. An initial longer snapshot path
failed two IPC fixtures at the existing 100-byte Unix-socket path guard; the
same sources pass from this shorter path without weakening that guard.
Tests verify exact segment-union preservation for
every glyph, unchanged extents/advances, disconnected dots, deterministic
bounded work, no increased estimated per-glyph drawing cost, and enforcement
of the real 64-stroke/3,000-point/30-second caps. Existing stroke-count fixtures
were updated to their measured lower contact counts; geometry assertions and
budget checks remain. Additional tests cover the exact dense-stage fallback,
typed-error-only retry, nested retry bound, context restoration and concurrent
request isolation.

Four unedited 14-question saved-answer runs were replayed without inference.
The candidate Astra run improves from ten to **twelve visual lessons**; its two
remaining failures are the original model deadlines, not renderer successes.
The other three runs retain ten visual lessons each, with no previously
accepted answer rejected. Candidate Luna still also has one text-only fallback,
which is not counted as a visual lesson. All forty previously accepted visual
plans retain identical procedural-layout, anchored-label and connection
metadata. Comparing all 162 earlier cumulative stage PNGs gives a largest mean
per-channel difference of 0.415/255. Font tests
prove exact glyph geometry; the raster comparison is supplemental, not a claim
that native e-ink pen weight is unchanged.

The formerly rejected proof-dependency stage now uses **56 strokes / 1,503
points / 17.447 estimated pen seconds** (previously 84 strokes). The service
dependency stage uses **60 / 1,700 / 19.500** (previously 87 strokes). Every
cumulative stage in those two new lessons was visually inspected. Captions
match the additions and the AND/OR distinctions are correct, but some long
labels remain too far from their arrows and the diagrams still need aesthetic
polish. This is not a claim of proof verification or finished lesson quality.

Evidence under `OUTBOX/general-relations-eval-20261028/`:
`astra-continuous-font-replay/font-review.json`,
`astra-continuous-font-review/`, `astra-continuous-font-comparison.html`, and
`two-model-continuous-font-comparison.html`. Native playback previews validate
the exact encoded assets and caption-before-ink order offline. No new model
request, tablet input, deployment, first-visible latency measurement or broader
notebook rollout occurred during this experiment.

The final budget-safe implementation was independently replayed into
`astra-continuous-font-safe-replay`, `luna-continuous-font-safe-replay`,
`astra-baseline-continuous-font-safe-replay`, and
`luna-baseline-continuous-font-safe-replay`. It retains respectively 12, 10, 10
and 10 visual lessons. All 169 SVG previews (including diagnostic previews)
are byte-identical to the earlier continuous-font renders. The updated
side-by-side artifact is `two-model-continuous-font-safe-comparison.html`.

### Source-grounded research-math stretch trial (2026-10-28)

James asked whether a fresh query could illustrate the central ideas behind
recent major proofs. Three new questions were tested through the same general
renderer and unchanged prompt-contract system prompt: the hat's forced
hierarchy, the three-dimensional Kakeya dimension result and tube-overlap
strategy, and unramified geometric Langlands. Each question received a short
evaluator-prepared source brief, not a canned drawing or theorem-specific
component. Sources are the authors' [hat paper](https://arxiv.org/html/2303.10798v3),
[streamlined Kakeya paper](https://arxiv.org/html/2601.14411v2), and
[Gaitsgory's IHES account](https://www.ihes.fr/en/gaitsgory-glc/).
This tests grounded explanation, not autonomous source retrieval or research
proof verification. The fixed review rubric distinguishes mathematical scope,
analogy, meaningful visual evidence, caption order and rendering acceptance.

The current fast single-pass configuration did **not** meet this challenge:

| Condition | Attempts | Complete drafts | Accepted visual lessons | Observed wall time |
|---|---:|---:|---:|---|
| PiDog / returned `openai-codex/gpt-5.6-luna` | 3 | 3 | 0 | 5.801 / 6.587 / 5.348 s |
| Owner-configured `openai-codex/gpt-6-astra` | 3 | 0 | 0 | all hit the 15 s deadline |

Same typeset images and source context, minimal reasoning, 2,400 output-token
cap, no tools or answer repair. Each question had one attempt per configured
model. The collector stops on deadlines; the next run included only questions
not previously attempted. The expected Astra configuration, unchanged prompt
hash and new live socket owner were verified before calls, but no successful
response returned its model identity. Do not invent completion timings, token
counts or explanation-quality scores for those timeouts.

All three Luna drafts failed automatic label placement. The hat draft crowded
its nested contours; Kakeya placed multiple long labels around crossing
segments and narrow tubes. The Langlands draft also omitted all six declared
relations from the reveal sequence, a semantic error currently obscured by
the earlier layout failure. The prose contains useful qualifications, but
the intended drawings often name a concept instead of demonstrating it.
Neither a finite sketch nor a compiler pass proves a research theorem.

A disposable offline probe tried bounded interior/edge-adjacent label
positions without changing model outputs or collision checks. It yielded
zero complete valid lessons and was **not installed**. A larger coordinate
search is not supported as the solution by this evidence. The next general
design work is to reserve readable annotation space as part of semantic scene
composition, validate reveal completeness before layout, and evaluate a
bounded explanation-plan stage separately before adding any second model
pass to the live latency path. Do not add a hat/Kakeya/Langlands renderer or
hand-repair these outputs and call them generated successes.

Frozen inputs, untouched outputs, individual deadline records, source/rubric
data and the two-model comparison are under
`OUTBOX/math-concept-eval-20261028/`. See `review.json`, `questions.json` and
`two-model-comparison.html`. Packet SHA-256:
`a5351a0594873c2341e39fe28f0d3a40c607af486e566a5ae8f62c9ecd94ec26`.
The compiler snapshot is `OUTBOX/gf-ot9xhfsd/tools/herd-board` (82d7504
implementation). No tablet input, production deployment, live handwritten
test or new Respond-to-first-visible measurement occurred. After all three
Astra attempts were terminal, the isolated evaluator was restored to Luna:
the owner configuration and unchanged eval prompt digest were checked, and
replacement process PID 70172 (20:09:29) owns both notebook sockets. This is
configuration/listener evidence, not an extra successful inference. Live
model and prompt changes were not requested.

### Reveal-contract preflight (2026-10-28, offline)

Semantic networks now validate the complete declared-ID/reveal partition
before generating any objects, connector routes or label candidates. Missing,
unknown or duplicated IDs, prematurely revealed connections, malformed labels
and caption markup are rejected directly. Same-step endpoint introductions
remain allowed; no graph, caption or reveal sequence is completed or repaired.
This removes the misleading layout diagnosis for the research-math Langlands
draft, which omitted all six relationships from its reveal sequence. It does
not make that draft a valid or successful lesson.

The isolated staged snapshot `OUTBOX/np-4zj6ajoo/tools/herd-board` passes
**551 Python tests**, including seven new preflight tests that assert zero
geometry/routing/label-allocation calls for invalid plans. Four saved-answer
runs retain 12/10/10/10 visual lessons and all 169 SVG preview files remain
byte-identical to the prior budget-safe font renders. Evidence directories
end in `-network-preflight-replay`; the math trial's direct missing-reveal
diagnosis is in `math-concept-eval-20261028/luna-network-preflight-replay`.
No model call or tablet input was needed for this change.

A separate, uninstalled label-first composition probe measures icon and text
cells before assigning positions, then routes around reserved label space.
It is not yet a replacement for the established layouts: some graphs fit but
others still cannot route, and mathematical explanation quality is not solved
by fitting labels. The experiment also exposed a virtual-arrowhead-point
boundary issue for near-edge paths; that needs an independent geometry test.

### Route tangent bounds and composition experiment (2026-10-28)

The route helper used a virtual point 30 units behind an arrow tip to compute
its fixed-size head, then validated that invisible point as if it were emitted
ink. Near the page edge this rejected valid heads. It now uses the same arrow
geometry function directly and validates every emitted shaft/head point with
the original drawing primitive checker. No point is clipped and no ink-bound
check is weakened. Tests cover all four page edges, exact equivalence for 72
interior orientations, and continued rejection of genuinely out-of-bounds ink.

The isolated staged snapshot `OUTBOX/ar-jhme552b/tools/herd-board` passes
**554 Python tests and 49 Node tests**. Replaying the four saved-answer sets
retains 12/10/10/10 visual lessons and all 169 prior SVG previews byte-for-byte;
evidence directories end in `-arrow-bounds-replay`. This fixes a generic
geometry bug but does not claim another model-answer success or tablet proof.

The separate label-first cell experiment was rendered side by side on seven
already accepted causal answers from the two prompt-contract runs. Only three
prototype compositions pass, versus all seven established layouts. Final
frames for those three were inspected: the service-dependency layout has
cleaner grouping, but the lemma graph wraps short names needlessly and the
sky example becomes a long circuit of arrows without adding explanatory
evidence. Therefore the prototype is **not installed**. Its stage-by-stage
comparison is `OUTBOX/math-concept-eval-20261028/reserved-layout-preview/review.html`.
This comparison does not repair any research-math answer or improve its score.

Next candidate: a measured-label graph layout engine, not another hand-tuned
grid. [ELK Layered](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html)
supports edge labels, explicit ports and compound graphs, and can supply
straight, orthogonal or spline routes. Its
[node-size constraints](https://eclipse.dev/elk/reference/options/org-eclipse-elk-nodeSize-constraints.html)
account for node labels when determining required space. Graphviz also emits
[layout JSON](https://www.graphviz.org/docs/outputs/json/), but no `dot` or
`neato` executable was found in the current command path. Neither dependency
was installed in this pass.

The evaluation contract for an external layout candidate is strict: use
measured plotter-label extents, fixed supported icon/port geometry and bounded
six-node/eight-edge data, never model-authored code or file paths. Preserve
graph direction, text and reveal order; never use schematic routing for a
physical ray or force. Do not shrink labels or exceed the canvas to obtain a
pass. Layout output still goes through the existing geometry, collision,
whole-lesson and native pen-budget validators. A pinned, isolated offline
dependency trial must show better readable compositions with bounded runtime
before it can replace the current router or enter the live workflow.

### Measured ELK trial: do not deploy (2026-10-28, offline)

The pinned `elkjs@0.12.1` package was fetched with `npm pack --ignore-scripts`
into `OUTBOX/elk-layout-eval-20261028`, not installed in either service tree.
Its SHA-512 integrity matches the registry metadata:
`IhMYKHE4S2vtx0QrhBP3lYOIKDeIiJXBrdq9MGYkuB8ZHqhrBnHNfSUndjXFewrX1CPK8chwq+2NA0K0hliYuw==`.
The archive retains its EPL-2.0 license and secondary-license notice. No
dependency or production configuration was changed. Any future distribution
needs an explicit dependency/license review; this experiment does not provide it.

The probe measures the existing 18-unit plotter labels, preserves icon sizes
and physical contour ports, and tries four bounded combinations: RIGHT/DOWN
flow and unwrapped/two-line labels. Each ELK subprocess has a three-second
deadline and fixed seed. No model request, raw-answer edit, caption rewrite,
font scaling, coordinate clipping or relaxed canvas/pen budget is involved.
Returned geometry must pass object/label clearance, endpoint attachment,
connector collision and original native compilation/playback checks. Five
adapter contract tests pass, including mandatory native-budget-gate execution.

Four previously collected 14-question runs contain 17 causal drafts. Four
have invalid endpoint/reveal contracts and remain rejected before layout.
The other 13 already compile with the established renderer. Results on those
same 13 valid drafts are:

| Composition | Valid layouts | New accepted model answers |
| --- | ---: | ---: |
| Established renderer | 13/13 | baseline |
| ELK layered, measured labels, wrapping, distinct contour ports | 3/13 | 0 |
| ELK node/label positions plus established routes/edge-label placement | 6/13 | 0 |

The first default layered attempt was too wide and merged arrows attached
to shared ports. ELK's documented
[graph wrapping](https://eclipse.dev/elk/reference/options/org-eclipse-elk-layered-wrapping-strategy.html)
and distinct physical ports helped some graphs, but did not make the full
collection fit. Long connector annotations force large layers; wrapping
often trades excessive width for excessive height. The hybrid avoids that
reservation but reintroduces edge-label placement failures. It is not a
general solution to the composition problem. Neither candidate replaces the
current renderer, and neither is installed as an accumulating fallback.

Final previews were inspected for the lemma, sensor, sky and proof-dependency
graphs. Some object/label groupings are cleaner, but some routes take long
detours or turn short names into unnecessary two-line labels. The sky graph
also illustrates a content limitation: a schematic causal arrow is not
evidence for physical scattering geometry. Layout acceptance cannot certify
the model's explanation or scientific interpretation.

Evidence is in `OUTBOX/elk-layout-eval-20261028/`:

- `benchmark.py`, `layout.cjs`, `test_probe.py`: isolated reproducible probe.
- `elk-verified/` and `hybrid-verified/`: manifests, returned layout graphs,
  accepted plans and stage-by-stage `review.html` comparisons.
- The 52 hybrid layout/validation attempts have median 141.70 ms and maximum
  195.97 ms, including Node startup. These are **offline composition times**,
  not model latency or Respond-to-visible latency.
- All 40 hybrid comparison SVGs are byte-identical on the repeat run after
  adding an explicit object-overlap gate. No physical-device test occurred.
- Early `first-pass` and `measured-pass` directories record harness failures
  (Node package-boundary lookup, then unsupported worker-shim termination),
  not renderer-quality results. They are excluded from the comparison.

MyDude review was requested through Buzz (queued request
`2d6db3d799d5732deec08a7eab0901ce`); delivery/review approval is not established.

### Next design boundary: explanation intent before composition

This is a proposed next experiment, **not an implemented capability**. It
must address the failed advanced-math trial as well as ordinary questions.
Replacing the graph library alone is insufficient: naming three boxes
"coarse", "fine" and "proof" does not illustrate a multiscale argument.

Keep three responsibilities separate:

1. **Source-grounded explanation plan.** Identify the precise claim, required
   assumptions and one visible reason for each step. Distinguish an exact
   construction, a schematic analogy and a proof outline explicitly. Every
   proposed drawing operation must support the caption rather than decorate
   it. A recent-proof request needs verified source material before teaching;
   the earlier evaluator-supplied briefs did not prove autonomous retrieval.
2. **Declarative scene composition.** Keep object identity and relationships
   separate from position, label width and stroke sampling. Reserve readable
   annotation space before geometry. Labels name what must remain identifiable
   in the picture; captions carry reasoning. A future contract may permit
   explicitly unlabeled relationships when the caption communicates their
   meaning, but it must not silently discard labels from existing answers.
   Physical geometry and schematic routing remain distinct types.
3. **Deterministic native playback.** Produce measured glyphs, contours and
   routes; validate the complete reveal plan and budget; then play caption
   before ink. The model never emits hundreds of timing/sampling points.
   Preserve page-change holds and existing user ink exactly as before.

Do not immediately add another model round trip to the live response path.
First evaluate a compact planning representation offline with fixed source
briefs and untouched questions. Compare direct generation against planning
plus deterministic compilation, counting **all** calls, tokens, timeouts and
time to a renderable first step. No hand-authored replacement answers, hidden
retries or theorem-specific renderer branches count as generated successes.
The ordinary 14 questions and held-out variants remain regression coverage;
the three research-math questions remain a separate stretch set.

The adoption gate is both explanatory quality and geometry: the picture must
make the caption's reason visible, stay readable, preserve declared meaning,
and fit the original native limits. A new plan format is not justified merely
because its JSON validates. Broader notebook rollout and research-math claims
remain unproven until the corresponding generated and live-device tests pass.

### Single-pass teaching-plan experiment prepared (2026-10-28)

`notebook_teaching_prompt.py` creates an **offline-only candidate**, not a new
live prompt selection. It replaces the teaching preamble of an explicitly
supplied frozen prompt and retains the full vocabulary, scene schemas, native
limits and worked examples byte-for-byte. No new response fields or second
model call are introduced. Existing `lesson`, `answer` and `clarify` modes,
the simple-shape exception, complete reveal partition, caption-before-ink
order, numeric-literal requirement and source/input trust boundaries remain.

The experimental change is pedagogical: choose one visual argument; show the
actual comparison, construction or dependency; use labels for indispensable
names and captions for reasoning; distinguish a schematic, finite example and
general proof. It contains no rules keyed to a question or theorem name. The
intent is to reduce concept-naming diagrams, not to make an invalid drawing
pass or weaken mathematical expectations. Whether the prompt works is **not
yet established**.

This first experiment keeps planning and the final lesson in one response.
Official OpenAI [latency guidance](https://developers.openai.com/api/docs/guides/latency-optimization)
recommends considering combined requests before adding serial round trips.
The [structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs)
also distinguishes schema adherence from correctness: structured answers can
still contain mistakes. These are design considerations, not evidence of a
measured improvement in this engine or a claim that its custom transport uses
provider-enforced Structured Outputs.

Frozen artifacts: `OUTBOX/teaching-plan-eval-20261028/`:

- Candidate prompt SHA-256:
  `8eae456c2923da71b096fbf3673b2d12225167665a10be71a1247cb831511761`.
  The candidate is 21,245 bytes versus 20,232 for the baseline; it adds teaching
  guidance, not a smaller input prompt. Output schema and requested cap do not change.
- `ordinary-packet/packet.json`: 14 unchanged questions, image bytes, contexts
  and ordering; SHA-256
  `95161562bc376498c229ec9444e5c66df3c37ce5689d2c2869b3174ab7816dfc`.
- `research-packet/packet.json`: the same three research-math questions and
  evaluator-supplied source briefs; SHA-256
  `76ef5e6dbdddb3e431aa01e388b1e5314b89cde9dac389e27d9595f1545c1a1e`.
- `review-contract.json`: criteria frozen before candidate calls. Review
  correctness, visible reasoning, scope, progression, readability and economy
  separately from native validity. Criteria are not sent to the model.

The full clean staged snapshot `OUTBOX/tp-vHAJ58n8/tools/herd-board` passes
**561 Python tests and 49 Node tests**. Seven new tests cover the frozen
contract boundary, original modes, general teaching principles, invalid and
oversized inputs, exclusive output creation and preservation of the original
prompt. The test activity messages are mocked fixtures, not tablet evidence.
Independent packet checks confirm unchanged inputs in both sets.

No candidate model calls have been made at this checkpoint. MyDude was asked
to install the candidate on the isolated evaluator only (queued request
`c86d4c2c7d5e603319e50a578114940f`), retaining Luna/minimal/2400 tokens and all
live settings. A read-only check still found the previous eval prompt hash
`3374ea2c9d7984f676155510027464e12b77e4916cd003c0aa453a69a84d7b14`
and socket owner PID 70172. Do not run the candidate packet against that old
configuration and label it a candidate test. Next is verified eval activation,
one unedited attempt per question with the same 15-second deadline, and
side-by-side visual/content review. No tablet proof or rollout is implied.

### Teaching-plan trial completed: do not promote (2026-10-28)

This supersedes the preparation checkpoint above. All 17 candidate questions
were attempted once against the verified candidate eval prompt. After a
collector stopped at its deadline, only the two **never attempted** ordinary
questions were placed in a continuation packet; no failed question was rerolled.
The model, minimal reasoning, 2,400-token request cap, 15-second deadline,
question inputs and renderer remained unchanged. No tablet was touched.

| Offline outcome | Ordinary baseline | Ordinary candidate | Research candidate |
| --- | ---: | ---: | ---: |
| Questions attempted | 14 | 14 | 3 |
| Raw replies received | 14 | 12 | 2 |
| Renderable visual lessons | 10 | 9 | 0 |
| Accepted text-only answers | 1 | 1 | 0 |
| Rendering/contract holds | 3 | 2 | 2 |
| Deadlines without a reply | 0 | 2 | 1 |
| Median completed reply, ms | 3594.6 | 3661.2 | 7086.4 |

Completed-reply timing excludes deadlines and all tablet capture/insertion
work. Output-token totals likewise omit timed-out responses and must not be
used to claim a token saving over the fully completed baseline. One sample
per question does not establish a statistically reliable prompt regression.
It does establish that this candidate has not earned promotion.

Compiler acceptance overstates explanatory success. Review of all nine
accepted ordinary previews found six useful visual explanations, with a
caption-length/readability caveat for compound interest. Three others showed
substantive limitations: water-cycle states were conflated; an inverse-mapping
caption claimed a reversal that its marks did not show; and two arrows into
a theorem did not distinguish jointly required premises from alternative
sufficient routes. This is DJ Codex's provisional visual review, not an
independent mathematical assessment or a production reliability rate.

The research trials failed on joint label placement, an overlength anchored
label and a deadline. Their raw drawings also did not adequately demonstrate
the mathematical ideas: nested empty outlines are not a recursive tiling
construction, and marks named finer scale do not establish overlap control.
Removing a layout rejection would not alone turn either into a good lesson.

Portable records are committed under `evaluations/teaching-plan-20261028/`:
the pre-call review contract, numerical results and criterion-by-criterion
review. Full untouched answers, run metrics, rendered stages and paired HTML
remain in `OUTBOX/teaching-plan-eval-20261028/`, particularly
`ordinary-comparison.html` and `research-comparison.html`. No raw response
was repaired for this comparison; missing answers remain missing.

The evaluator was restored to prompt SHA-256
`3374ea2c9d7984f676155510027464e12b77e4916cd003c0aa453a69a84d7b14`.
A fresh read-only configuration check confirmed that digest and Luna after
the run. Configuration is external verification, not wire-level attestation
of a prompt. Production prompt, server and tablet were not changed.

**Architecture consequence:** do not treat every bad explanation as a missing
renderer feature. Existing reciprocal `connect` operations already express
the reverse arrows omitted by the candidate, and their direction/attachment
are covered by renderer tests. Do not add a theorem-specific inverse primitive
or silently infer missing operations from captions. Likewise, do not relax
native budgets or shorten mathematical labels behind the agent's back.
Keep three failure classes separate: missing/incorrect explanation plan,
invalid scene contract, and valid intent that cannot be laid out. Compare
model-side interventions independently from compositor changes. A new scene
operation must have a general semantic purpose and a deterministic lowering;
it must not merely make one saved answer pass.

MyDude was asked for an architecture second opinion before the next model or
language experiment (queued request `356ceb1c74c82d6938ed33b4a4103c54`). No
additional model/configuration change was requested by that review message.
All rollout, fresh-handwriting and tablet-persistence gates remain open.

### Capacity diagnostic and bounded joint routing (2026-10-28)

The next experiment retained the restored baseline prompt and existing
vocabulary. It used the already-evaluated `openai-codex/gpt-6-astra`, minimal
reasoning and 2,400 requested output tokens, with an explicitly separate
**30-second offline deadline**. This is a capacity diagnostic, not a change
to the live under-ten-second target or a controlled improvement claim over
the earlier 15-second runs. Question images, text, supplied source briefs,
order within each packet and native limits were unchanged.

All 17 questions were attempted once, with no repair, fallback or reroll.
All 17 returned raw answers; none timed out. Original compiler results:

- **12/14 ordinary visual lessons**, no text-only fallback. Median completed
  response 10.075 s; median first text 2.565 s. Two replies exceeded 15 s.
- **1/3 research visual lessons**. Completed replies were 20.871, 27.003 and
  26.103 s. All three miss the old 15-second cutoff. First text is not a
  validated lesson or a visible tablet response.
- The successful Kakeya answer draws three equal-length sample segments,
  thickens them into overlapping tubes and adds narrower outlines. The raw
  geometry has equal 200-unit lengths and 20-to-6-unit widths. It explicitly
  distinguishes planar samples from the three-dimensional theorem and full
  dimension from positive volume. This is a useful conceptual introduction,
  **not a proof or a demonstration of the anti-clustering estimate**.
- The hat answer exceeded an anchored-label length cap. Langlands exceeded
  the native pen budget. The ordinary failures were a connector-allocation
  dead end and an empty final reveal group. None was silently repaired.

All accepted contact sheets were visually inspected. The generated
proof-dependency plan explicitly introduced an `A AND B` box; water-cycle
states included separate vapor and cloud droplets. These use existing
primitives and demonstrate that those missing distinctions were not blocked
by a lack of topic-specific engine components. A single trial still does not
establish reliability. Detailed provisional review is saved with the results.

`notebook_model_eval.collect` now records actual request deadlines in each
run, observation and preview manifest. The comparison page exposes unequal
or unrecorded budgets instead of implying an equal-budget comparison. An
explicit offline-only `--continue-on-deadline` option advances to the next
question once; it never retries the timed-out question. Default behavior
still stops on deadlines, and busy/closed/provider failures stop either mode.
Five new tests cover these semantics. This avoids manually resuming a batch
after every deadline without hiding failed attempts or adding a live layer.

The held five-node merge/split drawing exposed a compositor limitation:
greedily accepting each early route could block the fourth relation. The new
`notebook_relations._plan_routes` first uses the established allocation order.
Only on a route-placement failure does it try cyclic rotations of forward
and reverse allocation orders, with at most **48 route calls** total. Each
call retains existing contour, shaft, arrowhead, obstacle and clearance checks.
This changes planning order, never physical reveal order. Original objects,
coordinates, labels, captions and semantic endpoints are untouched. Other
errors are not treated as routing failures; native budgets still apply to
the complete compiled result.

Mirrored merge/split tests reproduce the greedy failure and verify the new
paths, preserved stage order and collision checks. Existing happy paths keep
their first result. Replaying six saved answer sets preserved **218 accepted
stage SVGs byte-for-byte**, with no lost accepted answers. The identical held
inverse-mapping answer newly renders; this makes the **compiler-only replay
13/14**, not the original model trial. The empty reveal remains rejected.
No question names or expected answers occur in the route planner.

Clean snapshot `OUTBOX/rt-mIdFtA6v/tools/herd-board` passes **569 Python tests
and 49 Node tests**. Existing reciprocal-route test iteration was corrected
to inspect every two-command shaft/head pair. These are offline/mocked tests,
not evidence of new tablet behavior. The native writer and page guards were
not changed.

Artifacts: `OUTBOX/model-capacity-eval-20261028/` contains the frozen contract,
original packets and raw runs, numerical results, `visual-review.json`,
`ordinary-comparison.html`, `research-comparison.html`, contact sheets and
the separately named `route-allocation-replay/`. Portable reports are in
`evaluations/model-capacity-20261028/`. No model calls were used for the replay.

The eval-only model was restored to Luna with baseline prompt SHA-256
`3374ea2c9d7984f676155510027464e12b77e4916cd003c0aa453a69a84d7b14`;
read-only verification found replacement listener PID 87400 owning both
notebook sockets. Production settings and tablet content were not changed.
MyDude code review was requested before deployment (queued request
`ad250a9f3ae1ae8dd711c2e465b9949e`). No rollout approval is inferred.

### Drawing-brief integration: reuse the native boundary (2026-10-28)

James supplied `reMarkable drawing brief for DJ Codex.pdf` and specifically
asked whether its documented reverse-engineering work helps. Yes, but the
projects expose different layers. This is a source/code comparison, not an
installation or a new tablet compatibility result.

| Reference | Verified responsibility | Decision for this engine |
| --- | --- | --- |
| [rmkit lamp](https://github.com/rmkit-dev/rmkit/tree/master/src/lamp) | Stylus/touch event injection; pen down/move/up and procedural shapes. | Compare event framing and device identification with our native input path. |
| [iago](https://github.com/rmkit-dev/rmkit/tree/master/src/iago) | Shape-selection UI built on lamp. | Useful interaction reference, not a lesson planner or persistence API. |
| [rmscene](https://github.com/ricklupton/rmscene) | v6 notebook scene parsing and round-trip format support. | Useful saved-ink verification reference; file-format access does not animate open notebooks. |
| [rm2fb](https://github.com/ddvk/remarkable2-framebuffer) | Shared-memory/message-queue access to the rM2 framebuffer, with Xochitl-version-specific addresses. | Display pixels are not notebook scene objects. Not a replacement for saved native ink. |
| [remagic](https://github.com/maximerivest/remagic) | Installer/tooling for xovi and AppLoad. | Deployment infrastructure, not a missing pen API; no reinstall or developer-mode reset. |
| [Official SDK](https://developer.remarkable.com/documentation/sdk) | Product-specific cross-compilation toolchains, libraries and headers. | Build support does not itself establish an API for editing an open notebook. |

The [lamp implementation](https://github.com/rmkit-dev/rmkit/blob/master/src/lamp/main.cpy)
writes Linux input events, maps display to stylus coordinates, sets pressure,
and sleeps between event frames. It identifies touch/stylus devices by
capabilities among event0–2. Its constants and sampling policy are not a
cross-device calibration guarantee. Our `tablet_live.draw_paths` already
uses the same class of evdev injection, with arc-length deadlines, guarded
emission and pen release on interruption. It currently hardcodes event1 and
an ARMv7 event representation. Those assumptions belong in a verified device
profile, not in model output. Do not copy lamp's defaults or launch it as an
unvalidated bypass around our request/page checks. No upstream code was copied.

The official [Xochitl documentation](https://developer.remarkable.com/documentation/xochitl)
warns that compatibility across versions is not guaranteed and that stored
documents should not be accessed/changed while Xochitl is running. Keep the
existing protected native insertion route; never replace it with live `.rm`
file overwrites. Raw input alone also does not prove persistence or safe
foreground ownership. A replacement adapter needs isolated, attended evidence
for both, using the same compiled fixture as the existing adapter.

#### Consequences for the brief's architecture

Keep separate representations: story intent → typed panel content → measured
layout → ordered strokes → native insertion. Device libraries help the last
boundary; they do not fix missing explanation structure or overloaded labels.
The model describes objects, relations and mathematical data. Deterministic
code owns coordinates, measured lettering, sampling and pace. Keep current
caption-before-drawing playback (James's direct interaction preference); place
captions below their pictures in the final layout. Temporal order and spatial
order are independent.

The brief's ten-panel example needs an explicit upper story/act layer; it must
not silently bypass the current six-step/12,000-point lesson validation.
First implement and preview a bounded panel contract with stable object IDs,
explicit base-panel inheritance and measured text/geometry costs. Reuse must
preserve coordinates, reject forward/cyclic references and never count copied
ink as newly emitted ink. Pagination and multi-act delivery remain separately
unproven until compiled and tested end to end. Whole-plan validation still
precedes any device insertion; no new lease or audit subsystem is proposed.

The newly committed offline resource feedback is a prerequisite, not this
panel architecture already implemented: it makes the existing failures
measurable without altering acceptance, fonts or geometry. The saved Langlands
first stage costs 90 strokes (88 lettering, two geometry) with the continuous
font. A device-library swap cannot reduce that semantic/layout burden.
Next work belongs in content/layout separation and offline panel previews,
not another tablet integration rewrite. Research claims in the brief must
also retain their source/status qualifications before becoming lesson content.

#### Story contract prototype (offline, not installed)

`notebook_story_plan.py` now implements the first representation from the
brief. It is independent of the existing `lesson` response grammar. It accepts
one bounded JSON object with these fields:

```json
{
  "v": 1,
  "mode": "story",
  "audience": "A curious twelve-year-old",
  "template": "explain_concept",
  "question": "What should this explanation answer?",
  "acts": [{"id": "setup", "beat": "One public teaching objective."}],
  "panels": [{
    "id": "first", "act": "setup", "title": "A concrete starting point",
    "question": "What does this panel help the learner understand?",
    "new_idea": "One new idea, not private model reasoning.",
    "visual_kind": "objects", "caption": "A short sentence accompanies the picture.",
    "base": null
  }],
  "takeaway": "The final answer in plain language."
}
```

Templates are `explain_result`, `explain_concept`, `solve`, `compare`.
Visual kinds are `objects`, `number_line`, `graph`, `relationship`, `comparison`,
`geometric`, `equation`, `checklist`. These describe intent, **not renderer
capability promises**. No coordinates, file paths, code, URLs, raw drawing
commands or style fields are admitted. Text uses the existing plain-text
validator. Captions have at most twelve whitespace-delimited words; the parser
does not pretend this proves one sentence, one idea or good teaching.

The planner is bounded to 24 KB, six acts and twelve panels. These are narrative
limits only: no native limit has changed. Every act must have panels, and panels
follow act order. A `base` is an earlier panel ID with the same visual kind.
Forward, self, cyclic, unknown and duplicate references fail. Cross-act reuse
is allowed. A base means that exact historical picture, not whatever happens
to be on the tablet when the next panel begins.

`panel_packet(story, id)` creates the narrative part of a later per-panel shape
request: audience, question, takeaway, current act/panel and only the chosen
base ancestry. It omits unrelated panels and all chat history. It returns
independent data and a canonical story digest so a later caller can detect
mixing revisions; it is not a lease or authority token. No shape-generation
call is installed. The next layer must attach validated immutable base shapes
and preserve their object identities/placement; narrative ancestry alone does
not resolve geometry.

Offline use:

```sh
/opt/homebrew/bin/python3.11 notebook_story_eval.py check story.json new-review-directory
/opt/homebrew/bin/python3.11 notebook_story_eval.py example odd-borders new-example-directory
```

The reviewer saves the unchanged input, an HTML **outline**, per-panel context
JSON and a result record. The outline intentionally has no dummy drawing or
fake animation. `story_valid` is separate from `geometry_validated`,
`native_validated`, `tablet_proven` and `quality_status`. Invalid stories get a
failure record, not a repaired outline. Directories are exclusive; old drafts
are not overwritten. The ten-panel odd-border fixture exercises two separate
home pictures and later returns to their exact earlier states across acts.
It is authored test data, not a new agent success or a prompt-specific engine
branch. The production prompt, model and delivery route are unchanged.

This separation follows the [official structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs)
to use clear structured fields and evaluate their suitability. Local validation
remains mandatory; no claim is made that PiDog's transport already requests a
provider-enforced schema. Mathematical review, visual critique and teach-back
evaluation remain separate from syntactic validation.

Next implementation gate: typed per-panel shapes with immutable base
resolution, measured bounding boxes and renderer-owned layout. Then compile
the entire resolved story against the actual ink limits and produce real
stage SVGs/PNGs before any model comparison or tablet integration. The twelve
narrative panels cannot be passed directly to the six-step native lesson
adapter, and this prototype supplies no such bypass. Multi-region pagination,
whole-story costs, late-panel failure and base reuse must be tested explicitly.

#### Typed data-space panels and real offline previews

`notebook_panel_shapes.py` now supplies the next, still offline, layer. It
accepts a complete validated story and a mapping of panel IDs to independent
`panel-shapes` JSON objects. No model or device call occurs here. The initial
supported subset is one axes frame per picture, mathematical values in that
frame, and relational labels. Object/network arrangements, standalone number
lines, equation objects, page pagination and model-generated panel calls remain
to be connected; unsupported types fail rather than become approximate icons.

```json
{
  "v": 1, "mode": "panel-shapes", "panel": "curve",
  "items": [
    {"id": "square", "type": "plot", "in": "ax",
     "coefficients": [0, 0, 1], "domain": [0, 1]},
    {"id": "name", "type": "label", "to": "square",
     "text": "squared output", "side": "auto"}
  ]
}
```

Here `ax` must already exist in the named base snapshot. A root panel can
define it with `{ "id":"ax", "type":"axes", "x":[0,1], "y":[0,1],
"aspect":"independent" }`. No panel can redefine an inherited item or frame.
Items appear in semantic drawing order. Labels refer only to earlier geometric
items, not to arbitrary paths or pixel positions.

| Type | Required fields beyond `id`, `type` | Interpretation |
| --- | --- | --- |
| axes | x, y, aspect | Increasing numeric ranges; equal or independent scale |
| line / arrow | in, from, to | Endpoints in the named frame's data units |
| vline / hline | in, value | Full-frame reference line at a data value |
| dot | in, at | Point marker; display radius is renderer-owned |
| rect | in, x, y | Two data intervals |
| region | in, x, y, fill | Rectangle with none or sparse renderer-owned hatching |
| circle | in, center, radius | Data-space radius; requires equal scale |
| polyline | in, points | Bounded 2–160 data samples, not device coordinates |
| plot | in, coefficients, domain | Degree 0–4 polynomial, ascending coefficients; engine samples 65 points |
| label | to, text, side | Unchanged plain text, up to 24 characters, placed beside its owner |

Polynomial evaluation is a fixed arithmetic operation, never `eval`, imported
code or an arbitrary function expression. The plotted polyline is a sampled
approximation, not a mathematical verification of the function. Out-of-frame
samples reject the draft rather than being silently clipped. Mathematical
circles reject unequal axes instead of silently becoming ellipses.

The renderer measures endpoint glyph widths before allocating its data box
inside the existing 600×360 region. A long exact endpoint value reserves more
margin; it is not rounded or shrunk to make it fit. Each item reports measured
bounds. Labels use the existing bounded joint placement search at its existing
font size, testing eight nearby directions at two gaps for `auto`, or the
explicitly requested side. Existing wrapping may be used without changing the
text. No safe placement means rejection, never silent omission.

Historical reuse is resolved by copying the selected base's items, frames,
resolved label locations and compiled stages. Later panels cannot rescale or
relocate that geometry. All new marks are checked against earlier labels;
crossing an old label rejects the new panel instead of moving already-drawn
ink. Branching back to an older panel excludes intervening additions. Root
panels are independent pictures and may reuse local IDs.

Every addition passes the existing procedural compiler's 64-stroke,
3,000-point and 30-second stage checks. Each cumulative preview is checked
again with `compile_storyboard`. The entire story conservatively counts all
materialized panel snapshots against 12,000 points: inherited paths count again
where another panel picture would need them. This is not a claim that the live
adapter already places or replays those snapshots. A late invalid panel means
no compiled story is returned and no encoder is invoked by the reviewer.

```sh
/opt/homebrew/bin/python3.11 notebook_panel_eval.py check story.json shapes.json new-directory
/opt/homebrew/bin/python3.11 notebook_panel_eval.py example new-example-directory
```

The reviewer uses the existing `preview_svg`, PNG preview and actual v6 asset
encoder. It writes no `.rm` files and contacts no device. Its HTML puts each
picture above its caption, with explicit base references and point counts.
`geometry_validated` and `ink_encoding_validated` do not imply
`native_delivery_supported`, `tablet_proven` or teaching quality. The authored
four-panel graph fixture builds axes, a squared curve and a marked value, then
returns to the original axes for a different relationship. It is a contract
fixture, not a new dynamic-agent result.

Next gate: independent model-generated panel drafts and comparative offline
review, with source-grounded content for research questions. Extend the typed
vocabulary by general semantic requirements, not by matching question strings.
Native multi-region/page placement remains a separate integration gate; neither
the live model contract nor the existing tablet path imports this prototype.

### Symbolic panels reuse the procedural renderer (2026-10-28)

The typed panel compiler now also accepts ordinary object/relationship
pictures, without imposing mathematical axes. These additions are generic
composition instructions, not question-specific scenes:

```json
{"id":"source","type":"object","shape":"box","position":"top-left"}
{"id":"reader","type":"object","shape":"person","position":"bottom-center"}
{"id":"delivery","type":"connect","from":"source","to":"reader"}
{"id":"name","type":"label","to":"source","text":"Source","side":"auto"}
```

`object` allows the existing committed contour vocabulary: circle, box,
person, sun, cloud and water. Named positions are the six combinations of
top/bottom and left/center/right. The engine supplies their coordinates,
contours and true connection ports; no pixel coordinates, sampled paths,
URLs or arbitrary SVG enter this schema. Occupied slots are rejected. This
is a bounded composition vocabulary, not arbitrary illustration synthesis.

`connect` joins two distinct already-declared objects. It reuses the existing
bounded curved/orthogonal routing and checks object/arrowhead clearance and
previous routes. Up to eight connections fit the symbolic contract, still
subject to the unchanged native budgets. Frozen labels are routing obstacles;
new automatic connector labels use measured candidates along their route.
Captions supply explanatory meaning; an arrow alone does not assert causality,
distinguish AND from OR, or prove the accompanying statement.

Existing object positions, labels and routes are never recalculated. A new
object that would enclose earlier ink is held instead of silently changing
its meaning or relocating prior strokes. Symbolic objects and mathematical
axes cannot share one picture in this version: use independent story panels.
Branching to an earlier symbolic snapshot works exactly like graph reuse.

`notebook_panel_objects.py` consumes the established procedural helpers but
does not modify their unrelated dirty contour drafts. The frozen story/model
prompt and fourteen-question packet remain unchanged; this new vocabulary is
not yet advertised to PiDog. Evaluate a separately versioned prompt after
the initial host integration is verified, rather than silently changing the
pending experiment's prompt hash.

Authored four-panel preview:
`OUTBOX/symbolic-panels-20261028/relationship/index.html`.
Its graph builds two objects, a data-flow arrow, an observer, then branches
back to the original pair and reverses the connection. It compiles and passes
the v6 encoder with 3,215 materialized snapshot points. The forward/observer
and reverse pictures were visually inspected: labels are clear, the connector
attaches to the person contour, and the historical branch excludes later ink.
These are renderer checks, not proof of model quality or live tablet delivery.

```sh
python3.11 notebook_panel_eval.py example NEW_DIRECTORY --scene relationship
```

Verification: clean export `OUTBOX/sp-or5UBs/tools/herd-board` passes all
**630 Python tests and 51 Node tests**. Nine new tests cover immutable symbolic
branches, all six contour types/positions, true-port attachment, old-label
clearance, new-object occlusion, intermediate obstacles, invalid fields,
mixed-frame rejection and the existing native encoder. All four earlier
graph fixture SVGs and PNGs are byte-identical to their prior clean previews.
The clean symbolic preview is
`OUTBOX/symbolic-panels-20261028/clean-relationship/index.html`.
No live model or tablet call was made for this addition.

### Freeze the complete picture, not provisional labels (2026-10-29)

The panel compiler now resolves the entire story's geometry before placing
labels. All panels sharing an ancestor picture use one layout calculation;
future paths and axis titles are measured before the first panel's positions
are frozen. The final returned snapshots retain byte-identical ancestor
stages. Independent pictures are laid out independently. Sibling item IDs are
scoped to their defining panel, so historical branches cannot steal each
other's labels. Alternative branches are conservatively treated as obstacles,
which can still reject a dense composition.

This only changes unpublished offline planning. It does not move notebook ink
or authorize reflow of a displayed answer. Geometry/data ranges, inherited
objects and label text are unchanged. The existing 64-stroke, 3,000-point,
30-second stage and 12,000 materialized-story-point limits remain enforced.
All panels must validate before the reviewer invokes the v6 encoder. Native
multi-region delivery is still unsupported by this prototype.

The narrative packet now includes a compact `picture_plan` containing only
the IDs, base references and new ideas for the same picture, including future
steps. This lets the agent choose data ranges that cover the complete intended
picture without prescribing screen coordinates. `visual_kind` is bounded
descriptive metadata, not a renderer opcode; actual capabilities remain the
strict typed-shape grammar. The isolated prompt now advertises the existing
six-object symbolic catalog and connectors, so nonnumeric explanations no
longer have to use fake mathematical axes. Production prompts are unchanged.

#### Evidence and limits

The previous frozen `packet-layout-v2` real-model comparison has **no complete
accepted lessons**: Luna attempted 8/14 questions; Astra attempted 5/14.
Each run stopped at a provider deadline, leaving 6 and 9 questions unattempted,
respectively. Those runs remain failures, not successful latency measurements.
The providers were confirmed idle before changing evaluation settings; Luna
was restored. A subsequent read-only check found listener PID 95514 and verified
that all non-evaluation configuration matches the pre-experiment backup.

Renderer-only replay in
`OUTBOX/story-panel-eval-20261028/renderer-whole-picture-v3/` uses unchanged
recorded answers from the two original and two layout-v2 runs. Of 25 available
answer sets, 15 compile; 14 of those are only prefixes. The remaining one is
the complete three-panel Astra fractions answer. Its three PNGs were inspected:
the area split and labels are readable, but unnecessary graph axes and ticks
make it unsuitable as a polished demonstration. This is a compiler recovery,
not a new first-pass model success, tablet test or teaching-quality pass.
Ten sets still fail (placement/search budget, equal-scale circles, a declined
panel, or the unchanged native stroke cap). Missing panels were not invented.

The side-by-side fresh-run report is
`OUTBOX/story-panel-eval-20261028/comparison-layout-v2/index.html`.
Next: test a separately frozen prompt with the same question/image set, then
review complete lessons before connecting this panel pipeline to the tablet.

Clean staged export `OUTBOX/whole-picture-IVh2Sa/tools/herd-board` passes
**641 Python tests and 51 Node tests**. Added regression checks cover final
ancestor identity, unpublished-label repositioning, sibling label-ID scope,
independent-picture isolation and rejection of an invalid future title before
any encoding. Device-facing test messages are mocks, not tablet observations.

### Distinguish filled areas from partition lines (2026-10-29)

Direct inspection of a fresh model-generated fraction picture exposed a
general renderer problem: vertical fill strokes looked like additional
mathematical partitions. `region(fill="hatch")` now uses sparse 45-degree
strokes with 32-display-unit perpendicular spacing. The lattice is aligned
across the entire picture, so adjacent regions do not restart an inconsistent
fill pattern. Segments stay inside the validated region; a tiny region between
grid lines receives one central fill stroke. No mathematical boundary, label
text or model answer changes. This is a renderer policy, not a fraction-specific
scene or prompt rule.

The extra diagonal segments are counted by the existing native budgets;
there is no exemption for decorative ink. Tests cover wide, narrow and tiny
regions, deterministic orientation, boundary containment and continuity when
one region is divided into two. The recorded Luna fraction answer replays
through the v6 encoder at 10,800 total materialized snapshot points, with
each new stage still below its existing cap. Its final PNG was inspected:
the two selected fourths are now visibly distinct from diagonal shading.
Labels and unwanted numeric axes still need improvement.

Artifact: `OUTBOX/story-panel-eval-20261028/diagonal-fill-fractions/`.
This separate renderer replay does not change the in-progress `picture-v3`
model comparison, which uses frozen export `whole-picture-IVh2Sa` and its
original fill policy. Neither version was sent to the tablet.

Clean export `OUTBOX/diagonal-fill-FdVSOU` passes **643 Python tests and 51 Node
tests**. The fresh comparison is preserved in
[`evaluations/story-picture-20261029/index.html`](evaluations/story-picture-20261029/index.html),
with visual review and exact scope in its README: Luna 4/14 complete compiler
passes; Astra 1/5 attempts before a deadline, nine unattempted. The evaluator
was confirmed idle before restoring Luna. No model success is a tablet result.

### One bounded contract correction, not a renderer bypass (2026-10-29)

The story/panel evaluator retains its default first-pass-only behavior. An
explicit `--max-corrections 1` permits at most one additional model call for
the entire lesson, not one retry per panel. This is limited to malformed JSON,
missing/extra declared fields, a non-object where an object is required, or
the existing twelve-word caption limit. Refusals/unavailable answers, model
or response-binding changes, transport failures, unsupported capabilities,
geometry/layout failures and resource-budget failures do not trigger retries.

The validator provides a static JSON location and known expected/missing keys,
or numeric counts. It does not echo arbitrary unexpected keys, values or parser
payloads in diagnostics. A shared field catalog keeps panel preflight and
lowering consistent. No field is silently added or removed. A corrected response
is a complete replacement for the same task, with the original question and
exact immutable base context; it passes the same whole-prefix validation. Only
after the whole lesson passes may previews or v6 encoding be generated.

The failed raw output, correction request and corrected raw output are all
retained. `first_pass_valid` and `corrections_used` are distinct from final
`valid`; reports warn when correction budgets differ. A context that cannot
fit the existing IPC bound is held before dispatch, never truncated. A provider
deadline during correction still stops the entire collector until the provider
is independently confirmed idle. Production host behavior, native insertion,
tablet guards and native budgets are unchanged.

This small local correction path follows the validation/retry alternative in
[OpenAI's structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs).
It is not a claim that the existing Pi OAuth streaming adapter now supports
API-level constrained JSON decoding, nor does valid JSON establish truth or
visual quality. Model access and model selection are unchanged.

Clean candidate `OUTBOX/cc-wFY4Vl` passes **660 Python tests and 51 Node
tests**. A first export exposed a test-only socket pathname over the existing
100-byte limit; the integration fixture now creates its private socket under
the resolved temporary directory, independent of checkout depth. The socket
limit and symlink checks remain unchanged. Native logs in these tests are
mocks, not tablet observations.

The fresh frozen correction experiment completed all fourteen attempts:
**4/14 complete compiler/encoder passes, all first-pass; zero complete
recoveries from three correction calls**. The last question hit its provider
deadline; an independent invalid-request probe subsequently confirmed the
provider idle. Fifty-four calls were attempted and 53 model envelopes returned.
The correction calls added 10.878 seconds combined. All non-evaluation host
configuration still matches the private pre-experiment backup.

The four complete lessons' fifteen stage PNGs were inspected. Non-overlap is
not enough: some labels are visually associated with the wrong region, and
some otherwise valid diagrams add clutter or reveal a later idea too early.
The evidence and unchanged final images are in
[`evaluations/story-correction-20261029/README.md`](evaluations/story-correction-20261029/README.md).
Do not enable correction by default or treat these compiler passes as polished
teaching examples. Next engine work should improve label-to-object association
and the typed drawing contract, preserving native budgets and original answers.
No new adapter or tablet deployment was performed.

### Label ownership rather than merely non-overlap (2026-10-29)

The deterministic panel renderer now considers a region label and its pointer
as one annotation during joint placement. Outside rectangle/region labels get
a straight unheaded line to the facing edge midpoint; inside labels need no
pointer. A crossing or boundary-straddling candidate is refused. Pointer ink
uses the ordinary native budgets, and inherited panels reuse the exact same
annotation geometry. The final whole-picture geometry is known before labels
are placed. Words, diagram data, font size and the 4,096-attempt search bound
are unchanged.

Curve labels now prefer arc-local candidates over empty bounding-box corners;
axis titles cannot migrate to a different edge. Eleven regression tests cover
attachment, crossing prevention, inheritance and resource accounting. The exact
clean candidate passes **671 Python and 51 Node tests**. All nine previously
complete model answers replay successfully with identical original source
hashes and no model calls. Five unaffected lessons have identical PNGs.

See [before/after evidence](evaluations/label-attachment-20261029/README.md).
The integral's axis and curve labels are visibly better associated; quarter
labels point to their regions. Clutter and poor model-authored content remain.
These are offline renderer results only: no fresh model success, deployment,
tablet persistence, handwriting or latency claim is implied. Continue toward
the general live engine, rather than treating nine compile passes as completion.

### Rectangular fill is a capability, not a spelling trap (2026-10-29)

The typed data-space `rect` accepts optional `fill: none | hatch`; absent fill
retains the prior outline. `region` still requires fill. Both lower through
the identical bounded geometry and label machinery. Inputs are never rewritten
or discarded; unsupported fills and extra fields remain errors. The isolated
prompt now describes that capability and the axis-title edge constraint, with
no change to live configuration or model selection. Optional-field diagnostics
remain value-free and identify missing required fields separately.

Clean tests: **677 Python, 51 Node passed**. Replaying three previously failed
recorded prefixes recovers the integral's first two panels and odd-squares'
first panel; Bayes still fails label placement. These are not newly completed
model answers. See [preserved prefix evidence](evaluations/rectangle-fill-20261029/README.md).
The next milestone must include complete general story/panel delivery, not
just improved prefixes or native mocks. No tablet deployment occurred here.

### Complete story to native delivery bridge (2026-10-29)

`notebook_story_native.native_story_bundle` compiles the entire typed story
before allocating any native source assets. Consecutive panels extending the
current picture contribute only their new strokes. A branch from an older
snapshot begins a separate picture containing the exact inherited geometry;
it never erases the extended original. One immutable source per original
addition can be cloned more than once, with each clone charged to the existing
12,000-point delivery limit. Per-stage 64-stroke, 3,000-point and 30-second
limits are unchanged. Captions precede their drawing; the takeaway appears once.

The delivery parser now accepts a service-assembled bounded envelope:
`{v:1, mode:"story-lesson", story:<validated outline>, panels:<typed drafts>}`.
It retains the existing 24,000-byte response bound and permits no source paths
or native identifiers from the model. Server and QML explicitly negotiate
`story_version:1`; legacy clients cannot accidentally import the new form.
Story imports allow up to twelve source pages; legacy imports retain seven.
The existing request binding, page/input-change holds, source byte checks,
registration, preservation and saved-ink completion checks remain the path.
The old single-picture evaluator rejects this form explicitly instead of
misreporting it as an accepted empty text answer; use the panel evaluator.

Offline evidence: a clean staged export, excluding unrelated worktree edits,
passes **691 Python tests and 51 Node tests**, with no skips. New tests include
all nine preserved complete model answers, branch source reuse, twelve-panel
archive bounds, late-invalid-panel rejection before encoding, capability loss
during import, changed page, and final saved-proof gating. The real `InkRuns`
verifier rejects one saved copy being counted twice and rejects loss of
pre-existing ink. Saved-page bytes in those tests are synthetic, not tablet
captures. Clean export: `OUTBOX/story-native-clean-jG9tJY/tools/herd-board`.

**Not yet live:** no server restart, tablet patch installation, production
prompt change or model call occurred for this bridge. The production model
worker still makes its single semantic call. Remaining work is the bounded
planner/panel producer feeding this envelope, review, then an isolated live
Respond test including scroll and reopen evidence. These tests do not prove
native multi-picture placement, latency or teaching quality on the tablet.
MyDude review request was queued as `7ab1b4f306127c1c9e2a6e5847069b2e`;
queued is not review approval. The overall goal remains incomplete.

### Image-first story producer connected to Respond (2026-10-29)

`notebook_story_generation.generate_notebook_story` now joins the production
worker to the native bridge. It sends the actual captured PNG first to a story
call, then to small panel calls carrying the panel plan and exact typed base
items. It never sends a cheap transcript, full chat history, device paths or
point-by-point motion. The fixed host prompt now explicitly reads the latest
question from the image when there is no supplied textual question. Ambiguity
may yield a bounded clarification; invalid geometry never becomes fallback
prose, and no partial picture is published.

One configured deadline (at most 30 seconds) covers the complete sequence and
compilation. Later calls receive only the remaining time. Each call has its
own request identity, while the original pending-job/page check guards the
entire sequence and publication. Returning to a changed page cannot revive
the worker. A provider/model change, invalid envelope, oversized context,
deadline or cancellation stops further calls without automatic retry. Model
selection, minimal reasoning, no-tools isolation and provider configuration
remain host-owned. Reported first model text is not first visible tablet ink.

Activation requires matching **operator** configuration, not a model field:
set the existing `model_transport.response_format` to `story-panel-v1` and
configure its production host with the same wire format and the generated
`story_panel_instructions()` prompt. Missing format still means `semantic-v1`.
The production producer refuses `notebook-eval.sock`; the offline evaluation
endpoint is not repurposed. No new job store, lease or audit layer was added.

Clean export `OUTBOX/story-producer-clean-XRInDX/tools/herd-board` passes
**699 Python and 51 Node tests**, no skips. Coverage includes real Unix socket
framing through the Node responder with a **fake provider**, five sequential
image-bearing calls, native compilation of the completed branch lesson,
cross-call cancellation, decreasing deadlines, explicit clarification and
stable model identity. This establishes wiring, not handwriting recognition,
generative teaching quality or actual response latency.

No running server/host configuration or tablet patch was changed. PR4 was
open with no GitHub reviews at verification; MyDude review request
`7c108a40334dcda44b77c697f59bf1f9` was queued. Next is reviewed isolated live
activation and a real generated lesson, followed by scroll/reopen evidence.
The broader acceptance tests and rollout remain incomplete.

The OpenAI Docs check informed explicit incomplete/unavailable handling and
validation of each subtask: [Structured outputs guidance](https://developers.openai.com/api/docs/guides/structured-outputs).
This host path is not claimed to use provider-enforced JSON Schema decoding;
the Python compiler remains authoritative. No model migration was made.

### Live-readiness check and procedural sampled areas (2026-10-29)

The PiDog host configuration accepts `eval_response_format` but does not yet
accept or forward a production `response_format`. Activation therefore needs
a small host change, not merely a notebook configuration edit. MyDude was
asked to own that change and review PR4 in queued request
`88015e9594e0f9efd5259bf48a33cb9f`; no approval or deployment is inferred.
The isolated evaluation socket was verified listening under PID 59881.
Tablet telemetry remains inactive; no notebook writes were attempted.

A fresh fixed integral evaluation through that existing isolated endpoint
returned three model responses in **13,072 ms**, then failed on a zero-height
rectangle in its left-endpoint approximation. This is a failure, not a recovered
lesson or first-visible timing. Raw requests/responses remain under
`OUTBOX/story-activation-20261029/fresh-integral`. The configured host prompt
was the existing `packet-correction-v4` prompt, not the newer intended prompt
saved by the evaluator; `host-provenance.json` records that difference.
The question was supplied as text with its image, not image-only transcription.

The generic tool improvement is `riemann`, a typed data-space item with
polynomial `coefficients`, `domain`, `baseline`, `count` (1–16), and `sample`
(`left`, `midpoint`, `right`). The model describes a mathematical operation;
the engine calculates all bar heights and vertices. Degree remains bounded
0–4, no expressions/code/paths are accepted, and existing native limits apply.
Signed heights remain signed. A sample exactly on the baseline becomes a
zero-area segment; nonzero subpixel heights are not inflated or discarded.
This does not repair or reinterpret invalid `rect` output. Refinements may
branch from the earlier curve snapshot rather than overwrite previous bars.
The prompt describes finite sums as approximations, not exact integrals.

Clean staged export `OUTBOX/riemann-clean-uHQGxh/tools/herd-board` passes
**706 Python tests and 51 Node tests**, no skips. Seven new tests cover the
sampling rules, signed baselines, zero and subpixel heights, invalid bounds,
immutable inherited geometry, native encoding and aggregate budget rejection.
The authored five-panel preview at
`OUTBOX/story-activation-20261029/authored-riemann-preview/index.html`
compares the three sampling rules. Its midpoint PNG was visually inspected;
it is an authored fixture, not a new model pass or a tablet capture.

Owner-only candidate prompts and matching host/notebook configuration files
are prepared in `OUTBOX/story-activation-20261029`. The Riemann-enabled prompt
is `system-prompt-riemann.txt`; its host override is
`host-overrides-riemann.json`. Merge only the two notebook-host fields, leaving
adapter location, evaluation prompt/model and general chat configuration intact.
The notebook candidate still enables only the existing test notebook and uses
one 30-second whole-story deadline. These files have NOT been installed. Next:
host review/change, reviewed candidate activation, a fresh complete generated
lesson, and actual tablet placement/latency/reopen evidence. Under-10-second
first-visible response is still unproven and the fresh failed run exceeded it.

The OpenAI Docs evaluation guidance informed retaining failures and recording
the actual test configuration instead of calling a rendering fixture a model
success: https://developers.openai.com/api/docs/guides/evaluation-best-practices.

### Isolated model reload and measured subscript lettering (2026-10-29)

The requested production-format change appeared in the separate
`nvoy-notebook-eval-live-host` checkout while its owner was working. This agent
did not edit that checkout. Independent checks passed all **7 host tests** and
the existing `node test/pi-harness.mjs` integration suite. This is source/test
evidence, not an assertion that production uses the new format.

An attempted evaluation-prompt config patch was denied by the filesystem;
no alternate writer was used. The exact installation was handed to MyDude.
Subsequently the configured `eval_prompt_file` changed to
`OUTBOX/story-activation-20261029/system-prompt-riemann.txt`, and the listener
changed from PID 59881 to PID 1766 after reload. Comparison with the private
rollback copy showed only the evaluation prompt path changed; production and
all other configuration were unchanged. Prompt SHA256:
`3b5f9a89343d3e40025dee1239260d9b8bdc3b9cb4a66c5bb49613224cfff255`.

The first fresh call sequence used `riemann` correctly for four and eight
right-endpoint bars, without enumerating vertices. It failed at the final
label `[x³/3]₀¹ = 1/3` because numeric subscripts were unsupported. All five
responses and the **21,284 ms** elapsed time remain at
`OUTBOX/story-activation-20261029/riemann-integral`; zero correction calls.

The plotter alphabet now supports all ten numeric subscripts using the same
digit paths and .67 scale as superscripts, with a lower baseline. Measurement
and placement use the actual paths, including their descenders. No source
text is replaced, no font fallback box is emitted, and unknown characters
still fail. Four new tests cover all digits in both font modes at four sizes,
measured bounds, native encoding, and explicit unsupported-glyph rejection.
Clean export `OUTBOX/subscripts-clean-apKD5y/tools/herd-board` passes
**710 Python tests and 51 Node tests**, no skips.

Recompiling the unchanged five model outputs now yields a valid four-panel
preview and native bundle: 5,043 delivered points, two picture runs. This is
recorded-output recovery, NOT a new model pass. Visual inspection found the
final label readable but the refinement panel cluttered by both coarse and
fine bars. Geometry validity alone is not the teaching-quality gate.
Preview: `OUTBOX/story-activation-20261029/riemann-integral/subscript-replay/index.html`.

A second fresh run with the same installed prompt explicitly returned
unavailable in its first drawing panel: the renderer cannot shade a curved
region. Its **9,251 ms** failure and raw output remain under
`OUTBOX/story-activation-20261029/subscripts-integral-fresh`. Do not claim this
as a successful fast response. The next capability gap is a general bounded
area-between-curve-and-baseline operation, not altered output for this one
question. Production activation, live multi-picture placement, scrolling,
saved-ink/reopen verification and wider rollout remain unproven. No tablet
content was changed during these checks.

### Procedural curved regions (2026-10-29)

Added the general `area` item: bounded polynomial coefficients, domain,
horizontal baseline and explicit `none|hatch` fill. The compiler samples the
same boundary as `plot` and clips a sparse, page-aligned hatch lattice against
that boundary. Even-odd intersections preserve separate lobes at baseline
crossings. Signed accumulation is explained by the caption; shading does not
compute an integral or claim exact area. No model-enumerated fill lines,
arbitrary expressions, dependencies or device changes are required.

Nine tests cover positive/negative/crossing regions, a deterministic sweep of
60 polynomials, exact domain endpoints, invalid input rejection before fill,
immutable inheritance, native encoding and existing aggregate limits. The
authored crossing fixture exposed a general full-span reference-line label
placement gap; hline/vline now use the same path-local candidates as ordinary
lines. The original failed preview is retained. The identical authored inputs
now render at `OUTBOX/story-activation-20261029/authored-area-preview-v2/index.html`;
above-baseline and crossing PNGs were visually inspected. This is offline
renderer evidence, not a model-generated or tablet success.

Clean staged export `OUTBOX/area-clean-gEDzEV/tools/herd-board` passes all
719 Python tests. Candidate evaluation prompt `system-prompt-area.txt` in
`OUTBOX/story-activation-20261029` matches source byte-for-byte, mode 0600,
SHA256 `5758e1d71e99c106d5c99cd63fb3c4336c048cdd72147108ffeef6957e0c2ac2`.
At verification the running isolated host was still PID 1766 with the earlier
Riemann prompt. Owner review/reload and a fresh model run remain next;
production and tablet rollout are not implied by these checks.

### Whole-reply offline evaluation and fresh curved-area lesson (2026-10-29)

The evaluator now checks the production `story-lesson` envelope, compiles the
complete native bundle, and renders `playback.html` from those exact decoded
strokes. Valid snapshot PNGs alone no longer count as full preparation success.
A delivery failure retains the snapshot evidence but marks the run failed;
it does not trigger another model call. The player sequences captions before
ink and preserves shared-picture/branch identity. Its timing is planned motion,
not measured tablet or Respond latency. No `.rm` files are persisted or imported.
Two new tests exercise envelope and native-delivery failures. Clean export
passes **721 Python tests**; the preceding unchanged Node sources passed **51**.

The isolated host was observed reloaded as PID 37685 with the area prompt and
matching SHA256 above. Production prompt/format remained unchanged. A fresh
Luna/minimal integral evaluation completed five model calls, no corrections,
in **17,533 ms**, validating both the four-panel preview and native bundle
(4,948 delivery points, two picture runs). It used `area` and `riemann` directly,
without listing hatch strokes or rectangle vertices. Final PNG inspection
found clear labels and no retained coarse-bar overlay in the refinement;
the exact answer is 1/3. This is a fresh model preparation pass, not device
proof or a passing under-10-second response. The evaluator supplied question
text plus its image, unlike production's image-only input.

Raw answers, configuration provenance, PNGs and animated playback are retained
in `OUTBOX/story-activation-20261029/area-integral-fresh`. Evaluation handling
follows the [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
on retaining evidence and combining metrics with visual judgment. The device
still reports inactive; no tablet content changed. Next: unrelated-question
regression, review, and the isolated production/device test when available.

### Region-label edge routing and cross-question failures (2026-10-29)

Fresh fractions run `area-fractions-fresh` failed at panel p2 after 12,316 ms:
full-height dividers blocked the inherited region label's default location
and its midpoint-only pointer. A generic bounded edge search now offers
interior edge anchors and slides labels along those edges. It never alters
text, size, object geometry or clearance rules. Two tests cover all four sides,
determinism, unchanged source geometry and a joint two-label divided region.
The existing symbolic-object candidate set is unchanged. Clean export passes
**723 Python and 51 Node tests**. An intermediate full regression caught the
unintended symbolic candidate expansion; it was scoped before this pass.

The unchanged two-panel recorded prefix now renders in
`area-fractions-fresh/edge-slide-prefix-replay`; its PNG was inspected. This is
only prefix recovery, not a complete or fresh model pass. Fresh run
`edge-fractions-fresh` still failed at p3 after **12,442 ms**, with a new crowded
layout and a duplicated inherited filled region. No repair or hidden retry
was used. This prevents claiming fractions reliable or shipping the new
producer broadly based solely on the successful integral.

Fresh `edge-proof-dependency-fresh` failed after **12,154 ms**: the model
explicitly declined an addition because the inherited picture already had
the lemma and arrow, and the available symbolic operations did not express
the planned emphasis without duplication. This is a story/operation-contract
gap, not a device or transport timeout. All original outputs are retained.
Next general work: reconcile planner steps with available reuse/emphasis
operations, and test layout across the fixed question set. Production stays
unchanged until review and end-to-end proof; the tablet remains untested for
these changes. Current PR4 was observed OPEN with no recorded GitHub reviews.

### Make each panel own a drawable addition (2026-10-29)

Inspection of the retained proof-dependency failure corrected the initial
diagnosis: the model claimed it could not label inherited symbolic objects,
but the renderer already supports that. Its setup had drawn both supports
before their planned steps. No extra emphasis tool is justified by that claim.

The fixed prompt now defines steps as supported additions, separates base
items from lookahead, permits label-only additions to inherited objects and
connectors, and prohibits redrawing old geometry under a new ID. It replaces
the single finished symbolic example with three actual calls: setup, connection,
then labels. A test decodes that exact prompt example and compiles it to one
native picture, asserting unchanged inherited object/connector paths. The
line contract also distinguishes bounded segments from full-frame hline/vline.
This is general instruction/contract alignment, not a hardcoded proof answer.

Clean export passes **724 Python tests**. The new fixed packet is prepared
from the original 14-question source SHA256
`96881cb138b7f8ed50c362239c477bee968d8f9b4a98fcdcd4d48eb0822dc942`, preserving
all questions/images/order at `OUTBOX/story-ownership-eval-20261029/packet`.
Prompt change guidance: [OpenAI prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering).
This test proves the example is executable, not that the model follows it.
The isolated evaluation prompt must be reviewed/reloaded before fresh calls;
production remains unchanged.

The matching isolated prompt was subsequently observed on listener PID 60653,
SHA256 `af7a9710fc6beaf9761be254d5feb7582f0a4445a93f008641138789c14e2ccf`,
with Luna unchanged. `story-ownership-eval-20261029/host-provenance-luna.json`
records that scoped configuration check; this is not provider attestation.
The full first-pass 14-question collection was launched with zero corrections.

The side-by-side comparison now includes each successful run's actual
`playback.html`, alongside snapshot images. It explicitly distinguishes
offline native preparation from device delivery and checks the fixed local
playback filename before copying. Historical results without that validation
remain marked not validated. New traversal-path rejection and existing report
tests pass; clean export passes **725 Python tests**. These are report/tool
checks, not a claim about the still-running model suite.

### Fixed-packet comparison and label ownership (2026-10-29)

The frozen `story-ownership-eval-20261029` packet has SHA256
`8fa20650898f1fdd06b3fde340b14426d561ac20e0c535e4075db075dd5c1090`.
Both models used the same prompt, question images, question order and frozen
compiler export `OUTBOX/area-clean-gEDzEV`, with zero corrections and a 30 s
per-call deadline. This deadline is not the production whole-lesson deadline.

Luna completed all 14: **10 native-preparation passes, four held answers**.
Gravity exhausted label placement; compound interest and Bayes exceeded the
64-stroke stage budget; transistor violated act order. Successful full offline
generation/preparation took **14.292–25.915 s, median 16.740 s**. These times
are not Respond-to-visible measurements, and do not meet the under-10 s aim.

Astra's collector is terminal (exit 2), not still running: integral prepared
in **31.729 s**; gravity exceeded the 12,000 materialized snapshot-point cap
after **43.443 s**; odd-squares hit a per-call deadline after **30.008 s**.
The remaining **11 were not attempted**, not failed. A subsequent invalid
request to the isolated socket returned `invalid_request`, not `busy`;
no provider restart or retry was performed. The partial comparison is at
`OUTBOX/story-ownership-eval-20261029/comparison/index.html`, including recorded
caption-before-drawing playback links. It is not a complete model ranking.

Visual review does not equate compiler acceptance with teaching quality:
Luna's fractions and proof-dependency snapshots are promising; odd-squares
misidentifies a top strip as the complete new border and still needs semantic
work. Astra's inspected integral has a correct area picture and a caption that
explains endpoint evaluation; its final label alone is not the whole lesson.
Full animation and all-answer visual review remain incomplete.

The accepted Luna blue-sky answer exposed a renderer bug: an explicitly
bottom-placed connector label could migrate beside a different arrow. The
generic fix constrains every symbolic connector label, regardless of its side
hint, to candidates along its actual route. Extra finite normal offsets clear
flanking endpoint shapes without shrinking text. External labels on symbolic
boxes now use the same checked edge pointer as rectangular regions. No model
output, object geometry, inherited paths, or resource cap is changed.

The first strict replay correctly held the ambiguous composition. The final
replay with bounded clearance succeeds; its inspected PNG places the two
labels with their intended owners. Original outputs/results remain untouched.
All **11 previously accepted outputs** (10 Luna, one Astra) replay through
both the panel renderer and full native bundle compiler successfully under
`OUTBOX/story-ownership-eval-20261029/label-fix-replays`. This is recorded-output
recovery/regression evidence, not 11 fresh model successes or tablet tests.

Clean export `OUTBOX/label-owner-clean-olDWfI` passes **728 Python tests** and
the **33 Node responder/lifecycle/isolation/socket tests**. New tests cover all
connector side hints, box-pointer ownership, and a wide label between endpoint
shapes while preserving words, size and native limits. Unrelated worktree
changes were excluded. No server, tablet or production prompt was changed.
Next: complete the remaining second-model questions without erasing the
timeout, review teaching quality, and obtain review before live deployment.

### Completed 14-question two-model comparison (2026-10-29)

The remaining Astra questions have now all been attempted. Every interrupted
collector was observed terminal before an invalid-request probe verified the
isolated endpoint was idle. Continuations used the original frozen evaluator,
preserved prior failures and never retried a model answer. An intermediate
sandbox socket-metadata denial occurred before any provider request; that
artifact remains separately preserved under `astra-continued`. The authorized
continuation was the first provider request for that question.

Final artifacts are under `OUTBOX/story-ownership-eval-20261029`:

- `comparison-complete/index.html`: all 14 questions side by side, with captions,
  snapshots, playback links for accepted answers and explicit failure reasons.
- `luna-firstpass`: 10 native-preparation passes, four holds, zero corrections.
- `astra-continued-3`: six native-preparation passes, eight holds, zero corrections.
- `comparison-summary.json`: provenance, denominator and timing distinctions.
- `extended-visual-review.json`: all accepted final snapshots/captions reviewed;
  this is not full-animation, pedagogical efficacy or tablet approval.

Successful full offline preparation timings:

| Fixed model | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| Luna | 14.292 s | 16.740 s | 25.915 s |
| Astra | 31.729 s | 38.607 s | 45.165 s |

Astra's eight holds: gravity exceeded the materialized story-point cap;
odd-squares, transistor and Bayes reached the 30 s per-call deadline;
compound-interest and dependency-failure exhausted label search; water-cycle
had no clear label location; inverse-mapping had no joint clear placement.
All 14 were attempted, so none are now marked missing. The successful Astra
captions often explain qualifications well, but this run provides no basis to
select it for the low-latency live path. No production model was changed.

Expanded recorded-output replay through label fix `4573cba` accepts **14 of
16** originally accepted outputs: all ten Luna and four of six Astra. The two
additional Astra compositions, blue-sky and proof-dependency, exhaust the joint
label search with the stricter ownership/pointer constraints. Their original
snapshots have ambiguous annotation ownership; silently allowing remote labels
again is not an acceptable fix. These are additional held cases, not claimed
recoveries. The earlier 11/11 replay statement covers only the initial subset.
Full replay outputs are in `label-fix-replays/astra-complete`.

Next renderer task: improve bounded joint label selection and allocation,
preserving original words, font size, geometry and pointer clearance. Benchmark
against these retained outputs and generic adversarial fixtures, not topic
names or question-specific exceptions. Then re-run fresh model quality checks
before reviewed isolated tablet deployment. Under-10 s response, scrolling,
reopen persistence and broader rollout remain unproven for the new producer.

### Bounded joint label search (2026-10-29)

The static initial ordering explored placements even after they made a later
label impossible. `notebook_label_solver.select_labels` now forward-checks
remaining domains and selects the currently most constrained label. It retains
deterministic tie/preference order and returns only a complete assignment.
Compatibility caching includes both text boxes and complete pointer geometry.
The unchanged 4,096 work budget charges candidate choices AND uncached pair
checks; pruning does not introduce an unlimited auxiliary search. Exact
duplicate annotations are removed without rounding coordinates; candidates
with different pointers remain distinct. No word, font size, object, stage
order or pen budget is changed.

The initial version recovered the two newly held Astra compositions but failed
two older retained native fixtures. Exact candidate deduplication resolved
those regressions without increasing the limit. Clean export
`OUTBOX/joint-label-clean-bROv6o` passes **736 Python tests and 33 Node tests**.
New tests compare selection with exhaustive enumeration of 160 small problems,
exercise the work bound, deterministic dynamic ordering, immutable inputs,
duplicate positions and preservation of distinct pointers. Existing tests still
reject crossing pointers, text collisions and native budget excesses.

`OUTBOX/story-ownership-eval-20261029/joint-label-replays-v2/summary.json`
records unchanged-output replays through the panel preview and full native
bundle compiler. All **16 originally accepted answers** now compile with the
stricter ownership rules. Astra dependency-failure is additionally recovered:
**17 of 22 complete retained drafts** compile. Five remain held: Luna gravity
and Astra compound-interest exhaust label search; Astra inverse-mapping has
no joint placement; Luna compound-interest and Astra gravity exceed unchanged
native budgets. Incomplete drafts and transport timeouts were not relabelled
as successes. Observed preview-plus-native preparation for accepted replays was
57–446 ms; this excludes model generation and is not tablet response latency.

Recovered final PNGs for blue-sky, proof-dependency and dependency-failure were
inspected. The box labels now have visible ownership pointers, but the blue-sky
circle annotations remain visually loose; compiling is not full visual approval.
Next: general contour-aware annotation and resource preflight, then fresh
quality/latency evaluation. No tablet writes, server changes, new model calls,
production prompt changes or broad rollout occurred in this solver iteration.

### Contour-owned symbolic labels (2026-10-29)

External labels on symbolic circles, people, suns, clouds and other objects now
attach to actual compiled contour segments, not empty bounding-box corners.
The deterministic selector considers at most 32 ranked distinct endpoints and
uses the same scene-ink clearance as rectangular pointers. Text wholly inside
a closed contour needs no pointer; the existing joint solver still rejects
text/ink collisions. Geometry, words, font size and all native budgets remain
unchanged. Added pointers consume the existing stroke budget.

Clean export `OUTBOX/contour-label-clean-hQKLDn` passes **742 Python tests and
33 Node tests**. Six new tests cover real contour endpoints on four sides,
diagonal circle labels, inside-versus-bounding-box containment, obstacles,
immutable inherited annotations and pointer budget accounting.
`OUTBOX/story-ownership-eval-20261029/contour-label-replays/summary.json`
retains **17/22** complete-draft preview/native-bundle successes, with the same
five holds as the joint-label replay. These are saved outputs, not fresh model
answers. Inspected final previews for Astra blue-sky and sensor-alarm and Luna
inverse-mapping show explicit object-label ownership. They are not a complete
teaching-quality approval: for example the inverse picture still relies on its
caption to explain why reversing a many-to-one mapping is not a function.

No tablet writes, installation, model calls or production changes occurred.
Next: detect unavoidable stroke-budget excess before joint placement, so an
impossible drawing receives useful resource feedback instead of search failure.

### Stroke-resource preflight before label search (2026-10-29)

`compile_panel_shapes` now counts each stage's new geometry strokes and its
label glyph strokes before joint placement. Word wrapping only translates
glyphs; it does not change their pen-lift count. Implicit axis labels count too.
Inherited ink is not charged as new ink. Pointers can add strokes, so the count
is explicitly a lower bound (`exact: false`); a passing preflight still runs
all layout, native encoding, point, time and whole-story checks. No content is
removed, no stage is split, and the 64-stroke ceiling is unchanged.

The new failure includes panel identity, stage index and separate geometry/text
costs through the existing typed resource-feedback path. It needs no provider
call or new retry mechanism. The continuous font never has more strokes than
the original glyphs (`notebook_glyph_paths.select_paths`), so an excess here
cannot be rescued by the existing original-font fallback.

Clean staged export `OUTBOX/panel-preflight-clean-G4JyPT` passes **747 Python
and 33 Node tests**. Tests cover immutable inputs, glyph-cost invariance under
both existing font modes and wrapping, implicit axis lettering, inherited
stages, and collision checks after a passing preflight.

The same 22 complete retained answers were compiled before and after the change
using `OUTBOX/story-ownership-eval-20261029/replay_preflight.py`; summaries are
`preflight-baseline-summary.json` and `preflight-replay-summary.json`. The same
17 succeed, with identical native delivery-point counts. Luna gravity now
reports a minimum **92 label strokes** instead of a layout-search failure;
single-run compilation took 2.852 ms versus 269.246 ms. Luna compound-interest
reports a minimum 65 strokes before placement (16.981 ms versus 181.164 ms).
These are offline compilation measurements, not provider or tablet latency.
Both answers remain held; useful feedback is not a successful answer.

Device-context inspection still reports `active: false`, `fresh: false` on the
test notebook. No device writes or runtime changes were made. Fresh generation
with bounded repair and an active-device preservation test are still required.

### Resource-feedback correction and fresh stress run (2026-10-29)

The offline evaluator's existing optional **one correction per lesson** now
accepts typed native-resource failures, not just JSON/schema failures.
`correction_feedback` returns the existing compiler-owned count/limit/breakdown
under `native_resource_budget`; exception prose is not forwarded. The original
question, panel intent and exact inherited items are retained. A corrected
panel goes through the same full validation. Resource and schema corrections
share the same single allowance. Default evaluation still uses zero repairs;
production `generate_notebook_story` still has no retries. Transport deadlines,
model mismatches, explicit unavailability and layout failures remain ineligible.
No prompt, host configuration, production runtime or tablet content changed.

Clean export `OUTBOX/resource-repair-clean-ZTrxsm` passes **752 Python and
33 Node tests**. New tests cover typed numeric feedback without exception prose,
default no-repair behavior, exact base preservation, retained original failed
outputs, a failed correction ending immediately, and the shared lesson-wide
allowance. Tests establish control flow, not generative quality.

Fresh stress questions used the original packet and frozen prompt with the
still-configured Astra evaluator, one allowed correction and a 30-second
per-call deadline. Artifacts:
`OUTBOX/story-ownership-eval-20261029/fresh-resource-repair-astra/`.

| Question | Fresh result | Total offline wall time |
| --- | --- | --- |
| Gravity | Story request timed out; zero completed responses | 30.017 s |
| Compound interest | First-pass preview and full native preparation pass | 47.144 s |
| Inverse mapping | Held at final panel: no joint clear label placement | 40.407 s |

After the timeout, the collector was confirmed terminal and the endpoint
returned `invalid_request` to an empty probe (not busy) before the two untouched
questions were attempted. The failed gravity run was not retried or replaced.
No fresh question used a correction. Thus this fresh run proves **1/3 compiler
successes**, not resource-repair effectiveness or an acceptable response time.
The compound-interest start, first-year and final previews were inspected:
the picture builds cumulatively, final values are $133.10 and $130, and its
takeaway correctly qualifies connecting segments between annual balances.
Its 47.144 s includes 45.823 s in model calls; changing renderer speed alone
cannot meet the under-10 s user target.

A separate **targeted saved-panel repair**, not another fresh lesson, uses the
retained Luna gravity draft that needs at least 92 label strokes. Astra received
that exact failed panel, its unchanged validated base and typed resource counts.
One call returned two concise labels (equal time steps; gaps 1,3,5,7) instead of
eight repetitive labels. Whole-story/native validation passed with 1,959 delivery
points in **5.383 s** total (5.000 s provider time). The final PNG was inspected:
the inherited distance-time curve/markers remain and the labels preserve the
panel's increasing-gap explanation. It is a limited visual check, not a learner
study or tablet proof. Original and corrected artifacts are retained under
`OUTBOX/story-ownership-eval-20261029/targeted-resource-repair-astra/`.

The evaluation approach keeps raw failures, separates compiler success from
visual judgment, and avoids counting retries as first-pass success, following
[OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).
MyDude was asked to restore the isolated model to Luna without changing production;
that queued request is not evidence of restoration. Device telemetry still says
`active: false`, `fresh: false`. Next: fast-model fresh checks, generic unresolved
label allocation, then reviewed active-device drawing/preservation tests.

### Progressive callout allocation (2026-10-29)

The fresh inverse-mapping failure had an identifiable generic cause: two labels
on one object had zero mutually compatible positions in their existing domains.
Text and pointers could fit nearby, but those positions were never offered.
`corner_callouts` adds twelve measured alternatives (three horizontal offsets
at the four corners), only for labels with checked object/region ownership
pointers. Unattached mathematical labels retain their existing candidates.
All new boxes/pointers still pass canvas, geometry and annotation clearance;
neither text, font size, object geometry nor teaching order changes.

Trying all alternatives immediately recovered the failure but regressed the
previously accepted Astra blue-sky answer by exhausting search. That version
was not shipped. The joint solver now searches existing domains first, then
adds fallback candidates only after proving those domains unsatisfiable.
**Both searches share the original 4,096-work allowance and compatibility
cache**; a budget exception does not trigger another search. Existing feasible
layouts therefore keep their placements. There is no new retry/model call.

Clean staged export `OUTBOX/progressive-callout-clean-36h7PW` passes **759 Python
and 33 Node tests**. New tests cover bounded measured candidates, unchanged
primary order, two annotations on a branched shared picture, preserved original
input/inherited ink, fallback collision checking, an empty initial domain,
unchanged successful assignments, and a five-unit search whose combined passes
must fail at a four-unit allowance. All native limits remain unchanged.

`OUTBOX/story-ownership-eval-20261029/progressive-callout-replay-summary.json`
records **18/22** complete saved drafts compiling through the full native path,
up from 17/22. All prior successes retain their native delivery-point counts.
The earlier Astra inverse-mapping answer is recovered (3,129 delivery points).
The separate fresh-run inverse-mapping failure is also recovered unchanged
(3,475 points). These are renderer replays, not fresh model success rates.
Original timeout/failure results remain untouched.

Final diagrams were visually inspected; ownership pointers now connect both
annotations without overlaps. The long callout and the left object's name
still share a crowded top line, so this is a recovered legible layout, not
blanket aesthetic approval. Step-by-step PNGs and exact native offline playback:
`OUTBOX/story-ownership-eval-20261029/progressive-callout-previews/{original,fresh}/`.
Four original complete drafts remain held (two stroke excesses, one whole-story
point excess, one search-budget exhaustion). No tablet write, deployment,
production model change or fresh provider call occurred in this iteration.

### Conflict-directed label backtracking (2026-10-29)

The remaining Astra compound-interest replay is not merely a slow search.
The two endpoint labels and the gap label each have pairwise-compatible
positions, but no combination places all three. Seven unrelated annotations
made chronological backtracking enumerate choices that could not repair this
cluster. An offline exhaustive probe of pairs/triples established that fact;
it is diagnostic code, not a new production search or a higher budget.

`notebook_label_solver.select_labels` now retains the earlier choice identities
that removed candidates from each remaining domain. On failure it backtracks
past a choice only when that choice cannot explain the failure. Causes are
conservative unions, not guesses based on label names, question text or model.
Every candidate choice and uncached pair check is still charged to the same
4,096-work allowance, shared by primary and fallback domains. Geometry,
candidate preference order, collision checks and ink limits are unchanged.
An impossible scene still returns no partial placement.

The retained failure now reaches a genuine `no joint clear label placement`
result with **1,366 pair checks**, instead of exhausting the work allowance
after 3,456 checks plus candidate choices. This does **not** recover that answer
or justify automatically retrying the model. It separates inadequate placement
options from insufficient search. The next layout work is generic ownership
and callout placement for tightly packed mathematical points/curves, without
moving the data, shrinking lettering or silently dropping annotations.

Clean staged snapshot `OUTBOX/cbt-KV1EUk` passes **763 Python and 33 Node tests**.
Added tests cover an impossible cluster surrounded by irrelevant choices,
backtracking to a genuinely responsible earlier choice, fresh fallback cause
state, and 200 additional small problems checked against exhaustive solutions.
The initial longer snapshot path exceeded the existing socket path guard in
two transport tests; the same code passes from the shorter path, with no change
to that guard. Saved-draft replay remains **18/22**, with identical rendered-plan
hashes and delivery-point counts for all successes, not a new model success rate.
Evidence is under `OUTBOX/story-ownership-eval-20261029/` in
`cbt-baseline-summary.json`, `cbt-clean-summary.json`, and `probe_label_search.py`.
Tablet telemetry remains inactive; no deployment, model call or notebook write
was performed. MyDude review was requested, not assumed received.

### Mathematical fallback callouts (2026-10-29)

Fallback placement now covers dots, circles, lines/arrows, sampled/polynomial
curves and connectors, not just symbolic objects and rectangular regions.
The same twelve bounded corner candidates are offered only after primary
placements prove impossible. Each mathematical fallback must acquire a clear
pointer to its owner's **actual drawn contour**, not an empty bounding-box
corner. Original near-label candidates retain their previous formatting and
pointer policy. Axis names and numeric axis endpoints do not gain remote
callouts. Data, words, font size, panel order and prior picture geometry stay
unchanged; only annotation placement is expanded.

`_place_labels` accepts separate fallback attachment validators, so rejected
pointers cannot silently turn into detached fallback text. Whole-scene
obstacles, reserved boxes and other labels/pointers still participate in the
joint collision checks. New pointers consume the existing native stroke,
point and pen-time limits, and search retains its shared 4,096-work ceiling.

Visual review of the first recovered chart found that two non-overlapping
wrapped labels still read too much like one phrase. Fallback text boxes now
reserve twelve units of padding versus six for local labels. An eighteen-unit
experiment improved that chart but made the retained inverse diagram
unplaceable; it is not the shipped policy. Twelve retains all previous
successes. The final previews have no ink/text overlap, but top-row grouping
is still crowded in the inverse diagram and needs further composition work.
This is a placement recovery, not a blanket visual/teaching-quality pass.

Clean staged export `OUTBOX/mco-19h3EN` passes **769 Python and 33 Node tests**.
New tests force generic point/circle/open-curve fallbacks, verify actual contour
endpoints, obstacle rejection, unchanged local labels, inherited math geometry,
fallback spacing and enforcement of the ordinary native stroke cap.
`OUTBOX/story-ownership-eval-20261029/math-callout-clean-summary.json` records
**19/22** complete retained answers accepted, up from 18/22. The recovered
Astra compound-interest draft is unchanged (2,796 native delivery points).
Seventeen old successful plans have identical hashes; inverse-mapping remains
accepted with its wider fallback clearance (3,133 points instead of 3,129).
The separate fresh-run inverse failure remains replay-recovered (3,479 points).
The other three original complete-draft holds are genuine resource excesses.

Stage-by-stage previews and native offline playback are in
`OUTBOX/story-ownership-eval-20261029/math-callout-spaced-preview/` and
`spaced-owner-callout-previews/{original,fresh}/`. Earlier experimental artifacts
remain separately labeled. No new model calls, production configuration change,
tablet write or deployment occurred. MyDude review was requested; rollout and
fresh-model reliability/latency remain unproven.

### Exact affine lowering before model correction (2026-10-29)

The font preflight correctly counts the currently selected glyph paths; the
two retained Luna stroke excesses are not an accounting bug. Investigation of
the remaining whole-story point hold exposed a separate procedural cost:
`_sample_curve` sampled constants and linear polynomials at 65 points, just
like genuinely curved polynomials. Subsequent native densification paid for
the unnecessary segment boundaries in every inherited snapshot.

An affine polynomial now lowers to its two domain endpoints, including lists
with exactly-zero higher coefficients. This is exact geometry, not approximate
decimation. Any nonzero higher coefficient, however small, retains the existing
65 samples. Model-supplied polyline vertices are untouched. The same data-range
checks, mapped coordinates, area baseline/closure, hatch generation and native
densifier still apply. No sampling parameter is delegated to the model.

The unchanged Astra gravity answer now fits: **11,821 materialized snapshot
points**, versus 12,187 before, under the unchanged 12,000 cap. Native delivery
uses 3,578 points. All nineteen previously accepted saved answers retain their
exact plan hashes and delivery-point counts. The complete-draft replay is now
**20/22**; the two remaining cases exceed the 64-stroke stage limit. No provider
call or model correction was needed for this improvement.

Clean staged export `OUTBOX/aff-RJbBwr` passes **776 Python and 33 Node tests**.
New tests cover constant/positive/negative/zero-padded affine coefficients,
exact equivalence to direct lines, preservation of tiny nonzero curvature,
unchanged authored polylines, invalid inputs and out-of-frame rejection.
Area tests still check every hatch against the sampled boundary, now using the
actual segment count. A separate comparison checks affine hatches against the
previous dense boundary to eight decimal places; no fill region is invented.

Evidence: `OUTBOX/story-ownership-eval-20261029/affine-sampling-clean-summary.json`
and `affine-gravity-preview/{index.html,playback.html,native-result.json}`.
The first and final stage PNGs were inspected: equal-width time regions and
the 4.9/14.7/24.5 metre annotations are preserved. The bottom annotation still
sits close to axis labeling, a composition concern rather than a geometry
failure. Recovered compiler acceptance is not a teaching-quality or tablet
pass. No production deployment occurred; the isolated evaluator remains Astra,
and PR4 had no recorded reviews when checked. MyDude review was requested.

### Fresh-generation latency gate (2026-10-29)

After the renderer fixes, three fresh Astra answers (fractions, integral,
inverse mapping) passed first-attempt compilation and native preparation with
zero corrections. The question packet and host prompt were unchanged. These
are newly generated answers, distinct from the 20/22 retained-draft replay.
Their complete generated JSON, measurements and a no-provider replay tool are
checked in under `evaluations/fresh-post-renderer-20261029/`.

Generation took **34.360, 34.244 and 39.375 seconds**. Each used five sequential
calls: one story and four panels. Summed provider time was 33.940, 33.467 and
38.375 seconds respectively. This identifies request/model time as the dominant
cost; the remainder includes transport and compilation, not just drawing.
All three exceed the live generator's single 30-second deadline. The offline
evaluator permits 30 seconds per call, so its success is not production
readiness. Internal JSON tokens at 2.8–3.0 seconds are not first visible ink.

The next controlled experiment should generate one complete typed story-lesson
envelope, retaining the existing additive panel/base structure, high-level
shapes and whole-lesson native validation. This avoids sending the model back
to the server once per stage, without giving the model responsibility for pen
points, placement or animation. Do not parallelize dependent requests or draw
an unvalidated prefix. Keep the serial implementation as the comparison control
until full-answer latency, reliability and quality have been measured. Configure
the isolated host through its owner; do not override its prompt per request.

Visual review still finds numeric-axis clutter and plain-text mathematical
notation; compiler acceptance is not a polished-lesson claim. No tablet writes
or production configuration changes accompanied this evaluation. MyDude was
asked to restore the isolated model to Luna and review the fewer-request
experiment; a queued request is not confirmation of either action.

### Single-call comparison implementation (2026-10-29, offline only)

`notebook_complete_story_eval.py` now implements that comparison arm. It sends
one `task=lesson` request to the existing isolated `notebook-eval.sock`, expects
the configured `story-panel-v1` bounded wire envelope, and requires its payload
to be one complete `story-lesson` with all additive panel drafts. The existing
`parse_semantic_reply` and `native_story_bundle` remain authoritative. No new
drawing language, geometry path, model selector, repair loop or live route was
introduced. The production server still uses its existing configuration.

The owner installs `complete_story_instructions()` as the isolated host prompt;
the notebook caller sends only the question and original PNG. Story schema and
drawing vocabulary are shared verbatim with the serial control prompt. A hash
regression test proves that the serial prompt remains byte-identical. Both arms
leave screen coordinates, label placement, hatch strokes and motion to code.

The evaluator records the request, exact bounded response, model identity,
usage, first-token metric and intended prompt hash. The latter is explicitly
not host attestation. It rejects wrong identity/model/format, incomplete or
duplicate-key JSON, changed questions and plain-answer substitutions. Explicit
clarifications are retained but do not count as visual successes. Exactly one
attempt is made, even for deadline and native-resource failures. The total
deadline includes model generation, whole-story validation and native asset
preparation. `preparation_ms` measures that path; `preview_ms` measures offline
HTML/image production separately. Neither is tablet first-visible latency.

Commands from `tools/herd-board`:

```sh
python3 notebook_complete_story_eval.py prompt
python3 notebook_complete_story_eval.py run QUESTION.txt INPUT.png /ABSOLUTE/PRIVATE/notebook-eval.sock NEW_OUTPUT_DIRECTORY --expected-model CONFIGURED_MODEL
```

The `prompt` command only prints the proposed fixed prompt; it does not install
or select it. The owner must configure and confirm the isolated host first.
Use the original fourteen-question packet and keep the model identical between
arms. Start with the same three recently generated questions; expand only after
checking full-answer validity and visual quality. Do not compare mock timings
or mistake regenerated saved answers for fresh model evidence.

This approach follows the recommendation to consolidate sequential model
requests in [OpenAI's latency guide](https://developers.openai.com/api/docs/guides/latency-optimization#make-fewer-requests),
but its latency and quality benefit here remains an empirical question. The
first implementation tests use injected transport fixtures only. No fresh
single-call model success, host installation or tablet rollout is claimed.

Clean staged export `OUTBOX/sc-9DNFW1` passes **792 Python and 33 Node tests**.
The sixteen new tests cover one-call success, preserved original capture,
branching native preparation, no output-directory overwrite, last-panel failure,
question/binding/model/format mismatches, duplicate JSON, byte caps, explicit
clarification, plain-answer rejection and native-preparation deadline/failure.
These are transport fixtures, not measured model successes.

### Human follow-up context failure (2026-10-29)

James's live handwritten request to explain the prisoner's dilemma visually
returned a clarification after misreading the words. Request
`notebook-495d4a0988b240ffaae36cd351280f99` completed save acknowledgment at
7.457 seconds; the screenshot shows handwriting retained above a Pi Dog label.
This is an understanding failure, not a visual lesson pass.

A clearer second note received prose. The follow-up "Can you do it visually?"
then received a generic promise rather than a diagram. Inspection of the actual
model input `~/.cache/herd-board/pages/905df7ae-20261029-052512.png` proves that
only this last sentence was supplied. The existing `notebook_crop(frame,
baseline)` removes prior page content, while the isolated model has no chat
history. It therefore lacks the referent for "it". This is separate from the
first handwriting misread and from rendering latency.

The next input-design fix must preserve latest-question focus AND bounded
same-page visual context, without borrowing unrelated chat history or adding
question-specific templates. Use these observed failures as regression inputs;
do not silently inject a corrected transcription and call that a human pass.
Evidence: `OUTBOX/human-question-20261029-watch/`,
`OUTBOX/human-question-20261029-settled.png`, and the exact cached input above.
No live input-path change has yet been deployed.

### Bounded visible context candidate (2026-10-29, offline only)

`notebook_visual_input.py` now prepares the isolated model's visual input from
one captured frame and the existing same-page answered-frame baseline. It
retains the current new-ink detector and refusal when nothing new was written.
The newest crop remains pixel-identical, unscaled, in a fixed left column. If
there is dark visible content outside that crop, an 80%-scale view of the same
visible paper appears on the right. A caller-generated description identifies
the two panels, explains the duplicated newest input, treats reference content
as data rather than instructions, and requires clarification for a missing or
ambiguous referent. No history service, OCR, other page, or chat transcript is
read. With no baseline, it keeps the existing crop and explicitly discloses
that newest-question identification depends on visible page order.

The maximum composite is 2145 by 1692 pixels, below the existing 4-million-pixel
IPC cap. Encoded byte limits remain unchanged and fail closed; there is no
lossy repair of an over-budget input. Existing pending-request, page, view,
surface and input-revision checks still bind generation and publication. Both
the semantic worker and experimental serial story worker carry the same image
description with the supplied image; fixtures and legacy routes are unchanged.

This preserves local handwriting resolution while adding visible reference,
consistent with the small-text caution in the [OpenAI vision guidance](https://developers.openai.com/api/docs/guides/images-vision).
The provider may still resize its input, so recognition quality and added
latency must be measured, not inferred from pixel tests. It deliberately does
not solve offscreen context or stale-baseline alignment after scrolling. Those
remain explicit limitations, not a claim of complete conversational memory.

Clean staged export `OUTBOX/vc-FmFDTH` passes **803 Python and 33 Node tests**.
The eleven new tests cover crop pixel identity, reference composition,
unchanged source images, no-new-input refusal, missing-baseline disclosure,
control masking, maximum transport dimensions, byte-budget rejection, route
isolation and description propagation to each isolated story call. There are
no fresh model calls or tablet writes in this suite. Production has not been
restarted or changed for this candidate. Next: review, then isolated crop-only
versus context-image tests using genuine follow-ups and standalone questions;
check that old content does not hijack a new subject before rollout.

During this work James also tried “How do capacitors work? Explain visually.”
Live request `notebook-999c42d5c9d34d7f89a26ee488aa6ee2` reached save acknowledgment
in **7.939 seconds**, but `OUTBOX/human-question-20261029-0537.png` shows prose
only. No first-visible frame interval was captured for that request. This is
another failed visual acceptance test, distinct from missing follow-up context:
a standalone question still needs reliable lesson generation. The same screen
also shows the preceding prisoner's-dilemma prompt misread as a publication.
Do not count successful delivery of these replies as illustrated-answer success.

### Region ownership across later additions (2026-10-29, offline only)

The fresh one-call odd-square answer exposed a semantic layout defect, not a
model geometry error: the label for the inner square cleared all ink strokes
but occupied the interior of the top strip added later. A short leader to their
shared edge was insufficient to distinguish the owner. Whole-picture line
collision checks alone cannot prevent that failure.

`notebook_label_attachment._region_clearance` now rejects a label candidate
overlapping a competing rectangular region anywhere in the planned picture.
An enclosing parent of the actual owner is not a competitor; child regions,
siblings and partial overlaps are. Both rectangular and contour attachments
apply this rule. It uses geometry, never the question, label wording or a
topic-specific placement. The finite joint search still chooses among existing
placements; it does not change geometry, resize text, move inherited ink during
playback, relax drawing budgets or call a model.

The unchanged saved odd-square answer now places its inner-area label below the
inner square with a pointer, outside the later strip. Actual final PNG inspected:
`OUTBOX/region-ownership-replay-20261029/case-4/panel-result.png`.
The fourteen retained one-call responses still yield six schema/native passes
and eight nonpasses; this fixes a visible defect, not the other model failures.
The older twenty-two complete drafts remain twenty accepted/two rejected, with
all twenty accepted native-plan hashes identical to the prior affine-sampling
baseline. Evidence: `OUTBOX/story-ownership-eval-20261029/region-ownership-clean-summary.json`.

Clean export `OUTBOX/ro-hg0aJo` passes **806 Python and 33 Node tests**. Three new
tests cover future sibling regions, nested/overlapping ownership and unchanged
inherited annotations/native limits. This is offline proof only; not deployed.
Remaining limitations include competing nonrectangular regions, ambiguous
nearby curve labels and the separate handwriting/context and generation failures.

### Mathematical relation glyphs (2026-10-29, offline only)

The unchanged fresh gravity answer failed because its correct `d ∝ t²` label
contained an unsupported glyph. The plotter alphabet now includes eleven
ordinary mathematical symbols: `∝ ≈ ∞ ± ÷ · → ← ↔ ↑ ↓`. Each is explicit pen
geometry, not a raster, replacement box or semantic substitution. Unknown
characters still fail. Label sizes, advance, collision checks and native
stroke/point/time caps are unchanged; no model retry is involved.

Clean staged export `OUTBOX/mg-C1ohLC` passes **810 Python and 33 Node tests**.
Four new tests cover distinct bounded glyphs at all three tested sizes,
proportionality versus infinity, actual v6 stroke round trips, and continued
refusal of unsupported characters. The original fourteen one-call responses
now yield seven native-preparation passes rather than six; gravity is the only
new pass. Its final preview is
`OUTBOX/math-glyph-replay-20261029/case-3/panel-gaps.png`.
This is recovery of a retained answer, not a new generation success or tablet
proof. Production is unchanged.

### Caption contract recovery (2026-10-29, not deployed)

Five cases across the same-model serial and one-call runs stopped because a
caption contained thirteen or fourteen whitespace-separated words. Inspection
found ordinary short explanatory sentences, including spaced mathematical
expressions, not overlong text. The story validator already had a separate
180-character plain-text limit. Treating twelve words as an additional hard
failure rejected valid explanations without improving geometric safety.

The 180-character limit is unchanged and now produces typed, value-free
`caption_characters` feedback. Short, single-sentence prose remains the prompt's
quality requirement; approximately twelve words is guidance. Captions are not
truncated or rewritten. Both prompt protocols share the same revised schema;
the prompt regression test proves this is the only serial-prompt change from
the frozen comparison baseline. The live prompt/configuration is untouched.

Clean snapshot `OUTBOX/cp-3BjJM7` passes **812 Python and 33 Node tests**. Tests
cover unchanged caption text through narrative packets/native text, actual
saved stroke geometry remaining identical, 180-character Unicode/Latin
boundaries, over-limit refusal and no private text in feedback. The fourteen
unchanged one-call answers now yield nine native-preparation passes (previously
seven after the glyph fix). Inverse mapping and Pythagoras recover. This is
compiler recovery, not fresh-model or visual-quality proof; their drawings
still need review. Evidence: `OUTBOX/caption-contract-replay-20261029`.
The three serial runs that stopped before drawing remain incomplete; accepting
their captions does not manufacture missing model responses.

Keeping the shared prompt in code and evaluating the scoped change follows
the [OpenAI prompt-engineering guidance](https://developers.openai.com/api/docs/guides/prompt-engineering).

### Live top-anchor blocker (2026-10-29, unresolved)

The held illustrated reply on page `a5890c3d-509a-45d0-9c9c-9fad100b636a`
reproduces in the production preservation parser: mode-2 TOP sentinel
`(0,281474976710654)` is not supported by its exact multi-anchor resolver.
The page also contains ordinary newline and BOTTOM anchors. This is a placement
failure after model completion, not evidence of a slow or missing model reply.
The foreground has since changed, so the held answer must not be replayed there.

`top_anchor_fixtures` adds six paired native stimuli: plain text, prefix
insertion, heading, wrapping, leading blanks and a nonblank first character.
Each pair has identical text and marker style, differing only in the marker's
coordinate frame. These fixtures deliberately do not enable TOP in the parser.
The 42 focused anchor/fixture/preservation/capture tests pass offline.

Device experiment `OUTBOX/top-anchor-yRzq60/record.json` provisioned twelve new
synthetic source pages in the existing isolated folder. The first hidden probe
returned `unavailable` before obtaining a source controller; the library has
not registered the new document. No retry or foreground insertion occurred.
Foreground saved-page hashes and document/page/surface/content/ink revisions
were unchanged across that attempt. Native TOP coordinates remain unproven.
Next: discover the diagnostic document with a user-coordinated interface reload,
measure paired marker displacement against native cursor/text bounds, then
implement the general anchor rule and test preservation before deployment.

### Exact saved-text append comparison (2026-10-29, source only)

`compare_text_append` reuses the existing measured preservation snapshots and
external character-HMAC key. In addition to preserving all existing text,
styles, ink and images, it requires the exact expected suffix, UTF-16 range
and bounded materialized newline gap. It rejects duplicate/extra text,
same-length substitutions, added ink/media and new styling on old paragraphs.
Native atom splitting or serialization order does not change character identity.
No extra journal, lease, transcript, retry or success authority is introduced.

The legacy leading-newline anchor heuristic now runs only when a live group
actually has an anchor; unanchored text still receives full CRDT validation.
This does not enable TOP or alter any anchored coordinate rule. Fifty focused
fixture/preservation/capture/append tests pass. The comparison is not wired to
production or sufficient by itself: stream ownership must still be claimed
before mutation, hold native input, bind both saved snapshots/measurements to
the exact job, and advance the consumed sequence atomically after proof. A
lost acknowledgement or restart must keep the existing attempt held.

Clean staged snapshot `OUTBOX/exact-append-X1iNmU` passes **896 Python and
57 Node tests**, none skipped. This is regression evidence, not an integrated
streaming or physical-tablet success. No production files/configuration changed.

### Measured TOP anchor support (2026-10-29)

The six controlled pairs in `OUTBOX/top-anchor-yRzq60/idle-page-measurements.json`
all completed on the tablet: plain, prefix-inserted, heading, wrapped, leading
blanks and nonblank first character. Each unanchored marker bounds Y was 96;
each TOP-anchored marker bounds Y was 363.59375. The 267.59375 difference
equals measured native cursor-zero Y, not text-bounds Y=234. The foreground
saved hash, document/page/surface and content/ink revisions remained identical.
The failed UI banner was dismissed without resending, enabling these hidden
source probes; no foreground drawing or text was inserted.

The parser now maps nonempty TOP anchors to index zero through the existing
exact, hash-bound native sample capture. It does not hard-code that observed Y
or infer offsets from a font. Legacy capture requests select the exact-order
path before applying the leading-newline heuristic. Empty text, unsupported
anchors, mismatched hashes/lengths/samples and moved old ink still fail closed.
62 focused fixture/multi-anchor/preservation/capture/run/append tests pass.
Read-only replay of both actual failing saved pages now produces complete
capture plans (2 and 14 distinct cursor indices). That proves preparation,
not yet successful insertion/persistence on those pages.

Separately, the latest spring–mass question's previous `invalid_response`
payload was not retained. One new diagnostic call on its saved image returned
valid prose in 2.715 seconds, not a visual lesson. Evidence is under
`OUTBOX/live-reply-diagnostic-FA1ipg/authorized`; this does not reproduce or
explain the original failure and was never inserted. Do not call it fixed or
substitute that prose for the user's requested illustration.

The TOP-only parser delta from `297e359` was deployed into the launchd server
copy, preserving its other differences; the backup is
`OUTBOX/top-anchor-yRzq60/production-preservation-before.py`. The installed
module passes 54 focused tests using the new fixture definitions from the
worktree (the first test invocation found the older production fixtures and
failed two imports, not parser assertions). The authenticated restart route
was called once after confirming no waiting/writing jobs. Listener PID93590
returned fresh telemetry on the same surface/page, with content revision4 and
ink revision73 unchanged. No tablet-interface restart, model resend, old held
answer replay or streaming activation occurred. Live insertion and reopen
proof on a TOP-bearing page still remain; review was requested in parallel.
The committed branch through `297e359` was pushed to the existing PR branch
using James's verified Mac GitHub login, without merging.

### Follow-up context deployment and retained rejection evidence (2026-10-29)

The saved 12:06 input (`pages/905df7ae-20261029-120600.png`) contains only
“Plot the oscillation of the mass.” The production route still used
`notebook_crop`, so earlier visible equations and discussion were absent from
the isolated call. This is a concrete context loss, not evidence that the
model had read and ignored the previous conversation.

Activated the narrow semantic-route portion of `3fb2600` plus `624a1d8`:
exact latest crop alongside bounded same-frame visible reference. The reference
is data, not a second instruction, and offscreen content is not retrieved.
Conceptual requests may use explicitly stated normalized examples; missing
measurements, personal facts or exact-calculation inputs must not be invented.
The production worker receives this description with the image; no model,
prompt-file, tablet QMD, streaming or shared-chat configuration changed.

Paired off-device evidence: `OUTBOX/followup-context-D0uiWu`. Exact byte
matching located the original crop once within its saved pre-reply frame.
Crop-only returned clarification in 2.231 seconds. Same-frame context attempted
a lesson in 4.504 seconds, but was rejected for nine samples exceeding the
eight-sample chart contract. Its caption also claimed cos(t) while its supplied
values described a different period. **This is not a successful illustration.**
Neither response was inserted. Do not fix it by truncating samples or changing
the eight-sample limit for this question: function-based plots must compute
their values procedurally from bounded mathematical parameters, and the critic
must check captions against the picture.

Three earlier independent saved-input calls in `OUTBOX/reply-rejection-TTo9sS`
reproduced the generic layout failures: one out-of-region label and two
cross-stage label collisions, completing in 5.984, 4.755 and 4.309 seconds.
The branch already has opt-in object-anchored label placement, but the deployed
old prompt/renderer do not expose it. Prefer bringing that general mechanism
through evaluation/deployment over making model-authored pixel coordinates
pass by guessing label meaning or weakening collision checks.

The rejection capture in `4b33063` was corrected by `92ca228` after review:
only semantic-call rejection is retained, never downstream publication failure;
private temporary bytes are fully written/fsynced, then published atomically
without overwriting an earlier request. Nothing in delivery/recovery reads
these files. Partial writes and capture failure cannot publish a response.
There is no automatic resend. The production-copy regression selection passes
18 tests; the source visual/worker selection passes 34. A broader focused
selection before the added assumptions assertion passed 44 tests.

An initial restart check stopped on an active user reply. After all jobs were
terminal, the authenticated Mac-server restart completed once; listener PID47128
returned fresh telemetry on the same page/surface, content revision7 and ink
revision213 unchanged from the immediately preceding observation. No tablet UI
restart or notebook input was sent. The installed delta includes only context
input and corrected rejection capture alongside the previously deployed TOP
fix. Source review is requested; native follow-up behavior still awaits a new
user exchange. First-visible latency and persistence are NOT established by
these off-device provider timings.

### Procedural function plots (source and offline previews only)

The typed panel `plot` now accepts exactly one of supplied data points,
polynomial coefficients, or a bounded `function` object with `name`,
`amplitude`, `rate`, `phase`, `offset` and a separate domain. The three function
names are `sin`, `cos`, `exp`; the rule is
`offset + amplitude * name(rate*x + phase)`. These are mathematical primitives,
not topic-specific scenes or code/expression evaluation. Existing point plots
remain honest unsmoothed data; no failing response is silently converted.

`notebook_function_plot` computes bounded samples deterministically. Sinusoidal
plots cover at most four cycles and include every interior maximum/minimum,
including negative rates and nonzero phase. The frame therefore rejects an
out-of-range peak even between uniform samples. Exponential arguments stay in
[-30,30]. Constant functions use one segment; existing polynomial paths remain
unchanged. All generated points still pass whole-story compilation, existing
3,000-point/64-stroke/30-second stage limits, and native v6 encoding. No limit
was widened to accept the failed nine-sample model reply.

Four explicitly authored three-step examples (periodic, phase/offset, growth,
decay) live in `notebook_function_examples.py`; their captions and parameter
rules can be compared with computed values. Previews and v6 checks are at
`OUTBOX/function-plots-iNydjp/labelled/<example>/index.html`. Snapshot totals are
2,633 / 2,403 / 2,167 / 2,189 points respectively. These are renderer fixtures,
not generated-agent answers, screenshots, or live latency results. They do not
establish scientific correctness of arbitrary captions. Planner/drawer/critic
evaluation on the revised vocabulary and actual deployment remain outstanding;
the running old semantic prompt does not advertise these function plots.

### Generated function evaluation and point-label ownership

`OUTBOX/function-eval-Z9Lun0/run/index.html` compares four identical authored
narratives given to the fixed Luna-medium and Astra-medium drawers. All eight
generated their own typed function geometry and passed whole-lesson/native
preparation. No planner was exercised in this ablation. Completed drawer-call
medians were 5.080 s and 9.839 s; these are not tablet first-visible timings.
Both independent critics flagged Luna's periodic `-1` annotation below the
horizontal axis as a misleading input coordinate. Three of four reviews
completed; the last reached its 30-second deadline, with no retry or subsequent
call. Critic scores are uncalibrated opinions, not acceptance verdicts.

The generic fix gives every dot annotation a checked contour pointer, using
the existing whole-picture label solver. A label cannot cross unrelated scene
ink to reach its owner. Nearby dots still use the existing candidate order;
bounded diagonal fallback positions provide clearance from axes/curves for
long annotations. Words, font size, mathematical values, geometry, historical
stage placements and native budgets remain unchanged. The pointer consumes
ordinary native ink budget. No code recognizes a question or label's wording.

Clean-snapshot evidence: `OUTBOX/point-labels-g0PTi7/v2/index.html` re-renders
all eight unchanged raw model outputs before/after with zero model calls or
tablet operations. All eight still compile, including the cramped growth case
that the initial pointer-only change rejected. 89 focused tests pass, including
all side preferences, axis-crossing refusal, exact inherited annotation ink,
deterministic placement, diagonal fallback and native-budget enforcement.
These are offline renderer results, not live screenshots or a general quality
pass. Scale choice and interval annotations still need improvement; the source
story/panel path is not yet the production semantic route.

### Fixed production planner/drawer boundary (source only)

The production adapter can now opt into `role-production-v1`, distinct from
`role-eval-v1`. Each host registration supplies `production: {role, reasoning,
outputTokens}`, `fixedModel`, and a private fixed prompt. The only permitted
roles are planner and drawer; socket basenames are respectively
`notebook-planner.sock` and `notebook-drawer.sock`. Existing socket ownership
checks and lifecycle cancellation/drain behavior are reused. Neither request
JSON nor notebook content selects the model, effort, output cap or prompt.

The operator's `model_transport` config has exactly `agent`, `response_format`,
`deadline_ms`, and `roles` in this mode. `roles` contains one planner and one
drawer binding, each `{socket, expected}`. Expected identity fields are role,
harness, provider, model, reasoning_requested, requested_output_tokens and
prompt_sha256. The wire result adds a `production` binding alongside the usual
request ID, format, text and metrics. Python checks the entire binding on every
call; production and evaluation results are not interchangeable. Prompt hashes
are consistency evidence, not cryptographic host attestation.

The story generator routes `story` to the planner and `panel` to the drawer,
passing only the remaining parent deadline (currently at most 30 seconds).
Both Python and the JS responder reject a role/task mismatch. There is no
automatic retry, fallback, JSON repair, partial ink publication, or new lease.
Per-role call metrics remain separate; aggregate usage is not attributed to
one model. This version explicitly does not combine role routing with the
unfinished answer-streaming route, so it does not solve first-visible latency.

Tests cover actual Python -> two private JS sockets -> distinct fake models ->
whole story validation -> native bundle, plus wrong role/model/prompt/format,
fixed settings, deadline consumption and real server pending-job cancellation
after a simulated page change. These are integration tests, not real-model
teaching quality or tablet delivery proof. The external Pi host still needs an
owner-config production roster and installation checks before activation.
No live configuration, server process, tablet interface or notebook was changed.
