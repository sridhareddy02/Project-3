# Data dictionary

## Raw sources (`data/raw/*.csv`)

| File | Columns | Quirks |
|---|---|---|
| `search_ads.csv` | `Day` (YYYY-MM-DD), `Campaign`, `Cost` (number), `Clicks`, `Impr.`, `Conversions` | |
| `social_ads.csv` | `date` (MM/DD/YYYY), `campaign_name`, `spend_usd` (text such as `$1,234.56`), `link_clicks`, `impressions`, `results` | Different column names, date format and currency formatting from the search export |
| `web_sessions.csv` | `date`, `source_medium`, `sessions`, `transactions`, `revenue` | One row per day and source |
| `crm_leads.csv` | `lead_id`, `created_at` (YYYY-MM-DD HH:MM:SS), `email`, `lead_source`, `status`, `owner` | Status wording varies |
| `orders.csv` | `order_id`, `order_date`, `customer_email`, `channel` (source / medium text), `revenue` | |

`manifest.json` is written next to the raw files only when defects are injected. It is the answer key used for evaluation and is never read by the pipeline itself.

## Canonical channels

`paid_search`, `paid_social`, `email`, `organic_search`, `direct`. Mapping lives in `ingest.py` (`CHANNEL_MAP`, `LEAD_SOURCE_MAP`); anything else becomes `unmapped` and is quarantined.

## Staging (Python, typed)

| Table | Grain | Notes |
|---|---|---|
| `stg_ads` | platform, date, campaign | `spend` parsed to a number; `campaign` null when blank |
| `stg_web` | date, source | `channel` mapped, `unmapped` if unknown |
| `stg_leads` | lead row as exported | `email` trimmed, lower-cased, blank to null; `status` mapped to MQL, SQL, Closed Won, Closed Lost, New |
| `stg_orders` | order row as exported | `channel` mapped |

## Core (SQL, `sql/10_core.sql`)

| Table | Grain | Rules |
|---|---|---|
| `dim_channel` | channel | label and `is_paid` |
| `dim_date` | day | recursive CTE from the window start to end; weekday, year-week, year-month |
| `fact_ad_spend` | date, channel, campaign | missing campaign labelled `(missing)` |
| `fact_web_daily` | date, channel | unmapped sources excluded |
| `quarantine_web` | row | unmapped sources, with a reason |
| `fact_leads` | lead | exact duplicates collapsed; one lead per email (earliest); leads without email kept individually |
| `fact_orders` | order | revenue above zero, date not after the extract date, channel mapped |
| `quarantine_orders` | order | everything else, with a reason |

## Mart (SQL, `sql/20_mart.sql`)

`mart_channel_daily`: one row per date and channel (181 days by 5 channels).

| Column | Meaning |
|---|---|
| `date`, `channel`, `is_paid`, `weekday`, `year_week`, `year_month` | grain and calendar attributes |
| `spend`, `impressions`, `clicks` | from the ad platforms (paid channels only) |
| `sessions`, `transactions`, `web_revenue` | from web analytics; `NULL` when the day is missing |
| `orders`, `order_revenue` | from the order system |
| `leads` | deduplicated CRM leads created that day |

## Check results (`reports/*/checks.csv`)

`id`, `name`, `category`, `severity` (error or warn), `status` (pass or fail), `failing_rows`, `description`, `detail`.
