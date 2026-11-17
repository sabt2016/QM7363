"""
Task 3.3: Trace logger (owner: Jessica Bedson).

Every tool call the agent makes, with its arguments and its return, is written to disk
in replayable form as it happens.

How it fits the agent loop (Task 3.1)
-------------------------------------
The logger wraps the tool functions before they are handed to run_agent. The agent loop
itself does not change:

    logger = TraceLogger(trace_dir="traces", metadata={...})
    tools = logger.wrap_tools(tools)            # the nine tools from src/tools.py
    result = run_agent(..., tools=tools)
    summary = logger.finish(agent_result=result, verifier=verify_evidence_links)

Trace format (one JSON object per line, file traces/<run_id>.jsonl)
-------------------------------------------------------------------
    run_start    format version, run id, metadata (firm alias, feature year, model version,
                 seed, language model, call budget, SHA-256 of the system prompt and schemas)
    tool_call    seq, expected_result_id, tool, arguments, status ("ok" or "error"),
                 return (or error), return_sha256, timestamps, duration
    note         optional free-form events (for example a language-model turn)
    agent_trace  the agent loop's own in-memory trace, copied at the end of the run
    final        raw final output (before verification), status, tool calls used
    verification verifier report and the verified output
    reconcile    whether the logged tool calls match the agent's own trace
    run_end      counts and completion flag

Design rules
------------
1. Write as you go. Each event is flushed to disk immediately, so a crash leaves a
   readable partial trace (load_trace reports it as incomplete).
2. Copy, never reference. Arguments and returns are serialised to plain JSON at the moment
   of the call. Later in-place edits (for example the verifier removing claims) cannot
   rewrite the record. This is the bug fixed in _jsonable on main.
3. Never overwrite. Trace files are opened in exclusive-create mode.
4. Tamper-evident. Each stored return carries a SHA-256 digest; load_trace re-checks it.
5. Replayable. Stored arguments are exactly what the tool received, so the same call can be
   re-run and its return compared with the stored digest (replay_check, the starting point
   for Task 6.5).

Data note: traces contain tool returns derived from WRDS data. Keep them local (add
traces/ to .gitignore) until the data-use question is settled.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import platform
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

TRACE_FORMAT_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _to_plain(value: Any) -> Any:
    """Convert common non-JSON types (numpy, pandas, dates, dataclasses, sets) to plain JSON types."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    if hasattr(value, "isoformat"):            # pandas.Timestamp
        return value.isoformat()
    if hasattr(value, "tolist"):               # numpy arrays and pandas Series
        return value.tolist()
    if hasattr(value, "item"):                 # numpy scalars
        return value.item()
    if hasattr(value, "to_dict"):              # pandas DataFrame
        return value.to_dict(orient="records")
    return str(value)


def _clean_floats(value: Any) -> Any:
    """Replace NaN and infinity with None so every trace line is strict JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _clean_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_floats(v) for v in value]
    return value


def canonical(value: Any) -> Any:
    """Return an independent, plain-JSON copy of value (dicts, lists, str, int, float, bool, None)."""
    text = json.dumps(value, default=_to_plain, allow_nan=True)
    return _clean_floats(json.loads(text))


def digest(value: Any) -> str:
    """SHA-256 of the canonical JSON form (sorted keys, no whitespace)."""
    text = json.dumps(canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def text_sha256(text: str) -> str:
    """SHA-256 of a string, for recording which system prompt or schema version was used."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class TraceLogger:
    """Persist every tool call, argument and return of one agent run as JSON lines."""

    def __init__(
        self,
        trace_dir: str | Path = "traces",
        run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.run_id = run_id or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex[:8]
        )
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / f"{self.run_id}.jsonl"
        self._file = self.path.open("x", encoding="utf-8")   # never overwrite an existing trace
        self._event_index = 0
        self._seq = 0
        self.tool_calls: list[dict[str, Any]] = []
        self.closed = False
        self._write({
            "event": "run_start",
            "format_version": TRACE_FORMAT_VERSION,
            "run_id": self.run_id,
            "started_at": _now(),
            "python": platform.python_version(),
            "metadata": dict(metadata or {}),
        })

    # -- writing -----------------------------------------------------------

    def _write(self, event: Mapping[str, Any]) -> dict[str, Any]:
        if self.closed:
            raise RuntimeError("Trace is closed; start a new TraceLogger for a new run.")
        record = canonical(dict(event))
        record["event_index"] = self._event_index
        record["run_id"] = self.run_id
        self._file.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        self._file.flush()
        self._event_index += 1
        return record

    def log_note(self, kind: str, **fields: Any) -> None:
        """Record an optional free-form event, for example a language-model turn."""
        self._write({"event": "note", "kind": kind, "at": _now(), **fields})

    # -- tool wrapping -----------------------------------------------------

    def wrap_tools(self, tools: Mapping[str, Callable[..., Any]]) -> dict[str, Callable[..., Any]]:
        """Return the same tools, each wrapped so that every call is logged."""
        return {name: self._wrap(name, fn) for name, fn in tools.items()}

    def _wrap(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def logged(*args: Any, **kwargs: Any) -> Any:
            self._seq += 1
            seq = self._seq
            started = datetime.now(timezone.utc)
            arguments = canonical(kwargs) if not args else canonical({"_args": list(args), **kwargs})
            event: dict[str, Any] = {
                "event": "tool_call",
                "seq": seq,
                # run_agent numbers executed calls result_1, result_2, ...; reconcile() checks this.
                "expected_result_id": f"result_{seq}",
                "tool": name,
                "arguments": arguments,
                "started_at": started.isoformat(),
            }
            try:
                value = fn(*args, **kwargs)
            except Exception as exc:
                finished = datetime.now(timezone.utc)
                event.update({
                    "status": "error",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "finished_at": finished.isoformat(),
                    "duration_ms": round((finished - started).total_seconds() * 1000, 3),
                })
                self.tool_calls.append(self._write(event))
                raise
            finished = datetime.now(timezone.utc)
            stored = canonical(value)      # independent copy, taken before anyone can mutate value
            event.update({
                "status": "ok",
                "return": stored,
                "return_sha256": digest(stored),
                "finished_at": finished.isoformat(),
                "duration_ms": round((finished - started).total_seconds() * 1000, 3),
            })
            self.tool_calls.append(self._write(event))
            return value

        return logged

    # -- closing -----------------------------------------------------------

    def finish(
        self,
        agent_result: Any = None,
        verifier: Callable[[dict, list], Mapping[str, Any]] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        Write the agent's trace and final output, run the verifier, reconcile, and close the file.

        Pass the verifier (e.g. verify_evidence_links) here rather than calling it first.
        The raw output and the agent trace are written to disk BEFORE the verifier runs,
        because the verifier edits the output in place. The verified output is written after.
        """
        agent_trace = getattr(agent_result, "trace", None)
        output = getattr(agent_result, "output", None)
        if agent_trace is not None:
            self._write({"event": "agent_trace", "trace": agent_trace})

        final_status = status or getattr(agent_result, "status", None)
        self._write({
            "event": "final",
            "stage": "raw",
            "status": final_status,
            "agent_run_id": getattr(agent_result, "run_id", None),
            "tool_calls_used": getattr(agent_result, "tool_calls_used", None),
            "output": output,
        })

        verification = None
        if verifier is not None and output is not None:
            verification = verifier(output, agent_trace or [])
            self._write({
                "event": "verification",
                "report": verification,
                "verified_output": output,
            })

        issues = reconcile(self.tool_calls, agent_trace) if agent_trace is not None else None
        self._write({
            "event": "reconcile",
            "checked": agent_trace is not None,
            "matches": None if issues is None else not issues,
            "issues": issues or [],
        })

        summary = {
            "run_id": self.run_id,
            "path": str(self.path),
            "status": final_status,
            "tool_calls_logged": len(self.tool_calls),
            "tool_errors": sum(1 for c in self.tool_calls if c["status"] == "error"),
            "reconciled": None if issues is None else not issues,
        }
        if verification is not None:
            summary["verified_items"] = verification.get("verified_items")
            summary["blocked_items"] = verification.get("blocked_items")
        self._write({"event": "run_end", "ended_at": _now(), "complete": True, **summary})
        self._file.close()
        self.closed = True
        summary["verification"] = verification
        return summary

    def close(self) -> None:
        """Close without a final record (the trace then loads as incomplete)."""
        if not self.closed:
            self._file.close()
            self.closed = True

    def __enter__(self) -> "TraceLogger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.closed and exc_type is not None:
            self._write({"event": "note", "kind": "run_aborted", "at": _now(),
                         "error": {"type": exc_type.__name__, "message": str(exc)}})
        self.close()


# ---------------------------------------------------------------------------
# Checks on a run
# ---------------------------------------------------------------------------

def reconcile(logged_calls: list[Mapping[str, Any]], agent_trace: list[Mapping[str, Any]]) -> list[dict]:
    """
    Compare the logged tool calls with the agent loop's own trace.

    Every executed call in the agent trace (event == "tool_call") must appear in the log,
    in the same order, with the same tool, arguments, status and result id.
    Returns a list of issues; an empty list means the two agree.
    """
    agent_calls = [e for e in agent_trace if e.get("event") == "tool_call"]
    issues: list[dict] = []
    if len(agent_calls) != len(logged_calls):
        issues.append({"issue": "call_count_mismatch",
                       "agent_calls": len(agent_calls), "logged_calls": len(logged_calls)})
    for i, (agent, logged) in enumerate(zip(agent_calls, logged_calls), start=1):
        agent_result = agent.get("result") or agent.get("error") or {}
        checks = {
            "tool": (agent.get("tool"), logged.get("tool")),
            "arguments": (canonical(agent.get("arguments")), logged.get("arguments")),
            "status": (agent.get("status"), logged.get("status")),
            "result_id": (agent_result.get("result_id"), logged.get("expected_result_id")),
        }
        for field, (a, b) in checks.items():
            if a != b:
                issues.append({"issue": f"{field}_mismatch", "position": i, "agent": a, "logged": b})
    return issues


def load_trace(path: str | Path) -> dict[str, Any]:
    """
    Read a trace file and check it.

    Checks: format version, contiguous event numbering, one run id, every tool call has a
    return or an error, and every stored return still matches its SHA-256 digest.
    """
    path = Path(path)
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    problems: list[str] = []
    if not events or events[0].get("event") != "run_start":
        problems.append("First event is not run_start.")
    elif events[0].get("format_version") != TRACE_FORMAT_VERSION:
        problems.append(f"Format version {events[0].get('format_version')} is not {TRACE_FORMAT_VERSION}.")
    if [e.get("event_index") for e in events] != list(range(len(events))):
        problems.append("Event numbering is not contiguous (events missing or reordered).")
    if len({e.get("run_id") for e in events}) > 1:
        problems.append("More than one run id in the file.")

    tool_calls = [e for e in events if e.get("event") == "tool_call"]
    for call in tool_calls:
        if call.get("status") == "ok":
            if digest(call.get("return")) != call.get("return_sha256"):
                problems.append(f"Tool call {call.get('seq')} ({call.get('tool')}): return does not match its digest.")
        elif call.get("status") == "error":
            if "error" not in call:
                problems.append(f"Tool call {call.get('seq')}: error status without an error record.")
        else:
            problems.append(f"Tool call {call.get('seq')}: unknown status {call.get('status')!r}.")

    def first(kind: str) -> dict | None:
        return next((e for e in events if e.get("event") == kind), None)

    run_end = first("run_end")
    return {
        "path": str(path),
        "run_start": events[0] if events else None,
        "tool_calls": tool_calls,
        "final": first("final"),
        "verification": first("verification"),
        "reconcile": first("reconcile"),
        "run_end": run_end,
        "complete": bool(run_end and run_end.get("complete")),
        "valid": not problems,
        "problems": problems,
        "events": events,
    }


def replay_check(path: str | Path, tools: Mapping[str, Callable[..., Any]]) -> dict[str, Any]:
    """
    Starting point for Task 6.5: re-run every stored successful call with its stored
    arguments and check that the tool returns the same value (same SHA-256 digest).
    Tool errors are re-run too and must raise the same exception type.
    """
    trace = load_trace(path)
    results = []
    for call in trace["tool_calls"]:
        name, arguments = call["tool"], dict(call["arguments"])
        args = arguments.pop("_args", [])
        entry = {"seq": call["seq"], "tool": name}
        if name not in tools:
            entry.update(match=False, reason="tool not supplied for replay")
        else:
            try:
                value = tools[name](*args, **arguments)
                if call["status"] == "ok":
                    entry["match"] = digest(value) == call["return_sha256"]
                    if not entry["match"]:
                        entry["reason"] = "return differs from stored return"
                else:
                    entry.update(match=False, reason="stored call raised, replay did not")
            except Exception as exc:
                stored_type = (call.get("error") or {}).get("type")
                entry["match"] = call["status"] == "error" and type(exc).__name__ == stored_type
                if not entry["match"]:
                    entry["reason"] = f"replay raised {type(exc).__name__}"
        results.append(entry)
    return {
        "path": str(path),
        "trace_valid": trace["valid"],
        "calls_replayed": len(results),
        "calls_matched": sum(r["match"] for r in results),
        "all_match": trace["valid"] and all(r["match"] for r in results),
        "results": results,
    }
