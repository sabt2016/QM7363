"""Task 5.2: connect Enock's agent loop to the team's real tool layer.

This module does not implement business-data tools. It binds the existing
project modules, checks required interfaces, runs one assessment, and hands
the raw result to Jessica's trace logger before the Task 5.3 verifier works
on a copy.
"""
from __future__ import annotations

import copy
import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from src.task_5_3_verifier import verify

REQUIRED_TOOLS = (
    "get_firm_history", "get_control_history", "score_firm",
    "get_percentile", "get_deviation", "get_peer_cohort",
    "get_cohort_rate", "get_industry_context", "get_filing_excerpt",
)

class IntegrationError(RuntimeError):
    pass

def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except Exception as exc:
        raise IntegrationError(f"Could not import {name}: {exc}") from exc

def _is_stub(fn: Callable) -> bool:
    """Best-effort fail-closed check for the known demonstration stub layer."""
    try:
        source = inspect.getsource(fn).lower()
    except (OSError, TypeError):
        return False
    markers = ("stub implementation", "invented", "demonstration value")
    return any(marker in source for marker in markers)

def build_tool_map(*, tools_module=None, model_module=None) -> dict[str, Callable]:
    """Build agent-callable functions from the current tools/model modules.

    Tool functions are passed through without changing their contract arguments.
    score_firm is routed through src.model.score_firm when available, because
    that module owns the model-to-tool contract adapter.
    """
    tools_module = tools_module or _load_module("src.tools")
    model_module = model_module or _load_module("src.model")
    mapping = {}
    missing = []
    for name in REQUIRED_TOOLS:
        if name == "score_firm":
            fn = getattr(model_module, name, None)
        else:
            fn = getattr(tools_module, name, None)
        if not callable(fn):
            missing.append(name)
        else:
            if _is_stub(fn):
                raise IntegrationError(f"{name} is still a stub; refusing a fake assessment.")
            mapping[name] = fn
    if missing:
        raise IntegrationError("Missing required tool functions: " + ", ".join(missing))
    return mapping

def validate_temporal_arguments(tool_map: Mapping[str, Callable], feature_year: int) -> None:
    """Check agent schema calls cannot omit the agreed time cutoff."""
    # The model decides arguments; this check confirms the schema passed to
    # run_agent has through_fyear required for history retrieval.
    for name in ("get_firm_history", "get_control_history"):
        fn = tool_map.get(name)
        if fn is None:
            continue
        params = inspect.signature(fn).parameters
        if "through_fyear" not in params:
            # The signed legacy contract allowed get_control_history(gvkey),
            # but the November global no-look-ahead decision requires cutoff.
            if name == "get_control_history":
                raise IntegrationError(
                    "get_control_history lacks required through_fyear cutoff; "
                    "update the real tool before running a no-look-ahead assessment."
                )
    # Explicitly document that cohort tools must take a year argument.
    cohort = tool_map.get("get_cohort_rate")
    if cohort is not None:
        params = inspect.signature(cohort).parameters
        if not ({"fyear", "feature_year"} & set(params)):
            raise IntegrationError("get_cohort_rate must accept fyear/feature_year.")

def run_task_5_2(
    *,
    firm_id: str,
    feature_year: int,
    user_question: str,
    llm,
    logger=None,
    max_tool_calls: int = 8,
    agent_module=None,
    tools_module=None,
    model_module=None,
    output_dir: str | Path = "task_outputs",
) -> dict[str, Any]:
    """Run real agent integration and persist raw assessment plus trace.

    `logger`, when supplied, must expose finish(agent_result=..., verifier=...).

    One verification pass, not two. Decision 2026-11-10, entry 29. This used to
    hand verify_evidence_links to the logger and then run the task 5.3 verifier
    on a separate copy, which produced two reports that both counted the same
    blocked claim. The 5.3 verifier does linkage itself under
    missing_or_unknown_ids, so it is the only pass. Jessica's logger already
    writes the raw output to disk before the verifier runs and the verified
    output after, so passing it the full verifier preserves the audit trail.
    """
    agent_module = agent_module or _load_module("src.agent")
    tool_map = build_tool_map(tools_module=tools_module, model_module=model_module)
    validate_temporal_arguments(tool_map, int(feature_year))

    result = agent_module.run_agent(
        firm_id=str(firm_id),
        feature_year=int(feature_year),
        user_question=user_question,
        llm=llm,
        tools=tool_map,
        max_tool_calls=max_tool_calls,
    )

    # Snapshot before anything mutates the output. The verifier removes items
    # in place, so this is the only record of what the model actually wrote.
    raw_output = copy.deepcopy(result.output)

    if logger is not None:
        finish = getattr(logger, "finish", None)
        if not callable(finish):
            raise IntegrationError("Trace logger must expose finish(agent_result=..., verifier=...).")
        # The logger writes raw output, runs the verifier, writes verified output.
        verification_report = finish(agent_result=result, verifier=verify)
    else:
        verification_report = verify(result.output, result.trace)

    verified_output = result.output

    payload = {
        "task": "5.2_and_5.3",
        "firm_id": str(firm_id),
        "feature_year": int(feature_year),
        "outcome_year": int(feature_year) + 1,
        "agent_status": result.status,
        "tool_calls_used": result.tool_calls_used,
        "run_id": result.run_id,
        "raw_output": raw_output,
        "verified_output": verified_output,
        "trace": result.trace,
        "verification_report": verification_report,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"task_5_2_5_3_{result.run_id}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["saved_to"] = str(path)
    return payload
