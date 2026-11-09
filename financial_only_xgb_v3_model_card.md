# Auditor Opinion Forecast Models v3

Frozen at UTC: 2026-11-09T19:40:20.821644+00:00

Status: capstone models built on the reviewed temporal split, frozen for evaluation. The primary (financial-only) model's pooled test ROC-AUC is 0.686 (95% bootstrap interval 0.662 to 0.710), below the corrected financial-only benchmark of 0.70 to 0.75. The prior-opinion variant's pooled test ROC-AUC is 0.806 (95% interval 0.782 to 0.830). ROC-AUC measures ranking ability; it is not the share of correct predictions.

## Prediction task

Use fiscal-year t information to forecast whether a firm receives an adverse internal-control opinion (auopic = 2) in fiscal year t+1. Both years are restricted to auopic codes 1 and 2. This is an internal-control risk indicator, not a fraud finding. No feature uses information observed after year t.

## Models

- Primary (financial_only_xgb_v3): XGBoost (300 trees, maximum depth 3, learning rate 0.05, minimum child weight 5, subsampling 0.8) on 19 financial predictors.
- Variant (prior_opinion_xgb_v3): the same XGBoost with the fiscal-year t adverse-opinion indicator added.
- Selection rule, fixed before test evaluation: highest validation ROC-AUC among logistic regression, Random Forest and XGBoost on financial predictors. XGBoost was selected; the runner-up was Random Forest (validation ROC-AUC difference 0.0017, 95% interval -0.0269 to 0.0303).
- Comparators, reported on test: the other financial-only models and their prior-opinion variants.
- Preprocessing: median imputation with missing indicators, fitted on training data only.
- Calibration: sigmoid mapping of log-odds, fitted on validation data only.

## Temporal split

| partition | rows | firms | feature_years | outcome_years | prediction_dates | adverse | adverse_rate |
|---|---|---|---|---|---|---|---|
| Training | 14092 | 4136 | 2011-2014 | 2012-2015 | 2011-09-30 to 2015-08-31 | 522 | 0.0370 |
| Validation | 3253 | 3253 | 2016-2016 | 2017-2017 | 2016-09-30 to 2017-08-31 | 116 | 0.0357 |
| Test | 12325 | 3785 | 2018-2021 | 2019-2022 | 2018-09-30 to 2022-08-31 | 471 | 0.0382 |

Timing rule: an earlier partition's outcome INFO_DATE must precede the next partition's earliest prediction date. INFO_DATE is an availability proxy, not a verified report date.

## Validation (model selection)

| model | rows | adverse | observed_rate | mean_predicted | ROC_AUC | PR_AUC | Brier |
|---|---|---|---|---|---|---|---|
| Logistic regression | 3253 | 116 | 0.0357 | 0.0379 | 0.6433 | 0.0592 | 0.0343 |
| Random Forest | 3253 | 116 | 0.0357 | 0.0381 | 0.7145 | 0.0889 | 0.0336 |
| XGBoost | 3253 | 116 | 0.0357 | 0.0353 | 0.7162 | 0.0857 | 0.0338 |
| Logistic regression + prior opinion | 3253 | 116 | 0.0357 | 0.0434 | 0.7742 | 0.1760 | 0.0321 |
| Random Forest + prior opinion | 3253 | 116 | 0.0357 | 0.0421 | 0.7977 | 0.2210 | 0.0306 |
| XGBoost + prior opinion | 3253 | 116 | 0.0357 | 0.0398 | 0.7984 | 0.2438 | 0.0304 |

Validation calibration is a fitting diagnostic. It uses 116 adverse cases and is not independent evaluation.

## Test results (outcome years 2019 to 2022)

| model | subgroup | rows | adverse | observed_rate | mean_predicted | ROC_AUC | PR_AUC | Brier |
|---|---|---|---|---|---|---|---|---|
| Logistic regression (raw) | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0360 | 0.6591 | 0.0703 | 0.0364 |
| Random Forest (raw) | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0400 | 0.6881 | 0.0931 | 0.0360 |
| XGBoost (raw) | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0347 | 0.6864 | 0.0873 | 0.0361 |
| Logistic regression + prior opinion (raw) | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0398 | 0.7849 | 0.2780 | 0.0303 |
| Random Forest + prior opinion (raw) | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0422 | 0.7964 | 0.2885 | 0.0308 |
| XGBoost + prior opinion (raw) | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0378 | 0.8064 | 0.2922 | 0.0308 |
| XGBoost (calibrated) | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0353 | 0.6864 | 0.0873 | 0.0360 |
| XGBoost + prior opinion (calibrated) | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0340 | 0.8064 | 0.2922 | 0.0311 |
| Constant prevalence benchmark | Pooled 2019-2022 | 12325 | 471 | 0.0382 | 0.0370 | n/a | n/a | 0.0368 |
| Logistic regression (raw) | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0374 | 0.6334 | 0.0694 | 0.0409 |
| Random Forest (raw) | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0400 | 0.6837 | 0.1063 | 0.0400 |
| XGBoost (raw) | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0367 | 0.6847 | 0.0957 | 0.0401 |
| Logistic regression + prior opinion (raw) | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0442 | 0.7666 | 0.2470 | 0.0347 |
| Random Forest + prior opinion (raw) | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0447 | 0.7907 | 0.2660 | 0.0347 |
| XGBoost + prior opinion (raw) | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0436 | 0.7948 | 0.2692 | 0.0351 |
| XGBoost (calibrated) | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0370 | 0.6847 | 0.0957 | 0.0400 |
| XGBoost + prior opinion (calibrated) | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0389 | 0.7948 | 0.2692 | 0.0351 |
| Constant prevalence benchmark | Outcome 2019 | 3225 | 138 | 0.0428 | 0.0370 | n/a | n/a | 0.0410 |
| Logistic regression (raw) | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0357 | 0.6372 | 0.0508 | 0.0285 |
| Random Forest (raw) | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0366 | 0.7111 | 0.0921 | 0.0280 |
| XGBoost (raw) | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0330 | 0.6863 | 0.0723 | 0.0283 |
| Logistic regression + prior opinion (raw) | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0394 | 0.7612 | 0.2218 | 0.0246 |
| Random Forest + prior opinion (raw) | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0391 | 0.8005 | 0.2645 | 0.0245 |
| XGBoost + prior opinion (raw) | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0355 | 0.8061 | 0.2474 | 0.0248 |
| XGBoost (calibrated) | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0338 | 0.6863 | 0.0723 | 0.0281 |
| XGBoost + prior opinion (calibrated) | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0320 | 0.8061 | 0.2474 | 0.0247 |
| Constant prevalence benchmark | Outcome 2020 | 3061 | 90 | 0.0294 | 0.0370 | n/a | n/a | 0.0286 |
| Logistic regression (raw) | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0366 | 0.6816 | 0.0566 | 0.0281 |
| Random Forest (raw) | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0419 | 0.6910 | 0.0705 | 0.0282 |
| XGBoost (raw) | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0355 | 0.6521 | 0.0585 | 0.0284 |
| Logistic regression + prior opinion (raw) | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0360 | 0.8200 | 0.2640 | 0.0239 |
| Random Forest + prior opinion (raw) | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0409 | 0.8089 | 0.2495 | 0.0246 |
| XGBoost + prior opinion (raw) | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0339 | 0.8244 | 0.2343 | 0.0249 |
| XGBoost (calibrated) | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0361 | 0.6521 | 0.0585 | 0.0282 |
| XGBoost + prior opinion (calibrated) | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0307 | 0.8244 | 0.2343 | 0.0249 |
| Constant prevalence benchmark | Outcome 2021 | 2986 | 87 | 0.0291 | 0.0370 | n/a | n/a | 0.0283 |
| Logistic regression (raw) | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0341 | 0.6884 | 0.1159 | 0.0477 |
| Random Forest (raw) | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0416 | 0.6714 | 0.1033 | 0.0476 |
| XGBoost (raw) | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0336 | 0.7088 | 0.1230 | 0.0472 |
| Logistic regression + prior opinion (raw) | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0393 | 0.7983 | 0.4078 | 0.0376 |
| Random Forest + prior opinion (raw) | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0438 | 0.7892 | 0.3916 | 0.0394 |
| XGBoost + prior opinion (raw) | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0379 | 0.8077 | 0.4060 | 0.0381 |
| XGBoost (calibrated) | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0343 | 0.7088 | 0.1230 | 0.0473 |
| XGBoost + prior opinion (calibrated) | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0340 | 0.8077 | 0.4060 | 0.0391 |
| Constant prevalence benchmark | Outcome 2022 | 3053 | 156 | 0.0511 | 0.0370 | n/a | n/a | 0.0487 |

Bootstrap 95% interval for the primary model's pooled ROC-AUC: 0.662 to 0.710.
Bootstrap 95% interval for the variant's pooled ROC-AUC: 0.782 to 0.830.

## Gap between the two models (prior-opinion variant minus primary, calibrated)

| subgroup | ROC_gap | ROC_lo | ROC_hi | PR_gap | PR_lo | PR_hi |
|---|---|---|---|---|---|---|
| Pooled 2019-2022 | 0.1200 | 0.1016 | 0.1406 | 0.2050 | 0.1708 | 0.2412 |
| Outcome 2019 | 0.1101 | 0.0761 | 0.1473 | 0.1735 | 0.1209 | 0.2339 |
| Outcome 2020 | 0.1198 | 0.0752 | 0.1654 | 0.1750 | 0.1087 | 0.2517 |
| Outcome 2021 | 0.1723 | 0.1203 | 0.2277 | 0.1758 | 0.1085 | 0.2602 |
| Outcome 2022 | 0.0989 | 0.0717 | 0.1325 | 0.2830 | 0.2161 | 0.3554 |

## Sensitivity: relaxed non-overlapping split

The timing buffer is removed. Training has 17,457 rows and validation has 6,464 rows with 273 adverse cases. The test set is unchanged. Training labels in this version can be known after some validation prediction dates, so this is a robustness check only.

| model | rows | adverse | mean_predicted | ROC_AUC | PR_AUC | Brier |
|---|---|---|---|---|---|---|
| XGBoost (relaxed, calibrated) | 12325 | 471 | 0.0423 | 0.6975 | 0.0917 | 0.0360 |
| XGBoost (primary split, calibrated) | 12325 | 471 | 0.0353 | 0.6864 | 0.0873 | 0.0360 |
| XGBoost + prior opinion (relaxed, calibrated) | 12325 | 471 | 0.0399 | 0.8082 | 0.3026 | 0.0305 |
| XGBoost + prior opinion (primary split, calibrated) | 12325 | 471 | 0.0340 | 0.8064 | 0.2922 | 0.0311 |

## Use by the agent (score_firm)

The agent calls score_firm(gvkey, feature_year) with a session alias such as FIRM_A. The alias is resolved to the real gvkey inside the local tool layer, and the result returns the alias, not the gvkey. The result contains the probability, model version, rank among assessed firms in the feature year, and the names of any features that were imputed. It contains no raw financial values. A risk score is not proof of a future adverse opinion.

## Limitations

- INFO_DATE is an availability proxy. The auditor report publication date is not verified.
- The test window (outcomes 2019 to 2022) overlaps the period examined in the opinion-history experiment, so test results are not fully clean.
- Validation has 116 adverse cases, so calibration is unstable.
- Per-year test samples are small, so the per-year intervals are wide.
- Firms recur across periods, so the test measures future firm-years rather than unseen firms only.
- The prior-opinion variant mostly reflects persistence of control weaknesses. It should be presented as such, and the report should state how much the financial features add beyond it.
- No operating threshold is selected. The score_firm rank is retrospective, not an as-of-date live ranking.
- Until the university confirms the WRDS data-use terms, agent tests use dummy data only.

## Reproducibility

Source file: final_panel 1.csv
Source SHA256: 482b5947612a99a6e3d9c0e5d09f781442967bf2d1f209db8ff48add16aac788
Random seed: 20260928 (decision-log value (config.SEED not importable from this folder))
Bootstrap draws: 1000
Environment: {"python": "3.13.5", "pandas": "2.2.3", "numpy": "2.1.3", "scikit_learn": "1.6.1", "xgboost": "3.2.0"}
Frozen artifacts: models/financial_only_xgb_v3.pkl and models/prior_opinion_xgb_v3.pkl
Decision record: models/decisions_v3.json
