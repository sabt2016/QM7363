# Scoring for the frozen v3 models (owner: Jessica Bedson).
#
# The model is loaded from the PORTABLE artifact, not from the pickle:
#
#     models/<model_version>.portable.json   plain data: feature order, imputer fill values,
#                                            missing-indicator columns, calibrator coefficient
#                                            and intercept, metadata
#     models/<model_version>.booster.json    the XGBoost booster, written by Booster.save_model
#
# This module needs only numpy, pandas and xgboost. It never imports scikit-learn and never
# unpickles anything, so it does not depend on the library versions the model was built under.
# XGBoost's JSON model format is documented and loads in later XGBoost versions.
#
# The original pickles (models/<model_version>.pkl) are kept unchanged as the record of what
# was frozen. "Portable Artifact Export v3.ipynb" shows the two produce the same probabilities.
#
# Usage (from the adapter in src/model.py):
#
#     artifact = load_artifact("models/financial_only_xgb_v3.portable.json")
#     result = score_firm_core(gvkey, feature_year, panel, artifact)

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

PORTABLE_FORMAT = "portable-model-v1"

FEATURE_COLS = [
    "LNEMP", "LNTA", "LNSALE", "LNTI", "IntanTA", "InvCA", "CapInt",
    "TobinQ", "RET1Y", "ROA", "ROE", "GPM", "CURR_RATIO", "AT_TURN",
    "INV_TURN", "DPR", "PTB", "PE", "cfsale",
]


# ---------------------------------------------------------------------------
# Loading and prediction from the portable artifact
# ---------------------------------------------------------------------------

def load_artifact(path):
    # Load a portable artifact (.portable.json plus the file it names for the classifier).
    path = Path(path)
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("format") != PORTABLE_FORMAT:
        raise ValueError(f"{path.name} is not a {PORTABLE_FORMAT} artifact.")
    artifact = dict(spec)
    clf = spec["classifier"]
    if clf["type"] == "xgboost":
        booster = xgb.Booster()
        booster.load_model(str(path.parent / clf["booster_file"]))
        artifact["_booster"] = booster
    elif clf["type"] != "logistic":
        raise ValueError(f"Unsupported classifier type {clf['type']!r}.")
    return artifact


def transform(artifact, frame):
    # Reproduce the fitted preprocessing: median imputation, missing indicators, optional scaling.
    imp = artifact["imputer"]
    values = frame[imp["input_columns"]].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
    missing = np.isnan(values)
    fill = np.array([np.nan if v is None else v for v in imp["fill_values"]], dtype=float)
    imputed = np.where(missing, fill, values)[:, imp["kept_columns"]]
    indicators = missing[:, imp["indicator_columns"]].astype(float)
    out = np.hstack([imputed, indicators])
    scaler = artifact.get("scaler")
    if scaler is not None:
        out = (out - np.array(scaler["mean"])) / np.array(scaler["scale"])
    return out


def predict_raw(artifact, frame):
    # Uncalibrated probability of an adverse opinion in t+1, as float64.
    X = transform(artifact, frame)
    clf = artifact["classifier"]
    if clf["type"] == "xgboost":
        raw = artifact["_booster"].predict(xgb.DMatrix(X, missing=np.nan))
    else:
        z = X @ np.array(clf["coef"]) + clf["intercept"]
        raw = 1.0 / (1.0 + np.exp(-z))
    return np.asarray(raw, dtype=float)


def calibrate(artifact, raw):
    # Apply the validation-fitted calibrator: logistic regression on the clipped log-odds.
    settings = artifact["calibration_transform"]
    p = np.clip(np.asarray(raw, dtype=float), settings["clip_min"], settings["clip_max"])
    z = artifact["calibrator"]["coef"] * np.log(p / (1 - p)) + artifact["calibrator"]["intercept"]
    return 1.0 / (1.0 + np.exp(-z))


# ---------------------------------------------------------------------------
# Scoring one firm-year
# ---------------------------------------------------------------------------

def _normalize_gvkey(value):
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.lstrip("0") or "0"


def _prepare(frame):
    out = frame.copy()
    sales = pd.to_numeric(out["sale"], errors="raise")
    income = pd.to_numeric(out["oibdp"], errors="raise")
    out["cfsale"] = income / sales.replace(0, np.nan)
    out[FEATURE_COLS] = (
        out[FEATURE_COLS].apply(pd.to_numeric, errors="raise")
        .replace([np.inf, -np.inf], np.nan)
    )
    return out


def score_firm_core(gvkey, feature_year, panel, artifact):
    # Score one firm-year with a frozen model loaded by load_artifact().
    # Called only by the adapter in src/model.py, which owns the tool contract and the alias.
    # Forecast: adverse internal-control opinion (auopic = 2) in fiscal year t+1.
    # Rank: descending risk among assessed firms in feature year t (1 = highest risk).
    # Uses only data from feature year t.
    year = int(feature_year)
    cols = list(artifact["feature_cols"])
    prior_col = artifact.get("prior_opinion_col")

    cohort = panel.loc[panel["fyear"].eq(year) & panel["auopic"].isin([1, 2])].copy()
    if cohort.empty:
        raise ValueError(f"No assessed firms available for FY{year}.")
    if cohort["gvkey"].isna().any():
        raise ValueError("Missing firm identifiers in the cohort.")

    cohort["_key"] = cohort["gvkey"].map(_normalize_gvkey)
    if cohort["_key"].duplicated().any():
        raise ValueError("Duplicate firm-year identifiers.")
    selected = cohort["_key"].eq(_normalize_gvkey(gvkey))
    if selected.sum() != 1:
        raise ValueError(
            f"Expected one assessed record for this firm in FY{year}; found {int(selected.sum())}."
        )

    cohort = _prepare(cohort)
    if prior_col:
        cohort[prior_col] = (cohort["auopic"] == 2).astype(int)
    features = cohort[cols].apply(pd.to_numeric, errors="raise")

    raw = predict_raw(artifact, features)
    calibrated = calibrate(artifact, raw)

    version = artifact["default_probability"]
    if version not in {"original", "calibrated"}:
        raise ValueError("Unknown default probability version.")
    probability = calibrated if version == "calibrated" else raw

    ranks = pd.Series(probability).rank(ascending=False, method="min").astype(int).to_numpy()
    position = int(np.flatnonzero(selected.to_numpy())[0])
    row = cohort.iloc[position]

    return {
        "gvkey": str(row["gvkey"]),
        "feature_year": year,
        "outcome_year": year + 1,
        "prediction_date": pd.Timestamp(row["INFO_DATE"]).isoformat(),
        "model_version": artifact["model_version"],
        "probability": float(probability[position]),
        "probability_version": version,
        "probability_original": float(raw[position]),
        "probability_calibrated": float(calibrated[position]),
        "risk_rank": int(ranks[position]),
        "cohort_size": int(len(cohort)),
        "rank_definition": "Descending risk among assessed firms in the feature year; 1 is highest; ties use minimum rank.",
        "missing_features_imputed": features.columns[features.iloc[position].isna()].tolist(),
        "interpretation": "Retrospective score from the frozen model. The year-wide rank is not an as-of-date live ranking. A risk score is not proof of a future adverse opinion.",
    }
