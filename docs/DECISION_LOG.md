# Decision Log

One row per scope, method, or schedule decision. Written **during** the meeting
where the decision is made, not afterward. This file is the raw material for the
methods section of the final report and it is what stops us relitigating settled
questions in November.

| Date | Decision | Reason | Decided by |
|---|---|---|---|
| 2026-09-09 | Working application plus automated evaluation. No human subjects. | Semester length and the instructor's stated deliverable. | Team |
| 2026-09-27 | Mouzam's `final_panel` replaces `FinalCleanedData.csv` for all purposes. | Clean firm identifier, recovered CFsale, no Excel error strings, validated against WRDS. | Team |
| 2026-09-27 | Exclude `auopic` code 0 from the modelling sample. | Code 0 means never audited under the SOX 404(b) exemption. Those rows are unknown, not clean, and they are 48.8% of the panel. | Team |
| 2026-09-27 | Primary target is the adverse ICFR opinion. Narrative retrieval returns as a second evidence source, gated on CIK coverage at task 5.7. | The panel supplies `gvkey`, which restores the identifier that killed the original design. | Team |
| 2026-09-27 | Schedule slides one week to December 7 rather than compressing to nine weeks. | Compressing puts the final phase on top of finals. | Mark |
| 2026-10-06 | Outcome timing: predict the following fiscal year's opinion from the current year's financials, rather than explaining the current year. | Prediction is the useful product and the defensible claim. Each row matched to the same firm in exactly the next fiscal year, using INFO_DATE for availability. Yields 36,246 consecutive-year pairs, 1,433 adverse, 3.95%. | Jessica, ratified by team |
| 2026-10-06 | Tool contract agreed in full. Nine functions, their arguments, return schemas, source string format and failure behaviour are fixed. | Unblocks parallel work: Said Shoaib writes stubs, Enock builds the agent against them, neither waits on the other. Signed by all five in the Teams thread. | Team |
| 2026-10-06 | Model performance target corrected. Financial-features-only model targets ROC .70 to .75, not .826. | The .826 figure came from a configuration that includes prior-year control opinion, which the main workflow excludes by design. Both configurations are reported, and the gap between them is a finding. | Mark |
| | | | |
| | | | |
