"""Task 4.1: tests for the Streamlit interface (app.py).

These are the app checks in docs/EVALUATION_DESIGN.md section 9. They run the
real app through Streamlit's AppTest in the "Offline demo" mode, so they need
no browser, no API key, no panel and no model file.

Run from the repository root:

    pytest tests/test_app.py -v

The panel-picker check in section 9 ("only offers firm-years that exist in the
panel") is not tested here: the app takes a typed gvkey until the panel is
wired in. It is listed as a skipped test so the gap stays visible.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP = str(ROOT / "app.py")
GVKEY = "001004"
FYEAR = 2018
YEAR_ARGS = ("fyear", "through_fyear", "feature_year")


# --------------------------------------------------------------------- helpers

def run_app(gvkey: str = GVKEY, fyear: int = FYEAR, inject: bool = False) -> AppTest:
    """Open the app, fill in the sidebar and press Run assessment."""
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.text_input[0].set_value(gvkey)
    at.sidebar.number_input[0].set_value(fyear)
    box = at.sidebar.checkbox[0]
    box.check() if inject else box.uncheck()
    at.sidebar.button[0].click()
    at.run()
    return at


def visible_text(at: AppTest) -> list[str]:
    """Every metric value, caption and markdown line currently on screen."""
    texts = [str(m.value) for m in at.metric]
    texts += [c.value for c in at.caption]
    texts += [m.value for m in at.markdown]
    return texts


def tool_calls(at: AppTest) -> list[dict]:
    return [e for e in at.session_state["result"]["trace"] if e.get("event") == "tool_call"]


@pytest.fixture(scope="module")
def clean_run() -> AppTest:
    return run_app(inject=False)


@pytest.fixture(scope="module")
def injected_run() -> AppTest:
    return run_app(inject=True)


# --------------------------------------------------------------------- tests

def test_opens_with_prompt_and_no_error():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    assert any("run an assessment" in i.value for i in at.info)


def test_offline_run_completes(clean_run):
    assert not clean_run.exception
    assert not clean_run.error, [e.value for e in clean_run.error]
    labels = [m.label for m in clean_run.metric]
    for expected in ("Probability", "Tool calls used", "Claims blocked"):
        assert expected in labels


def test_demonstration_claim_is_off_by_default():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert at.sidebar.checkbox[0].value is False


def test_missing_values_never_shown_as_none(clean_run):
    # Section 9: a None tool value displays as "not available", never as None or 0.
    offenders = [t for t in visible_text(clean_run) if re.search(r"\bNone\b", t)]
    offenders = [t for t in offenders if "None recorded" not in t]
    assert not offenders, offenders


def test_every_shown_claim_carries_its_source_string(clean_run):
    # Section 9: every source string from the trace appears on screen.
    result = clean_run.session_state["result"]
    captions = [c.value for c in clean_run.caption]
    shown = result["output"].get("evidence", []) + result["output"].get("contradictory_evidence", [])
    for item in shown:
        for rid in item.get("tool_result_ids", []):
            assert any(c.startswith(f"Source: {rid}: ") for c in captions), rid


def test_trace_names_each_call_by_result_id(clean_run):
    labels = [e.label for e in clean_run.expander]
    for event in tool_calls(clean_run):
        rid = (event.get("result") or {}).get("result_id")
        if rid:
            assert any(rid in label for label in labels), rid


def test_no_tool_called_with_a_later_year(clean_run):
    # Section 9: the app never calls a tool with a year after the selected year.
    for event in tool_calls(clean_run):
        args = event.get("arguments") or {}
        for key in YEAR_ARGS:
            if args.get(key) is not None:
                assert int(args[key]) <= FYEAR, (event.get("tool"), key, args[key])


def test_real_gvkey_never_reaches_the_model(clean_run):
    # Identifier exposure (section 6): tool arguments and tool returns carry
    # the alias, never the real gvkey.
    for event in tool_calls(clean_run):
        sent = json.dumps(event.get("arguments") or {})
        returned = json.dumps(event.get("result") or {}, default=str)
        assert GVKEY not in sent, event.get("tool")
        assert GVKEY not in returned, event.get("tool")


def test_injected_claim_is_blocked_and_labelled(injected_run):
    report = injected_run.session_state["result"]["report"]
    assert report["blocked_items"] >= 1
    blocked_claims = [i["item"].get("tool_result_ids") for i in report["issues"]]
    assert ["result_99"] in blocked_claims
    assert any("demonstration claim" in w.value for w in injected_run.warning)


def test_clean_run_has_no_demonstration_warning(clean_run):
    assert not any("demonstration claim" in w.value for w in clean_run.warning)


def test_raw_output_kept_beside_verified_output(injected_run):
    # The raw output keeps the claim the verifier removed, which is what raw
    # claim support in the evaluation is measured on.
    result = injected_run.session_state["result"]
    if "raw_output" not in result:
        pytest.skip("src/session.py does not return raw_output yet")
    raw_ids = [i.get("tool_result_ids") for i in result["raw_output"].get("evidence", [])]
    shown_ids = [i.get("tool_result_ids") for i in result["output"].get("evidence", [])]
    assert ["result_99"] in raw_ids
    assert ["result_99"] not in shown_ids


def test_short_gvkey_is_padded():
    at = run_app(gvkey="1004")
    assert not at.exception
    assert at.session_state["result"]["gvkey"] == GVKEY


def test_invalid_gvkey_is_refused():
    at = run_app(gvkey="ABC12")
    assert any("six digits" in e.value for e in at.error)


@pytest.mark.skip(reason="Firm picker waits for the panel to be wired into the app")
def test_picker_only_offers_firm_years_in_panel():
    pass
