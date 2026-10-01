import json

import numpy as np
import pandas as pd
import pytest

from mktg_pipeline.generate import SOURCE_MEDIUM, build_clean, generate
from mktg_pipeline.ingest import CHANNEL_MAP, STATUS_MAP, clean_email, load_staging, normalize_label, parse_money


def test_generation_is_deterministic(tmp_path):
    generate(tmp_path / "a", seed=3)
    generate(tmp_path / "b", seed=3)
    for name in ("orders", "crm_leads", "search_ads", "social_ads", "web_sessions"):
        assert (tmp_path / "a" / f"{name}.csv").read_bytes() == (tmp_path / "b" / f"{name}.csv").read_bytes()


def test_clean_world_is_internally_consistent():
    clean = build_clean(seed=2)
    web, orders = clean["web"], clean["orders"]
    by_day = orders.groupby(["order_date", "channel"]).agg(n=("order_id", "size"), rev=("revenue", "sum")).reset_index()
    merged = web.merge(by_day, left_on=["date", "channel"], right_on=["order_date", "channel"], how="left").fillna({"n": 0, "rev": 0})
    assert (merged["transactions"] == merged["n"]).all()
    assert np.allclose(merged["revenue"], merged["rev"], atol=0.01)
    assert orders["order_id"].is_unique and clean["leads"]["lead_id"].is_unique
    assert len(web) == 181 * 5


def test_raw_sources_really_are_messy(raw_clean):
    assert raw_clean["social_ads"]["spend_usd"].str.startswith("$").all()
    assert raw_clean["social_ads"]["date"].str.match(r"\d\d/\d\d/\d{4}").all()
    assert raw_clean["search_ads"]["Day"].str.match(r"\d{4}-\d\d-\d\d").all()
    assert set(raw_clean["orders"]["channel"]) == set(SOURCE_MEDIUM.values())


def test_defect_manifest_documents_everything(defect_dir):
    manifest = json.loads((defect_dir / "manifest.json").read_text())
    assert manifest["defects_injected"] and [d["id"] for d in manifest["defects"]] == [f"D{i:02d}" for i in range(1, 12)]
    assert all(d["expected_checks"] for d in manifest["defects"])


@pytest.mark.parametrize("raw,expected", [("$1,234.50", 1234.5), ("$0.99", 0.99), ("12", 12.0), (" $ 7 ", 7.0), ("-5.25", -5.25)])
def test_parse_money(raw, expected):
    assert parse_money(raw) == pytest.approx(expected)


def test_parse_money_returns_nan_for_non_money():
    assert np.isnan(parse_money("n/a")) and np.isnan(parse_money(None)) and np.isnan(parse_money(float("nan")))


def test_label_normalisation_collapses_case_and_spacing():
    assert normalize_label("  Google/CPC ") == "google / cpc"
    assert normalize_label("Facebook  /  Paid_Social") == "facebook / paid_social"
    assert normalize_label("(Direct) / (None)") == "(direct) / (none)"
    assert np.isnan(normalize_label(None))
    assert CHANNEL_MAP[normalize_label("GOOGLE / CPC")] == "paid_search"


def test_status_mapping_covers_every_generated_status(raw_clean):
    assert {normalize_label(s) for s in raw_clean["crm_leads"]["status"]} <= set(STATUS_MAP)


def test_email_cleaning_trims_lowercases_and_nulls_blanks():
    out = clean_email(pd.Series([" A@X.COM ", "", None, "b@y.com"]))
    assert out.tolist()[0] == "a@x.com" and out.isna().tolist() == [False, True, True, False]


def test_clean_staging_has_no_unmapped_or_unparseable_values(clean_dir):
    stg = load_staging(clean_dir)
    assert sum(stg.parse_errors.values()) == 0
    for df in (stg.web, stg.leads, stg.orders):
        assert (df["channel"] != "unmapped").all()
    assert (stg.leads["status"] != "unmapped").all()
    assert stg.ads["campaign"].notna().all()
    assert stg.ads["spend"].notna().all() and (stg.ads["spend"] >= 0).all()


def test_staging_keeps_every_row(clean_dir, raw_clean):
    stg = load_staging(clean_dir)
    assert len(stg.ads) == len(raw_clean["search_ads"]) + len(raw_clean["social_ads"])
    assert len(stg.orders) == len(raw_clean["orders"]) and len(stg.leads) == len(raw_clean["crm_leads"])
