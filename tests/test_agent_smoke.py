"""Walking skeleton: the agent loop driving the real tool layer, end to end.

This is the first test that crosses a component boundary. Every other test
exercises one module. This one runs src.agent against the merged src.tools and
then puts the result through the evidence-link check, so it fails the moment
those three drift apart.

The language model is scripted rather than real. The point is not to test the
model, it is to test that the loop, the tool contract and the verifier still
fit together. Swap FakeLLM for a real client to turn this into a live run.
"""

from __future__ import annotations

import pytest

from src import tools
from src.agent import TOOL_NAMES, run_agent, verify_evidence_links

TOOLS = {name: getattr(tools, name) for name in TOOL_NAMES}

# A deliberately unreachable result id. Nothing in the trace will ever match it.
FABRICATED_ID = "result_99"

# A real gvkey. Amended 2026-11-20, when the real tool layer replaced the stubs.
# This used to pass the literal string "FIRM_A", which the stubs ignored. The real
# tools do not: src/model.py calls int() on the identifier before its own error
# handling, so the alias raised ValueError and the call was recorded as a failure.
# The alias boundary belongs to src/session.py and is tested there, not here.
GVKEY = "001004"
FYEAR = 2018


class FakeLLM:
    """Scripted model: two real tool calls, then an answer with one invented claim."""

    def __init__(self) -> None:
        self.step = 0

    def complete(self, messages, tools):  # noqa: ARG002 - protocol signature
        self.step += 1

        if self.step == 1:
            return {
                "type": "tool_call",
                "name": "get_control_history",
                # through_fyear is required since the look-ahead amendment of
                # 2026-11-06. Omitting it used to return the outcome year.
                "arguments": {"gvkey": GVKEY, "through_fyear": FYEAR},
            }

        if self.step == 2:
            return {
                "type": "tool_call",
                "name": "score_firm",
                "arguments": {"gvkey": GVKEY, "fyear": FYEAR},
            }

        return {
            "type": "final",
            "content": {
                "assessment": {
                    "risk_level": "moderate",
                    "summary": "Relative rank recorded, no prior adverse opinion on record.",
                    "target": "adverse ICFR opinion",
                    "firm_id": GVKEY,
                    "feature_year": FYEAR,
                    "outcome_year": FYEAR + 1,
                    "confidence": "low",
                },
                # No quoted figures. Amended 2026-11-20. These claims used to hard-code
                # the stub values, 0.1187 and the 94.9th percentile. Against real data
                # those are simply wrong, so the claim check deleted them and the test
                # counted two blocks where it expected one. Pinning real values here
                # would make the test fail whenever the panel or the model changes,
                # which is not what a walking skeleton is for. Numeric support is
                # covered in tests/test_task_5_3_verifier.py and against live values in
                # tests/test_task_5_2_integration.py.
                "evidence": [
                    {
                        "claim": "A control history is on record for the assessment year.",
                        "tool_result_ids": ["result_1"],
                        "interpretation": "Retrieved for the year under review.",
                    },
                    {
                        "claim": "The model returned a score for this firm and year.",
                        "tool_result_ids": ["result_2"],
                        "interpretation": "A relative rank, not an absolute threshold.",
                    },
                    {
                        "claim": "The filing discloses a remediation plan.",
                        "tool_result_ids": [FABRICATED_ID],
                        "interpretation": "Unsupported. Cites a result that was never produced.",
                    },
                ],
                "contradictory_evidence": [],
                "uncertainty": ["One scripted provider. Not a real assessment."],
                "recommended_checks": [
                    {"check": "Re-run through the application", "reason": "Scripted provider."}
                ],
            },
        }


@pytest.fixture(name="run")
def _run():
    return run_agent(
        firm_id=GVKEY,
        feature_year=FYEAR,
        user_question="Assess this firm's risk of an adverse internal-control opinion.",
        llm=FakeLLM(),
        tools=TOOLS,
        max_tool_calls=8,
    )


def test_loop_completes_against_the_real_tool_layer(run):
    assert run.status == "completed"
    assert run.tool_calls_used == 2
    assert run.run_id


def test_every_executed_call_is_in_the_trace(run):
    executed = [e for e in run.trace if e.get("event") == "tool_call"]
    assert len(executed) == run.tool_calls_used
    assert all(e.get("status") == "ok" for e in executed)


def test_call_budget_is_enforced():
    """A budget of zero must execute no tools, not raise."""
    result = run_agent(
        firm_id=GVKEY,
        feature_year=FYEAR,
        user_question="Assess this firm.",
        llm=FakeLLM(),
        tools=TOOLS,
        max_tool_calls=0,
    )
    assert result.tool_calls_used == 0


def test_the_fabricated_claim_is_blocked(run):
    """The point of the whole project: an unsupported claim never reaches the reader."""
    before = len(run.output["evidence"])
    report = verify_evidence_links(run.output, run.trace)
    after = len(run.output["evidence"])

    assert before == 3
    assert after == 2
    assert report["blocked_items"] == 1
    assert report["verified_items"] == 2

    surviving = [item["claim"] for item in run.output["evidence"]]
    assert not any("remediation plan" in claim for claim in surviving)


def test_blocked_items_are_reported_with_a_reason(run):
    report = verify_evidence_links(run.output, run.trace)
    assert len(report["issues"]) == 1
    assert report["issues"][0]["reason"]
