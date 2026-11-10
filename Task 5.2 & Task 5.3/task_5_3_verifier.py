"""Task 5.3: claim verification against the exact tool results in an agent trace.

This verifier is intentionally conservative. It verifies linkage, numeric
support, direction language, and entity/year/filing-section grounding. It does
not claim to prove the semantic truth of arbitrary prose.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

REASONS = (
    "missing_or_unknown_ids",
    "numeric_claim_unsupported",
    "direction_contradicts_result",
    "entity_not_in_results",
)

NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
DIRECTION_TERMS = {
    "above": ("above", "higher than", "greater than", "exceeds", "increased", "higher"),
    "below": ("below", "lower than", "less than", "under", "decreased", "lower"),
    "unchanged": ("unchanged", "no change", "stable", "the same"),
}
ENTITY_KEYS = {
    "firm": ("firm_name", "company_name", "entity_name"),
    "gvkey": ("gvkey",),
    "fyear": ("fyear", "feature_year", "fiscal_year", "year"),
    "sic": ("sic", "sic_code"),
    "section": ("section", "filing_section"),
}

def _walk_values(obj: Any) -> Iterable[Any]:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            yield k
            yield from _walk_values(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _walk_values(v)
    else:
        yield obj

def _successful_results(trace: list[dict]) -> dict[str, dict]:
    results = {}
    for event in trace:
        if event.get("event") == "tool_call" and event.get("status") == "ok":
            result = event.get("result") or {}
            rid = result.get("result_id")
            if rid:
                results[str(rid)] = result
    return results

def _decimal_forms(token: str) -> set[Decimal]:
    raw = token.replace(",", "").replace("%", "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return set()
    forms = {value}
    if token.endswith("%"):
        forms.add(value / Decimal("100"))
    else:
        # A prose percentage can express a decimal rate returned by a tool.
        if abs(value) > 1:
            forms.add(value / Decimal("100"))
    return forms

def _numeric_values(obj: Any) -> set[Decimal]:
    found: set[Decimal] = set()
    for value in _walk_values(obj):
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float, Decimal)):
            try:
                found.add(Decimal(str(value)))
            except InvalidOperation:
                pass
        elif isinstance(value, str):
            # Numeric strings in structured tool returns are included only if
            # the entire string is numeric, avoiding accidental text matches.
            s = value.strip().replace(",", "").replace("%", "")
            try:
                found.add(Decimal(s))
                if value.strip().endswith("%"):
                    found.add(Decimal(s) / Decimal("100"))
            except InvalidOperation:
                pass
    return found

def _claim_numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(text or "")

def _direction_conflict(claim: str, result_obj: Any) -> bool:
    claim_l = (claim or "").lower()
    for value in _walk_values(result_obj):
        if not isinstance(value, str):
            continue
        direction = value.strip().lower()
        if direction not in DIRECTION_TERMS:
            continue
        expected = direction
        for opposite, terms in DIRECTION_TERMS.items():
            if opposite == expected:
                continue
            if any(term in claim_l for term in terms):
                return True
    # Peer lift: lift < 1 means below peer baseline; > 1 means above.
    for obj in _walk_mappings(result_obj):
        lift = obj.get("lift")
        if isinstance(lift, (int, float)):
            if lift < 1 and any(t in claim_l for t in DIRECTION_TERMS["above"]):
                return True
            if lift > 1 and any(t in claim_l for t in DIRECTION_TERMS["below"]):
                return True
    return False

def _walk_mappings(obj: Any):
    if isinstance(obj, Mapping):
        yield obj
        for v in obj.values():
            yield from _walk_mappings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_mappings(v)

def _entity_tokens(result_obj: Any) -> set[str]:
    tokens = set()
    for value in _walk_values(result_obj):
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            text = str(value).strip()
            if text:
                tokens.add(text.lower())
    return tokens

def _entity_grounded(item: Mapping[str, Any], result_objects: list[dict]) -> bool:
    claim = str(item.get("claim", ""))
    combined = " ".join(str(v) for v in item.values() if isinstance(v, str))
    corpus = " ".join(" ".join(_entity_tokens(r)) for r in result_objects)
    # Explicit firm/entity fields in a claim object must be present in sources.
    for key in ("firm_name", "company_name", "gvkey", "sic", "fyear",
                "feature_year", "fiscal_year", "section", "filing_section"):
        value = item.get(key)
        if value is not None and str(value).strip().lower() not in corpus:
            return False
    # Detect common filing section references in prose.
    for section in ("item 7", "item 9a", "item 15"):
        if section in combined.lower() and section not in corpus:
            return False
    # If claim text contains an explicit year, it must exist in cited result.
    result_years = set()
    for result in result_objects:
        for obj in _walk_mappings(result):
            for key in ("fyear", "feature_year", "fiscal_year", "year"):
                if key in obj and obj[key] is not None:
                    result_years.add(str(obj[key]))
    for token in re.findall(r"\b(?:19|20)\d{2}\b", claim):
        if result_years and token not in result_years:
            return False
    return True

def verify(output: dict, trace: list[dict], *, inplace: bool = True) -> dict:
    """Filter unsupported evidence items and return aggregate verification metrics.

    Output shape is retained. Pass a deep copy when the unmodified agent output
    must be preserved for audit/replay.
    """
    target = output if inplace else copy.deepcopy(output)
    successful = _successful_results(trace)
    report = {"verified_items": 0, "blocked_items": 0, "block_rate": 0.0,
              "issues": [], "reasons": {reason: 0 for reason in REASONS}}
    for section in ("evidence", "contradictory_evidence"):
        kept = []
        for item in target.get(section, []):
            reason = None
            if not isinstance(item, Mapping):
                reason = "missing_or_unknown_ids"
                cited = []
            else:
                refs = item.get("tool_result_ids", [])
                if not isinstance(refs, list) or not refs or any(str(x) not in successful for x in refs):
                    reason = "missing_or_unknown_ids"
                    cited = []
                else:
                    cited = [successful[str(x)] for x in refs]
                    claim = str(item.get("claim", ""))
                    source_numbers = set().union(*(_numeric_values(x) for x in cited))
                    unsupported = []
                    for number in _claim_numbers(claim):
                        forms = _decimal_forms(number)
                        if forms and not forms.intersection(source_numbers):
                            unsupported.append(number)
                    if unsupported:
                        reason = "numeric_claim_unsupported"
                    elif any(_direction_conflict(claim, result) for result in cited):
                        reason = "direction_contradicts_result"
                    elif not _entity_grounded(item, cited):
                        reason = "entity_not_in_results"
            if reason:
                report["blocked_items"] += 1
                report["reasons"][reason] += 1
                report["issues"].append({"section": section, "item": dict(item) if isinstance(item, Mapping) else item,
                                         "reason": reason})
            else:
                kept.append(item)
                report["verified_items"] += 1
        target[section] = kept
    total = report["verified_items"] + report["blocked_items"]
    report["block_rate"] = round(report["blocked_items"] / total, 4) if total else 0.0
    return report

def verify_copy(output: dict, trace: list[dict]) -> tuple[dict, dict]:
    """Return (verified_copy, report), preserving the raw output."""
    checked = copy.deepcopy(output)
    report = verify(checked, trace, inplace=True)
    return checked, report
