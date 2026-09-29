# Tool Contract — DRAFT, task 0.1

**Due signed off by October 4.** Nobody starts real implementation until all five
of us have agreed to this file. It is what lets four people build in parallel
instead of waiting in line.

Fill in the return schema for each tool, then everyone signs at the bottom.

---

## Shared conventions

Every tool returns a dict with exactly these keys:

```python
{
  "value":  ...,        # the answer. type varies by tool, specified below
  "source": "...",      # resolvable reference. see below
  "notes":  "..." | None
}
```

`source` must let a reader find the number themselves. Format:

```
final_panel | gvkey=001004 | fyear=2018 | col=ROA
final_panel | gvkey=001004 | all rows
model_v1 | trained fyear<=2017 | gvkey=001004 fyear=2018
edgar | CIK=0000001750 | 10-K FY2018 | Item 9A | para 3
```

Missing data returns `value: None` with a note. Tools never guess and never
return a default.

---

## The nine tools

| # | Tool | Arguments | Returns | Owner |
|---|---|---|---|---|
| 1 | `get_firm_history` | gvkey, through_fyear | | Said Shoaib |
| 2 | `get_control_history` | gvkey | | Said Shoaib |
| 3 | `score_firm` | gvkey, fyear | | Said Shoaib |
| 4 | `get_percentile` | gvkey, fyear, variable | | Said Shoaib |
| 5 | `get_deviation` | gvkey, fyear, variable | | Said Shoaib |
| 6 | `get_peer_cohort` | gvkey, fyear, k | | Said Shoaib |
| 7 | `get_cohort_rate` | slice_spec | | Said Shoaib |
| 8 | `get_industry_context` | gvkey, fyear | | Said Shoaib |
| 9 | `get_filing_excerpt` | gvkey, fyear, section | | Said Shoaib |

Tool 9 is gated at task 5.7 and only ships if CIK coverage supports it.

---

## Sign-off

| Name | Date | Agreed |
|---|---|---|
| Mark | | |
| Jessica | | |
| Said Shoaib | | |
| Enock | | |
| Mouzam Younas | | |
