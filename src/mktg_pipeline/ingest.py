"""Read the raw sources and standardise them into typed staging tables.

Standardisation is deliberately conservative: it fixes formats (dates, currency, case, whitespace) and maps labels to
a canonical taxonomy, but it never drops or repairs rows. Anything it cannot map is kept and flagged so that the
quality checks can see it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

CHANNEL_MAP = {
    "google / cpc": "paid_search",
    "facebook / paid_social": "paid_social",
    "instagram / paid_social": "paid_social",
    "newsletter / email": "email",
    "google / organic": "organic_search",
    "bing / organic": "organic_search",
    "(direct) / (none)": "direct",
}
LEAD_SOURCE_MAP = {
    "google ads": "paid_search",
    "facebook": "paid_social",
    "newsletter": "email",
    "organic": "organic_search",
    "direct": "direct",
}
STATUS_MAP = {
    "marketing qualified lead": "MQL", "mql": "MQL",
    "sales qualified lead": "SQL", "sql": "SQL",
    "closed won": "Closed Won", "won": "Closed Won",
    "closed lost": "Closed Lost", "lost": "Closed Lost",
    "new": "New",
}
UNMAPPED = "unmapped"


def normalize_label(value) -> str | float:
    """Lower-case, trim and tidy spacing around slashes. Keeps nulls as NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    text = re.sub(r"\s+", " ", str(value).strip().lower())
    return re.sub(r"\s*/\s*", " / ", text)


def parse_money(value) -> float:
    """'$1,234.50' -> 1234.5. Returns NaN when the text is not money."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return np.nan


def clean_email(series: pd.Series) -> pd.Series:
    """Trim and lower-case; blank strings become real nulls."""
    out = series.astype("string").str.strip().str.lower()
    return out.mask(out.fillna("") == "")


@dataclass
class Staging:
    ads: pd.DataFrame
    web: pd.DataFrame
    leads: pd.DataFrame
    orders: pd.DataFrame
    parse_errors: dict[str, int] = field(default_factory=dict)
    raw_rows: dict[str, int] = field(default_factory=dict)


def _read(raw_dir: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(raw_dir / f"{name}.csv", dtype=str, keep_default_na=True)


def load_staging(raw_dir: Path) -> Staging:
    raw_dir = Path(raw_dir)
    errors: dict[str, int] = {}
    rows: dict[str, int] = {}

    # ---- advertising platforms (two export formats)
    s = _read(raw_dir, "search_ads")
    g = _read(raw_dir, "social_ads")
    rows["search_ads"], rows["social_ads"] = len(s), len(g)
    search = pd.DataFrame({
        "date": pd.to_datetime(s["Day"], format="%Y-%m-%d", errors="coerce"), "platform": "search_platform",
        "channel": "paid_search", "campaign": s["Campaign"], "spend": s["Cost"].map(parse_money),
        "impressions": pd.to_numeric(s["Impr."], errors="coerce"), "clicks": pd.to_numeric(s["Clicks"], errors="coerce"),
        "platform_conversions": pd.to_numeric(s["Conversions"], errors="coerce")})
    social = pd.DataFrame({
        "date": pd.to_datetime(g["date"], format="%m/%d/%Y", errors="coerce"), "platform": "social_platform",
        "channel": "paid_social", "campaign": g["campaign_name"], "spend": g["spend_usd"].map(parse_money),
        "impressions": pd.to_numeric(g["impressions"], errors="coerce"), "clicks": pd.to_numeric(g["link_clicks"], errors="coerce"),
        "platform_conversions": pd.to_numeric(g["results"], errors="coerce")})
    ads = pd.concat([search, social], ignore_index=True)
    ads["campaign"] = ads["campaign"].astype("string").str.strip().mask(lambda c: c.fillna("") == "")
    errors["ads"] = int(ads[["date", "spend", "impressions", "clicks"]].isna().any(axis=1).sum())

    # ---- web analytics
    w = _read(raw_dir, "web_sessions")
    rows["web_sessions"] = len(w)
    label = w["source_medium"].map(normalize_label)
    web = pd.DataFrame({
        "date": pd.to_datetime(w["date"], format="%Y-%m-%d", errors="coerce"), "source_medium": label,
        "channel": label.map(CHANNEL_MAP).fillna(UNMAPPED), "sessions": pd.to_numeric(w["sessions"], errors="coerce"),
        "transactions": pd.to_numeric(w["transactions"], errors="coerce"), "revenue": pd.to_numeric(w["revenue"], errors="coerce")})
    errors["web"] = int(web[["date", "sessions", "transactions", "revenue"]].isna().any(axis=1).sum())

    # ---- CRM leads
    l = _read(raw_dir, "crm_leads")
    rows["crm_leads"] = len(l)
    created = pd.to_datetime(l["created_at"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    status_norm = l["status"].map(normalize_label)
    leads = pd.DataFrame({
        "lead_id": l["lead_id"], "created_at": created, "created_date": created.dt.normalize(),
        "email": clean_email(l["email"]), "channel": l["lead_source"].map(normalize_label).map(LEAD_SOURCE_MAP).fillna(UNMAPPED),
        "status_raw": l["status"], "status": status_norm.map(STATUS_MAP).fillna(UNMAPPED), "owner": l["owner"]})
    errors["leads"] = int(leads["created_at"].isna().sum())

    # ---- orders
    o = _read(raw_dir, "orders")
    rows["orders"] = len(o)
    olabel = o["channel"].map(normalize_label)
    orders = pd.DataFrame({
        "order_id": o["order_id"], "order_date": pd.to_datetime(o["order_date"], format="%Y-%m-%d", errors="coerce"),
        "customer_email": clean_email(o["customer_email"]), "source_medium": olabel,
        "channel": olabel.map(CHANNEL_MAP).fillna(UNMAPPED), "revenue": pd.to_numeric(o["revenue"], errors="coerce")})
    errors["orders"] = int(orders[["order_date", "revenue"]].isna().any(axis=1).sum())

    return Staging(ads=ads, web=web, leads=leads, orders=orders, parse_errors=errors, raw_rows=rows)
