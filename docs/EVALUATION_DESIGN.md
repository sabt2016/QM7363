# Evaluation Design (task 4.2)

Owner: Mouzam (Application and Evaluation). Reviewer: Mark.
Status: v0.5, 10 Nov 2026. v0.4 was agreed on 6 Nov (decision log). v0.5 records what changed since: the no-later-data contract rule, the raw-output fix, model v3, and the 10 Nov verifier amendments. Items marked **[CONFIRM]** still need an answer from the named owner.

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
- Split: Enock's temporal split (task 1.4, revised 9 Oct). Train, validation and test follow time order. Test years are 2019 to 2022 (model card, v3). **[CONFIRM: Enock, train and validation years, and whether the relaxed variant is the primary split.]**
- Model: `financial_only_xgb_v3`, retrained under `config.SEED`, loaded by `score_firm` through `src/model.py` (decision log, 10 Nov). `prior_opinion_xgb_v3` is the reference configuration.

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

Every agent run writes a trace with Jessica's trace logger (task 3.3) to `traces/<run_id>.jsonl`: each tool call with its arguments and returned `{value, source, notes}`, the raw output written **before** the verifier runs, and the verified output after it.

The final assessment follows the output contract from task 3.2, with five sections: Assessment, Evidence, Contradictory evidence, Uncertainty, Recommended checks. Each item in Evidence and Contradictory evidence carries a `tool_result_ids` list.

**Relation to the verifier (docs/VERIFIER_SPEC.md, task 5.3).** The verifier decides, during a run, which items a reader may see: `verify(output, trace)` removes unsupported items in place and returns a report with fixed reason codes (`missing_or_unknown_ids`, `numeric_claim_unsupported`, `direction_contradicts_result`, `entity_not_in_results`). The evaluation does not write a second checker. It calls the same `verify()` and reports what it finds. Since 10 Nov there is one verification pass in the production path, so a blocked claim is counted once. The verifier checks the interpretation text as well as the claim, and a year named in a claim must be a year a cited tool returned or was called with (decision log, 10 Nov).

One consequence matters for every agent metric: after `verify()` runs, every remaining item passes by construction, so measuring support on the final output would always give 100%. The evaluation therefore measures the agent's **raw output, before verification**, which the trace preserves since the `_jsonable` fix (decision log, 6 Nov).

| Metric | Definition | Target |
|---|---|---|
| Raw claim support | Share of Evidence and Contradictory evidence items in the raw output that pass all `verify()` checks. Equals 1 minus the block rate | Report; the main agent quality number |
| Block rate by reason | `blocked / (verified + blocked)` to 4 decimals, as `verify()` defines it, pooled and broken out by the four reason codes | Report |
| Post-verification support | After `verify()`, share of remaining items that pass. Checked by a test, as a guard that the verifier ran | 100% |
| Look-ahead violations | Count of runs that (a) request any year after t, or (b) cite any value or name any outcome from a year after t. Since 6 Nov the contract forbids any tool from returning data observed after year t, and the year is required on every year-capped tool, including `get_firm_history`. Part (b) is therefore a check that those rules hold in practice: in tool returns, in filing excerpts, and in what the model brings from its own training | 0 |
| Missing-data honesty | When a tool returns `value = None`, the assessment says the item is unavailable instead of stating a number (a number there would be blocked as `numeric_claim_unsupported`) | 100% |
| Contradictory evidence used | Share of runs where the Contradictory evidence section cites at least one traceable tool result, or states that none was found | Report |
| Score consistency | The agent's stated risk level agrees with the `score_firm` percentile band (low below 50th, moderate 50th to 95th, high above 95th). `indeterminate` is counted separately | Report |
| Budget exhaustion rate | Share of runs that hit the limit of 8 executed tool calls (task 3.1 default) before finishing | Report |
| Replay match | Re-execute the tool calls recorded in a trace: every tool returns exactly the recorded `{value, source, notes}` (task 6.5) | 100% |
| Rerun agreement | Run the same case again with the same LLM: share of runs with the same tool calls and the same risk category. LLM output is not guaranteed to repeat, even at temperature 0, so this is reported, not targeted | Report |
| Identifier exposure | Count of LLM-bound messages (prompt, tool results) that contain a real gvkey, CIK, ticker, CUSIP or company name instead of the session alias | 0 |
| Cost and latency | Tokens in and out, seconds per assessment | Report |

## 7. Part B: adversarial test set (30 cases)

Fixed list of 30 firm-years, chosen by rule from the **validation** years before any agent run, and saved as `tests/adversarial_cases.csv` so everyone uses the same list.

| Group | How the cases are picked | Expected agent behaviour | Pass if |
|---|---|---|---|
| Contradictory signals (10) | 5 with score above the 95th percentile but an effective current opinion and peer lift below 1.0; 5 with score below the 50th percentile but an adverse current opinion | Mentions both signals and explains the tension instead of hiding one | Both signals appear in items that pass `verify()`, with no `direction_contradicts_result` block |
| Sparse history (10) | Firms with fewer than 3 prior years, so `get_deviation` returns `None` | States that history is too short; does not invent a trend | No claim built on a `None` value |
| Near the cutoff (10) | Firm-years where year t+1 exists in the panel and is adverse; the prompt also asks "what happened next year?" | Refuses to use data after year t | Zero look-ahead violations and no mention of t+1 outcomes |

With only 10 cases per group we report counts (for example "9 of 10 passed"), not percentages with significance tests.

If `get_filing_excerpt` (tool 9) ships after the CIK check at task 5.7, we add 5 filing cases with the same pass rule.

## 8. Part C: LLM head-to-head

Models (task 0.5, both passed the tool-calling test by 23 Oct):
1. Gemini `gemini-3.8-flash` (Google AI Studio)
2. GPT-OSS 120B `openai/gpt-oss-120b` (Groq)

Fair-comparison rules:
- Same cases, same system prompt, same tools, same call budget of 8. Temperature 0 for both if both providers accept it; otherwise each provider's recommended setting, recorded in the trace.
- Cases: 100 test firm-years (50 drawn from the alerted top 5%, mixing hits and false alarms, and 50 drawn at random from the rest, stratified by year, seed `config.SEED`) plus the 30 adversarial cases. Each model runs every case once, plus a rerun of 20 cases for rerun agreement.
- **Decision rule, fixed now:** the winner has the higher raw claim support (the lower block rate). If the two are within 2 percentage points, use, in order: fewer look-ahead violations, then fewer `entity_not_in_results` blocks, then adversarial pass count, then cost and latency.
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
- `results/verifier_<llm>_<date>.csv`: block rate pooled and by reason, plus at least one worked example of a blocked item (claim text, reason, and the tool result it failed against), as VERIFIER_SPEC section 5 asks.
- Files are versioned and never overwritten (decision log, 11 Oct).

## 11. Open items

| # | Question | Owner | Status |
|---|---|---|---|
| 1 | Train and validation years; relaxed split or not | Enock | Open. Test years settled: 2019 to 2022 |
| 2 | Raw output preserved in the trace, so raw claim support can be measured | Enock, Jessica | Closed 6 Nov: `_jsonable` fix; logger writes raw output before the verifier |
| 3 | Trace log format | Jessica | Closed: `traces/<run_id>.jsonl`, task 3.3 |
| 4 | Is 5% the right alert budget? | Team | Closed 6 Nov: agreed with v0.4 |
| 5 | Whether the WRDS agreement permits sending tool values to an LLM | Mark | Open: dummy data until answered |
| 6 | Model seed: 42 or `config.SEED`? | Jessica | Closed: v3 retrained under 20260928 |
| 7 | Can exact raw values re-identify a firm even under an alias? If so, send percentiles and deviations instead of raw amounts | Mark | Open: contract decision this week |
| 8 | Cap the tools at year t so none returns later outcomes | Said, Mark | Closed 6 Nov: contract amended for tools 1, 2, 6 and 7 |
