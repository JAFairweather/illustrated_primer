# Offline lesson resource feedback

The draft checker accepts either the original fenced board-step format or the
current semantic JSON reply. It compiles and encodes with the existing native
validators, preserves the input unchanged, and never contacts a model/tablet or
writes native `.rm` assets. It does not repair the lesson or certify its teaching
quality.

```sh
python3 notebook_lesson_eval.py check draft.json fresh-preview-directory --semantic
```

Omit `--semantic` for the original board-step format. Each invocation requires a
new output directory. Exit status is 0 for compiler acceptance and 2 for a held
draft or tool failure. `result.json` and stdout carry the result; filesystem
failures may prevent `result.json` from being written. Semantic input is bounded
to the same 24 KB as the native reply parser. The checker does not autodetect or
salvage malformed JSON as text.

## Separate success criteria

- `valid` / `compiler_valid`: the relevant compiler/encoding checks passed.
- `visual_lesson`: an accepted lesson with complete stage previews; plain
  `answer` and `clarify` replies never count as visual lessons.
- `quality_status: "unreviewed"`: mathematical/teaching quality is a separate
  review, even when all resource limits pass.
- `tablet_proven: false`: offline checks establish no physical display,
  handwriting, placement, latency or persistence result.

Accepted lessons get cumulative SVG/PNG previews. A native-budget rejection
gets no ink assets or picture pretending to be an accepted result. Existing
explicit diagnostic previews for collision-rejected board-step drafts retain
their rejected status.

## Structured resource failures

`resource_feedback` is present when a typed compiler budget error supplies
measurements. It is additive to the original error text; validation behavior,
limits, font choices and accepted geometry are unchanged.

```json
{
  "version": 1,
  "attempts": [
    {
      "font": "continuous",
      "failure": {
        "resource": "strokes",
        "observed": 90,
        "limit": 64,
        "exact": true,
        "scope": "stage",
        "stage": 1,
        "strokes": 90,
        "stroke_breakdown": {"labels": 88, "geometry": 2, "complete": true}
      }
    }
  ]
}
```

This example is the first compilation attempt for the saved Langlands response,
not a hypothetical model improvement. Its existing original-font fallback also
failed and is reported separately (143 strokes, 141 from lettering). The
`attempts` list records only those two existing compiler/font choices; it never
means additional model calls or a new repair loop.

- `resource` is `strokes`, `points`, or `estimated_seconds`.
- `stage` and optional `command` are one-based when available.
- `scope` distinguishes a stage from the whole lesson.
- `exact: false` means **at least** the observed amount. For example, point
  densification stops at the first excessive segment without scanning the rest,
  and unresolved connections/anchored labels are not included in preflight
  counts. Do not present those numbers as full-plan totals.
- `stroke_breakdown.complete` independently indicates whether the counted
  strokes cover the whole stage. An inexact point count can still have a
  complete stroke count. Pending labels/connections make both incomplete.
- `estimated_seconds` uses the existing compiler estimate, not measured tablet
  time or Respond-to-visible-response latency.
- Old unstructured errors and non-budget failures remain ordinary errors. No
  feedback is inferred by matching words in an exception message.

The fixed-answer evaluator also puts this object on held manifest rows and
shows it in the side-by-side report. Original responses, model-call provenance,
acceptance and quality assessments remain separate.

## Planner integration boundary

This is a preflight interface for the next composition/planning experiment,
**not an installed automatic correction policy**. A planner can use the result
to propose a new complete draft; that draft must be stored separately and pass
the full compiler again. A feedback-assisted result must not be counted as an
unassisted first-pass success. Never silently remove labels, rewrite claims,
split semantic steps, shrink fonts or raise a native limit to make a draft fit.

Compiler success remains distinct from mathematical and visual evidence. This
separation follows the [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
to combine scoped metrics with human review rather than treat one numeric pass
as overall quality.
