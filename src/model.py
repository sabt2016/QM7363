"""Contract adapter for score_firm.

The frozen model in src/scoring.py was written against task 1.6C and returns a
flat dictionary. docs/TOOL_CONTRACT.md requires the three-key envelope and a
different set of value keys. This module is the only place those two shapes
meet, so the drift between them is handled once instead of everywhere.

Conversions performed here:
  risk_rank + cohort_size  ->  percentile          (contract section 3, tool 3)
  artifact prior_opinion_col -> uses_prior_opinion
  nothing                  ->  cohort_base_rate    (computed from the panel)
  full float precision     ->  4dp, percentiles 1dp (contract section 1)
  stripped gvkey           ->  six characters, zeros kept (contract section 1)

Failure behaviour follows contract section 1: value is None, notes says why,
and nothing raises.
"""

from __future__ import annotations

import pickle
from functools import lru_cache

import pandas as pd

import config
from src import scoring

EFFECTIVE = 1
ADVERSE = 2

ARTIFACT_NAME = "financial_only_xgb_v2.pkl"


def _envelope(value, source, notes):
    """Contract section 1: exactly three keys, on every return path."""
    return {"value": value, "source": source, "notes": notes}


@lru_cache(maxsize=1)
def _artifact():
    """Load the frozen model once per process."""
    path = config.MODEL_DIR / ARTIFACT_NAME
    with path.open("rb") as fh:
        return pickle.load(fh)


@lru_cache(maxsize=1)
def _panel():
    """Load the panel once per process. The agent calls score_firm repeatedly."""
    path = config.PANEL_FILE
    dtypes = {"gvkey": "string", "cik": "string", "cusip": "string"}
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=dtypes, parse_dates=["datadate", "INFO_DATE"])
    return pd.read_excel(path, dtype=dtypes, parse_dates=["datadate", "INFO_DATE"])


def _gvkey6(value):
    """Contract section 1: gvkey is six characters with leading zeros kept.

    src/scoring.py strips leading zeros internally, which is fine inside that
    module because it normalises both sides of its comparison. The contract
    form is restored here so nothing downstream ever sees a bare integer.
    """
    text = str(value).strip().split(".")[0]
    return f"{int(text):06d}"


def _cohort_base_rate(panel, outcome_year):
    """Observed adverse rate among assessed firms in the outcome year."""
    cohort = panel.loc[
        panel["fyear"].eq(outcome_year) & panel["auopic"].isin([EFFECTIVE, ADVERSE])
    ]
    if cohort.empty:
        return None
    return round(float(cohort["auopic"].eq(ADVERSE).mean()), 4)


def score_firm(gvkey, fyear):
    """Return the calibrated probability of an adverse opinion in fyear + 1."""
    key = _gvkey6(gvkey)
    year = int(fyear)

    artifact = _artifact()
    panel = _panel()

    uses_prior = artifact.get("prior_opinion_col") is not None
    source = (
        f"model_v2 | xgb_calibrated | "
        f"trained fyear {config.TRAIN_START_YEAR}-{config.TRAIN_END_YEAR} | "
        f"gvkey={key} fyear={year}"
    )
    # Contract section 3: notes must state whether prior-year opinion is used,
    # so the agent never credits the model with information it did not have.
    disclosure = (
        "Model excludes prior-year opinion."
        if not uses_prior
        else "Model includes prior-year opinion."
    )

    keys = panel["gvkey"].map(_gvkey6)

    if not keys.eq(key).any():
        return _envelope(None, source, f"gvkey not in panel. {disclosure}")

    this_year = panel.loc[keys.eq(key) & panel["fyear"].eq(year)]
    if this_year.empty or not this_year["auopic"].isin([EFFECTIVE, ADVERSE]).any():
        return _envelope(None, source, f"not assessed in fyear {year}. {disclosure}")

    next_year = panel.loc[keys.eq(key) & panel["fyear"].eq(year + 1)]
    if next_year.empty or not next_year["auopic"].isin([EFFECTIVE, ADVERSE]).any():
        return _envelope(
            None, source, f"no following year assessed after {year}. {disclosure}"
        )

    try:
        result = scoring.score_firm(key, year, panel, artifact)
    except (ValueError, KeyError) as exc:
        return _envelope(None, source, f"{exc} {disclosure}")

    rank = int(result["risk_rank"])
    size = int(result["cohort_size"])
    percentile = round(100.0 * (1.0 - (rank - 1) / size), 1)

    notes = (
        f"{disclosure} Rank {rank} of {size} assessed firms in FY{year}, "
        f"highest risk first; percentile is derived from that rank. "
        f"cohort_base_rate is the observed adverse rate among assessed firms "
        f"in FY{year + 1}."
    )
    imputed = result.get("missing_features_imputed") or []
    if imputed:
        notes += f" Imputed features: {', '.join(imputed)}."

    return _envelope(
        {
            "probability": round(float(result["probability"]), 4),
            "percentile": percentile,
            "cohort_base_rate": _cohort_base_rate(panel, year + 1),
            "model_version": artifact["model_version"],
            "uses_prior_opinion": uses_prior,
        },
        source,
        notes,
    )
