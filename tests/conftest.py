import numpy as np
import pandas as pd
import pytest

from mktg_pipeline import anomalies, checks, warehouse
from mktg_pipeline.generate import build_clean, export_raw, generate, inject_defects
from mktg_pipeline.ingest import load_staging


@pytest.fixture(scope="session")
def raw_clean():
    """Exported raw sources with no defects (built once, copied by tests)."""
    return export_raw(build_clean(seed=7), None, np.random.default_rng(0))


def write_raw(raw, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in raw.items():
        df.to_csv(folder / f"{name}.csv", index=False)
    return folder


def run_checks_on(folder, legacy_dashboard=False):
    stg = load_staging(folder)
    con = warehouse.build(stg)
    mart = warehouse.read_table(con, "mart_channel_daily")
    inc = anomalies.detect(mart)
    ctx = checks.Context(con, stg, mart, warehouse.dashboard_extract(con, legacy_dashboard), inc)
    return checks.run_checks(ctx), ctx, inc


@pytest.fixture(scope="session")
def clean_dir(tmp_path_factory, raw_clean):
    return write_raw(raw_clean, tmp_path_factory.mktemp("clean"))


@pytest.fixture(scope="session")
def clean_run(clean_dir):
    return run_checks_on(clean_dir)


@pytest.fixture(scope="session")
def defect_dir(tmp_path_factory):
    folder = tmp_path_factory.mktemp("defects")
    generate(folder, seed=7, defects=True)
    return folder


@pytest.fixture(scope="session")
def defect_run(defect_dir):
    return run_checks_on(defect_dir, legacy_dashboard=True)


def isolated(raw_clean, defect_id, tmp_path):
    """Inject exactly one defect into a copy of the clean data and write it out."""
    raw, manifest = inject_defects({k: v.copy() for k, v in raw_clean.items()}, np.random.default_rng(3), only={defect_id})
    return write_raw(raw, tmp_path), manifest
