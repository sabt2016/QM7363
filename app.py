"""Task 4.1: the Streamlit shell. Firm and year selection, results pane, trace viewer.

Run it from the repository root:

    streamlit run app.py

It works today with no data file, no model file and no API key, because the
"Offline demo" provider drives the agent through the merged tool stubs. Swap
the provider once keys and the panel are in place; nothing else here changes.

All of the wiring lives in src/session.py. This file is only the interface.
"""

from __future__ import annotations

import json

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

st.set_page_config(page_title="Agentic Risk Analyst", layout="wide")


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Assessment")

    gvkey = st.text_input("Firm identifier (gvkey)", value="001004")
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

    inject = st.checkbox(
        "Inject an unsupported claim (demonstration)", value=True,
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
    try:
        st.session_state["result"] = run_assessment(
            gvkey=gvkey,
            fyear=int(fyear),
            provider=provider,
            max_tool_calls=int(budget),
            inject_unsupported=inject,
            api_key=st.session_state.get("api_key", ""),
        )
    except NotImplementedError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:  # noqa: BLE001 - surface anything to the operator
        st.error(f"{type(exc).__name__}: {exc}")
        st.stop()

res = st.session_state["result"]
out = res["output"]
report = res["report"]
assessment = out.get("assessment", {})


# ---------------------------------------------------------------- summary
a, b, c, d = st.columns(4)
level = str(assessment.get("risk_level", "indeterminate"))
a.markdown(
    f"**Risk level**<br><span style='font-size:30px;font-weight:700;"
    f"color:{RISK_COLOR.get(level, NAVY)}'>{level.title()}</span>",
    unsafe_allow_html=True,
)
b.metric("Probability", assessment.get("probability", "n/a"))
c.metric("Tool calls used", res["tool_calls_used"])
d.metric("Claims blocked", report["blocked_items"],
         delta=f"{report['block_rate']:.1%} block rate", delta_color="off")

st.write(assessment.get("summary", ""))

meta = (
    f"Firm {res['gvkey']} shown as **{res['alias']}** to the model &nbsp;|&nbsp; "
    f"features FY{res['fyear']}, opinion predicted for FY{res['fyear'] + 1} &nbsp;|&nbsp; "
    f"model `{assessment.get('model_version')}` &nbsp;|&nbsp; "
    f"confidence {assessment.get('confidence')} &nbsp;|&nbsp; "
    f"run `{res['run_id']}`"
)
st.caption(meta, unsafe_allow_html=True)

st.divider()


# ---------------------------------------------------------------- panes
shown, blocked, trace_tab, raw = st.tabs(
    ["Assessment", f"Blocked ({report['blocked_items']})", "Trace", "Raw output"]
)

with shown:
    left, right = st.columns(2)

    with left:
        st.subheader("Supporting evidence")
        items = out.get("evidence", [])
        if not items:
            st.write("Nothing survived the claim check.")
        for item in items:
            st.markdown(f"**{item.get('claim')}**")
            st.caption(item.get("interpretation", ""))
            st.caption("Source: " + ", ".join(item.get("tool_result_ids", [])))

    with right:
        st.subheader("Contradictory evidence")
        items = out.get("contradictory_evidence", [])
        if not items:
            st.write("None recorded.")
        for item in items:
            st.markdown(f"**{item.get('claim')}**")
            st.caption(item.get("interpretation", ""))
            st.caption("Source: " + ", ".join(item.get("tool_result_ids", [])))

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Uncertainty")
        for line in out.get("uncertainty", []) or ["None recorded."]:
            st.markdown(f"- {line}")

    with right:
        st.subheader("Recommended checks")
        for check in out.get("recommended_checks", []):
            st.markdown(f"- **{check.get('check')}** &mdash; {check.get('reason')}")

with blocked:
    st.subheader("Removed before display")
    st.caption(
        f"{report['verified_items']} claims verified, {report['blocked_items']} removed. "
        "A removed claim is deleted rather than flagged, and the rate is reported."
    )
    if not report["issues"]:
        st.success("Every claim traced back to a tool result.")
    for issue in report["issues"]:
        with st.container(border=True):
            st.markdown(f"**{issue['item'].get('claim')}**")
            st.caption(f"Reason: {issue['reason']}")
            st.caption("Cited: " + ", ".join(issue["item"].get("tool_result_ids", [])))

with trace_tab:
    st.subheader("Every call the agent made")
    st.caption("Replayable. This is what the claim check matches against.")
    for event in res["trace"]:
        if event.get("event") != "tool_call":
            continue
        ok = event.get("status") == "ok"
        label = f"{event.get('result', {}).get('result_id', '?')} &nbsp; {event.get('tool')}"
        with st.expander(f"{'OK' if ok else 'ERROR'}  {event.get('tool')}", expanded=False):
            st.caption("Arguments")
            st.json(event.get("arguments", {}))
            st.caption("Returned")
            st.json(event.get("result", {}))

    others = [e for e in res["trace"] if e.get("event") != "tool_call"]
    if others:
        with st.expander("Other trace events"):
            st.json(others)

with raw:
    st.caption("The output contract as the agent produced it, after the claim check.")
    st.json(out)
    st.download_button(
        "Download this assessment",
        data=json.dumps({"result": res}, indent=2, default=str),
        file_name=f"assessment_{res['gvkey']}_{res['fyear']}.json",
        mime="application/json",
    )
