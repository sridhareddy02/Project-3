import json

import pandas as pd

from mktg_pipeline import cli, evaluate, report


def test_evaluation_scores_full_detection(defect_dir, defect_run):
    res, _, inc = defect_run
    manifest = json.loads((defect_dir / "manifest.json").read_text())
    ev = evaluate.evaluate(manifest, res, inc)
    assert ev["defects_injected"] == 11 and ev["defects_caught"] == 11 and ev["recall"] == 1.0
    assert ev["unexpected_failures"] == []
    covered = ev["table"].set_index("defect")["incident_covers_dates"]
    assert covered["D06"] is True and covered["D07"] is True and pd.isna(covered["D01"])


def test_evaluation_notices_a_missed_defect(defect_dir, defect_run):
    res, _, inc = defect_run
    manifest = json.loads((defect_dir / "manifest.json").read_text())
    weakened = res.assign(status=lambda d: d["status"].where(d["id"] != "C04", "pass"))
    ev = evaluate.evaluate(manifest, weakened, inc)
    assert ev["defects_caught"] == 10 and not ev["table"].set_index("defect").loc["D01", "caught"]


def test_evaluation_flags_a_check_that_fires_for_no_reason(defect_dir, defect_run):
    res, _, inc = defect_run
    manifest = json.loads((defect_dir / "manifest.json").read_text())
    noisy = res.assign(status=lambda d: d["status"].where(d["id"] != "C03", "fail"))
    assert evaluate.evaluate(manifest, noisy, inc)["unexpected_failures"] == ["C03"]


def test_gate_flag_sets_the_exit_status(clean_dir, defect_dir, tmp_path):
    assert cli.main(["run", "--raw", str(clean_dir), "--out", str(tmp_path / "a"), "--gate"]) == 0
    assert cli.main(["run", "--raw", str(defect_dir), "--out", str(tmp_path / "b"), "--gate", "--legacy-dashboard"]) == 1
    assert cli.main(["run", "--raw", str(defect_dir), "--out", str(tmp_path / "c"), "--legacy-dashboard"]) == 0  # no --gate: report only


def test_demo_writes_both_reports_and_summaries(tmp_path):
    res = cli.demo(tmp_path, seed=5)
    assert res["clean"]["gate_passed"] and not res["defects"]["gate_passed"]
    for run in ("clean", "defects"):
        for name in ("report.html", "summary.md", "checks.csv", "incidents.csv", "mart_channel_daily.csv", "results.json", "spend.png"):
            assert (tmp_path / run / name).stat().st_size > 0
    payload = json.loads((tmp_path / "defects" / "results.json").read_text())
    assert payload["evaluation"]["recall"] == 1.0
    assert json.loads((tmp_path / "clean" / "results.json").read_text())["clean_run"] == {"failing_checks": [], "incidents": 0}
    html = (tmp_path / "defects" / "report.html").read_text()
    assert "synthetic" in html and "Detection scorecard" in html and "FAIL" in html


def test_markdown_summary_lists_only_failures(defect_run):
    res, _, inc = defect_run
    md = report.markdown_summary("T", res, inc)
    assert "Quality gate: FAIL" in md and "C04" in md and "C02 " not in md


def test_weekly_kpis_shape_and_arithmetic(clean_run):
    _, ctx, _ = clean_run
    k = report.weekly_kpis(ctx.mart).set_index("channel")
    assert set(k.index) == {"paid_search", "paid_social", "email", "organic_search", "direct"}
    assert k.loc["paid_search", "roas"] == k.loc["paid_search", "revenue"] / k.loc["paid_search", "spend"]
    assert pd.isna(k.loc["direct", "cac"]) and pd.isna(k.loc["direct", "roas"])
