"""Generate five messy raw marketing sources, optionally with a known set of injected defects.

The sources deliberately disagree about column names, date formats and channel labels, like real exports do.
When defects are injected, an answer key (``manifest.json``) records exactly what was broken and which quality
checks are expected to catch it, so the pipeline's detection can be measured instead of assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

START, END = "2025-01-01", "2025-06-30"
EXTRACT_DATE = "2025-07-01"  # date the data was "pulled"; anything later is invalid

CHANNELS = ["paid_search", "paid_social", "email", "organic_search", "direct"]
WEEKDAY = np.array([1.00, 1.05, 1.05, 1.00, 0.95, 0.80, 0.75])  # Monday first

CAMPAIGNS = {  # name: (impressions per day, click-through rate, cost per click)
    "paid_search": {"Brand": (9_000, 0.09, 0.55), "Generic": (40_000, 0.030, 1.40), "Competitor": (15_000, 0.025, 1.90)},
    "paid_social": {"Prospecting": (120_000, 0.009, 0.75), "Retargeting": (30_000, 0.020, 0.60), "Lookalike": (70_000, 0.011, 0.85)},
}
SESSION_PER_CLICK = {"paid_search": (0.90, 0.96), "paid_social": (0.84, 0.92)}
BASE_SESSIONS = {"email": 2400, "organic_search": 1800, "direct": 1200}
CONVERSION_RATE = {"paid_search": 0.034, "paid_social": 0.017, "email": 0.045, "organic_search": 0.026, "direct": 0.040}
ORDER_VALUE = {"paid_search": 78.0, "paid_social": 64.0, "email": 85.0, "organic_search": 70.0, "direct": 90.0}
LEAD_RATE = {"paid_search": 0.040, "paid_social": 0.050, "email": 0.020, "organic_search": 0.030, "direct": 0.010}

SOURCE_MEDIUM = {
    "paid_search": "google / cpc",
    "paid_social": "facebook / paid_social",
    "email": "newsletter / email",
    "organic_search": "google / organic",
    "direct": "(direct) / (none)",
}
LEAD_SOURCE = {
    "paid_search": "Google Ads",
    "paid_social": "Facebook",
    "email": "Newsletter",
    "organic_search": "Organic",
    "direct": "Direct",
}
LEAD_STATUSES = ["Marketing Qualified Lead", "Sales Qualified Lead", "Closed Won", "Closed Lost", "New"]
LEAD_STATUS_P = [0.30, 0.15, 0.08, 0.17, 0.30]
OWNERS = ["Priya", "Marcus", "Elena", "Tom"]


def _trend(n: int) -> np.ndarray:
    return 1 + 0.0015 * np.arange(n)


def build_clean(seed: int = 7) -> dict[str, pd.DataFrame]:
    """Internally consistent 'truth' tables before any export quirks or defects."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(START, END, freq="D")
    n = len(days)
    wk = WEEKDAY[days.dayofweek]
    tr = _trend(n)

    ad_rows = []
    clicks_by_channel = {c: np.zeros(n) for c in CHANNELS}
    for channel, camps in CAMPAIGNS.items():
        for name, (imp0, ctr, cpc) in camps.items():
            impressions = (imp0 * wk * tr * rng.lognormal(0, 0.08, n)).round().astype(int)
            clicks = rng.binomial(impressions, ctr)
            spend = np.round(clicks * cpc * rng.lognormal(0, 0.05, n), 2)
            conversions = rng.binomial(clicks, 0.03)
            clicks_by_channel[channel] += clicks
            ad_rows.append(pd.DataFrame({"date": days, "channel": channel, "campaign": name, "spend": spend,
                                         "impressions": impressions, "clicks": clicks, "platform_conversions": conversions}))
    ads = pd.concat(ad_rows, ignore_index=True)

    sessions = {}
    for channel in CHANNELS:
        if channel in SESSION_PER_CLICK:
            lo, hi = SESSION_PER_CLICK[channel]
            sessions[channel] = np.round(clicks_by_channel[channel] * rng.uniform(lo, hi, n)).astype(int)
        else:
            sessions[channel] = np.round(BASE_SESSIONS[channel] * wk * tr * rng.lognormal(0, 0.07, n)).astype(int)

    order_rows, web_rows, lead_rows = [], [], []
    email_pool = np.array([f"customer{i}@example.com" for i in range(30_000)])
    order_counter, lead_counter = 0, 0
    for channel in CHANNELS:
        transactions = rng.binomial(sessions[channel], CONVERSION_RATE[channel])
        for i, day in enumerate(days):
            k = int(transactions[i])
            values = np.round(np.exp(rng.normal(np.log(ORDER_VALUE[channel]) - 0.45**2 / 2, 0.45, k)), 2)
            order_rows.append(pd.DataFrame({
                "order_id": [f"O{order_counter + j:07d}" for j in range(k)],
                "order_date": day, "customer_email": rng.choice(email_pool, k), "channel": channel, "revenue": values,
            }))
            order_counter += k
            web_rows.append({"date": day, "channel": channel, "sessions": int(sessions[channel][i]),
                             "transactions": k, "revenue": round(float(values.sum()), 2)})
            n_leads = int(rng.binomial(int(sessions[channel][i]), LEAD_RATE[channel]))
            if n_leads:
                secs = rng.integers(0, 86_400, n_leads)
                lead_rows.append(pd.DataFrame({
                    "lead_id": [f"L{lead_counter + j:07d}" for j in range(n_leads)],
                    "created_at": day + pd.to_timedelta(secs, unit="s"),
                    "email": [f"lead{lead_counter + j}@example.com" for j in range(n_leads)],
                    "channel": channel,
                    "status": rng.choice(LEAD_STATUSES, n_leads, p=LEAD_STATUS_P),
                    "owner": rng.choice(OWNERS, n_leads),
                }))
                lead_counter += n_leads
    return {
        "ads": ads,
        "web": pd.DataFrame(web_rows),
        "orders": pd.concat(order_rows, ignore_index=True),
        "leads": pd.concat(lead_rows, ignore_index=True),
    }


# ------------------------------------------------------------------ export formats (the messy part)


def export_raw(clean: dict[str, pd.DataFrame], out: Path, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """Turn clean tables into the five differently formatted raw sources."""
    ads = clean["ads"]
    search = ads[ads.channel == "paid_search"]
    social = ads[ads.channel == "paid_social"]
    raw = {
        "search_ads": pd.DataFrame({
            "Day": search["date"].dt.strftime("%Y-%m-%d"), "Campaign": search["campaign"], "Cost": search["spend"],
            "Clicks": search["clicks"], "Impr.": search["impressions"], "Conversions": search["platform_conversions"]}),
        "social_ads": pd.DataFrame({
            "date": social["date"].dt.strftime("%m/%d/%Y"), "campaign_name": social["campaign"],
            "spend_usd": social["spend"].map(lambda v: f"${v:,.2f}"), "link_clicks": social["clicks"],
            "impressions": social["impressions"], "results": social["platform_conversions"]}),
        "web_sessions": pd.DataFrame({
            "date": clean["web"]["date"].dt.strftime("%Y-%m-%d"), "source_medium": clean["web"]["channel"].map(SOURCE_MEDIUM),
            "sessions": clean["web"]["sessions"], "transactions": clean["web"]["transactions"], "revenue": clean["web"]["revenue"]}),
        "crm_leads": pd.DataFrame({
            "lead_id": clean["leads"]["lead_id"], "created_at": clean["leads"]["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "email": clean["leads"]["email"], "lead_source": clean["leads"]["channel"].map(LEAD_SOURCE),
            "status": clean["leads"]["status"], "owner": clean["leads"]["owner"]}),
        "orders": pd.DataFrame({
            "order_id": clean["orders"]["order_id"], "order_date": clean["orders"]["order_date"].dt.strftime("%Y-%m-%d"),
            "customer_email": clean["orders"]["customer_email"], "channel": clean["orders"]["channel"].map(SOURCE_MEDIUM),
            "revenue": clean["orders"]["revenue"]}),
    }
    return {k: v.reset_index(drop=True) for k, v in raw.items()}


# ------------------------------------------------------------------ defects


def inject_defects(raw: dict[str, pd.DataFrame], rng: np.random.Generator,
                   only: set[str] | None = None) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Break the raw sources in ten documented ways. Returns the broken sources and the answer key.

    ``only`` limits injection to a subset of defect ids (used by the tests to prove each check is specific).
    """
    raw = {k: v.copy() for k, v in raw.items()}
    manifest: list[dict] = []

    def want(defect_id: str) -> bool:
        return only is None or defect_id in only

    seed = lambda: int(rng.integers(1e9))  # noqa: E731

    if want("D01"):
        leads = raw["crm_leads"]
        raw["crm_leads"] = pd.concat([leads, leads.sample(60, random_state=seed())], ignore_index=True)
        manifest.append({"id": "D01", "type": "exact_duplicate_leads", "table": "crm_leads", "rows": 60, "expected_checks": ["C04"]})

    if want("D02"):
        leads = raw["crm_leads"]
        near = leads.sample(40, random_state=seed()).copy()
        near["lead_id"] = [f"L9{i:06d}" for i in range(len(near))]
        near["email"] = near["email"].map(lambda e: f" {e.upper()} ")
        raw["crm_leads"] = pd.concat([leads, near], ignore_index=True)
        manifest.append({"id": "D02", "type": "near_duplicate_leads_by_email", "table": "crm_leads", "rows": 40, "expected_checks": ["C05"]})

    if want("D03"):
        leads = raw["crm_leads"]
        idx = leads.sample(80, random_state=seed()).index
        leads.loc[idx, "email"] = ["" if r < 0.5 else None for r in rng.random(80)]  # blank string or true null
        manifest.append({"id": "D03", "type": "missing_lead_email", "table": "crm_leads", "rows": 80, "expected_checks": ["C07"]})

    if want("D04"):
        ads = raw["search_ads"]
        ads.loc[ads.sample(15, random_state=seed()).index, "Campaign"] = ""
        manifest.append({"id": "D04", "type": "missing_campaign_name", "table": "search_ads", "rows": 15, "expected_checks": ["C08"]})

    if want("D05"):
        leads = raw["crm_leads"]
        leads.loc[leads.sample(25, random_state=seed()).index, "status"] = "??"
        manifest.append({"id": "D05", "type": "unmapped_lead_status", "table": "crm_leads", "rows": 25, "expected_checks": ["C09"]})

    if want("D06"):
        social = raw["social_ads"]
        mask = (social["date"] == pd.Timestamp("2025-04-17").strftime("%m/%d/%Y")) & (social["campaign_name"] == "Prospecting")
        old = float(social.loc[mask, "spend_usd"].iloc[0].replace("$", "").replace(",", ""))
        social.loc[mask, "spend_usd"] = f"${old * 6:,.2f}"
        manifest.append({"id": "D06", "type": "spend_spike_decimal_error", "table": "social_ads", "dates": ["2025-04-17"],
                         "factor": 6, "expected_checks": ["C20"]})

    if want("D07"):
        web = raw["web_sessions"]
        brk = [d.strftime("%Y-%m-%d") for d in pd.date_range("2025-03-10", periods=4)]
        mask = web["date"].isin(brk) & (web["source_medium"] == SOURCE_MEDIUM["paid_search"])
        web.loc[mask, ["transactions", "revenue"]] = 0
        manifest.append({"id": "D07", "type": "tracking_break_zero_transactions", "table": "web_sessions", "dates": brk,
                         "channel": "paid_search", "expected_checks": ["C15", "C21"], "also_triggers": ["C16"]})

    if want("D08"):
        web = raw["web_sessions"]
        gap = [d.strftime("%Y-%m-%d") for d in pd.date_range("2025-05-05", periods=3)]
        raw["web_sessions"] = web[~web["date"].isin(gap)].reset_index(drop=True)
        manifest.append({"id": "D08", "type": "missing_days", "table": "web_sessions", "dates": gap, "expected_checks": ["C01"]})

    if want("D09"):
        orders = raw["orders"]
        neg = orders.sample(5, random_state=seed()).index
        orders.loc[neg, "revenue"] = -orders.loc[neg, "revenue"]
        fut = orders.drop(neg).sample(3, random_state=seed()).index
        orders.loc[fut, "order_date"] = "2025-08-15"
        manifest.append({"id": "D09", "type": "invalid_orders_negative_revenue_and_future_date", "table": "orders", "rows": 8,
                         "expected_checks": ["C12", "C13"]})

    if want("D10"):
        web = raw["web_sessions"]
        extra = pd.DataFrame({"date": pd.date_range("2025-06-01", periods=6).strftime("%Y-%m-%d"), "source_medium": "tiktok / paid_social",
                              "sessions": rng.integers(300, 600, 6), "transactions": rng.integers(5, 15, 6), "revenue": rng.integers(300, 900, 6)})
        raw["web_sessions"] = pd.concat([web, extra], ignore_index=True)
        manifest.append({"id": "D10", "type": "unknown_traffic_source", "table": "web_sessions", "rows": 6,
                         "source": "tiktok / paid_social", "expected_checks": ["C10"]})
    return raw, manifest


def generate(out: Path, seed: int = 7, defects: bool = False, only: set[str] | None = None) -> list[dict]:
    """Write the five raw CSVs (and, with defects, the answer key) to ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed + 1000)
    raw = export_raw(build_clean(seed), out, rng)
    manifest: list[dict] = []
    if defects:
        raw, manifest = inject_defects(raw, rng, only)
        if only is None or "D11" in only:
            manifest.append({"id": "D11", "type": "dashboard_join_fanout", "table": "dashboard_extract",
                             "description": "the legacy dashboard query joins orders to leads and multiplies revenue",
                             "expected_checks": ["C18"]})
    for name, df in raw.items():
        df.to_csv(out / f"{name}.csv", index=False)
    (out / "manifest.json").write_text(json.dumps({"defects_injected": defects, "seed": seed, "defects": manifest}, indent=2))
    return manifest
