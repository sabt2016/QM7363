"""Tests for Task 3.3, the trace logger. Run with: pytest test_trace_logger.py -q"""

import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from trace_logger import TraceLogger, canonical, digest, load_trace, reconcile, replay_check


# Dummy tools with the same call style as the agent loop (keyword arguments). No real data.
def score_firm(gvkey, feature_year):
    return {"firm_id": gvkey, "feature_year": feature_year, "outcome_year": feature_year + 1,
            "probability": 0.0421, "model_version": "dummy_v0", "source": "dummy"}


def get_control_history(gvkey, through_fyear):
    if through_fyear < 2011:
        raise ValueError("No history before FY2011.")
    return {"firm_id": gvkey, "adverse_years": [2015], "through_fyear": through_fyear, "source": "dummy"}


TOOLS = {"score_firm": score_firm, "get_control_history": get_control_history}


def fake_agent_trace(logged):
    """The shape run_agent records for executed calls (event, tool, arguments, status, result/error)."""
    out = []
    for i, c in enumerate(logged, start=1):
        e = {"event": "tool_call", "call_id": f"tool_{i}", "tool": c["tool"],
             "arguments": c["arguments"], "status": c["status"]}
        if c["status"] == "ok":
            e["result"] = {**c["return"], "result_id": f"result_{i}"}
        else:
            e["error"] = {"result_id": f"result_{i}", **c["error"]}
        out.append(e)
    return out


def test_ok_call_is_persisted_with_arguments_and_return(tmp_path):
    log = TraceLogger(tmp_path, metadata={"firm_id": "FIRM_A"})
    tools = log.wrap_tools(TOOLS)
    value = tools["score_firm"](gvkey="FIRM_A", feature_year=2018)
    log.finish()

    trace = load_trace(log.path)
    assert trace["valid"] and trace["complete"], trace["problems"]
    (call,) = trace["tool_calls"]
    assert call["tool"] == "score_firm"
    assert call["arguments"] == {"gvkey": "FIRM_A", "feature_year": 2018}
    assert call["return"] == value
    assert call["return_sha256"] == digest(value)
    assert call["expected_result_id"] == "result_1"
    assert trace["run_start"]["metadata"]["firm_id"] == "FIRM_A"


def test_tool_error_is_persisted_and_still_raised(tmp_path):
    log = TraceLogger(tmp_path)
    tools = log.wrap_tools(TOOLS)
    with pytest.raises(ValueError):
        tools["get_control_history"](gvkey="FIRM_A", through_fyear=2005)
    log.finish()
    (call,) = load_trace(log.path)["tool_calls"]
    assert call["status"] == "error"
    assert call["error"] == {"type": "ValueError", "message": "No history before FY2011."}


def test_later_mutation_does_not_rewrite_the_record(tmp_path):
    """The bug fixed in _jsonable on main: editing the output in place must not change the trace."""
    log = TraceLogger(tmp_path)
    tools = log.wrap_tools(TOOLS)
    value = tools["get_control_history"](gvkey="FIRM_A", through_fyear=2018)
    value["adverse_years"].clear()        # e.g. a verifier removing items in place
    value["injected"] = True
    log.finish()
    (call,) = load_trace(log.path)["tool_calls"]
    assert call["return"]["adverse_years"] == [2015]
    assert "injected" not in call["return"]


def test_trace_file_is_never_overwritten(tmp_path):
    TraceLogger(tmp_path, run_id="fixed").finish()
    with pytest.raises(FileExistsError):
        TraceLogger(tmp_path, run_id="fixed")


def test_tampering_is_detected(tmp_path):
    log = TraceLogger(tmp_path)
    log.wrap_tools(TOOLS)["score_firm"](gvkey="FIRM_A", feature_year=2018)
    log.finish()
    lines = log.path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["return"]["probability"] = 0.99
    lines[1] = json.dumps(rec)
    log.path.write_text("\n".join(lines) + "\n")
    trace = load_trace(log.path)
    assert not trace["valid"]
    assert any("digest" in p for p in trace["problems"])


def test_crash_leaves_a_readable_incomplete_trace(tmp_path):
    with pytest.raises(RuntimeError):
        with TraceLogger(tmp_path, run_id="crash") as log:
            log.wrap_tools(TOOLS)["score_firm"](gvkey="FIRM_A", feature_year=2018)
            raise RuntimeError("agent crashed")
    trace = load_trace(tmp_path / "crash.jsonl")
    assert trace["valid"] and not trace["complete"]
    assert len(trace["tool_calls"]) == 1


def test_reconcile_agrees_with_agent_trace_and_catches_mismatch(tmp_path):
    log = TraceLogger(tmp_path)
    tools = log.wrap_tools(TOOLS)
    tools["score_firm"](gvkey="FIRM_A", feature_year=2018)
    with pytest.raises(ValueError):
        tools["get_control_history"](gvkey="FIRM_A", through_fyear=2000)
    agent_trace = fake_agent_trace(log.tool_calls)
    assert reconcile(log.tool_calls, agent_trace) == []

    agent_trace[0]["arguments"] = {"gvkey": "FIRM_A", "feature_year": 2019}
    issues = reconcile(log.tool_calls, agent_trace)
    assert [i["issue"] for i in issues] == ["arguments_mismatch"]

    issues = reconcile(log.tool_calls, agent_trace[:1])
    assert issues[0]["issue"] == "call_count_mismatch"
    log.finish()


def test_replay_reproduces_returns_and_flags_changes(tmp_path):
    log = TraceLogger(tmp_path)
    tools = log.wrap_tools(TOOLS)
    tools["score_firm"](gvkey="FIRM_A", feature_year=2018)
    with pytest.raises(ValueError):
        tools["get_control_history"](gvkey="FIRM_A", through_fyear=2000)
    log.finish()

    report = replay_check(log.path, TOOLS)
    assert report["all_match"] and report["calls_matched"] == 2

    changed = dict(TOOLS, score_firm=lambda gvkey, feature_year: {**score_firm(gvkey, feature_year), "probability": 0.5})
    report = replay_check(log.path, changed)
    assert not report["all_match"]
    assert report["results"][0]["reason"] == "return differs from stored return"


def test_numpy_pandas_and_nan_values_serialise(tmp_path):
    def odd_tool():
        return {"p": np.float64(0.1), "n": np.int64(3), "flag": np.bool_(True), "arr": np.array([1, 2]),
                "when": pd.Timestamp("2018-09-30"), "at": datetime(2020, 1, 1), "missing": float("nan")}
    log = TraceLogger(tmp_path)
    log.wrap_tools({"odd": odd_tool})["odd"]()
    log.finish()
    trace = load_trace(log.path)
    assert trace["valid"], trace["problems"]
    ret = trace["tool_calls"][0]["return"]
    assert ret == {"p": 0.1, "n": 3, "flag": True, "arr": [1, 2], "when": "2018-09-30T00:00:00",
                   "at": "2020-01-01T00:00:00", "missing": None}


def test_canonical_returns_independent_copy():
    original = {"a": [1, 2]}
    copy = canonical(original)
    copy["a"].append(3)
    assert original == {"a": [1, 2]}


def test_raw_output_is_saved_before_the_verifier_edits_it(tmp_path):
    class Result:  # same attributes as AgentResult
        def __init__(self):
            self.output = {"evidence": [{"claim": "a", "tool_result_ids": ["result_1"]},
                                        {"claim": "b", "tool_result_ids": ["result_9"]}]}
            self.trace = []
            self.status, self.run_id, self.tool_calls_used = "completed", "r1", 0

    def verifier(output, trace):          # removes the unsupported claim in place, like verify_evidence_links
        output["evidence"] = [e for e in output["evidence"] if e["tool_result_ids"] == ["result_1"]]
        return {"verified_items": 1, "blocked_items": 1, "issues": []}

    log = TraceLogger(tmp_path)
    summary = log.finish(agent_result=Result(), verifier=verifier)
    trace = load_trace(log.path)
    assert len(trace["final"]["output"]["evidence"]) == 2              # raw output intact
    assert len(trace["verification"]["verified_output"]["evidence"]) == 1
    assert summary["blocked_items"] == 1
