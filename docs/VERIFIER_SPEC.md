# Verifier Specification, task 5.3

**Status:** DRAFT, for sign-off at the next meeting.
**Owner:** Mark Wells.
**Start:** week 6. **Target complete:** end of week 7, 15 November.

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
component is useful before it is finished.

### 3.1 Numeric agreement (required)

Every number appearing in a claim's text must appear in one of the tool results
that claim cites.

- The tool contract fixes rounding at four decimal places, and percentiles and
  rates at one, so comparison is exact rather than approximate. That rule exists
  for trace replay in task 6.5 and it makes this layer tractable.
- Percentages in prose match their decimal form in the result. `4.70%` matches
  `0.0470`.
- Counts and years match literally.
- A number in the claim with no match in the cited results blocks the item,
  with reason `numeric_claim_unsupported`.

### 3.2 Direction and comparison (required)

Where a tool returns a direction, the claim's language must not contradict it.

- `get_deviation` returns `direction` as `above`, `below` or `unchanged`. A
  claim saying "above its own history" against a result of `below` is blocked
  with reason `direction_contradicts_result`.
- `get_peer_cohort` returns `lift`. The contract already requires that a lift
  below 1.0 be reported, because a safer-than-average peer group is evidence
  against the assessment. A claim that reads the lift the wrong way is blocked.

### 3.3 Entity grounding (required)

A claim must not name a firm, a fiscal year, an industry or a filing section
that no cited result returned. This is what stops the model importing a company
it knows about from training rather than from our data, which is the single most
dangerous failure mode in a tool like this.

Reason: `entity_not_in_results`.

### 3.4 Qualitative language (later, if time allows)

Hedges and characterisations such as "materially", "sharply", "consistent with
prior years". These resist mechanical checking. The honest treatment is to
define a small allowed vocabulary in the system prompt and block the rest,
rather than attempting to judge whether a vague word is true. Do not start this
until 3.1 to 3.3 are done, and be willing to report it as future work.

## 4. Interface

Keep the existing shape so nothing downstream changes.

```python
def verify(output: dict, trace: list[dict]) -> dict:
    """Remove unsupported items from output in place. Return the report."""
```

Returns, extending what `verify_evidence_links` already produces:

```python
{
  "verified_items": int,
  "blocked_items":  int,
  "block_rate":     float,   # blocked / (verified + blocked), 4dp
  "issues": [ {"section": str, "item": dict, "reason": str} ],
  "reasons": {"<reason>": int},   # counts per category
}
```

The reason strings are fixed, so the evaluation can report them as a table:
`missing_or_unknown_ids`, `numeric_claim_unsupported`,
`direction_contradicts_result`, `entity_not_in_results`.

## 5. What gets reported

The block rate is a headline number for the final report, not a debugging
statistic. Report it pooled and broken out by reason, across the evaluation
sample. A system that never blocks anything has either a very obedient model or
a verifier that is not working, and the breakdown is how a reader tells those
apart.

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
