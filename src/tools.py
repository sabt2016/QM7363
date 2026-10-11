"""Nine agent tools for the QM 7363 capstone.

These are initial stubs that follow the agreed Tool Contract.
Real data/model implementations will replace the stubs later.
"""

from __future__ import annotations


def _result(value, source="stub", notes="Stub implementation"):
    """Return the shared three-key tool envelope."""
    return {
        "value": value,
        "source": source,
        "notes": notes,
    }


def get_firm_history(gvkey, through_fyear=None):
    """Return a firm's historical firm-year records."""
    return _result(
        [
            {
                "fyear": 2018,
                "auopic": 1,
                "auop": None,
                "SIC": 7372,
                "LNEMP": 5.0,
                "LNTA": 10.0,
                "LNSALE": 10.5,
                "LNTI": 8.0,
                "IntanTA": 0.1,
                "InvCA": 0.2,
                "CapInt": 0.3,
                "TobinQ": 1.2,
                "RET1Y": 0.05,
                "ROA": 0.04,
                "ROE": 0.08,
                "GPM": 0.30,
                "CURR_RATIO": 1.5,
                "AT_TURN": 1.1,
                "INV_TURN": 4.0,
                "DPR": 0.2,
                "PTB": 2.0,
                "PE": 18.0,
                "CFsale": 0.10,
            }
        ],
        source="stub | final_panel",
        notes="Stub implementation; returns invented firm history.",
    )


def get_control_history(gvkey):
    """Return the firm's internal-control history."""
    return _result(
        {
            "adverse_years": [],
            "effective_years": [2018],
            "not_assessed_years": [],
            "current_status": "effective",
            "prior_year_status": "unknown",
        },
        source="stub | final_panel",
        notes=(
            "Stub implementation. not_assessed_years would represent years "
            "with no auditor attestation, not clean controls."
        ),
    )


def score_firm(gvkey, fyear):
    """Return the model's calibrated adverse-opinion risk score."""
    return _result(
        {
            "probability": 0.1187,
            "percentile": 94.9,
            "cohort_base_rate": 0.0404,
            "model_version": "financial_only_rf_v1",
            "uses_prior_opinion": False,
        },
        source="stub | model_v1 | rf_calibrated",
        notes=(
            "Stub implementation. Model excludes prior-year opinion."
        ),
    )


def get_percentile(gvkey, fyear, variable):
    """Return the firm's percentile for a feature in a fiscal year."""
    return _result(
        75.0,
        source=f"stub | final_panel | gvkey={gvkey} | fyear={fyear} | col={variable}",
        notes="Stub implementation; raw value and comparison count are invented.",
    )


def get_deviation(gvkey, fyear, variable):
    """Return the firm's deviation from its own historical baseline."""
    return _result(
        {
            "current": -0.0839,
            "own_median": -0.0667,
            "difference": -0.0172,
            "years_used": 7,
            "direction": "below",
        },
        source=f"stub | final_panel | gvkey={gvkey} | fyear={fyear} | col={variable}",
        notes="Stub implementation; invented historical baseline.",
    )


def get_peer_cohort(gvkey, fyear, k=200):
    """Return nearest peers and their observed adverse rate."""
    return _result(
        {
            "k": k,
            "matched_on": [
                "LNTA",
                "ROA",
                "CapInt",
                "GPM",
                "AT_TURN",
                "CURR_RATIO",
                "IntanTA",
                "TobinQ",
            ],
            "peer_adverse_rate": 0.1150,
            "cohort_base_rate": 0.0429,
            "lift": 2.68,
            "peers_resolved": k,
        },
        source=f"stub | final_panel | gvkey={gvkey} | fyear={fyear}",
        notes=(
            "Stub implementation. If lift is below 1.0 in the real "
            "implementation, the safer peer group must be reported."
        ),
    )


def get_cohort_rate(slice_name, fyear=None):
    """Return the observed adverse rate for a named cohort."""
    return _result(
        {
            "slice": slice_name,
            "adverse_rate": 0.0399,
            "n": 4273,
            "fyear": fyear,
        },
        source="stub | final_panel",
        notes="Stub implementation; invented cohort rate.",
    )


def get_industry_context(gvkey, fyear):
    """Return industry context and within-industry comparisons."""
    return _result(
        {
            "sic": 7372,
            "sic2": 73,
            "industry_label": "Business Services",
            "industry_rate": 0.0648,
            "n_firms": 4216,
            "within_industry_percentiles": {
                "ROA": 14.2,
                "CURR_RATIO": 9.8,
                "LNTA": 31.0,
            },
        },
        source=f"stub | final_panel | gvkey={gvkey} | fyear={fyear}",
        notes=(
            "Stub implementation. Real implementation must carry "
            "SIC_SOURCE when SIC is filled from a neighboring year."
        ),
    )


def get_filing_excerpt(gvkey, fyear, section):
    """Return an SEC filing excerpt.

    This tool is gated and will be implemented after the filing-coverage
    gate is cleared.
    """
    return _result(
        None,
        source="stub | edgar",
        notes="Filing excerpt tool is gated pending the filing-coverage gate.",
    )
