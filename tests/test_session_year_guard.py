"""The year guard in src/session.py: no tool runs on a year after the assessment year.

docs/EVALUATION_DESIGN.md section 9 says the app never calls a tool with a
year after the selected year. The scripted Offline demo model never asks for
one, so a test that only watches the demo would pass whether or not anything
enforces the rule. These tests make the request on purpose and check it is
refused before the tool runs.

Run from the repository root:

    pytest tests/test_session_year_guard.py -v
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import session, tools  # noqa: E402
from src.agent import TOOL_NAMES  # noqa: E402

FYEAR = 2018
GVKEY = "001004"
YEAR_ARGS = ("fyear", "through_fyear")  # every year argument in the nine signatures


def year_arg(name: str) -> str | None:
    """The year argument a tool takes, read from its real signature."""
    params = inspect.signature(getattr(tools, name)).parameters
    return next((k for k in YEAR_ARGS if k in params), None)


YEAR_TOOLS = [n for n in TOOL_NAMES if year_arg(n)]


def test_year_capped_tools_were_found():
    # Guards the parametrised test below against passing on an empty list.
    assert YEAR_TOOLS, "no tool signature has fyear or through_fyear"


@pytest.mark.parametrize("name", YEAR_TOOLS)
def test_later_year_is_refused_before_the_tool_runs(monkeypatch, name):
    key = year_arg(name)  # read the real signature before it is replaced

    def must_not_run(**kwargs):
        raise AssertionError(f"{name} ran with {kwargs}")

    monkeypatch.setattr(tools, name, must_not_run)
    wrapped = session.alias_tools(GVKEY, max_year=FYEAR)[name]

    out = wrapped(**{"gvkey": session.ALIAS, key: FYEAR + 1})

    assert out["value"] is None
    assert "Refused" in out["notes"]


@pytest.mark.parametrize("name", YEAR_TOOLS)
def test_assessment_year_itself_is_allowed(monkeypatch, name):
    key = year_arg(name)
    calls = []

    def spy(**kwargs):
        calls.append(kwargs)
        return {"value": 1.0, "source": f"spy | gvkey={kwargs.get('gvkey')}", "notes": ""}

    monkeypatch.setattr(tools, name, spy)
    wrapped = session.alias_tools(GVKEY, max_year=FYEAR)[name]

    out = wrapped(**{"gvkey": session.ALIAS, key: FYEAR})

    assert len(calls) == 1
    assert calls[0]["gvkey"] == GVKEY            # alias swapped for the real key going in
    assert GVKEY not in str(out)                  # and masked again coming out


def test_a_model_asking_for_next_year_never_reaches_the_data(monkeypatch):
    """End to end: a model that asks for t+1 through run_assessment."""
    name = "score_firm" if "score_firm" in YEAR_TOOLS else YEAR_TOOLS[0]
    key = year_arg(name)
    seen = []
    real = getattr(tools, name)

    def spy(**kwargs):
        seen.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(tools, name, spy)

    class AsksForNextYear:
        def __init__(self, fyear, inject_unsupported=False):
            self.fyear = int(fyear)
            self.asked = False

        def complete(self, messages, tools_):  # noqa: ARG002
            if not self.asked:
                self.asked = True
                return {"type": "tool_call", "name": name,
                        "arguments": {"gvkey": session.ALIAS, key: self.fyear + 1}}
            return {"type": "final", "content": {
                "assessment": {"risk_level": "indeterminate"},
                "evidence": [], "contradictory_evidence": [],
                "uncertainty": [], "recommended_checks": []}}

    monkeypatch.setattr(session, "OfflineLLM", AsksForNextYear)

    result = session.run_assessment(gvkey=GVKEY, fyear=FYEAR, inject_unsupported=False)

    assert seen == [], f"{name} ran on a later year: {seen}"
    calls = [e for e in result["trace"] if e.get("event") == "tool_call"]
    assert calls, "the request for a later year left no trace"
    assert "Refused" in str(calls[0].get("result"))
