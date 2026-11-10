"""Task 4.1: the Streamlit shell. Firm and year selection, results pane, trace viewer.

Run it from the repository root:

    streamlit run app.py

It works today with no data file, no model file and no API key, because the
"Offline demo" provider drives the agent through the merged tool stubs. Swap
the provider once keys and the panel are in place; nothing else here changes.

All of the wiring lives in src/session.py. This file is only the interface.

Display rules (docs/EVALUATION_DESIGN.md section 9, tested in tests/test_app.py):
  - a missing value is shown as "not available", never as None or 0
  - every claim shows the source string of each tool result it cites
  - the trace names each call by its result id, so a claim can be matched to it
  - the demonstration claim is off by default and labelled when it is on
"""

from __future__ import annotations

import json
import re
from typing import Any

import streamlit as st

from src.session import PROVIDERS, run_assessment

NAVY = "#16253F"
GOLD = "#B8860B"
GREEN = "#2F6130"
RUST = "#9B2F2F"

RISK_COLOR = {
    "low": GREEN,
    "moderate": GOLD,
    "high": RUST,
    "indeterminate": "#4A5568",
}

NOT_AVAILABLE = "not available"


def show(value: Any) -> str:
    """A value as text, with None (or an empty string) shown as 'not available'."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return NOT_AVAILABLE
    return str(value)


def show_probability(value: Any) -> str:
    """A probability as a percentage. 0.0731 becomes 7.3%."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.1%}"
    return show(value)


def source_index(trace: list[dict]) -> dict[str, str]:
    """result_id to source string, for every successful tool call in the trace."""
    index = {}
    for event in trace:
        if event.get("event") != "tool_call":
            continue
        result = event.get("result") or {}
        rid = result.get("result_id")
        if rid:
            index[rid] = show(result.get("source"))
    return index


def cited_sources(item: dict, index: dict[str, str]) -> list[str]:
    """One line per cited result: its id and the source string it came from."""
    lines = []
    for rid in item.get("tool_result_ids", []) or []:
        lines.append(f"{rid}: {index.get(rid, 'not in the trace')}")
    return lines or ["no tool result cited"]


st.set_page_config(page_title="Agentic Risk Analyst", layout="wide")


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Assessment")

    gvkey = st.text_input("Firm identifier (gvkey)", value="001004",
                          help="Six digits. Leading zeros are added if missing.")
    fyear = st.number_input(
        "Fiscal year", min_value=2011, max_value=2022, value=2018, step=1,
        help="Features come from this year. The opinion predicted is the following year.",
    )

    st.divider()
    provider = st.selectbox("Language model", PROVIDERS, index=0)
    if provider != "Offline demo":
        st.text_input("API key", type="password", key="api_key",
                      help="Entered at runtime. Never stored in the repository.")

    budget = st.slider("Tool call budget", 1, 12, 8,
                       help="The agent stops after this many executed calls.")

    # Off by default: an injected claim is always blocked, so leaving it on
    # would add a block to every real run and overstate the block rate.
    inject = st.checkbox(
        "Inject an unsupported claim (demonstration)", value=False,
        help="Adds one claim citing a tool result that was never produced, "
             "so you can see the claim check remove it.",
    )

    st.divider()
    run = st.button("Run assessment", type="primary", use_container_width=True)

    st.caption(
        "The model is sent a session-local alias, never the gvkey. "
        "Substitution happens locally in both directions."
    )


# ---------------------------------------------------------------- header
st.title("Agentic Risk Analyst")
st.caption(
    "Assesses a firm's risk of an adverse internal-control opinion. "
    "Any claim that cannot be traced back to a tool result is removed before display."
)

if not run and "result" not in st.session_state:
    st.info("Set a firm and a year in the sidebar, then run an assessment.")
    st.stop()

if run:
    if not re.fullmatch(r"\d{1,6}", gvkey.strip()):
        st.error("The firm identifier must be a gvkey of up to six digits, for example 001004.")
        st.stop()
    try:
        st.session_state["result"] = run_assessment(
            gvkey=gvkey,
            fyear=int(fyear),
            provider=provider,
            max_tool_calls=int(budget),
            inject_unsupported=inject,
            api_key=st.session_state.get("api_key", ""),
        )
        st.session_state["inject_used"] = inject
    except NotImplementedError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:  # noqa: BLE001 - surface anything to the operator
        st.error(f"{type(exc).__name__}: {exc}")
        st.stop()

res = st.session_state["result"]
out = res["output"]
report = res["report"]
assessment = out.get("assessment", {}) or {}
sources = source_index(res.get("trace", []))
inject_used = res.get("inject_unsupported", st.session_state.get("inject_used", False))


# ---------------------------------------------------------------- summary
a, b, c, d = st.columns(4)
level = str(assessment.get("risk_level") or "indeterminate")
a.markdown(
    f"**Risk level**<br><span style='font-size:30px;font-weight:700;"
    f"color:{RISK_COLOR.get(level, NAVY)}'>{level.title()}</span>",
    unsafe_allow_html=True,
)
b.metric("Probability", show_probability(assessment.get("probability")))
c.metric("Tool calls used", show(res.get("tool_calls_used")))
d.metric("Claims blocked", show(report.get("blocked_items")))
d.caption(f"Block rate {report.get('block_rate') or 0:.1%}")

st.write(show(assessment.get("summary")))

meta = (
    f"Firm {res['gvkey']} shown as **{res['alias']}** to the model &nbsp;|&nbsp; "
    f"features FY{res['fyear']}, opinion predicted for FY{res['fyear'] + 1} &nbsp;|&nbsp; "
    f"model `{show(assessment.get('model_version'))}` &nbsp;|&nbsp; "
    f"confidence {show(assessment.get('confidence'))} &nbsp;|&nbsp; "
    f"run `{show(res.get('run_id'))}`"
)
st.caption(meta, unsafe_allow_html=True)

if inject_used:
    st.warning(
        "This run includes the demonstration claim. One block is deliberate, "
        "so the block rate shown is not a measure of the model."
    )

st.divider()


# ---------------------------------------------------------------- panes
shown, blocked, trace_tab, raw = st.tabs(
    ["Assessment", f"Blocked ({show(report.get('blocked_items'))})", "Trace", "Raw output"]
)


def render_items(items: list[dict], empty: str) -> None:
    if not items:
        st.write(empty)
    for item in items:
        st.markdown(f"**{show(item.get('claim'))}**")
        if item.get("interpretation"):
            st.caption(item["interpretation"])
        for line in cited_sources(item, sources):
            st.caption("Source: " + line)


with shown:
    left, right = st.columns(2)

    with left:
        st.subheader("Supporting evidence")
        render_items(out.get("evidence", []), "Nothing survived the claim check.")

    with right:
        st.subheader("Contradictory evidence")
        render_items(out.get("contradictory_evidence", []), "None recorded.")

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Uncertainty")
        for line in out.get("uncertainty", []) or ["None recorded."]:
            st.markdown(f"- {line}")

    with right:
        st.subheader("Recommended checks")
        for check in out.get("recommended_checks", []):
            st.markdown(f"- **{show(check.get('check'))}**: {show(check.get('reason'))}")

with blocked:
    st.subheader("Removed before display")
    st.caption(
        f"{show(report.get('verified_items'))} claims verified, "
        f"{show(report.get('blocked_items'))} removed. "
        "A removed claim is deleted rather than flagged, and the rate is reported."
    )

    # The breakdown by reason, not just the rate. A system that never blocks
    # anything has either a very obedient model or a verifier that is not
    # working, and this table is how a reader tells those apart.
    # docs/VERIFIER_SPEC.md section 5.
    reasons = report.get("reasons") or {}
    if reasons:
        cols = st.columns(len(reasons))
        labels = {
            "missing_or_unknown_ids": "No such result",
            "numeric_claim_unsupported": "Number unsupported",
            "direction_contradicts_result": "Direction wrong",
            "entity_not_in_results": "Entity not in results",
        }
        for col, (key, count) in zip(cols, reasons.items()):
            col.metric(labels.get(key, key), count)
        st.divider()

    if not report.get("issues"):
        st.success("Every claim traced back to a tool result.")
    for issue in report.get("issues", []):
        with st.container(border=True):
            st.markdown(f"**{show(issue['item'].get('claim'))}**")
            st.caption(f"Reason: {issue['reason']}")
            if issue.get("detail"):
                st.caption("Failed on: " + ", ".join(str(d) for d in issue["detail"]))
            for line in cited_sources(issue["item"], sources):
                st.caption("Cited: " + line)

with trace_tab:
    st.subheader("Every call the agent made")
    st.caption(
        "Replayable. This is what the claim check matches against. "
        "Each call is named by the result id that claims cite."
    )
    for event in res.get("trace", []):
        if event.get("event") != "tool_call":
            continue
        ok = event.get("status") == "ok"
        rid = (event.get("result") or {}).get("result_id") or "no result id"
        title = f"{'OK' if ok else 'ERROR'}  ·  {rid}  ·  {event.get('tool')}"
        with st.expander(title, expanded=False):
            st.caption("Arguments")
            st.json(event.get("arguments", {}))
            st.caption("Returned")
            st.json(event.get("result", {}))

    others = [e for e in res.get("trace", []) if e.get("event") != "tool_call"]
    if others:
        with st.expander("Other trace events"):
            st.json(others)

with raw:
    raw_output = res.get("raw_output")
    if raw_output is not None:
        st.caption(
            "Before verification: everything the agent wrote, including the claims "
            "the check removed. The evaluation measures raw claim support on this."
        )
        st.json(raw_output)
        st.divider()
    st.caption("After verification: the output contract as displayed above.")
    st.json(out)
    st.download_button(
        "Download this assessment",
        data=json.dumps({"result": res}, indent=2, default=str),
        file_name=f"assessment_{res['gvkey']}_{res['fyear']}.json",
        mime="application/json",
    )
