import numpy as np
import pandas as pd
import pytest

from mktg_pipeline import anomalies
from mktg_pipeline.generate import build_clean, export_raw
from tests.conftest import run_checks_on, write_raw


def weekly_series(n=120, seed=0, noise=0.06):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n)
    pattern = np.array([1.0, 1.05, 1.05, 1.0, 0.95, 0.8, 0.75])[idx.dayofweek]
    return pd.Series(1000 * pattern * rng.lognormal(0, noise, n), index=idx)


def test_clean_weekly_series_raises_no_alarm_across_seeds():
    for seed in range(20):
        assert not anomalies.flag(anomalies.score_series(weekly_series(seed=seed))).any(), seed


def test_a_spike_is_detected_and_a_normal_weekend_is_not():
    s = weekly_series()
    s.iloc[60] *= 4
    inc = anomalies.incidents(anomalies.score_series(s))
    assert len(inc) == 1 and inc.loc[0, "start"] == s.index[60] and inc.loc[0, "direction"] == "spike"


def test_a_drop_to_zero_is_detected_and_consecutive_days_form_one_incident():
    s = weekly_series()
    s.iloc[70:74] = 0
    inc = anomalies.incidents(anomalies.score_series(s))
    assert len(inc) == 1 and inc.loc[0, "days"] == 4 and inc.loc[0, "direction"] == "drop"


def test_two_separate_events_make_two_incidents():
    s = weekly_series()
    s.iloc[50] *= 5
    s.iloc[90] = 0
    assert len(anomalies.incidents(anomalies.score_series(s))) == 2


def test_missing_values_are_skipped_not_flagged():
    s = weekly_series()
    s.iloc[40:43] = np.nan
    scored = anomalies.score_series(s)
    assert scored["z"].iloc[40:43].isna().all() and not anomalies.flag(scored).any()


def test_detection_is_scale_invariant():
    s = weekly_series()
    s.iloc[60] *= 4
    small = anomalies.incidents(anomalies.score_series(s / 10))
    large = anomalies.incidents(anomalies.score_series(s * 100))
    assert list(small["start"]) == list(large["start"]) == [s.index[60]]


def test_weekday_pattern_does_not_trigger_false_alarms():
    s = weekly_series(noise=0.02)  # strong weekly shape, tiny noise: a plain moving average would flag weekends
    assert not anomalies.flag(anomalies.score_series(s)).any()


def test_threshold_controls_sensitivity():
    s = weekly_series()
    s.iloc[60] *= 1.6
    scored = anomalies.score_series(s)
    assert anomalies.flag(scored, threshold=3).sum() >= 1 > anomalies.flag(scored, threshold=50).sum()


def test_the_injected_incidents_are_found_on_the_right_dates_and_nothing_else(defect_run):
    _, _, inc = defect_run
    assert len(inc) == 2
    spike = inc[inc.metric == "spend"].iloc[0]
    drop = inc[inc.metric == "transactions"].iloc[0]
    assert (spike.channel, str(spike.start.date()), spike.direction) == ("paid_social", "2025-04-17", "spike")
    assert (drop.channel, str(drop.start.date()), drop.end.date().isoformat(), drop.direction) == ("paid_search", "2025-03-10", "2025-03-13", "drop")


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_no_false_incidents_on_clean_data_for_several_seeds(tmp_path, seed):
    raw = export_raw(build_clean(seed=seed), None, np.random.default_rng(0))
    res, _, inc = run_checks_on(write_raw(raw, tmp_path))
    assert len(inc) == 0 and (res.status == "pass").all()
