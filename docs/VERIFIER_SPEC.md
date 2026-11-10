# Verifier Specification, task 5.3

**Status:** sections 3.1 to 3.3 implemented and tested. Section 3.4 is future work.
**Owner:** Enock Banda. (Reassigned from Mark Wells on 2026-11-10. See the decision log.)
**Implementation:** `src/task_5_3_verifier.py`. **Tests:** `tests/test_task_5_3_verifier.py`.
**Start:** week 6. **Delivered:** 2026-11-10.

The verifier is the component the whole project argues for. Everything else
produces a claim; this decides whether a reader is allowed to see it. It is the
difference between this work and a dashboard sitting on top of a classifier.

---

## 1. What already exists

`verify_evidence_links` in `src/agent.py`, written by Enock as part of task 3.2.

Every item in `evidence` and `contradictory_evidence` carries a
`tool_result_ids` list. The function keeps an item only when that list is
non-empty and every id in it belongs to a tool call that appears in the trace
and succeeded. Everything else is removed from the output and counted.

```python
{"verified_items": 2, "blocked_items": 1,
 "issues": [{"section": "evidence", "item": {...},
             "reason": "Missing or unknown tool_result_ids"}]}
```

This is the linkage check, and it works. `tests/test_agent_smoke.py` proves it
by feeding the agent a fabricated claim citing `result_99` and asserting the
claim never reaches the output.

**As of 2026-11-10 it is no longer in the production path.** `verify` in
`src/task_5_3_verifier.py` performs linkage itself, under the reason code
`missing_or_unknown_ids`. Running both counted the same blocked claim in two
reports and overstated the block rate, which is a reported result rather than a
debugging statistic. `verify_evidence_links` remains in `src/agent.py` as the
linkage primitive the smoke test documents. Nothing else calls it.

## 2. What it does not establish

**Linkage is not support.** The check confirms a citation points at something
real. It does not confirm the claim is what that thing said.

A claim reading "ROA fell by forty percent" that cites a genuine
`get_deviation` result passes today, even when the tool returned eight percent.
The citation exists, so the claim survives. That is the gap, and it is the
failure mode most likely to embarrass us in a demonstration, because a wrong
number with a correct-looking source is worse than no number at all.

## 3. The work that remains

Three layers, in priority order. Each is independently shippable, so the
component is useful before it is finished. 3.1 to 3.3 are now implemented.

### 3.1 Numeric agreement (required) — DONE

Every number appearing in a claim's text must appear in one of the tool results
that claim cites.

- The tool contract fixes rounding at four decimal places, and percentiles and
  rates at one, so comparison is exact rather than approximate. That rule exists
  for trace replay in task 6.5 and it makes this layer tractable.
- Percentages in prose match their decimal form in the result. `4.70%` matches
  `0.0470`.
- Counts match literally.
- A number in the claim with no match in the cited results blocks the item,
  with reason `numeric_claim_unsupported`.

Two amendments of 2026-11-10, both from probing the implementation against the
live offline pipeline:

- **The interpretation text is verified alongside the claim text.** This section
  originally said "claim's text". The interpretation is displayed to the reader,
  so an unsupported figure there reaches them exactly as one in the claim does.
- **Digits inside document and statutory labels are not quantities.** The number
  pattern pulled `10` out of "10-K", `9` out of "Item 9A" and `404` out of
  "SOX 404(b)". None matched a tool value, so every claim naming a filing was
  blocked as `numeric_claim_unsupported`. That would have blocked everything the
  filing tools (5.5, 5.6) produce before they landed, and it put the wrong
  reason code on the block. Those labels are now masked out before numbers are
  read. A real quantity in the same sentence is still checked. SIC codes are
  deliberately not masked, because a tool returns the SIC code as a value and
  the claim should be checked against it.

**A rounded figure still blocks, and that is correct.** "roughly 0.119" against
a returned 0.1187 fails, because this section requires exact comparison at the
contract's four decimal places. The system prompt is what has to change: it must
forbid the model from rounding a figure it quotes. Until it does, rounding will
show up in the block rate as noise rather than as a finding.

### 3.2 Direction and comparison (required) — DONE

Where a tool returns a direction, the claim's language must not contradict it.

- `get_deviation` returns `direction` as `above`, `below` or `unchanged`. A
  claim saying "above its own history" against a result of `below` is blocked
  with reason `direction_contradicts_result`.
- `get_peer_cohort` returns `lift`. The contract already requires that a lift
  below 1.0 be reported, because a safer-than-average peer group is evidence
  against the assessment. A claim that reads the lift the wrong way is blocked.

Amendment of 2026-11-10: direction terms match on word boundaries. Substring
matching made "undergo" collide with "under", so a neutral sentence could be
reported as contradicting the tool.

### 3.3 Entity grounding (required) — DONE

A claim must not name a firm, a fiscal year, an industry or a filing section
that no cited result returned. This is what stops the model importing a company
it knows about from training rather than from our data, which is the single most
dangerous failure mode in a tool like this.

Reason: `entity_not_in_results`.

Two amendments of 2026-11-10:

- **Entity grounding reads the claim prose.** The first implementation checked
  only structured keys on the claim object, so "Enron shows elevated risk"
  passed. A capitalised word must now either be in a small allowed vocabulary of
  reporting language and feature names (`ALLOWED_PROSE_TERMS`) or appear in the
  cited results. This is the approach 3.4 below already proposed for qualitative
  language. It is strict by design. The vocabulary is expected to grow from
  observed false positives in live runs, never from guessing.
- **Years are grounded here, not by the numeric layer.** A claim saying
  "Features are drawn from 2018" was blocked, because 2018 is not among the
  values `score_firm` returns, and the numeric layer fired before this one was
  reached. The system prompt asks the model to state the assessment year, so the
  verifier was blocking compliant output. A year in a claim must now be a year
  a cited call returned **or was called with**. The call arguments are the right
  grounding: the agent asked about FY2018 and the tool answered for FY2018,
  whether or not the return echoes the year. The rule is fail-closed, so no
  grounded year at all means no year may be named.

### 3.4 Qualitative language (later, if time allows)

Hedges and characterisations such as "materially", "sharply", "consistent with
prior years". These resist mechanical checking. The honest treatment is to
define a small allowed vocabulary in the system prompt and block the rest,
rather than attempting to judge whether a vague word is true. Do not start this
until 3.1 to 3.3 are done, and be willing to report it as future work.

## 4. Interface

Keep the existing shape so nothing downstream changes.

```python
def verify(output: dict, trace: list[dict], *, inplace: bool = True) -> dict:
    """Remove unsupported items from output in place. Return the report."""

def verify_copy(output: dict, trace: list[dict]) -> tuple[dict, dict]:
    """Return (verified_copy, report), preserving the raw output."""
```

Returns, extending what `verify_evidence_links` already produces:

```python
{
  "verified_items": int,
  "blocked_items":  int,
  "block_rate":     float,   # blocked / (verified + blocked), 4dp
  "issues": [ {"section": str, "item": dict, "reason": str, "detail": list} ],
  "reasons": {"<reason>": int},   # counts per category
}
```

The reason strings are fixed, so the evaluation can report them as a table:
`missing_or_unknown_ids`, `numeric_claim_unsupported`,
`direction_contradicts_result`, `entity_not_in_results`.

`detail` is additive and optional. It carries the exact tokens the item failed
on: the unmatched numbers, the ungrounded names and years, or the cited ids that
do not exist. It is there so section 5's worked example can show a reader what
failed rather than only that something did.

## 5. What gets reported

The block rate is a headline number for the final report, not a debugging
statistic. Report it pooled and broken out by reason, across the evaluation
sample. A system that never blocks anything has either a very obedient model or
a verifier that is not working, and the breakdown is how a reader tells those
apart. The application shows the same breakdown on the Blocked tab.

Also report, for the demonstration: at least one worked example where a claim
was blocked, with the claim text, the reason and the tool result it failed
against. One concrete example is worth more than the rate.

## 6. Dependencies

None that are outstanding. The agent produces output in the required shape
today, the trace carries the tool results, and `tests/test_agent_smoke.py`
gives a working harness to develop against. This can start before the panel and
the model files are distributed.

That is deliberate. It is the one major piece of work on the project with
nothing blocking it.

## 7. How this component is tested

Unit tests in `tests/test_task_5_3_verifier.py`, one per amendment, each naming
the claim that got through or was wrongly blocked.

Cross-component tests in `tests/test_task_5_2_integration.py` run the offline
pipeline end to end and assert that the fabricated claim is the only thing
blocked. That test matters more than the unit tests: every defect found on
10 November was found by connecting components, not by reading either one. The
over-blocking was invisible to the verifier's own unit tests because those
supply hand-built traces, and a hand-built trace tends to contain exactly what
the test author expected the claim to cite.
