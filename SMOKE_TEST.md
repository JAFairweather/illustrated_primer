# Herd-board smoke test (on the tablet)

Run `./herd-board-replay` first (offline, every captured reply must say `ok`). Then, on the tablet, after any restart or
deploy, in a "To pidog" notebook. Write down each request id from `herd-board-trace 5` next to its result.

1. **Text answer.** Fresh page. Write a short question ("what is 7 × 8?"). Press Respond. The answer appears inline,
   below the writing, within ~15 s. `herd-board-trace 1` ends at `acknowledged`.
2. **Follow-up on the same page.** Write a second question under the answer. Press Respond. A second answer appears;
   the first one is untouched.
3. **Nothing new.** Press Respond again without writing. The page says "No new handwriting found"; the trace shows
   `new_ink none` with a saved frame.
4. **Press twice quickly.** Write a question, press Respond twice. One answer arrives; the trace shows the first
   request `cleared` ("Replaced by a newer Respond"), never "already pending".
5. **Forced drawing.** Fresh page. Write "DRAW a right triangle with its sides labelled". Press Respond. A drawing is
   placed below the writing. The trace shows `rendered` with `mode: lesson`, then `placed`, `written`, `acknowledged`.
6. **Second notebook.** Repeat 1 in a different "To pidog" notebook.
7. **Ink untouched.** Each page still has all of its handwriting, nothing drawn over it.

Any failure: run `herd-board-trace <id>` and note where it stopped before trying again.
