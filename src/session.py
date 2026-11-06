"""Task 5.4: wire the application to the agent.

Pure Python with no Streamlit import, so it can be tested on its own and
reused by anything else that needs to drive a run. app.py is a thin interface
on top of this.

One assessment goes through four stages here:

    1. the real gvkey is swapped for a session-local alias
    2. the agent runs, choosing tools and working to a call budget
    3. every claim is checked against the tool results it cites
    4. whatever failed that check is removed and counted

Stage 1 is the decision of 2026-11-03. The model never receives a Compustat
identifier. The substitution happens inside this process, after the model has
chosen a call and before the tool runs.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from src import tools
from src.agent import TOOL_NAMES, run_agent, verify_evidence_links

ALIAS = "FIRM_A"

PROVIDERS = ("Offline demo", "Gemini", "Groq")


# --------------------------------------------------------------------------
# alias boundary
# --------------------------------------------------------------------------

def _mask(obj: Any, real: str, alias: str) -> Any:
    """Replace the real identifier with the alias anywhere in a tool return.

    This half of the boundary is easy to miss and it is the half that leaks.
    Section 2 of the tool contract requires every return to carry a source
    string such as "final_panel | gvkey=001004 | fyear=2018 | col=ROA", and
    the agent loop feeds those returns straight back to the model as tool
    messages. Substituting only on the way out leaves the identifier to walk
    back in through the source.
    """
    if isinstance(obj, str):
        return obj.replace(real, alias)
    if isinstance(obj, dict):
        return {k: (alias if k == "gvkey" and v == real else _mask(v, real, alias))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask(v, real, alias) for v in obj]
    return obj


def alias_tools(real_gvkey: str) -> dict[str, Callable[..., Any]]:
    """The tool layer with the alias boundary enforced in both directions.

    Outbound: the model asks for FIRM_A, the real gvkey is substituted here.
    Inbound:  the real gvkey is masked out of the return before the loop
              hands it back to the model.
    """

    def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        def inner(**kwargs: Any) -> Any:
            if kwargs.get("gvkey") == ALIAS:
                kwargs = {**kwargs, "gvkey": real_gvkey}
            return _mask(fn(**kwargs), real_gvkey, ALIAS)

        inner.__name__ = getattr(fn, "__name__", "tool")
        return inner

    return {name: wrap(getattr(tools, name)) for name in TOOL_NAMES}


# --------------------------------------------------------------------------
# providers
# --------------------------------------------------------------------------

class OfflineLLM:
    """Deterministic stand-in so the application runs with no key and no network.

    It follows a fixed investigation plan, then writes the brief out of the
    values the tools actually returned. That matters: the numbers in the
    output are the numbers the tools produced, so the claim check is doing
    real work rather than theatre.
    """

    def __init__(self, fyear: int, inject_unsupported: bool = True) -> None:
        self.fyear = int(fyear)
        self.inject_unsupported = inject_unsupported
        self.plan: list[tuple[str, dict[str, Any]]] = [
            ("get_control_history", {"gvkey": ALIAS, "through_fyear": self.fyear}),
            ("score_firm", {"gvkey": ALIAS, "fyear": self.fyear}),
            ("get_percentile", {"gvkey": ALIAS, "fyear": self.fyear, "variable": "ROA"}),
            ("get_peer_cohort", {"gvkey": ALIAS, "fyear": self.fyear}),
        ]

    @staticmethod
    def _results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for m in messages:
            if m.get("role") != "tool":
                continue
            try:
                out.append(json.loads(m.get("content") or "{}"))
            except (TypeError, ValueError):
                continue
        return out

    def complete(self, messages, tools):  # noqa: ARG002 - protocol signature
        seen = self._results(messages)

        if len(seen) < len(self.plan):
            name, args = self.plan[len(seen)]
            return {"type": "tool_call", "name": name, "arguments": args}

        by_name = {}
        for res in seen:
            src = str(res.get("source") or "")
            for candidate, _ in self.plan:
                if candidate not in by_name and candidate in src:
                    by_name[candidate] = res
        ordered = {name: seen[i] for i, (name, _) in enumerate(self.plan) if i < len(seen)}

        score = ordered.get("score_firm", {}).get("value") or {}
        peers = ordered.get("get_peer_cohort", {}).get("value") or {}
        control = ordered.get("get_control_history", {}).get("value") or {}
        pct = ordered.get("get_percentile", {}).get("value")

        rid = {name: ordered.get(name, {}).get("result_id") for name, _ in self.plan}

        probability = score.get("probability")
        percentile = score.get("percentile")
        peer_rate = peers.get("peer_adverse_rate")
        base_rate = peers.get("cohort_base_rate")
        lift = peers.get("lift")
        prior = control.get("prior_year_status")

        evidence = [
            {
                "claim": f"The calibrated probability of an adverse opinion is {probability}.",
                "tool_result_ids": [rid["score_firm"]],
                "interpretation": (
                    "A model estimate from financial features only. It excludes "
                    "the prior-year opinion by design."
                ),
            },
            {
                "claim": f"That places the firm at the {percentile} percentile of scored firms.",
                "tool_result_ids": [rid["score_firm"]],
                "interpretation": "A relative rank, not an absolute threshold.",
            },
            {
                "claim": f"Comparable firms show an adverse rate of {peer_rate} against a base rate of {base_rate}.",
                "tool_result_ids": [rid["get_peer_cohort"]],
                "interpretation": f"A lift of {lift} over the cohort.",
            },
            {
                "claim": f"ROA sits at the {pct} percentile for the year.",
                "tool_result_ids": [rid["get_percentile"]],
                "interpretation": "One feature among nineteen. Not decisive alone.",
            },
        ]

        if self.inject_unsupported:
            evidence.append(
                {
                    "claim": "The firm's latest 10-K discloses an ongoing remediation plan.",
                    "tool_result_ids": ["result_99"],
                    "interpretation": (
                        "DEMONSTRATION. This claim cites a tool result that was "
                        "never produced, and the claim check should remove it."
                    ),
                }
            )

        contradictory = []
        if prior and prior != "adverse":
            contradictory.append(
                {
                    "claim": f"The firm's prior-year control status is recorded as {prior}.",
                    "tool_result_ids": [rid["get_control_history"]],
                    "interpretation": (
                        "Evidence against the assessment. Persistence of a prior "
                        "problem is the strongest single predictor we have, and "
                        "it is absent here."
                    ),
                }
            )

        return {
            "type": "final",
            "content": {
                "assessment": {
                    "risk_level": "moderate",
                    "summary": (
                        "Model risk is elevated relative to peers, with no prior "
                        "adverse opinion on record."
                    ),
                    "target": "adverse ICFR opinion in the following fiscal year",
                    "firm_id": ALIAS,
                    "feature_year": self.fyear,
                    "outcome_year": self.fyear + 1,
                    "probability": probability,
                    "model_version": score.get("model_version"),
                    "confidence": "low",
                },
                "evidence": evidence,
                "contradictory_evidence": contradictory,
                "uncertainty": [
                    "Every tool in this run is a stub. No real panel data was read.",
                    "The filings tool is gated and returned nothing.",
                ],
                "recommended_checks": [
                    {
                        "check": "Re-run against the distributed panel",
                        "reason": "Stub values cannot support a real assessment.",
                    },
                    {
                        "check": "Read Item 9A of the most recent 10-K",
                        "reason": "No filing evidence is available in this run.",
                    },
                ],
            },
        }


def _live_client(provider: str, model: str, api_key: str):
    """Build a real provider client. Imported lazily so the app runs without them."""
    raise NotImplementedError(
        f"{provider} is not wired up yet. Use Offline demo. "
        "The tool-calling pattern for both providers is in "
        "tests/llm_access_test_gemini.ipynb and tests/llm_access_test_groq.ipynb."
    )


# --------------------------------------------------------------------------
# one assessment
# --------------------------------------------------------------------------

def run_assessment(
    *,
    gvkey: str,
    fyear: int,
    provider: str = "Offline demo",
    max_tool_calls: int = 8,
    inject_unsupported: bool = True,
    api_key: str = "",
    model: str = "",
) -> dict[str, Any]:
    """Run one assessment and return everything the interface needs to show."""

    gvkey = str(gvkey).strip()
    if not gvkey:
        raise ValueError("A firm identifier is required.")
    gvkey = f"{int(gvkey):06d}" if gvkey.isdigit() else gvkey

    if provider == "Offline demo":
        llm: Any = OfflineLLM(fyear=fyear, inject_unsupported=inject_unsupported)
    else:
        llm = _live_client(provider, model, api_key)

    result = run_agent(
        firm_id=ALIAS,
        feature_year=int(fyear),
        user_question=(
            "Assess this firm's risk of receiving an adverse internal-control "
            "opinion in the following fiscal year."
        ),
        llm=llm,
        tools=alias_tools(gvkey),
        max_tool_calls=int(max_tool_calls),
    )

    before = len(result.output.get("evidence", [])) + len(
        result.output.get("contradictory_evidence", [])
    )
    report = verify_evidence_links(result.output, result.trace)
    total = report["verified_items"] + report["blocked_items"]
    report["block_rate"] = round(report["blocked_items"] / total, 4) if total else 0.0

    return {
        "gvkey": gvkey,
        "alias": ALIAS,
        "fyear": int(fyear),
        "provider": provider,
        "status": result.status,
        "run_id": result.run_id,
        "tool_calls_used": result.tool_calls_used,
        "claims_before": before,
        "output": result.output,
        "report": report,
        "trace": result.trace,
    }
