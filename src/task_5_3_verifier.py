"""Task 5.3: claim verification against the exact tool results in an agent trace.

Owner: Enock Banda. Written for docs/VERIFIER_SPEC.md sections 3.1 to 3.3.

This verifier is intentionally conservative. It verifies linkage, numeric
support, direction language, and entity/year/filing-section grounding. It does
not claim to prove the semantic truth of arbitrary prose.

Amendments of 2026-11-10, after adversarial probing against the live offline
pipeline. Each one is a defect that let a bad claim through or blocked a good
one. See docs/DECISION_LOG.md entries 26 to 29.

  1. Digits inside document and statutory labels are no longer read as
     quantities. "The 10-K was filed" produced the number 10, "Item 9A"
     produced 9, and "SOX 404(b)" produced 404. None matched a tool value, so
     every claim naming a filing was blocked as numeric_claim_unsupported.
     That would have broken the filings tools (5.5, 5.6) before they landed
     and put the wrong reason code on the block, which matters because the
     reason breakdown is a reported result.

  2. Four-digit years are grounded by the entity layer, not the numeric layer.
     A claim saying "Features are drawn from 2018" was blocked, because 2018
     is not among the values score_firm returns. Years are now checked
     against the years the cited tools actually returned OR were called with,
     which is the correct test and is fail-closed: a year with no grounding
     blocks.

  3. Entity grounding now reads the claim prose. It previously checked only
     structured keys on the claim object, so "Enron shows elevated risk"
     passed. Section 3.3 of the spec calls prose entity import the most
     dangerous failure mode in a tool like this, because the model can supply
     a company it knows from training rather than from our data.

  4. Numbers and names are checked in the interpretation text as well as the
     claim text. The interpretation is displayed to the reader, so an
     unsupported figure there reaches them exactly as one in the claim does.
     Spec section 3.1 said "claim's text" and is amended to match.

  5. Direction terms match on word boundaries. Substring matching made
     "undergo" collide with "under".
"""
from __future__ import annotations

import copy
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

REASONS = (
    "missing_or_unknown_ids",
    "numeric_claim_unsupported",
    "direction_contradicts_result",
    "entity_not_in_results",
)

NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")

# A bare four-digit year is an entity fact, not a quantity. Amendment 2.
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
YEAR_IN_TEXT_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")

# Digits that belong to the name of a document or a statute, not to a
# measurement. Masked out before numbers are extracted. Amendment 1.
#
# SIC codes are deliberately absent: a tool returns the SIC code as a value,
# so "SIC 7372" should be checked against it rather than excused.
DOCUMENT_LABEL_RE = re.compile(
    r"""
      \b\d{1,2}\s*-\s*[KQ]\b                      # 10-K, 10-Q, 8-K
    | \bitems?\s+\d+[A-Za-z]?\b                   # Item 7, Item 9A
    | \bsections?\s+\d+[A-Za-z]?(?:\([a-z0-9]+\))?\b
    | \b404\s*\([a-z]\)                           # 404(b)
    | \bsox\s+404\b
    | \bparts?\s+[ivxlc]+\b                       # Part II
    """,
    re.IGNORECASE | re.VERBOSE,
)

DIRECTION_TERMS = {
    "above": ("above", "higher than", "greater than", "exceeds", "increased", "higher"),
    "below": ("below", "lower than", "less than", "decreased", "lower"),
    "unchanged": ("unchanged", "no change", "stable", "the same"),
}

FILING_SECTIONS = ("item 7", "item 7a", "item 9a", "item 15")

ENTITY_FIELDS = (
    "firm_name", "company_name", "entity_name", "gvkey", "sic",
    "fyear", "feature_year", "fiscal_year", "section", "filing_section",
)

YEAR_KEYS = ("fyear", "feature_year", "fiscal_year", "year",
             "outcome_year", "through_fyear")

# Amendment 3. A capitalised word in a claim must either be in this vocabulary
# or appear in the tool results the claim cites. Anything else is treated as a
# named entity the model supplied from somewhere other than our data.
#
# This list is expected to grow as live runs expose legitimate wording. That
# is the approach section 3.4 of the spec already proposed for qualitative
# language: a small allowed vocabulary, and block the rest. Widen it from
# observed false positives, never by guessing.
ALLOWED_PROSE_TERMS = frozenset("""
a an and as at but by for from in into is are was were be been being it its
no not of on or that the their then there these this to with than against
between over under above below both all any each per if when while after
before during because however although though which who whose what where
based comparable compared considering current despite evidence every given
model neither none nothing overall relative taken using within without
across among one two three four five six seven eight nine ten nineteen
high higher highest low lower lowest moderate elevated strong weak
icfr sox sec edgar compustat gaap pcaob auditor auditors audited unaudited
opinion opinions adverse effective ineffective remediation weakness
weaknesses material immaterial filing filings filed item items section
sections part form forms firm firms peer peers cohort cohorts industry
industries percentile percentiles probability probabilities rank ranks
ranking lift baseline median mean average rate rates year years fiscal
control controls internal financial statement statements disclosure
disclosures attestation assessment assessed estimate estimates feature
features data record records history status risk threshold calibrated
uncertainty confidence stub stubs panel
lnemp lnta lnsale lnti intanta invca capint tobinq ret1y roa roe gpm
curr_ratio at_turn inv_turn dpr ptb pe cfsale auopic auop sic sic2 gvkey
cik cusip tic firm_a
""".split())

PROPER_TOKEN_RE = re.compile(r"\b[A-Z][A-Za-z0-9&._'\-]*\b")


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


def _walk_mappings(obj: Any):
    if isinstance(obj, Mapping):
        yield obj
        for v in obj.values():
            yield from _walk_mappings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_mappings(v)


def _successful_calls(trace: list[dict]) -> dict[str, dict]:
    """Map result_id to the whole successful tool-call event.

    The arguments matter, not only the return. A claim may name the fiscal
    year the agent asked about, and the tool is not obliged to echo it back.
    """
    calls = {}
    for event in trace:
        if event.get("event") != "tool_call" or event.get("status") != "ok":
            continue
        result = event.get("result") or {}
        rid = result.get("result_id")
        if rid:
            calls[str(rid)] = event
    return calls


def _successful_results(trace: list[dict]) -> dict[str, dict]:
    """Kept for callers that only need the returns."""
    return {rid: (event.get("result") or {})
            for rid, event in _successful_calls(trace).items()}


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


def _scrub_labels(text: str) -> str:
    """Remove document and statutory labels before reading numbers."""
    return DOCUMENT_LABEL_RE.sub(" ", text or "")


def _claim_numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(_scrub_labels(text))


def _claim_text(item: Mapping[str, Any]) -> str:
    """Everything in the item that a reader will see. Amendment 4."""
    parts = [str(item.get("claim") or ""), str(item.get("interpretation") or "")]
    return " ".join(p for p in parts if p)


def _mentions(text: str, term: str) -> bool:
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def _direction_conflict(claim: str, result_obj: Any) -> bool:
    claim_l = (claim or "").lower()
    for value in _walk_values(result_obj):
        if not isinstance(value, str):
            continue
        direction = value.strip().lower()
        if direction not in DIRECTION_TERMS:
            continue
        for opposite, terms in DIRECTION_TERMS.items():
            if opposite == direction:
                continue
            if any(_mentions(claim_l, term) for term in terms):
                return True
    # Peer lift: lift < 1 means below peer baseline; > 1 means above.
    for obj in _walk_mappings(result_obj):
        lift = obj.get("lift")
        if isinstance(lift, (int, float)) and not isinstance(lift, bool):
            if lift < 1 and any(_mentions(claim_l, t) for t in DIRECTION_TERMS["above"]):
                return True
            if lift > 1 and any(_mentions(claim_l, t) for t in DIRECTION_TERMS["below"]):
                return True
    return False


def _corpus(events: list[dict]) -> tuple[str, set[str]]:
    """Return (phrase corpus, word corpus) built from cited calls.

    The phrase corpus keeps whole values intact so a multi-word reference such
    as "Item 9A" can be matched. The word corpus is split so a single name can
    be looked up on its own.
    """
    phrases = []
    words: set[str] = set()
    for event in events:
        for obj in (event.get("result") or {}, event.get("arguments") or {}):
            for value in _walk_values(obj):
                if isinstance(value, bool) or value is None:
                    continue
                if isinstance(value, (str, int, float)):
                    text = str(value).strip().lower()
                    if not text:
                        continue
                    phrases.append(text)
                    for word in re.split(r"[^a-z0-9_]+", text):
                        if word:
                            words.add(word)
    return " | ".join(phrases), words


def _grounded_years(events: list[dict]) -> set[str]:
    """Every year the cited calls returned or were called with."""
    years: set[str] = set()
    for event in events:
        for obj in (event.get("result") or {}, event.get("arguments") or {}):
            for mapping in _walk_mappings(obj):
                for key in YEAR_KEYS:
                    value = mapping.get(key)
                    if value is not None and not isinstance(value, bool):
                        years.update(YEAR_IN_TEXT_RE.findall(str(value)))
            for value in _walk_values(obj):
                if isinstance(value, bool):
                    continue
                if isinstance(value, int) and 1900 <= value <= 2099:
                    years.add(str(value))
                elif isinstance(value, str):
                    years.update(YEAR_IN_TEXT_RE.findall(value))
    return years


def _ungrounded_entities(item: Mapping[str, Any], events: list[dict]) -> list[str]:
    """Names, years and filing sections in the item that no cited call produced.

    Returns the offending tokens so the report can show a reader exactly what
    failed, which is what section 5 of the spec asks for in a worked example.
    """
    offenders: list[str] = []
    text = _claim_text(item)
    lowered = text.lower()
    phrases, words = _corpus(events)

    # Explicit entity fields on the claim object must appear in the sources.
    for key in ENTITY_FIELDS:
        value = item.get(key)
        if value is None:
            continue
        token = str(value).strip().lower()
        if token and token not in phrases and token not in words:
            offenders.append(f"{key}={value}")

    # Filing sections named in prose must have been returned by a cited tool.
    for section in FILING_SECTIONS:
        if section in lowered and section not in phrases:
            offenders.append(section)

    # A year in the prose must be a year a cited call returned or asked about.
    # Fail-closed: no grounded years at all means no year may be named.
    grounded = _grounded_years(events)
    for token in YEAR_IN_TEXT_RE.findall(text):
        if token not in grounded:
            offenders.append(token)

    # A capitalised word must be allowed vocabulary or present in the sources.
    for token in PROPER_TOKEN_RE.findall(text):
        key = token.strip("._'-").lower()
        if not key or key in ALLOWED_PROSE_TERMS or key in words or key in phrases:
            continue
        offenders.append(token)

    # Preserve order, drop duplicates.
    seen = set()
    unique = []
    for token in offenders:
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def verify(output: dict, trace: list[dict], *, inplace: bool = True) -> dict:
    """Filter unsupported evidence items and return aggregate verification metrics.

    Output shape is retained. Pass a deep copy when the unmodified agent output
    must be preserved for audit/replay, or call verify_copy.
    """
    target = output if inplace else copy.deepcopy(output)
    calls = _successful_calls(trace)
    report = {"verified_items": 0, "blocked_items": 0, "block_rate": 0.0,
              "issues": [], "reasons": {reason: 0 for reason in REASONS}}

    for section in ("evidence", "contradictory_evidence"):
        kept = []
        for item in target.get(section, []):
            reason = None
            detail: list[str] = []

            if not isinstance(item, Mapping):
                reason = "missing_or_unknown_ids"
            else:
                refs = item.get("tool_result_ids", [])
                if (not isinstance(refs, list) or not refs
                        or any(str(x) not in calls for x in refs)):
                    reason = "missing_or_unknown_ids"
                    if isinstance(refs, list):
                        detail = [str(x) for x in refs if str(x) not in calls]
                else:
                    cited = [calls[str(x)] for x in refs]
                    results = [event.get("result") or {} for event in cited]
                    text = _claim_text(item)

                    source_numbers = set().union(*(_numeric_values(r) for r in results))
                    unsupported = []
                    for number in _claim_numbers(text):
                        forms = _decimal_forms(number)
                        if not forms or forms & source_numbers:
                            continue
                        if YEAR_RE.match(number):
                            # Years are grounded below, not here. Amendment 2.
                            continue
                        unsupported.append(number)

                    if unsupported:
                        reason = "numeric_claim_unsupported"
                        detail = unsupported
                    elif any(_direction_conflict(text, r) for r in results):
                        reason = "direction_contradicts_result"
                    else:
                        offenders = _ungrounded_entities(item, cited)
                        if offenders:
                            reason = "entity_not_in_results"
                            detail = offenders

            if reason:
                report["blocked_items"] += 1
                report["reasons"][reason] += 1
                issue = {
                    "section": section,
                    "item": dict(item) if isinstance(item, Mapping) else item,
                    "reason": reason,
                }
                if detail:
                    issue["detail"] = detail
                report["issues"].append(issue)
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
