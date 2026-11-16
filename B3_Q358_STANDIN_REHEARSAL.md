---
title: "B3 q-358 Stand-in Scoring Rehearsal"
tags: [illustrated-primer, b3, handwriting, evaluation]
status: active
created: 2026-11-16
---

# B3 q-358 stand-in scoring rehearsal

Checked 2026-11-16 UTC. This tests the score path on agent-made pages; it is **not** a B3 accuracy result or permission to export James's pages. The B3 requirement is 100 James-authored pages, transcribed by him, with per-model corpus CER and WER committed ([Frontier PLAN](https://github.com/JAFairweather/herd-infra/blob/main/docs/frontier-review/PLAN.md), B3). The [method](HANDWRITING_ACCURACY_METHOD.md) and scorer at `illustrated_primer` `efd8213291b359271c1ac84d4d0d68b9bab72882` govern the run.

## Frozen stand-in method

- Twenty unique, agent-written one-sentence questions/statements were rendered as two-line 1200×520 PNGs with the open-licensed [Caveat handwriting font](https://github.com/googlefonts/caveat), subtle rotation and lined paper. Font SHA-256: `7af58d70e539c9195cc328617a68c9961ed804a4404b0b818989ba7c013e8776`. These are typeset glyphs, **not** pen strokes and not a representative child or James sample. Images, references, model text, and page hashes remain in `.scratch/dennis_q358/`, outside a checkout; only aggregates appear here.
- A separate set of **120** unique synthetic PNGs and manifest rows exercised the merged `handwriting_sample.py` with seed `q358-2026-11-16`: it returned **100 selected and 20 reserves**. The `eligible: true` flags mean only “eligible for this synthetic sampler exercise,” never James authorship or provider permission. None of these 120 images entered the 20-page model score.
- Each model saw the same frozen PNG and exact prompt once per page: “Transcribe exactly the handwritten text in this image, in reading order. Preserve spelling, case, punctuation, numbers and math. Do not answer the question or add commentary. Return only the transcription.” Prompt SHA-256: `05756206d001903d582b2f2c7bd2205383d079e1e7a5856a8d4112d366ba2df1`. No model result was shown while writing the references; the reference sentences were written before rendering.
- `codex login status` reported `Logged in using ChatGPT`; `codex exec --image` accepted `gpt-5.6-luna` at medium effort and `gpt-6-astra` at high effort through that existing sign-in. No API key, account, or billable Gemini call was made. `gemini-3.5-flash-lite` is the B3 planned direct-image baseline, but its project billing/terms and OCR adapter remain unverified (Hive `illustrated-primer-b3-provider-route-1116`). Its score is **missing**, not zero.
- The merged `handwriting_accuracy.py` applies Unicode NFC, collapses whitespace and trims ends, retains case and punctuation, then sums Levenshtein character edits over all reference characters for CER and word edits over all whitespace-delimited reference words for WER. Rates are corpus weighted. Error and missing counts accompany each rate. The 20-page exercise uses `score(..., require_complete=False)`; the actual B3 `--require-complete` requires 100 reference pages and complete Gemini/Luna outputs, plus Astra if enabled. [Method, References and score](HANDWRITING_ACCURACY_METHOD.md).

## Run and negative controls

All 40 calls returned a text file and exited zero. The output JSONL was scored with the merged scorer against the frozen references; all page/model text is stored only in scratch. The denominators are 710 reference characters and 151 reference words per model.

The actual CLI run used private stand-in JSONL files outside the checkout with `--model gpt-5.6-luna --model gpt-6-astra`; the scorer reported 20 pages. `git rev-parse HEAD` was `efd8213291b359271c1ac84d4d0d68b9bab72882` both before and after that check in the same shell. A real one-run score still depends on the upstream export, consent, Gemini adapter, adapter-generated receipts, and 100 references below.

| Stand-in arm | Scored / errors / missing | Character edits / CER | Word edits / WER |
| --- | ---: | ---: | ---: |
| Luna medium | 20 / 0 / 0 | 2 / **0.28%** | 2 / **1.32%** |
| Astra high | 20 / 0 / 0 | 0 / **0%** | 0 / **0%** |

These values describe only rendered Caveat pages. They cannot rank the models on physical handwriting or establish a B3 target. The scorer's actual unrounded ratios were Luna CER 2/710 = 0.0028169, WER 2/151 = 0.0132450; Astra 0/710 and 0/151.

**Failure mutation:** replace Luna's page 1 text with `z`, without changing any reference or image hash. Luna CER rises from 0.28% to **5.63%** and WER from 1.32% to **5.96%**. Under a **rehearsal-only** gate of CER ≤1% and WER ≤2%, the original passes and the mutant fails. This is not a B3 acceptance target; PLAN says the real target is set at B3. Changing an output's *declared* image digest was rejected; attempting `require_complete=True` on 20 pages was rejected. Those controls did **not** verify manifest membership or actual PNG bytes.

Pi Dog's q-358 method read (Buzz event `adce345fec1bbe71eb98dbd19a0c28d3f1c59f77adc36b5fbb444920a974dc98`; Hive `illustrated-primer-b3-scorer-manifest-binding`) exposed the boundary: the scorer accepts 100 wholly synthetic, internally consistent references and 200 outputs without a sample manifest. Its strict mode proves completeness of rows, not their provenance. The new `handwriting_binding.py` preflight checks final selected IDs, rank-ordered reserve swaps, actual PNG SHA-256 against the frozen sample, references and outputs against that digest, and adapter receipts against frozen prompt/model-config digests and exact output rows. A synthetic 100-page/200-output test passes; changing a PNG byte, a row digest, a receipt digest, or reserve order fails. This proves the validator's checks on stand-ins only. Actual receipts must be generated by the reviewed adapters; a self-consistent manually authored receipt cannot prove a provider call, permission, or the prompt actually sent.

## End-to-end B3 hop status

| Hop | q-358 state | Live gate and owner |
| --- | --- | --- |
| Saved tablet page → metadata snapshot | **Waiting on PR #264.** Agent-made PNG generation proves only stand-in input handling, not a saved-page read. PR #264 is [OPEN/draft at `b9c0e335`](https://github.com/JAFairweather/herd-infra/pull/264); its synthetic freezer is not `b3-export metadata`. | Pi Dog supplies reviewed read-only exporter, then operator readback. No tablet action in q-358. |
| Frozen list → authorship and separate provider permission | **Waiting on PR #264 and James.** A stand-in reference list needs no James attestation; it does not exercise caller authentication or per-page provider consent. | Pi Dog implements authenticated receipt; Dead Rabbit presents the enumerated private list; James gives page-linked authorship and provider-specific yes/no. |
| Authorized PNG → one-way private drop | **Waiting on PR #264.** Scratch PNGs prove neither one-way drop permissions nor an installed exporter. The draft has a writer primitive, not a working `b3-export run` or installed unit. | Pi Dog completes/reviews the route; James approves final-head install; operator reads back effective permissions and one authorized export. |
| Eligible PNGs → frozen sample | **Proven on 120 stand-ins:** merged sampler selected 100 and 20 reserves under a fixed seed. This tests deterministic selection and manifest shape, not real page eligibility. | James supplies enough authorized, inspectable pages; Dennis freezes real eligibility, seed, 100 plus reserves. |
| Frozen image → model transcription | **Proven on stand-ins for Luna/Astra CLI only; Gemini missing.** Same prompt and PNG per model; per-page results bind to opaque ID and image digest. No verified private-data adapter or live Gemini arm. | Dennis verifies effective IDs, account/terms, and provider-permission recheck before any real image call. Gemini money choice belongs to James. |
| Image → human reference | **Proven on stand-ins as a prewritten reference, waiting on James for B3.** Stand-in author knew the sentence. | Dead Rabbit sends private batches without model text; James writes 100 usable references. |
| Frozen sample → PNG bytes → references/outputs/receipts | **Preflight proven on 100 stand-ins, with byte/hash/receipt/reserve mutations rejected.** The earlier 20-page model exercise did not use this preflight. | Pi Dog reviews the private runner and real adapters; Dennis verifies immutable manifest, actual bytes and adapter-generated receipts before scoring. Authorship and permission remain separate live checks. |
| Complete pairs → CER/WER and committed baseline | **Scorer and mutation proven on stand-ins; actual B3 baseline waiting on James and all arms.** The earlier 20-page `--require-complete` check correctly rejected the incomplete exercise. | Dennis scores all 100 after complete model/reference pairs, checks JSON for private fields, commits only aggregates, Pi Dog reviews. No B3 target/real score exists yet. |

This status follows Pi Dog's q-297 source audit in Buzz, the [method](HANDWRITING_ACCURACY_METHOD.md), and current [PR #264](https://github.com/JAFairweather/herd-infra/pull/264). A local stand-in score does not turn a missing live route into a completed hop.

## Candidate models and data retention, read 2026-11-16 UTC

| Candidate | Rehearsal reachability | Provider terms as published; account fact still needed |
| --- | --- | --- |
| Direct `gemini-3.5-flash-lite` | **Not run.** Existing Primer credential exists, but this seat has no verified direct OCR adapter or billing status; a metered call would require a money decision. | Google's [Gemini API terms](https://ai.google.dev/gemini-api/terms) distinguish Paid API use through a Cloud Project with **active billing** from Unpaid use. Paid prompts, images and responses are not used for product improvement; [abuse monitoring](https://ai.google.dev/gemini-api/docs/usage-policies) retains prompts, context and outputs for **55 days** and may permit authorized human review of flagged content. Unpaid inputs and outputs may be used to develop products and human-reviewed; Google says not to send sensitive/personal content under Unpaid terms. [Storage features](https://ai.google.dev/gemini-api/docs/zdr) can add retention. The actual project tier and features are unverified. |
| `gpt-5.6-luna`, medium | **Run on stand-ins** via current ChatGPT-sign-in Codex CLI. No API key route used. | OpenAI's [Codex authentication docs](https://learn.chatgpt.com/docs/auth) say ChatGPT sign-in follows the workspace's permissions and retention settings; API-key use follows separate API organization controls and standard API pricing. The [Work admin FAQ](https://learn.chatgpt.com/docs/enterprise/work-admin-faq) says retention varies by plan, settings, and data type. CLI sign-in status does **not** identify the workspace plan or its exact retention; do not import API default periods into this route. |
| `gpt-6-astra`, high (optional B3 arm) | **Run on stand-ins** via the same ChatGPT-sign-in CLI. | Same OpenAI provider terms and unverified workspace-specific retention as Luna. If enabled for B3, the method requires its output on every page. |

## James / money decisions: yes or no

1. **Use direct Gemini on this specific active-billing Cloud Project and authorize metered B3 OCR calls?** No call or cost approved by this rehearsal. Operator first reads back project billing tier/status, actual adapter/model, optional storage setting, and estimated incremental cost; Dead Rabbit takes the bounded decision to James.
2. **Permit each enumerated James-authored page to leave the box for Gemini OCR?** Separate page-linked yes/no after actual paid/unpaid terms are shown. A missing/uncertain answer means no.
3. **Permit each enumerated page to leave the box for Luna through the verified ChatGPT workspace?** Separate page-linked yes/no after the actual workspace plan, training/retention controls and image adapter are disclosed. A missing/uncertain answer means no.
4. **Include optional Astra?** Yes adds a third provider arm through the same OpenAI route, a page-linked permission choice and a complete-output requirement; no leaves the mandatory Gemini/Luna pair.
5. **Confirm authorship of each candidate page and transcribe 100 frozen usable pages without seeing model text?** James may mark exclusions and reserves; without 100 references, no B3 score.
6. **Approve the reviewed PR #264 final-head installer on the tablet/private-drop path?** James's earlier conditional yes for a `b3-dennis` group is limited to creation through the reviewed final-head installer (Hive `herd-infra-b3-group-approval`); the current draft is no install authorization.

The provider permission copy in [B3 provider data-use brief](B3_PROVIDER_DATA_USE_2026_11_13.md) remains conditional until the actual account routes and settings are verified. No real image was transmitted in q-358.
