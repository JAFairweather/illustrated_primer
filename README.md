# Illustrated Primer

A handwritten teaching companion on a reMarkable tablet, after the Young Lady's Illustrated Primer in Neal
Stephenson's *The Diamond Age*. Ask a question in your own hand on the page, or by voice on a Rabbit R1, and it
answers "James, once upon a time..." with a tale written in its own script and a picture that builds as the story is
told, narrated in the earbuds.

- Root: the notebook server (`herd-board-serve`, launchd `pub.nave.herd-board.serve` on 127.0.0.1:8791), the tablet
  patch (`xochitl/herdRespond.qmd`), the story writer, picture and ink pipeline, hands and voice
  (`notebook_*.py`), and `herd-board-primer`, which the R1 runs over ssh.
- `r1/lib`: the R1 Primer app (`primer`, `feed`); `r1/ui`: its screen (`r1-primer-ui.c`).

Split out of `JAFairweather/rabidrabbit` on 2026-11-01 (`tools/herd-board`, plus `lib/r1-primer` and
`tools/r1-primer-ui` from `feat/r1-primer`), history kept. Branch `feat/voice-pacing` carries the undeployed voice
pacing work. Decisions are logged in `~/.buzz/RESEARCH/HERD_BOARD_DECISIONS.md`; the plan is
`~/.buzz/PLANS/PRIMER_A_PLAN.md`.

Tests: `python3 -m unittest` (about two minutes) and `node test_native_inline_ink.cjs`; `./herd-board-replay` before
any deploy.

License: MIT (see `LICENSE`).
