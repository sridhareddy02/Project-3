"""Declarative data-quality checks.

Every check has an id, a severity, a description and a function that returns the number of failing rows plus a short
detail string. Errors fail the quality gate; warnings are reported but do not.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from . import anomalies
from .generate import END, EXTRACT_DATE, START
from .ingest import Staging


@dataclass
class Context:
    con: sqlite3.Connection
    staging: Staging
    mart: pd.DataFrame
    dashboard: pd.DataFrame
    incidents: pd.DataFrame
    start: str = START
    end: str = END
    extract_date: str = EXTRACT_DATE


@dataclass
class Check:
    id: str
    name: str
    category: str
    severity: str  # "error" or "warn"
    description: str
    fn: Callable[[Context], tuple[int, str]]


def _q(ctx: Context, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, ctx.con)


def _sample(values, n: int = 5) -> str:
    values = [str(v) for v in values]
    more = f" (+{len(values) - n} more)" if len(values) > n else ""
    return ", ".join(values[:n]) + more if values else ""


# ---------------------------------------------------------------- completeness and freshness


def c01(ctx):
    d = _q(ctx, "SELECT d.date FROM dim_date d LEFT JOIN (SELECT DISTINCT date FROM fact_web_daily) w ON w.date = d.date WHERE w.date IS NULL")
    return len(d), f"days with no web data: {_sample(d['date'])}"


def c02(ctx):
    d = _q(ctx, """SELECT d.date, c.channel FROM dim_date d CROSS JOIN dim_channel c
                   LEFT JOIN (SELECT DISTINCT date, channel FROM fact_ad_spend) a ON a.date = d.date AND a.channel = c.channel
                   WHERE c.is_paid = 1 AND a.date IS NULL""")
    return len(d), f"missing channel-days: {_sample(d['date'] + ' ' + d['channel'])}"


def c03(ctx):
    latest = _q(ctx, "SELECT MAX(date) AS d FROM fact_web_daily")["d"].iloc[0]
    stale = latest is None or pd.Timestamp(latest) < pd.Timestamp(ctx.end) - pd.Timedelta(days=1)
    return int(stale), f"latest web date {latest}, expected {ctx.end}"


# ---------------------------------------------------------------- uniqueness


def c04(ctx):
    d = _q(ctx, "SELECT COUNT(*) - COUNT(DISTINCT lead_id) AS n FROM stg_leads")["n"].iloc[0]
    return int(d), "repeated lead_id rows"


def c05(ctx):
    d = _q(ctx, """SELECT email, COUNT(*) AS n FROM (SELECT DISTINCT lead_id, email FROM stg_leads WHERE email IS NOT NULL)
                   GROUP BY email HAVING n > 1""")
    return int((d["n"] - 1).sum()) if len(d) else 0, f"emails with several lead ids: {_sample(d['email'])}"


def c06(ctx):
    d = _q(ctx, "SELECT COUNT(*) - COUNT(DISTINCT order_id) AS n FROM stg_orders")["n"].iloc[0]
    return int(d), "repeated order_id rows"


# ---------------------------------------------------------------- not null, accepted values, ranges


def c07(ctx):
    n = _q(ctx, "SELECT COUNT(DISTINCT lead_id) AS n FROM stg_leads WHERE email IS NULL")["n"].iloc[0]
    return int(n), "leads without an email address"


def c08(ctx):
    n = _q(ctx, "SELECT COUNT(*) AS n FROM stg_ads WHERE campaign IS NULL")["n"].iloc[0]
    return int(n), "ad rows with no campaign name"


def c09(ctx):
    d = _q(ctx, "SELECT status_raw, COUNT(DISTINCT lead_id) AS n FROM stg_leads WHERE status = 'unmapped' GROUP BY status_raw")
    return int(d["n"].sum()) if len(d) else 0, f"unmapped statuses: {_sample(d['status_raw'])}"


def c10(ctx):
    d = _q(ctx, "SELECT source_medium, COUNT(*) AS n FROM stg_web WHERE channel = 'unmapped' GROUP BY source_medium")
    return int(d["n"].sum()) if len(d) else 0, f"unknown web sources: {_sample(d['source_medium'])}"


def c11(ctx):
    n = _q(ctx, "SELECT (SELECT COUNT(*) FROM stg_orders WHERE channel='unmapped') + (SELECT COUNT(*) FROM stg_leads WHERE channel='unmapped') AS n")["n"].iloc[0]
    return int(n), "orders or leads with an unknown channel"


def c12(ctx):
    n = _q(ctx, "SELECT COUNT(*) AS n FROM stg_orders WHERE revenue IS NULL OR revenue <= 0")["n"].iloc[0]
    return int(n), "orders with missing or non-positive revenue"


def c13(ctx):
    n = _q(ctx, f"SELECT COUNT(*) AS n FROM stg_orders WHERE order_date > '{ctx.extract_date}'")["n"].iloc[0]
    return int(n), f"orders dated after the extract date {ctx.extract_date}"


def c14(ctx):
    n = _q(ctx, "SELECT COUNT(*) AS n FROM stg_ads WHERE spend < 0 OR impressions < 0 OR clicks < 0 OR clicks > impressions")["n"].iloc[0]
    return int(n), "ad rows with negative values or more clicks than impressions"


# ---------------------------------------------------------------- reconciliation


def c15(ctx):
    m = ctx.mart.dropna(subset=["transactions", "orders"]).copy()
    diff = (m["transactions"] - m["orders"]).abs()
    bad = m[diff > (0.05 * m["orders"]).clip(lower=2)]
    return len(bad), f"channel-days where web transactions and orders disagree: {_sample(bad['date'] + ' ' + bad['channel'])}"


def c16(ctx):
    both = ctx.mart.dropna(subset=["web_revenue", "order_revenue"])  # compare only days present in both sources
    g = both.groupby("channel")[["web_revenue", "order_revenue"]].sum()
    rel = (g["web_revenue"] - g["order_revenue"]).abs() / g["order_revenue"]
    bad = rel[rel > 0.02]
    return len(bad), "channels whose web revenue differs from order revenue by more than 2%: " + _sample(f"{c} ({v:.1%})" for c, v in bad.items())


def c17(ctx):
    m = ctx.mart[(ctx.mart["is_paid"] == 1)].dropna(subset=["sessions", "clicks"])
    ratio = m["sessions"] / m["clicks"].where(m["clicks"] > 0)
    bad = m[(ratio < 0.75) | (ratio > 1.05)]
    return len(bad), "paid channel-days where sessions are outside 75% to 105% of clicks"


def c18(ctx):
    wh = _q(ctx, "SELECT channel, SUM(order_revenue) AS warehouse FROM mart_channel_daily GROUP BY channel")
    m = wh.merge(ctx.dashboard[["channel", "revenue"]], on="channel", how="outer")
    rel = (m["revenue"] - m["warehouse"]).abs() / m["warehouse"]
    bad = m[rel > 0.005]
    return len(bad), "channels where dashboard revenue differs from the warehouse by more than 0.5%: " + _sample(
        f"{r.channel} (dashboard {r.revenue:,.0f} vs warehouse {r.warehouse:,.0f})" for r in bad.itertuples())


def c19(ctx):
    total = sum(ctx.staging.parse_errors.values())
    return int(total), "values that could not be parsed as dates or numbers: " + ", ".join(f"{k}={v}" for k, v in ctx.staging.parse_errors.items())


def c23(ctx):
    mapping = {"search_ads": None, "social_ads": None, "web_sessions": "stg_web", "crm_leads": "stg_leads", "orders": "stg_orders"}
    diffs = []
    for raw_name, table in mapping.items():
        if table is None:
            continue
        loaded = int(_q(ctx, f"SELECT COUNT(*) AS n FROM {table}")["n"].iloc[0])
        if loaded != ctx.staging.raw_rows[raw_name]:
            diffs.append(f"{raw_name}: raw {ctx.staging.raw_rows[raw_name]} vs loaded {loaded}")
    ads_loaded = int(_q(ctx, "SELECT COUNT(*) AS n FROM stg_ads")["n"].iloc[0])
    if ads_loaded != ctx.staging.raw_rows["search_ads"] + ctx.staging.raw_rows["social_ads"]:
        diffs.append("ads: row count changed during loading")
    return len(diffs), "; ".join(diffs)


# ---------------------------------------------------------------- anomalies


def _anomaly_check(metric: str):
    def run(ctx):
        inc = ctx.incidents[ctx.incidents["metric"] == metric]
        text = _sample(f"{r.channel} {r.start:%Y-%m-%d} ({r.direction}, {r.days} day{'s' if r.days > 1 else ''})" for r in inc.itertuples())
        return len(inc), f"incidents: {text}"

    return run


CHECKS: list[Check] = [
    Check("C01", "web_sessions has every day", "completeness", "error", "Every date in the reporting window has web analytics rows", c01),
    Check("C02", "ads has every paid channel-day", "completeness", "error", "Each paid channel reports spend for every day", c02),
    Check("C03", "data is fresh", "freshness", "warn", "Latest web data is at most one day older than the window end", c03),
    Check("C04", "lead_id is unique", "uniqueness", "error", "No lead id appears twice in the CRM export", c04),
    Check("C05", "one lead per email", "uniqueness", "warn", "No normalised email is attached to several lead ids", c05),
    Check("C06", "order_id is unique", "uniqueness", "error", "No order id appears twice", c06),
    Check("C07", "leads have an email", "not null", "warn", "Every lead has an email address", c07),
    Check("C08", "ads have a campaign name", "not null", "error", "Every ad row names its campaign", c08),
    Check("C09", "lead status is known", "accepted values", "error", "Every lead status maps to the standard list", c09),
    Check("C10", "web traffic sources are known", "accepted values", "error", "Every source / medium maps to a channel", c10),
    Check("C11", "orders and leads map to a channel", "accepted values", "error", "No order or lead has an unknown channel", c11),
    Check("C12", "order revenue is positive", "range", "error", "Every order has revenue above zero", c12),
    Check("C13", "no orders from the future", "range", "error", "No order is dated after the extract date", c13),
    Check("C14", "ad metrics are sane", "range", "error", "No negative metrics and clicks never exceed impressions", c14),
    Check("C15", "web transactions match orders", "reconciliation", "error", "Daily web transactions and orders agree within 5% (minimum 2)", c15),
    Check("C16", "web revenue matches orders", "reconciliation", "warn", "Revenue in web analytics and in the order system agree within 2% per channel", c16),
    Check("C17", "sessions track ad clicks", "reconciliation", "warn", "Paid sessions are between 75% and 105% of platform clicks", c17),
    Check("C18", "dashboard matches the warehouse", "reconciliation", "error", "Dashboard revenue agrees with the warehouse within 0.5% per channel", c18),
    Check("C19", "values parse", "validity", "error", "No unparseable dates or numbers in any source", c19),
    Check("C20", "no spend anomalies", "anomaly", "error", "Daily spend stays within the weekday-adjusted band", _anomaly_check("spend")),
    Check("C21", "no conversion anomalies", "anomaly", "error", "Daily transactions and conversion rate stay within the weekday-adjusted band", lambda ctx: _merge(ctx, ["transactions", "conversion_rate"])),
    Check("C22", "no session anomalies", "anomaly", "warn", "Daily sessions stay within the weekday-adjusted band", _anomaly_check("sessions")),
    Check("C23", "no rows lost on load", "lineage", "error", "Every raw row reaches staging", c23),
]


def _merge(ctx, metrics):
    inc = ctx.incidents[ctx.incidents["metric"].isin(metrics)]
    # the same event usually shows up as both a transaction drop and a conversion-rate drop; count it once
    unique = inc.drop_duplicates(["channel", "start"])
    text = _sample(f"{r.channel} {r.start:%Y-%m-%d} ({r.direction}, {r.days} day{'s' if r.days > 1 else ''})" for r in unique.itertuples())
    return len(unique), f"incidents: {text}"


def run_checks(ctx: Context) -> pd.DataFrame:
    rows = []
    for check in CHECKS:
        failing, detail = check.fn(ctx)
        rows.append({"id": check.id, "name": check.name, "category": check.category, "severity": check.severity,
                     "status": "pass" if failing == 0 else "fail", "failing_rows": int(failing),
                     "description": check.description, "detail": detail if failing else ""})
    return pd.DataFrame(rows)


def gate_passed(results: pd.DataFrame) -> bool:
    return not ((results["severity"] == "error") & (results["status"] == "fail")).any()
