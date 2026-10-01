"""Score the pipeline against the answer key: did it catch every injected defect, and nothing else?"""

from __future__ import annotations

import pandas as pd


def _dates_covered(defect: dict, incidents: pd.DataFrame) -> bool | None:
    """For defects with known dates, check that an incident overlaps them (None when not applicable)."""
    if "dates" not in defect or defect["id"] == "D08":
        return None
    dates = pd.to_datetime(defect["dates"])
    for r in incidents.itertuples():
        if r.start <= dates.max() and r.end >= dates.min():
            return True
    return False


def evaluate(manifest: dict, results: pd.DataFrame, incidents: pd.DataFrame) -> dict:
    failing = set(results.loc[results["status"] == "fail", "id"])
    rows = []
    expected_all, tolerated = set(), set()
    for d in manifest["defects"]:
        expected_all |= set(d["expected_checks"])
        tolerated |= set(d.get("also_triggers", []))
        caught_by = [c for c in d["expected_checks"] if c in failing]
        rows.append({
            "defect": d["id"], "type": d["type"], "expected_checks": ", ".join(d["expected_checks"]),
            "caught_by": ", ".join(caught_by), "caught": bool(caught_by), "incident_covers_dates": _dates_covered(d, incidents),
        })
    table = pd.DataFrame(rows)
    unexpected = sorted(failing - expected_all - tolerated)
    return {
        "defects_injected": len(rows),
        "defects_caught": int(table["caught"].sum()) if len(table) else 0,
        "recall": float(table["caught"].mean()) if len(table) else None,
        "unexpected_failures": unexpected,
        "table": table,
    }


def clean_run_summary(results: pd.DataFrame, incidents: pd.DataFrame) -> dict:
    """On clean data every check should pass and nothing should be flagged."""
    return {"failing_checks": results.loc[results["status"] == "fail", "id"].tolist(), "incidents": int(len(incidents))}
