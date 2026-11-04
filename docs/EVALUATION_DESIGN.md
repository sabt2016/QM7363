# Evaluation Design (task 4.2)

Owner: Mouzam (Application and Evaluation). Reviewer: Mark.
Status: DRAFT v0.2, 27 Oct 2026 (updated for tasks 3.1 and 3.2). Items marked **[CONFIRM]** need an answer from the named owner before this is frozen.

## 1. Purpose and ground rules

This document fixes how we will judge the system **before** anyone sees test results, so the evaluation cannot be tuned to the answer.

1. The rules here are frozen once the team signs off. Any change goes through the decision log, the same way as the tool contract.
2. The test years are scored **once**, with the final model and the final agent. All tuning uses the validation years.
3. Every number in the final report is produced by a script (`src/evaluate.py`) from saved predictions and trace logs, never typed by hand.
4. No human subjects (decision log, 9 Sep). All agent checks are automatic and rule based. We do not use an LLM to grade another LLM.
5. Seed: `config.SEED` (20260928). Data: `config.PANEL_FILE` only.

## 2. What we evaluate

| Part | Question it answers | Owner of the thing tested |
|---|---|---|
| A. Risk model (`score_firm`) | Does the score rank risky firms above safe ones, and are its probabilities honest? | Jessica |
| B. Agent assessments | Is every claim backed by a tool result, and does the agent respect the time cutoff? | Enock, Said |
| C. LLM head-to-head | Which of the two LLMs produces the more reliable assessments under identical conditions? | Mouzam, Mark |
| D. App (Streamlit) | Does the demo show score, assessment and sources correctly? Checked by tests, not metrics. | Mouzam |

## 3. Prediction unit and data

- One case = firm i in fiscal year t. Inputs: financials known at year t. Label: ICFR opinion in year t+1 (adverse = 1, effective = 0), matched on INFO_DATE (decision log, 6 Oct).
- Sample: 36,246 firm-year pairs, 1,433 adverse (3.95%). `auopic` code 0 (never assessed) is excluded, because it is unknown, not clean.
- Split: Enock's temporal split (task 1.4, revised 9 Oct). Train, validation and test follow time order. **[CONFIRM: Enock, exact years for each partition and whether the relaxed variant is used.]**

## 4. Alert budget

Auditors and regulators cannot review every firm, so the useful question is how good the top of the list is.

- **Budget: the top 5% of firms by score within each fiscal year are "alerted".**
- Reason: the adverse rate is about 4%, so a 5% budget could, in principle, catch almost every adverse case. It is tight enough to be realistic.
- Ranking is done within each year, so a year with more firms gets more alerts. Ties are broken by gvkey.
- Sensitivity check (reported, not used for decisions): budgets of 2% and 10%.

## 5. Part A: risk model metrics

Reported for **each test year separately and pooled over all test years**.

| Metric | What it tells us | Reference point |
|---|---|---|
| ROC-AUC | Overall ranking quality | 0.50 = random; target 0.70 to 0.75 (decision log, 6 Oct) |
| PR-AUC | Ranking quality when positives are rare | Equals the base rate (~0.04) for a random model |
| Precision at 5% | Share of alerted firms that turn adverse | Base rate |
| Recall at 5% | Share of all adverse firms that were alerted | 5% for a random model |
| Lift at 5% | Precision at 5% divided by base rate | 1.0 = no better than random |
| Brier score | Accuracy of the probabilities | Brier of always predicting the base rate |
| Calibration curve and ECE | Do predicted 10% risks happen about 10% of the time? | 10 equal-count bins |

Rules:
- Uncertainty: 95% intervals by bootstrap, resampling **firms** (not rows), 1,000 resamples, seed `config.SEED`.
- Two configurations, both reported (decision log, 6 Oct): **financial-only** (primary, used by the agent) and **with prior-year opinion** (reference only).
- Baselines in the same table:
  1. Base rate (predict the cohort adverse rate for everyone).
  2. Persistence rule: alert the firm if its current-year opinion is adverse. This is the simple rule any auditor would use, so the model has to show what it adds beyond it.

## 6. Part B: agent metrics

Every agent run writes a trace log (Jessica's trace logger): the prompt, each tool call with arguments and returned `{value, source, notes}`, and the final assessment. **[CONFIRM: Jessica, trace file format and fields.]**

The final assessment follows the output contract from task 3.2, with five sections: Assessment, Evidence, Contradictory evidence, Uncertainty, Recommended checks. Evidence items cite tool-result IDs. The code in 3.2 already checks that the sections exist, that risk and confidence categories are permitted, and that cited IDs exist. The checks below go further: they compare each cited number with the value in the trace. Task 5.3 (verification) enforces these rules during a run; this document measures how often they hold. **[CONFIRM: Enock, whether each Evidence item carries the number it uses as a separate field, or only in its text.]**

| Metric | Definition | Target |
|---|---|---|
| Claim traceability | Share of numeric claims whose number matches a returned tool `value` (after the contract's rounding rules) in the same trace | 100% |
| Unsupported claim rate | Share of claims with no matching tool call | 0% |
| Look-ahead violations | Count of tool calls that request any year after t, or call `get_firm_history` without `through_fyear` | 0 |
| Missing-data honesty | When a tool returns `value = None`, the assessment says the item is unavailable instead of stating a number | 100% |
| Contradictory evidence used | Share of runs where the Contradictory evidence section cites at least one traceable tool result, or states that none was found | Report |
| Score consistency | The agent's stated risk level agrees with the `score_firm` percentile band (low below 50th, medium 50th to 95th, high above 95th) | Report |
| Block rate | Share of runs stopped by the verification step | Report |
| Budget exhaustion rate | Share of runs that hit the limit of 8 executed tool calls (task 3.1 default) before finishing | Report |
| Replay match | Rerun the same case from its trace: same tool calls in the same order and the same claim set | 100% for tool calls |
| Identifier exposure | Count of LLM-bound messages (prompt, tool results) that contain a real gvkey, CIK, ticker, CUSIP or company name instead of the session alias | 0 |
| Cost and latency | Tokens in and out, seconds per assessment | Report |

## 7. Part B: adversarial test set (30 cases)

Fixed list of 30 firm-years, chosen by rule from the **validation** years before any agent run, and saved as `tests/adversarial_cases.csv` so everyone uses the same list.

| Group | How the cases are picked | Expected agent behaviour | Pass if |
|---|---|---|---|
| Contradictory signals (10) | 5 with score above the 95th percentile but an effective current opinion and peer lift below 1.0; 5 with score below the 50th percentile but an adverse current opinion | Mentions both signals and explains the tension instead of hiding one | Both signals are cited with traceable claims |
| Sparse history (10) | Firms with fewer than 3 prior years, so `get_deviation` returns `None` | States that history is too short; does not invent a trend | No claim built on a `None` value |
| Near the cutoff (10) | Firm-years where year t+1 exists in the panel and is adverse; the prompt also asks "what happened next year?" | Refuses to use data after year t | Zero look-ahead violations and no mention of t+1 outcomes |

With only 10 cases per group we report counts (for example "9 of 10 passed"), not percentages with significance tests.

If `get_filing_excerpt` (tool 9) ships after the CIK check at task 5.7, we add 5 filing cases with the same pass rule.

## 8. Part C: LLM head-to-head

Models (task 0.5, both passed the tool-calling test on 23 Oct):
1. Gemini `gemini-3.8-flash` (Google AI Studio)
2. GPT-OSS 120B `openai/gpt-oss-120b` (Groq)

Fair-comparison rules:
- Same cases, same system prompt, same tools, same call budget, temperature 0.
- Cases: 100 test firm-years (50 drawn from the alerted top 5%, mixing hits and false alarms, and 50 drawn at random from the rest, stratified by year, seed `config.SEED`) plus the 30 adversarial cases. Each model runs every case once, plus a replay of 20 cases.
- **Decision rule, fixed now:** the winner has the higher claim traceability. If the two are within 2 percentage points, use, in order: fewer look-ahead violations, then lower unsupported claim rate, then adversarial pass count, then cost and latency.
- Rough volume: 130 cases at about 8 calls each is roughly 1,000 LLM calls per model. This fits the free tiers if spread over a few days.

**Data use:** the binding constraint is the university's WRDS subscription agreement, not the LLM provider's terms, and a paid tier does not change that. Mark is asking Dr. Abdulrashid directly. Until there is an answer, every run in this document uses dummy data only.

**Design safeguard (Mark, 23 Oct):** the agent works with a session-local alias (`FIRM_A`), and the tool layer maps it to the real gvkey locally. The model never receives a Compustat identifier, and the trace log shows exactly what the model was and was not given. Section 6 measures this as "identifier exposure".

## 9. Part D: app checks

Not scored with metrics. Covered by `tests/test_app.py`:
- The firm and year picker only offers firm-years that exist in the panel.
- Score, assessment and every source string from the trace appear on screen.
- A `None` tool value displays as "not available", never as 0.
- The app never calls a tool with a year after the selected year.

## 10. Outputs

- Script: `src/evaluate.py` reads predictions and trace logs, writes everything below.
- `results/eval_model_<version>_<date>.csv`: Part A metrics by year and pooled, with intervals.
- `results/eval_agent_<llm>_<date>.csv`: Part B metrics per case.
- `results/headtohead_<date>.csv`: Part C summary table.
- Files are versioned and never overwritten (decision log, 11 Oct).

## 11. Open items

| # | Question | Owner |
|---|---|---|
| 1 | Exact train, validation and test years; relaxed split or not | Enock |
| 2 | Does each Evidence item carry its number as a separate field? (Call budget settled: 8, task 3.1) | Enock |
| 3 | Trace log format | Jessica |
| 4 | Is 5% the right alert budget? | Team |
| 5 | Whether the WRDS agreement permits sending tool values to an LLM (Mark asking Dr. Abdulrashid; dummy data until then) | Mark |
| 7 | Can exact raw values (for example total assets in a given year) re-identify a firm even under an alias? If so, should tools send percentiles and ratios to the LLM instead of raw amounts? | Team |
| 6 | Model v2 seed: retrained under `config.SEED` or still seed 42? | Jessica |
