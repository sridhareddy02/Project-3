# KPI definitions

| KPI | Definition | Notes |
|---|---|---|
| Spend | Sum of ad platform cost | Paid channels only |
| Impressions, clicks | Platform counts | |
| CTR | `Clicks / Impressions` | |
| CPC | `Spend / Clicks` | |
| Sessions | Web analytics sessions | |
| Click-to-session ratio | `Sessions / Clicks` | Expected 75% to 105%; outside means tracking loss or double counting (check C17) |
| Transactions | Web analytics purchases | Compared with `Orders` (check C15) |
| Orders | Orders in the order system after quarantine | The source of truth for revenue |
| Revenue | Sum of order revenue | |
| Average order value | `Revenue / Orders` | |
| Conversion rate | `Transactions / Sessions` in the mart; `Orders / Sessions` in the weekly KPI table | State which one a chart uses |
| Leads | Distinct leads after deduplication | |
| CAC | `Spend / Orders` | Paid channels; last-touch by channel, not incremental |
| ROAS | `Revenue / Spend` | Paid channels; last-touch by channel, not incremental |

## Data-quality metrics

| Metric | Definition |
|---|---|
| Gate | PASS when no error-level check fails; warnings do not block |
| Failing rows | Number of rows (or channel-days, or incidents) violating a check |
| Anomaly incident | One or more consecutive days whose weekday-adjusted robust z-score exceeds 5 in magnitude |
| Robust z-score | `(log1p(value) - log1p(median of same weekday, prior 4 weeks)) / (1.4826 * MAD of all residuals)` |
| Recall (evaluation) | Injected defects caught by at least one of their documented checks / injected defects |
| Unexpected failure | A check that fails although no injected defect documents it |
