# Tool Contract

**Status:** proposal for team review. Amend freely, then sign at the bottom.
**Task:** 0.1. Nothing downstream can be built until this is settled.

Nine functions. Said Shoaib implements them, Enock's agent calls them, and the
verifier in task 5.3 matches every claim in a generated brief back to one of
these returns. That last use is why the shapes below carry raw numbers rather
than formatted sentences: the verifier compares values, not prose.

---

## 1. Shared envelope

Every tool returns a dictionary with exactly these three keys.

```python
{
  "value":  ...,        # the answer, or None. Type is specified per tool below.
  "source": "...",      # where the answer came from. Format in section 2.
  "notes":  "..."       # context, or the reason value is None. Never required reading.
}
```

Rules that hold for all nine:

- **Never guess and never substitute a default.** If the answer is unavailable,
  `value` is `None` and `notes` says why. A tool that returns 0 when it means
  "unknown" produces a brief that is confidently wrong.
- **Raw numbers, not strings.** Return `0.0470`, not `"4.70%"`. Formatting is the
  interface layer's job, and the verifier cannot compare formatted text.
- **Round floats to 4 decimal places.** Percentiles and rates to 1 decimal.
  Fixed so the same call always produces a byte-identical answer, which trace
  replay in task 6.5 depends on.
- **`gvkey` is a string**, six characters, leading zeros preserved. `"001004"`,
  never `1004`.
- **Unknown `gvkey`** returns `value: None` with `notes: "gvkey not in panel"`.
  It is not an error and must not raise.

---

## 2. Source string format

Pipe-separated, left to right from general to specific. A reader must be able to
find the number themselves from this string alone.

```
final_panel | gvkey=001004 | fyear=2018 | col=ROA
final_panel | gvkey=001004 | fyear<=2018 | 8 rows
final_panel | cohort=size_decile_2 | fyear=2018 | n=347
model_v1 | rf_calibrated | trained fyear 2011-2017 | gvkey=001004 fyear=2018
edgar | cik=0001750 | 10-K FY2018 | Item 9A | para 3
```

---

## 3. The nine tools

### 1. `get_firm_history(gvkey, through_fyear=None)`

Everything on record for one firm. The agent's usual first call.

**value:** list of dicts, one per fiscal year, oldest first. Each dict holds
`fyear`, `auopic`, `auop`, `SIC`, and all 19 features.
`through_fyear` caps the list so the agent cannot see past the year under review.
Omit it only for a retrospective question.

**source:** `final_panel | gvkey=001004 | fyear<=2018 | 8 rows`

**notes:** how many years, and whether any are missing from the middle.

---

### 2. `get_control_history(gvkey)`

The firm's internal control record. Separate from tool 1 because the three
auopic codes mean different things and the agent must not conflate them.

**value:**
```python
{
  "adverse_years":       [2016, 2017],   # auopic = 2
  "effective_years":     [2014, 2015, 2018],   # auopic = 1
  "not_assessed_years":  [2011, 2012, 2013],   # auopic = 0, exempt filer
  "current_status":      "effective",    # effective | adverse | not_assessed | unknown
  "prior_year_status":   "adverse"
}
```

**notes:** must state plainly that `not_assessed_years` are years with no auditor
attestation, not years with clean controls. The agent will say the wrong thing
otherwise.

---

### 3. `score_firm(gvkey, fyear)`

Jessica's model, asked about one firm-year. Loads `financial_only_rf_v1.pkl`.

**value:**
```python
{
  "probability":      0.1187,    # calibrated, probability of adverse in fyear+1
  "percentile":       94.9,      # rank among all scored firms in this fyear
  "cohort_base_rate": 0.0404,
  "model_version":    "financial_only_rf_v1",
  "uses_prior_opinion": False
}
```

`value: None` when the firm-year is not in the modelling sample, with `notes`
saying which condition failed: not assessed, no following year, or features
missing beyond what the model tolerates.

**source:** `model_v1 | rf_calibrated | trained fyear 2011-2017 | gvkey=001004 fyear=2018`

**notes:** must state that the model excludes prior-year opinion, so the agent
does not credit it with information it never had.

---

### 4. `get_percentile(gvkey, fyear, variable)`

Where one value sits among all firms that year.

**value:** float 0 to 100, one decimal. `None` if the firm has no value.
**source:** `final_panel | gvkey=001004 | fyear=2018 | col=ROA | n=3475`
**notes:** the raw value and how many firms were in the comparison.

`variable` must be one of the 19 feature names. Anything else returns `None`
with `notes: "unknown variable"`.

---

### 5. `get_deviation(gvkey, fyear, variable)`

How far a value sits from the firm's own history. This is what separates a firm
that has always had thin margins from one whose margins just collapsed.

**value:**
```python
{
  "current":      -0.0839,
  "own_median":   -0.0667,   # median across that firm's other years
  "difference":   -0.0172,
  "years_used":   7,
  "direction":    "below"    # above | below | unchanged
}
```

`None` when fewer than three prior years exist. Two points is not a baseline.

---

### 6. `get_peer_cohort(gvkey, fyear, k=200)`

The k nearest firms in standardised feature space, and what happened to them.

**value:**
```python
{
  "k":                200,
  "matched_on":       ["LNTA", "ROA", "CapInt", "GPM", "AT_TURN", "CURR_RATIO", "IntanTA", "TobinQ"],
  "peer_adverse_rate": 0.1150,   # share adverse the following year
  "cohort_base_rate":  0.0429,
  "lift":              2.68,
  "peers_resolved":    200
}
```

**notes:** must say when the lift is below 1.0, because a peer group that is
*safer* than average is evidence against the risk assessment and the brief is
required to report it.

---

### 7. `get_cohort_rate(slice_name, fyear=None)`

The observed adverse rate for a named group. Supplies the base rates a brief
compares against.

Valid `slice_name` values, fixed so the agent cannot invent one:
`size_decile_1` through `size_decile_10`, `sic2_<nn>`, `auop_1`, `auop_4`,
`fin`, `nonfin`, `all`.

**value:**
```python
{"slice": "size_decile_2", "adverse_rate": 0.0399, "n": 4273, "fyear": 2018}
```

`fyear=None` pools all years and `notes` says so.

---

### 8. `get_industry_context(gvkey, fyear)`

The firm's industry and how it compares inside it.

**value:**
```python
{
  "sic":               7372,
  "sic2":              73,
  "industry_label":    "Business Services",
  "industry_rate":     0.0648,
  "n_firms":           4216,
  "within_industry_percentiles": {"ROA": 14.2, "CURR_RATIO": 9.8, "LNTA": 31.0}
}
```

**notes:** must carry `SIC_SOURCE` when the code was filled from a neighbouring
year rather than reported, so a claim about industry is not treated as firmer
than the data behind it.

---

### 9. `get_filing_excerpt(gvkey, fyear, section)`  — GATED

Ships only if CIK coverage clears the gate at task 5.7. Built in phase 2.

`section` is one of `"item7"`, `"item9a"`, `"auditor_report"`.

**value:**
```python
{
  "text":       "...",          # the passage, 500 words maximum
  "section":    "Item 9A",
  "paragraph":  3,
  "accession":  "0000001750-19-000034",
  "filed_date": "2019-02-14"
}
```

`None` when the firm has no CIK, no filing for that year, or the section cannot
be located. Each of those gets a distinct message in `notes`.

**Claims drawn from this tool need their own verification.** Matching a sentence
to a passage is not the same check as matching a number to a cell, which is why
task 6.7 scores it separately.

---

## 4. Stubs come first

Said Shoaib writes nine fake versions returning correctly shaped invented data
before any real implementation. Enock builds the whole agent against the fakes.
Real versions replace them one at a time and the agent never changes.

This is the entire reason the contract exists. Without it, Enock waits for Said,
and Said waits for Jessica.

---

## 5. Sign-off

Signing means you have read all nine and will build or call them exactly as
written. Changing anything after sign-off requires telling the other four and a
row in the decision log.

| Name | Role | Date | Agreed |
|---|---|---|---|
| Mark | Team lead | | |
| Jessica | Data and model | | |
| Said Shoaib | Tool layer | | |
| Enock | Agent | | |
| Mouzam Younas | Application and evaluation | | |
