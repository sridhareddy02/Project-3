# Data-quality runbook

How to respond when the gate fails. Work through the failing checks in this order, because upstream problems cause downstream ones.

## 1. Is the data complete and loaded?
| Check | Meaning | First steps |
|---|---|---|
| C23 lineage | Rows were lost between raw and staging | Re-run the load; compare row counts per file |
| C19 unparseable values | A date or number could not be read | Look at the source export format; a platform may have changed a date or currency format |
| C01 / C02 missing days | A source did not deliver a day | Re-pull that day from the source; confirm the scheduler ran; do not publish partial weeks |
| C03 freshness | The latest day is stale | Check the extract job and credentials |

## 2. Are the keys and labels sound?
| Check | Meaning | First steps |
|---|---|---|
| C04 / C06 duplicate ids | The export repeated rows | Confirm the date window did not overlap between pulls; deduplicate at the source |
| C05 repeated email | Same person captured twice | Core SQL keeps the earliest lead; review form or integration double-firing |
| C07 missing email | Leads cannot be matched | Check the form validation and the CRM sync mapping |
| C08 missing campaign | Spend with no campaign | Fix naming in the ad platform (a campaign was renamed or paused mid-pull) |
| C09 / C10 / C11 unknown labels | A new status, traffic source or channel appeared | Decide the mapping, add it to the taxonomy in `ingest.py`, document it; quarantined rows reappear after a re-run |

## 3. Are values plausible?
| Check | Meaning | First steps |
|---|---|---|
| C12 / C13 invalid orders | Negative revenue or a future date | Quarantined automatically; check refunds being exported as negative orders and timezone or clock problems |
| C14 ad metric sanity | Negative values or clicks above impressions | Usually a platform export bug; raise it with the platform contact |

## 4. Do sources agree?
| Check | Meaning | First steps |
|---|---|---|
| C15 transactions vs orders | The web tag and the order system disagree on a day | Open the site on that day: is the purchase tag firing? Compare with a deployment or consent-banner change. If orders are right, annotate the dashboard and backfill analytics from orders |
| C16 revenue vs orders | Same question for revenue | Check currency, tax and shipping treatment |
| C17 sessions vs clicks | Landing traffic does not match ad clicks | Check auto-tagging, redirects and bot filtering |
| C18 dashboard vs warehouse | The dashboard's own query differs from the mart | Diff the SQL. The usual culprit is a join to a table at a different grain (fan-out); aggregate each source to the day and channel *before* joining |

## 5. Anomalies
| Check | Meaning | First steps |
|---|---|---|
| C20 spend | A day's spend is far outside its weekday band | Check the platform UI for that day; a decimal or budget typo is common. Pause or correct before the budget is spent |
| C21 conversion | Transactions or conversion rate collapsed or spiked | A drop to zero is almost always tracking, not demand; check the tag first |
| C22 sessions | Traffic volume jumped or fell | Check campaigns launched or paused, outages, and bot traffic |

## Communicating an incident
State the check id, what is affected (channel, dates, metric), whether published numbers are wrong, what you did (corrected, quarantined, annotated) and when the next refresh will be clean. Keep a short log so recurring causes show up.
