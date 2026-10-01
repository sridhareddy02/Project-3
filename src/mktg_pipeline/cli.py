"""Command line: ``python -m mktg_pipeline generate | run | demo``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import anomalies, checks, evaluate, report, warehouse
from .generate import END, START, generate
from .ingest import load_staging


def run_pipeline(raw: Path, out: Path, db: str | Path = ":memory:", legacy_dashboard: bool = False, title: str | None = None) -> dict:
    """Ingest, build the warehouse, run every check, detect anomalies and write the reports."""
    raw, out = Path(raw), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stg = load_staging(raw)
    con = warehouse.build(stg, db)
    mart = warehouse.read_table(con, "mart_channel_daily")
    incidents = anomalies.detect(mart)
    dashboard = warehouse.dashboard_extract(con, faulty=legacy_dashboard)
    ctx = checks.Context(con, stg, mart, dashboard, incidents)
    results = checks.run_checks(ctx)
    passed = checks.gate_passed(results)

    manifest_path = raw / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if manifest and manifest.get("defects_injected"):
        evaluation = evaluate.evaluate(manifest, results, incidents)
    else:
        evaluation = None
    clean = evaluate.clean_run_summary(results, incidents) if manifest and not manifest.get("defects_injected") else None

    title = title or "Marketing data quality report"
    report.build_report(out, title, results, incidents, mart, {"start": START, "end": END}, evaluation)
    summary = report.markdown_summary(title, results, incidents, evaluation)
    (out / "summary.md").write_text(summary)
    results.to_csv(out / "checks.csv", index=False)
    incidents.to_csv(out / "incidents.csv", index=False)
    mart.to_csv(out / "mart_channel_daily.csv", index=False)
    payload = {
        "gate_passed": passed,
        "checks_total": len(results), "checks_failed": int((results.status == "fail").sum()),
        "incidents": len(incidents),
        "evaluation": None if evaluation is None else {k: v for k, v in evaluation.items() if k != "table"},
        "clean_run": clean,
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str))
    con.close()
    return {**payload, "results": results, "incidents": incidents, "summary": summary}


def demo(out: Path, seed: int = 7) -> dict:
    """Generate a clean and a broken dataset, run the pipeline on both and write both reports."""
    out = Path(out)
    base = out / "_raw"
    generate(base / "clean", seed, defects=False)
    generate(base / "defects", seed, defects=True)
    clean = run_pipeline(base / "clean", out / "clean", title="Clean data: every check should pass")
    broken = run_pipeline(base / "defects", out / "defects", legacy_dashboard=True, title="Data with 11 injected defects")
    return {"clean": clean, "defects": broken}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mktg_pipeline", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write the five raw CSV sources")
    g.add_argument("--out", type=Path, default=Path("data/raw"))
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--defects", action="store_true", help="inject the 11 documented defects and write manifest.json")

    r = sub.add_parser("run", help="run the pipeline on a folder of raw CSVs")
    r.add_argument("--raw", type=Path, default=Path("data/raw"))
    r.add_argument("--out", type=Path, default=Path("reports/latest"))
    r.add_argument("--db", default=":memory:", help="SQLite file to keep the warehouse in (default: in memory)")
    r.add_argument("--legacy-dashboard", action="store_true", help="use the buggy dashboard query to demonstrate reconciliation")
    r.add_argument("--gate", action="store_true", help="exit with status 1 if any error-level check fails")

    d = sub.add_parser("demo", help="generate clean and broken data, run both, write reports")
    d.add_argument("--out", type=Path, default=Path("reports"))
    d.add_argument("--seed", type=int, default=7)

    args = parser.parse_args(argv)
    if args.cmd == "generate":
        manifest = generate(args.out, args.seed, args.defects)
        print(f"Wrote raw sources to {args.out} ({len(manifest)} defects injected)")
        return 0
    if args.cmd == "run":
        res = run_pipeline(args.raw, args.out, args.db, args.legacy_dashboard)
        print(res["summary"])
        return 1 if args.gate and not res["gate_passed"] else 0
    res = demo(args.out, args.seed)
    for name, r_ in res.items():
        print(f"\n=== {name} ===\n{r_['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
