"""Smoke tests. Run `python -m pytest tests/ -v` after setup.

If test_panel_loads fails, DATA_DIR in config.py is wrong.
"""
import pytest
from src import data


@pytest.fixture(scope="module")
def panel():
    return data.load_panel()


def test_panel_loads(panel):
    assert len(panel) > 0, "panel is empty -- check DATA_DIR in config.py"


def test_audited_sample_size(panel):
    # 42,728 audited firm-years as of the September 2026 panel
    assert 42_000 < len(panel) < 43_500


def test_code_zero_excluded(panel):
    assert (panel["auopic"] == 0).sum() == 0, "auopic code 0 leaked into the sample"


def test_base_rate(panel):
    rate = panel["y"].mean()
    assert 0.045 < rate < 0.049, f"base rate {rate:.4f}, expected about .047"


def test_cfsale_recovered(panel):
    # Lower case. Decision of 2026-10-19, applied to this module 2026-11-16.
    assert "cfsale" in panel.columns
    assert panel["cfsale"].notna().mean() > 0.85


def test_identifiers_keep_their_leading_zeros(panel):
    """gvkey and cik are text, not numbers.

    Read as numbers, pandas drops the leading zeros, and every six-character
    gvkey comparison in src/tools.py then matches nothing while reporting it
    as "gvkey not in panel".
    """
    assert panel["gvkey"].astype(str).str.fullmatch(r"\d{6}").all()
    assert panel["cik"].astype(str).str.fullmatch(r"\d{10}").any()


def test_no_random_split():
    train, test = data.temporal_split(data.load_panel())
    assert train["fyear"].max() < test["fyear"].min(), "train and test years overlap"


def test_prior_opinion_is_lagged(panel):
    out = data.add_prior_opinion(panel)
    linked = out[out["prior_adverse"].notna()]
    assert (linked["prev_fyear"] == linked["fyear"] - 1).all()
