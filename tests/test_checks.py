import pandas as pd
import pytest

from mktg_pipeline import checks
from tests.conftest import isolated, run_checks_on

FAILING = lambda res: set(res.loc[res.status == "fail", "id"])  # noqa: E731


def test_clean_data_passes_every_check_and_the_gate(clean_run):
    res, _, inc = clean_run
    assert len(res) == 23 and (res.status == "pass").all()
    assert checks.gate_passed(res) and len(inc) == 0


def test_full_defect_set_fails_the_gate_with_the_exact_counts(defect_run):
    res, _, _ = defect_run
    assert not checks.gate_passed(res)
    n = res.set_index("id")["failing_rows"]
    assert (n["C01"], n["C04"], n["C05"], n["C07"], n["C08"], n["C09"], n["C10"], n["C12"], n["C13"], n["C15"]) == (3, 60, 40, 80, 15, 25, 6, 5, 3, 4)
    assert n["C18"] == 5 and n["C20"] == 1 and n["C21"] == 1


# each defect injected ALONE must trip exactly the checks documented for it, and nothing else
ISOLATED = {
    "D01": {"C04"}, "D02": {"C05"}, "D03": {"C07"}, "D04": {"C08"}, "D05": {"C09"},
    "D06": {"C20"}, "D07": {"C15", "C16", "C21"}, "D08": {"C01"}, "D09": {"C12", "C13"}, "D10": {"C10"},
}


@pytest.mark.parametrize("defect_id,expected", ISOLATED.items())
def test_each_check_is_specific_to_its_defect(raw_clean, tmp_path, defect_id, expected):
    folder, manifest = isolated(raw_clean, defect_id, tmp_path)
    res, _, _ = run_checks_on(folder)
    assert FAILING(res) == expected, f"{defect_id} tripped {sorted(FAILING(res))}"
    assert set(manifest[0]["expected_checks"]) <= FAILING(res)


def test_dashboard_check_catches_the_fanout_bug_and_only_that(clean_dir):
    res, _, _ = run_checks_on(clean_dir, legacy_dashboard=True)
    assert FAILING(res) == {"C18"}


def test_severity_decides_the_gate(defect_run):
    res, _, _ = defect_run
    warn_only = res[res.severity == "warn"]
    assert (warn_only.status == "fail").any()
    assert checks.gate_passed(res.assign(status=lambda d: d.status.where(d.severity == "warn", "pass")))


def test_every_check_has_a_unique_id_and_valid_severity():
    ids = [c.id for c in checks.CHECKS]
    assert len(ids) == len(set(ids)) == 23
    assert {c.severity for c in checks.CHECKS} <= {"error", "warn"}
