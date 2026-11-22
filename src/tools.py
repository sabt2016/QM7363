"""Data-backed agent tools implementing the QM 7363 capstone Tool Contract."""

from __future__ import annotations


def _result(value, source="unspecified", notes=""):
    """Return the shared three-key tool envelope."""
    return {
        "value": value,
        "source": source,
        "notes": notes,
    }


def get_firm_history(gvkey, through_fyear):
    """Return actual firm-year records, oldest first, through the cutoff."""
    import pandas as pd
    from src.data import load_panel, FEATURES

    key = str(gvkey).zfill(6)
    cutoff = int(through_fyear)
    df = load_panel(audited_only=False)
    firm = df[df["gvkey"].astype(str).str.zfill(6) == key].copy()

    if firm.empty:
        return _result(None, source="final_panel | gvkey=" + key,
                       notes="gvkey not in panel")

    firm = firm[firm["fyear"] <= cutoff].sort_values("fyear")
    columns = ["fyear", "auopic", "auop", "SIC"] + FEATURES
    records = []
    for row in firm[columns].to_dict(orient="records"):
        record = {}
        for col, value in row.items():
            if pd.isna(value):
                record[col] = None
            elif hasattr(value, "item"):
                record[col] = value.item()
            else:
                record[col] = value
        records.append(record)

    years = [int(record["fyear"]) for record in records]
    missing = sorted(set(range(min(years), max(years) + 1)) - set(years)) if years else []
    gap_note = "missing fiscal years: " + ", ".join(map(str, missing)) if missing else "no missing fiscal years within observed range"
    notes = f"{len(records)} firm-year records through FY{cutoff}; {gap_note}."
    source = f"final_panel | gvkey={key} | fyear<={cutoff} | {len(records)} rows"
    return _result(
        {
            "records": records,
            "n_records": len(records),
            "missing_years": missing,
        },
        source=source,
        notes=notes,
    )

def get_control_history(gvkey, through_fyear):
    """Return actual internal-control history through the requested year."""

    from src.data import load_panel

    # Preserve the six-character GVKEY format.
    gvkey = str(gvkey).zfill(6)
    through_fyear = int(through_fyear)

    # Include unaudited records because auopic=0 means not assessed.
    df = load_panel(audited_only=False)

    # Find the requested company.
    firm = df[df["gvkey"].astype(str).str.zfill(6) == gvkey].copy()

    if firm.empty:
        return _result(
            None,
            source=f"final_panel | gvkey={gvkey}",
            notes="gvkey not in panel",
        )

    # Keep only information available through the requested fiscal year.
    firm = firm[firm["fyear"] <= through_fyear].copy()
    firm = firm.sort_values("fyear")

    # Classify only the three codes defined in the contract.
    adverse_years = sorted(
        firm.loc[firm["auopic"] == 2, "fyear"].astype(int).tolist()
    )

    effective_years = sorted(
        firm.loc[firm["auopic"] == 1, "fyear"].astype(int).tolist()
    )

    not_assessed_years = sorted(
        firm.loc[firm["auopic"] == 0, "fyear"].astype(int).tolist()
    )

    def get_status(year):
        record = firm[firm["fyear"] == year]

        if record.empty:
            return "unknown"

        code = record.iloc[-1]["auopic"]

        if code == 0:
            return "not_assessed"
        elif code == 1:
            return "effective"
        elif code == 2:
            return "adverse"

        return "unknown"

    value = {
        "adverse_years": adverse_years,
        "effective_years": effective_years,
        "not_assessed_years": not_assessed_years,
        "current_status": get_status(through_fyear),
        "prior_year_status": get_status(through_fyear - 1),
    }

    return _result(
        value,
        source=(
            f"final_panel | gvkey={gvkey} | "
            f"fyear<={through_fyear} | {len(firm)} rows"
        ),
        notes=(
            "not_assessed_years are years with no auditor attestation, "
            "not years with clean controls. "
            f"Record capped at fiscal year {through_fyear}."
        ),
    )



def score_firm(gvkey, fyear):
    """Return the model's calibrated adverse-opinion risk score."""
    from src.model import score_firm as model_score_firm
    return model_score_firm(gvkey, fyear)

def get_percentile(gvkey, fyear, variable):
    """Return a firm's percentile among all firms in the same fiscal year."""

    from src.data import load_panel, FEATURES

    gvkey = str(gvkey).zfill(6)
    fyear = int(fyear)

    # Validate the requested feature.
    if variable not in FEATURES:
        return _result(
            None,
            source=f"final_panel | gvkey={gvkey} | fyear={fyear} | col={variable}",
            notes="unknown variable",
        )

    # Compare assessed firms only: effective (1) or adverse (2).
    df = load_panel(audited_only=False)

    # Select the requested fiscal year and nonmissing feature values.
    comparison = df.loc[
        (df["fyear"] == fyear)
        & df["auopic"].isin([1, 2])
        & df[variable].notna(),
        ["gvkey", variable],
    ].copy()

    # Find the requested firm's value.
    firm = comparison[
        comparison["gvkey"].astype(str).str.zfill(6) == gvkey
    ]

    if firm.empty:
        return _result(
            None,
            source=(
                f"final_panel | gvkey={gvkey} | "
                f"fyear={fyear} | col={variable} | n={len(comparison)}"
            ),
            notes="gvkey not assessed or firm has no value for this variable and year.",
        )

    raw_value = float(firm.iloc[0][variable])

    # Calculate percentile using average ranks for tied values.
    percentile = comparison[variable].rank(
        method="average",
        pct=True,
    ).loc[firm.index[0]] * 100

    percentile = round(float(percentile), 1)

    return _result(
        {
            "percentile": percentile,
            "raw_value": round(raw_value, 4),
            "n": len(comparison),
        },
        source=(
            f"final_panel | gvkey={gvkey} | "
            f"fyear={fyear} | col={variable} | n={len(comparison)}"
        ),
        notes=(
            f"Comparison firms: {len(comparison)}. "
            "Compared against assessed firms with nonmissing values "
            "for this variable in the same fiscal year."
        ),
    )




def get_deviation(gvkey, fyear, variable):
    """Compare a current financial value with the firm's prior history."""
    import pandas as pd
    from src.data import load_panel, FEATURES

    key = str(gvkey).zfill(6)
    year = int(fyear)

    if variable not in FEATURES:
        return _result(None, source=f"final_panel | gvkey={key} | fyear={year} | col={variable}", notes="unknown variable")

    df = load_panel(audited_only=False)
    firm = df[df["gvkey"].astype(str).str.zfill(6) == key].copy()

    source = f"final_panel | gvkey={key} | fyear={year} | col={variable}"

    if firm.empty:
        return _result(None, source=source, notes="gvkey not in panel")

    current_rows = firm.loc[firm["fyear"] == year, variable]
    if current_rows.empty or pd.isna(current_rows.iloc[0]):
        return _result(None, source=source, notes="current-year value unavailable")

    prior = firm.loc[firm["fyear"] < year, variable]
    prior = pd.to_numeric(prior, errors="coerce").dropna()

    if len(prior) < 3:
        return _result(None, source=source, notes=f"fewer than 3 prior years with valid {variable} values; found {len(prior)}")

    current = float(current_rows.iloc[0])
    own_median = float(prior.median())
    difference = current - own_median

    if difference > 0:
        direction = "above"
    elif difference < 0:
        direction = "below"
    else:
        direction = "unchanged"

    value = {
        "current": round(current, 4),
        "own_median": round(own_median, 4),
        "difference": round(difference, 4),
        "years_used": int(len(prior)),
        "direction": direction,
    }
    notes = f"Compared FY{year} with {len(prior)} prior firm-year observations; historical median excludes the current year and all future years."
    return _result(value, source=source, notes=notes)

def get_peer_cohort(gvkey, fyear, k=200):
    """Return the k nearest assessed firms in standardized feature space."""

    import numpy as np
    import pandas as pd

    from src.data import load_panel
    from sklearn.preprocessing import StandardScaler
    from sklearn.neighbors import NearestNeighbors

    gvkey = str(gvkey).zfill(6)
    fyear = int(fyear)
    k = int(k)

    features = [
        "LNTA", "ROA", "CapInt", "GPM",
        "AT_TURN", "CURR_RATIO", "IntanTA", "TobinQ",
    ]

    if k < 1:
        return _result(
            None,
            source=f"final_panel | gvkey={gvkey} | fyear={fyear}",
            notes="k must be at least 1.",
        )

    df = load_panel(audited_only=False)

    # Use only firms in the requested fiscal year.
    year_df = df[df["fyear"] == fyear].copy()

    if year_df.empty:
        return _result(
            None,
            source=f"final_panel | gvkey={gvkey} | fyear={fyear}",
            notes="No records found for this fiscal year.",
        )

    # Find the target firm's financial profile.
    target = year_df[
        year_df["gvkey"].astype(str).str.zfill(6) == gvkey
    ]

    if target.empty:
        return _result(
            None,
            source=f"final_panel | gvkey={gvkey} | fyear={fyear}",
            notes="gvkey not in panel for this fiscal year.",
        )

    # Require complete, finite values for all matching features.
    year_df[features] = year_df[features].apply(
        pd.to_numeric, errors="coerce"
    )
    complete = year_df[features].notna().all(axis=1)
    complete &= np.isfinite(year_df[features]).all(axis=1)

    target = year_df.loc[target.index.intersection(
        year_df.index[complete]
    )]

    if target.empty:
        return _result(
            None,
            source=f"final_panel | gvkey={gvkey} | fyear={fyear}",
            notes="Target firm has missing matching features.",
        )

    # Use assessed firms only for peer outcomes.
    candidates = year_df[
        complete & year_df["auopic"].isin([1, 2])
    ].copy()

    # Exclude the target firm from its own peer group.
    candidates = candidates[
        candidates["gvkey"].astype(str).str.zfill(6) != gvkey
    ]

    # Overall adverse rate among assessed firms in the same year.
    assessed = year_df[year_df["auopic"].isin([1, 2])]
    if assessed.empty:
        return _result(
            None,
            source=f"final_panel | gvkey={gvkey} | fyear={fyear}",
            notes="No assessed firms available for the cohort base rate.",
        )

    cohort_base_rate = float((assessed["auopic"] == 2).mean())

    if candidates.empty:
        return _result(
            None,
            source=f"final_panel | gvkey={gvkey} | fyear={fyear}",
            notes="No eligible assessed peers with complete matching features.",
        )

    # Standardize the eight financial features.
    scaler = StandardScaler()
    candidate_scaled = scaler.fit_transform(candidates[features])
    target_scaled = scaler.transform(target[features].iloc[[0]])

    # Find the nearest assessed firms.
    n_neighbors = min(k, len(candidates))
    model = NearestNeighbors(n_neighbors=n_neighbors)
    model.fit(candidate_scaled)

    distances, indices = model.kneighbors(target_scaled)

    peers = candidates.iloc[indices[0]]
    peers_resolved = len(peers)

    peer_adverse_rate = float((peers["auopic"] == 2).mean())

    lift = (
        round(peer_adverse_rate / cohort_base_rate, 4)
        if cohort_base_rate > 0
        else None
    )

    notes = (
        f"Matched on eight standardized features. "
        f"Excluded target firm. Missing-feature firms excluded. "
        f"Used assessed peers only (auopic 1 and 2). "
        f"Peer outcomes and cohort base rate are from fiscal year {fyear}."
    )

    if lift is not None and lift < 1.0:
        notes += (
            " IMPORTANT: Peer group is safer than average "
            "(lift below 1.0); this is evidence against the risk assessment."
        )

    return _result(
        {
            "k": k,
            "matched_on": features,
            "peer_adverse_rate": round(peer_adverse_rate, 4),
            "cohort_base_rate": round(cohort_base_rate, 4),
            "lift": lift,
            "peers_resolved": peers_resolved,
        },
        source=(
            f"final_panel | gvkey={gvkey} | "
            f"fyear={fyear} | {peers_resolved} peers"
        ),
        notes=notes,
    )



def get_cohort_rate(slice_name, fyear):
    """Return the adverse rate for a validated cohort through the cutoff year."""
    import re
    import numpy as np
    import pandas as pd
    from src.data import load_panel

    year = int(fyear)
    name = str(slice_name).strip()

    valid_fixed = {"auop_1", "auop_4", "fin", "nonfin", "all"}
    size_match = re.fullmatch(r"size_decile_(10|[1-9])", name)
    sic_match = re.fullmatch(r"sic2_(\d{2})", name)

    if not (name in valid_fixed or size_match or sic_match):
        return _result(
            None,
            source=f"final_panel | invalid slice={name}",
            notes="Unrecognized slice name. Valid slices are size_decile_1 through size_decile_10, sic2_<nn>, auop_1, auop_4, fin, nonfin, and all.",
        )

    df = load_panel(audited_only=False).copy()
    df = df[df["fyear"] <= year].copy()

    # Only firms with an observed internal-control assessment define cohorts.
    df = df[df["auopic"].isin([1, 2])].copy()

    if df.empty:
        return _result(
            None,
            source=f"final_panel | slice={name} | fyear<={year}",
            notes="No assessed firm-year observations are available through the requested year.",
        )

    if name == "all":
        cohort = df

    elif name == "auop_1":
        cohort = df[df["auop"] == 1]

    elif name == "auop_4":
        cohort = df[df["auop"] == 4]

    elif name == "fin":
        cohort = df[df["FIN"] == 1]

    elif name == "nonfin":
        cohort = df[df["NONFIN"] == 1]

    elif sic_match:
        sic2 = int(sic_match.group(1))
        cohort = df[df["SIC"].notna()].copy()
        cohort = cohort[
            cohort["SIC"].astype(int) // 100 == sic2
        ]

    else:
        requested_decile = int(size_match.group(1))
        cohort = df[df["LNTA"].notna()].copy()
        cohort["LNTA"] = pd.to_numeric(cohort["LNTA"], errors="coerce")
        cohort = cohort[np.isfinite(cohort["LNTA"])].copy()

        # Rank separately within each fiscal year.
        # Sorting by GVKEY resolves tied LNTA values reproducibly.
        cohort["_gvkey_sort"] = cohort["gvkey"].astype(str).str.zfill(6)
        cohort = cohort.sort_values(
            ["fyear", "LNTA", "_gvkey_sort"],
            kind="mergesort",
        )

        cohort["_position"] = cohort.groupby("fyear").cumcount()
        cohort["_year_count"] = cohort.groupby("fyear")["gvkey"].transform("size")

        cohort["_size_decile"] = (
            (cohort["_position"] * 10 // cohort["_year_count"]) + 1
        )

        cohort = cohort[cohort["_size_decile"] == requested_decile]

    n = int(len(cohort))

    if n == 0:
        return _result(
            None,
            source=f"final_panel | slice={name} | fyear<={year} | n=0",
            notes="No assessed observations matched this cohort through the requested fiscal year.",
        )

    adverse_rate = float((cohort["auopic"] == 2).mean())

    value = {
        "slice": name,
        "adverse_rate": round(adverse_rate, 4),
        "n": n,
        "fyear": year,
    }

    source = (
        f"final_panel | cohort={name} | fyear<={year} | n={n}"
    )

    notes = (
        f"Adverse rate is calculated from assessed firm-year observations "
        f"(auopic 1 and 2) in FY{year} and earlier; no future years are used. "
    )

    if size_match:
        notes += (
            "Size deciles are assigned separately within each fiscal year "
            "using ascending LNTA; decile 1 is smallest and decile 10 largest. "
            "Ties are resolved deterministically by GVKEY. "
            "Rows with missing or nonfinite LNTA cannot be assigned to a decile."
        )
    elif sic_match:
        notes += f"Industry membership uses SIC2 {int(sic_match.group(1)):02d}."
    elif name in {"auop_1", "auop_4"}:
        notes += f"Cohort membership uses auop={1 if name == 'auop_1' else 4}."
    elif name in {"fin", "nonfin"}:
        notes += f"Cohort membership uses {name.upper()} classification."

    return _result(value, source=source, notes=notes)


def get_industry_context(gvkey, fyear):
    """Return industry context and within-industry financial comparisons."""
    import pandas as pd
    from src.data import load_panel

    key = str(gvkey).zfill(6)
    year = int(fyear)
    df = load_panel(audited_only=False).copy()

    firm = df[
        (df["gvkey"].astype(str).str.zfill(6) == key)
        & (df["fyear"] == year)
    ]

    if firm.empty:
        return _result(
            None,
            source=f"final_panel | gvkey={key} | fyear={year}",
            notes="No firm record found for this fiscal year.",
        )

    row = firm.iloc[0]

    if pd.isna(row["SIC"]):
        return _result(
            None,
            source=f"final_panel | gvkey={key} | fyear={year}",
            notes="SIC is missing for this firm-year.",
        )

    sic = int(row["SIC"])
    sic2 = sic // 100

    year_df = df[df["fyear"] == year].copy()
    year_df = year_df[year_df["SIC"].notna()].copy()
    year_df["sic2"] = year_df["SIC"].astype(int) // 100

    industry = year_df[year_df["sic2"] == sic2].copy()

    assessed = industry[industry["auopic"].isin([1, 2])]
    n_firms = int(len(assessed))

    industry_rate = (
        float((assessed["auopic"] == 2).mean())
        if n_firms else None
    )

    percentiles = {}
    for variable in ["ROA", "CURR_RATIO", "LNTA"]:
        values = pd.to_numeric(assessed[variable], errors="coerce")
        target = pd.to_numeric(
            pd.Series([row[variable]]), errors="coerce"
        ).iloc[0]

        valid = values.dropna()

        if pd.isna(target) or valid.empty:
            percentiles[variable] = None
        else:
            percentile = (
                (valid < target).sum()
                + 0.5 * (valid == target).sum()
            ) / len(valid) * 100
            percentiles[variable] = round(float(percentile), 1)

    labels = {
        73: "Business Services",
    }
    industry_label = labels.get(sic2, f"SIC2 {sic2:02d}")

    sic_source = row.get("SIC_SOURCE")
    sic_source = (
        str(sic_source) if pd.notna(sic_source) else "unknown"
    )

    value = {
        "sic": sic,
        "sic2": sic2,
        "industry_label": industry_label,
        "industry_rate": (
            round(industry_rate, 4)
            if industry_rate is not None else None
        ),
        "n_firms": n_firms,
        "within_industry_percentiles": percentiles,
    }

    source = (
        f"final_panel | gvkey={key} | fyear={year} "
        f"| sic2={sic2:02d} | n={n_firms}"
    )
    notes = (
        f"Industry comparisons use SIC2 {sic2:02d} in FY{year}. "
        f"Industry adverse rate uses assessed firms only (auopic 1 and 2). "
        f"Financial percentiles compare nonmissing values among assessed "
        f"firms within the same SIC2 group and fiscal year. "
        f"SIC_SOURCE={sic_source}."
    )

    return _result(value, source=source, notes=notes)


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
