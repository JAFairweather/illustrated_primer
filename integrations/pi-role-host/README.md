# Isolated role-evaluation host integration

Status: source approved by MyDude at `760f6d8`, installed for isolated evaluation
on 2026-10-29. Production notebook settings and the live Respond route are unchanged.

This patch belongs to the separate `nvoy-pi-harness` repository. It is retained
here so the notebook evaluation work does not depend on an unrecorded external
worktree edit. The existing dirty host checkout was left unchanged. This is not
a second implementation of the notebook renderer.

## Base and candidate

Host checkout HEAD: `fa31f128acfac85f30e109ffbc91155ecf26883a`.
The base includes existing, uncommitted single-evaluation-host changes. Therefore
**do not apply this directly to that clean commit**. Check these base file hashes
and use `git apply --check` before applying `host.patch` in the host repository:

| File | SHA-256 before this patch |
| --- | --- |
| `mcp/tools/pi_notebook_host.mjs` | `a9878bfbf9944e95aeb60f620552e0bceff4699b04876f5dd27d4228d9dffedd` |
| `mcp/tools/pi_harness_extension.mjs` | `92d16ae71607f71334d82ea99614d6b3b6f7447bc1c665598aa5eeb583f578aa` |
| `test/pi-notebook-host.mjs` | `3b20ad638414699b202f20d24ed0151732c8d83dcc9e84c2fbcfc795826968ba` |
| `test/pi-harness.mjs` | `2cab883736a36ba3aa716d774738ea0010cb42ce4759b2adda413d8f2e0fefca` |

Full test snapshot: `~/.buzz/OUTBOX/pi-role-host-DO4xNX`.
Notebook adapter tested: this repository at `cc666211a90a220a1be29c3f598d07204546eccc`.

## Contract

An optional `notebook.eval_roster` contains exactly six entries, two per role:
`planner`, `drawer`, `critic`. Each entry has exactly these fields:

```json
{
  "role": "planner",
  "prompt_file": "/absolute/private/planner.txt",
  "model": {"provider": "openai-codex", "id": "configured-model"},
  "reasoning": "medium",
  "output_tokens": 4096,
  "socket_path": "/absolute/private/p0/notebook-eval.sock"
}
```

The paths above illustrate the schema, not an installed configuration.
Prompts must be private and distinct from the production prompt. Socket paths
must be unique, absolute, canonical, at most 100 UTF-8 bytes, and end in
`notebook-eval.sock`. Each socket's parent must already exist, be owner-only,
and have a non-replaceable ancestor chain. No directories or credentials are
created by the host. The roster-bearing client config must be owner-only.
Efforts are `minimal`, `low`, `medium`, `high`, `xhigh`; output caps are integers
from 1 through 8192. A role cannot repeat an identical model/effort/token-cap
candidate. Per-model support still has to be checked against the real registry.

The roster replaces, rather than coexists with, the legacy `eval_prompt_file`,
`eval_model`, `eval_response_format` binding. Without a roster the legacy
configuration remains supported. The production `notebook.sock` receives the
same options as before. Wire requests never choose model, effort or prompt.

The extension registers six independent responder handles on the **existing Pi
process and model registry**, plus the unchanged production handle. It retains
all handles and closes and settles acquired handles after partial registration
failure. Each adapter drains its socket on session shutdown but retains its
registration for the next session. Permanent closure is reserved for the
returned harness's explicit `dispose()` (or registration/factory failure), not
`stop()` or `session_shutdown`. The Pi runtime has no assumed process-terminal
meaning for a session shutdown. It does not start another Pi runtime,
copy an OAuth store, add a channel consumer, or change the live Respond route.
Fixed-model unavailability is asynchronous: after session binding that candidate
has no listening socket; it does not silently fall back to the chat model.
`settled()` alone is not a readiness or model-availability assertion.

## Evidence and limits

From the snapshot above:

```sh
HERD_BOARD_ADAPTER_TEST_DIR=~/.buzz/REPOS/r1-work-remarkable/tools/herd-board \
  /opt/homebrew/bin/node --test test/pi-notebook-host.mjs
/opt/homebrew/bin/node test/pi-harness.mjs
```

- Host suite: 12 tests pass, zero skipped. Includes actual local Unix sockets
  with the actual notebook adapter and a fake provider, six registrations sharing
  one registry, fixed model/effort/token settings, missing-model refusal, legacy
  routing, unchanged production options, strict roster validation and cleanup.
  The restart regression first failed against the original candidate (11/12),
  then passed after the lifecycle fix: two shutdown/start cycles reopen all
  seven sockets and answer requests with the same fixed evaluator settings.
  Explicit permanent disposal prevents subsequent rebinding.
- Expanded harness suite: all checks pass. Includes retaining six evaluators
  alongside production, owner-only roster configuration, no extra feed at load,
  preserving registrations on session shutdown/stop, and closing/settling all
  seven handles exactly once on permanent extension disposal.
- No real model calls, OAuth refresh, live deployment, tablet writes, or answer
  quality claims are established by these tests.

## Installed evaluation bindings (2026-10-29)

MyDude approved the lifecycle-fixed source in Buzz envelope
`a0fdcf29372f9da981e9167d1a76ddc01cffedb9c5aa73b32b8a714e5073627b`.
The four base hashes above were rechecked and `git apply --check` passed before
installation. Installed host bytes match `OUTBOX/pi-role-host-DO4xNX` exactly.
The host suite again passed 12/12 without skips, and the expanded harness suite
passed. Prior external-worktree edits were preserved, not committed as ours.

Private preparation and rollback directory:
`~/.buzz/OUTBOX/role-live-CtvuMd`. Its `before/` contains the four
previous host files and previous client configuration; no OAuth data was copied.
The current adapter is the existing worktree adapter; role prompts match the
renderer at `ee870a3` byte-for-byte. `candidates.json` records the expected model,
effort, output cap and exact prompt digest; `roster.json` records host bindings.

| Role | Baseline | Comparison | Output cap |
| --- | --- | --- | --- |
| Planner | GPT-5.6 Luna, medium | GPT-6 Astra, high | 4,096 |
| Drawer | GPT-5.6 Luna, medium | GPT-6 Astra, medium | 8,192 |
| Critic | GPT-5.6 Luna, medium | GPT-6 Astra, high | 4,096 |

Only the legacy evaluation fields in `pi-dog-harness.json` were replaced with
`eval_roster`; comparison after removing those fields proves all other settings,
including production prompt, model and adapter path, stayed unchanged. Under
James's earlier install/restart authorization, only
`gui/501/pub.nave.nvoy.pi-dog.harness` was restarted. PID 83007 was observed owning
production `notebook.sock` and all six private evaluation sockets. A listening
socket is a registry-binding check, not proof of answer quality or tablet delivery.

All six endpoints subsequently returned real completed model calls on a single
fractions case: two planners, two drawers using the same baseline plan, and two
critics using the same successful preview. The baseline drawer's malformed JSON
was preserved and rejected without repair. Astra's drawer passed whole-lesson
ink preparation; separate model critic scores remain uncalibrated. See
`STORY_MODEL_EVAL.md` for results and limitations. No tablet operation occurred.

Next: DJ Codex runs the frozen corpus and evaluates story/picture quality
separately before choosing a pairing or changing live Respond.

The evaluation design keeps stage-specific failures visible and requires human
calibration of quality judgments, consistent with the
[OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).
