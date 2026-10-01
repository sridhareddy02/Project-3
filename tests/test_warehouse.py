import numpy as np
import pandas as pd

from mktg_pipeline import warehouse


def count(con, table):
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_dimensions(clean_run):
    _, ctx, _ = clean_run
    assert count(ctx.con, "dim_date") == 181
    assert count(ctx.con, "dim_channel") == 5
    assert warehouse.read_table(ctx.con, "dim_date")["date"].is_unique


def test_core_tables_keep_all_valid_rows_on_clean_data(clean_run):
    _, ctx, _ = clean_run
    stg = ctx.staging
    assert count(ctx.con, "fact_orders") == len(stg.orders)
    assert count(ctx.con, "fact_leads") == len(stg.leads)
    assert count(ctx.con, "quarantine_orders") == 0 and count(ctx.con, "quarantine_web") == 0


def test_mart_grid_is_complete_and_totals_tie_to_the_facts(clean_run):
    _, ctx, _ = clean_run
    mart = ctx.mart
    assert len(mart) == 181 * 5
    assert not mart.duplicated(["date", "channel"]).any()
    fact_rev = ctx.con.execute("SELECT SUM(revenue) FROM fact_orders").fetchone()[0]
    assert np.isclose(mart["order_revenue"].sum(), fact_rev)
    assert np.isclose(mart["spend"].sum(), ctx.con.execute("SELECT SUM(spend) FROM fact_ad_spend").fetchone()[0])
    assert mart["leads"].sum() == count(ctx.con, "fact_leads")


def test_defects_are_quarantined_not_merged_or_silently_dropped(defect_run):
    _, ctx, _ = defect_run
    assert count(ctx.con, "quarantine_web") == 6
    assert count(ctx.con, "quarantine_orders") == 8
    reasons = set(warehouse.read_table(ctx.con, "quarantine_orders")["reason"])
    assert reasons == {"non-positive revenue", "order date in the future"}
    assert count(ctx.con, "fact_orders") + 8 == len(ctx.staging.orders)


def test_lead_deduplication_rules(defect_run, clean_run):
    _, ctx, _ = defect_run
    fl = warehouse.read_table(ctx.con, "fact_leads")
    with_email = fl.dropna(subset=["email"])
    assert with_email["email"].is_unique and fl["lead_id"].is_unique
    # exact and near duplicates collapse back to the clean lead count; leads with no email each stay
    assert len(fl) == len(clean_run[1].staging.leads)


def test_missing_campaign_is_labelled_not_dropped(defect_run):
    _, ctx, _ = defect_run
    assert ctx.con.execute("SELECT COUNT(*) FROM fact_ad_spend WHERE campaign = '(missing)'").fetchone()[0] > 0
    stg_spend = ctx.staging.ads["spend"].sum()
    assert np.isclose(ctx.con.execute("SELECT SUM(spend) FROM fact_ad_spend").fetchone()[0], stg_spend)


def test_missing_days_appear_as_nulls_in_the_mart(defect_run):
    _, ctx, _ = defect_run
    gap = ctx.mart[ctx.mart["date"].isin(["2025-05-05", "2025-05-06", "2025-05-07"])]
    assert gap["sessions"].isna().all() and gap["order_revenue"].notna().any()


def test_faulty_dashboard_query_inflates_revenue(defect_run):
    _, ctx, _ = defect_run
    good = warehouse.dashboard_extract(ctx.con, faulty=False).set_index("channel")["revenue"]
    bad = warehouse.dashboard_extract(ctx.con, faulty=True).set_index("channel")["revenue"]
    assert (bad > 10 * good).all()
    assert np.isclose(good.sum(), ctx.mart["order_revenue"].sum())
