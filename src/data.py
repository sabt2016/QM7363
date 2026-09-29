"""Panel loading for QM 7363.

One rule this module exists to enforce:

    auopic = 0 means the firm was NEVER AUDITED for internal controls.
    Smaller filers are exempt under SOX 404(b). Those rows carry a label that
    means "unknown", not "clean", and they are 48.8% of the panel.

    Treat them as negatives and the base rate halves from 4.70% to 2.41% while
    half the sample is mislabelled. Every result after that is quietly wrong.

Use load_panel(). Do not read the Excel file straight into a model.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

import config

# auopic codes
NOT_AUDITED = 0
EFFECTIVE = 1
ADVERSE = 2

# The 18 panel features plus CFsale, which we recover as oibdp / sale.
FEATURES = [
    "LNEMP", "LNTA", "LNSALE", "LNTI", "IntanTA", "InvCA", "CapInt", "TobinQ",
    "RET1Y", "ROA", "ROE", "GPM", "CURR_RATIO", "AT_TURN", "INV_TURN", "DPR",
    "PTB", "PE", "CFsale",
]

# Winsorized copies exist for the original 18. CFsale has none because we build it.
FEATURES_W = [f + "_W" for f in FEATURES if f != "CFsale"] + ["CFsale"]

ID_COLS = ["gvkey", "conm", "fyear", "datadate", "INFO_DATE", "SIC", "FIN"]


def _read_raw() -> pd.DataFrame:
    """Read the panel, caching it because the Excel read takes about 40 seconds.

    Caches to parquet when pyarrow is available, otherwise to pickle. The cache
    is a local convenience and is gitignored; delete it if the panel is updated.
    """
    cache = config.CACHE_FILE
    pickle_cache = cache.with_suffix(".pkl")

    if cache.exists():
        try:
            return pd.read_parquet(cache)
        except ImportError:
            pass
    if pickle_cache.exists():
        return pd.read_pickle(pickle_cache)

    df = pd.read_excel(config.PANEL_FILE, dtype={"gvkey": str, "cusip": str})
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(cache, index=False)
    except ImportError:
        df.to_pickle(pickle_cache)
    return df


def load_panel(audited_only: bool = True, add_cfsale: bool = True) -> pd.DataFrame:
    """Load the firm-year panel.

    Parameters
    ----------
    audited_only
        Keep only auopic 1 and 2. Leave this True unless you have a specific
        reason and a decision log entry. See the module docstring.
    add_cfsale
        Compute CFsale = oibdp / sale, the fifth GA-TAN variable, which is not
        in the panel as a column but is recoverable from the raw inputs.

    Returns
    -------
    DataFrame with a boolean/int column `y`: 1 = adverse opinion, 0 = effective.
    """
    df = _read_raw()

    if add_cfsale:
        df["CFsale"] = np.where(df["sale"] > 0, df["oibdp"] / df["sale"], np.nan)

    if audited_only:
        df = df[df["auopic"].isin([EFFECTIVE, ADVERSE])].copy()
        df["y"] = (df["auopic"] == ADVERSE).astype(int)
    else:
        df["y"] = np.where(df["auopic"] == ADVERSE, 1,
                           np.where(df["auopic"] == EFFECTIVE, 0, np.nan))

    return df.sort_values(["gvkey", "fyear"]).reset_index(drop=True)


def temporal_split(df: pd.DataFrame):
    """Split by fiscal year using the boundaries in config.

    Never split randomly. A random split lets the model learn from the future,
    and every reported number becomes optimistic for a reason a reader will
    find in five minutes.
    """
    train = df[df["fyear"] <= config.TRAIN_END_YEAR]
    test = df[df["fyear"] >= config.TEST_START_YEAR]
    return train, test


def add_prior_opinion(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the firm's previous fiscal year opinion as `prior_adverse`.

    This is the single strongest predictor we have found: it moves ROC from
    .751 to .826. Report results with AND without it, because a reader needs to
    know how much of the model is financial signal and how much is persistence.
    """
    out = df.copy()
    g = out.groupby("gvkey")
    out["prev_fyear"] = g["fyear"].shift(1)
    out["prior_adverse"] = g["y"].shift(1)
    # only valid when the previous row is the directly preceding fiscal year
    out.loc[out["prev_fyear"] != out["fyear"] - 1, "prior_adverse"] = np.nan
    return out


def label_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Counts by fiscal year. Put this in the report's data section."""
    t = df.groupby("fyear").agg(rows=("y", "size"), adverse=("y", "sum"))
    t["rate_pct"] = (100 * t["adverse"] / t["rows"]).round(2)
    return t
