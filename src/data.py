"""Panel loading for QM 7363.

One rule this module exists to enforce:

    auopic = 0 means the firm was NEVER AUDITED for internal controls.
    Smaller filers are exempt under SOX 404(b). Those rows carry a label that
    means "unknown", not "clean", and they are 48.8% of the panel.

    Treat them as negatives and the base rate halves from 4.70% to 2.41% while
    half the sample is mislabelled. Every result after that is quietly wrong.

Use load_panel(). Do not read the panel file straight into a model.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

import config

# auopic codes
NOT_AUDITED = 0
EFFECTIVE = 1
ADVERSE = 2

# The 18 panel features plus cfsale, which we recover as oibdp / sale.
#
# The name is lower case. Decision of 2026-10-19: the frozen scoring module and
# the notebook that produced it both use `cfsale`, and two spellings of one
# feature raise a KeyError at whichever boundary they meet. This module kept the
# capitalised spelling until 2026-11-16, which meant src/tools.py rejected the
# agreed name with "unknown variable" and accepted only the wrong one.
FEATURES = [
    "LNEMP", "LNTA", "LNSALE", "LNTI", "IntanTA", "InvCA", "CapInt", "TobinQ",
    "RET1Y", "ROA", "ROE", "GPM", "CURR_RATIO", "AT_TURN", "INV_TURN", "DPR",
    "PTB", "PE", "cfsale",
]

# Winsorized copies exist for the original 18. cfsale has none because we build it.
FEATURES_W = [f + "_W" for f in FEATURES if f != "cfsale"] + ["cfsale"]

ID_COLS = ["gvkey", "conm", "fyear", "datadate", "INFO_DATE", "SIC", "FIN"]


def _read_raw() -> pd.DataFrame:
    """Read the panel, caching it because the first read is slow.

    Reads by file extension. The panel was an .xlsx when this module was
    written and became a .csv on 2026-10-19, but the read_excel call survived
    the change. Nothing caught it, because anyone who had read the panel once
    had a cache and never reached this line again. The real tool layer landed
    on top of it on 2026-11-16 and every one of the eight functions raised
    "Excel file format cannot be determined" on a clean machine.

    Identifier columns are forced to text. config.PANEL_FILE's own comment
    warns about this: read them as numbers and pandas strips the leading zeros
    from gvkey, cik and cusip, after which the six-character gvkey comparisons
    in src/tools.py match nothing and report it as "gvkey not in panel".

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

    dtypes = {"gvkey": "string", "cik": "string",
              "cusip": "string", "tic": "string"}
    dates = ["datadate", "INFO_DATE"]

    if config.PANEL_FILE.suffix.lower() == ".csv":
        df = pd.read_csv(config.PANEL_FILE, dtype=dtypes, parse_dates=dates)
    else:
        df = pd.read_excel(config.PANEL_FILE, dtype=dtypes, parse_dates=dates)

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
        Compute cfsale = oibdp / sale, the fifth GA-TAN variable, which is not
        in the panel as a column but is recoverable from the raw inputs.

    Returns
    -------
    DataFrame with a boolean/int column `y`: 1 = adverse opinion, 0 = effective.
    """
    df = _read_raw()

    if add_cfsale:
        df["cfsale"] = np.where(df["sale"] > 0, df["oibdp"] / df["sale"], np.nan)

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
