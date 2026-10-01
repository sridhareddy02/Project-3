## Data with 11 injected defects

**Quality gate: FAIL**  
9 of 23 checks passed, 11 errors, 3 warnings, 2 anomaly incidents.

| Check | Severity | Failing rows | Detail |
|---|---|---:|---|
| C01 web_sessions has every day | error | 3 | days with no web data: 2025-05-05, 2025-05-06, 2025-05-07 |
| C04 lead_id is unique | error | 60 | repeated lead_id rows |
| C08 ads have a campaign name | error | 15 | ad rows with no campaign name |
| C09 lead status is known | error | 25 | unmapped statuses: ?? |
| C10 web traffic sources are known | error | 6 | unknown web sources: tiktok / paid_social |
| C12 order revenue is positive | error | 5 | orders with missing or non-positive revenue |
| C13 no orders from the future | error | 3 | orders dated after the extract date 2025-07-01 |
| C15 web transactions match orders | error | 4 | channel-days where web transactions and orders disagree: 2025-03-10 paid_search, 2025-03-11 paid_search, 2025-03-12 paid_search, 2025-03-13  |
| C18 dashboard matches the warehouse | error | 5 | channels where dashboard revenue differs from the warehouse by more than 0.5%: direct (dashboard 10,949,595 vs warehouse 822,520), email (da |
| C20 no spend anomalies | error | 1 | incidents: paid_social 2025-04-17 (spike, 1 day) |
| C21 no conversion anomalies | error | 1 | incidents: paid_search 2025-03-10 (drop, 4 days) |
| C05 one lead per email | warn | 40 | emails with several lead ids: lead109@example.com, lead12793@example.com, lead16070@example.com, lead16087@example.com, lead18213@example.co |
| C07 leads have an email | warn | 80 | leads without an email address |
| C16 web revenue matches orders | warn | 1 | channels whose web revenue differs from order revenue by more than 2%: paid_search (2.2%) |

Detection: 11 of 11 injected defects caught.
