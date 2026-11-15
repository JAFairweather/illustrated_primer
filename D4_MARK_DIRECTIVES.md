# D4: mark-to-directive draft

This is the paper-review mapping for [Frontier D4](https://github.com/JAFairweather/herd-infra/blob/main/docs/frontier-review/PLAN.md). Biggy owns the D4 package; this q-119 draft gives it four unambiguous candidate directives to test. The [fixtures](evaluations/d4-mark-directives/fixtures.json) are synthetic examples, not signed events or evidence of a tablet workflow. The C1 directive/receipt wire format and C2 tablet identity path are still separate package gates. Adapt the field names to C1 when that contract lands; keep the decisions and holds below.

## A mark has one target

A decision row must show its stable item ID, current owner, and the exact PR head or issue revision before James marks it. Capture the page revision, row ID, mark ID, mark geometry, and a crop of the marked row. A verifier must bind the tablet identity to James, the mark to one visible row, and that row to the current target before emitting a directive. A copied image, uncertain mark, stale row, or unreadable recipient stays **held for clarification**. No OCR guess executes a decision.

| Mark on one decision row | Candidate intent | Bound target and payload | Receipt that closes the mark |
|---|---|---|---|
| Tick beside the approval box | `approve_review` | One PR at the head printed on the page; no implied merge | Review approval recorded at that exact head, with its event ID; any merge waits for the normal review, CI, risk, and hold gates. |
| Strike through the decision line | `reject_review` | The same PR head; a nearby margin reason is attached only if its anchor is clear | Rejection or changes-requested review recorded at that head, with its event ID. The PR remains open for revision. |
| Margin note anchored to a row | `post_review_comment` | Verbatim transcription and image crop, attached to the indicated PR or issue; keep uncertain words marked as uncertain | Comment ID and the text actually posted, or a held receipt if transcription or anchor needs James's confirmation. |
| Arrow from a row to a named person | `reassign_item` | One issue/task ID and a recipient resolved to a current member identity; the old owner is retained in the audit record | Assignment read back on that item with the resolved identity and operation ID. An unresolved name stays held. |

The mark ID is the idempotency key: retransmitting a page cannot make a second approval, comment, or assignment. A changed PR head, row revision, or assignment state after the page was rendered returns a stale-target receipt and asks for a fresh page. An expiry limits how long an offline mark may be submitted. Each receipt links the source mark and target to the action or a specific hold reason, so every mark can be traced without treating capture as execution.

The tick and strike are mutually exclusive at one PR head. If both appear, or if a strike crosses several rows, hold the row for James rather than infer an order. A margin note accompanying a strike becomes its reason only when the anchor is explicit; otherwise it is its own comment mark. An arrow cannot silently grant access or override the queue's owner rules. The executing service rechecks authority and the live target at action time.

## Fixture boundary

`fixtures.json` contains one proposed directive per mark. The `source` values stand in for a signed tablet capture, and `expected` states the cold read-back needed for acceptance. These examples are intentionally not C1 wire vectors; they do not prove signing, UI recognition, delivery, or a live review. D4's package exit remains a real day's decisions cleared on paper with each mark traced to a merge or comment, as the Frontier plan specifies.
