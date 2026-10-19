from datetime import date, datetime

import pytest

from s200 import analysis as a

DAY = a.DAY
T0 = int(datetime(2026, 10, 1, 7, 0).timestamp())


def daily(weights, start=T0):
    return [(start + i * DAY, w) for i, w in enumerate(weights)]


def row(i, ts, w, status="ok", manual=False):
    return {
        "id": i,
        "ts": ts,
        "profile_id": 1,
        "weight_kg": w,
        "status": status,
        "reason": None,
        "manual": manual,
    }


# --- trend -----------------------------------------------------------------


def test_trend_starts_at_first_value_and_lags():
    t = a.trend_series(daily([75.0, 74.0]))
    assert t[0] == 75.0
    assert 74.0 < t[1] < 75.0
    # one day with tau=10 days moves ~9.5% of the gap
    assert t[1] == pytest.approx(75.0 - (1 - 2.718281828**-0.1), rel=1e-6)


def test_trend_handles_irregular_gaps():
    near = a.trend_series([(T0, 75.0), (T0 + 3600, 74.0)])[1]
    far = a.trend_series([(T0, 75.0), (T0 + 30 * DAY, 74.0)])[1]
    assert near > far  # longer gap -> trust the new value more


def test_trend_at_uses_only_prior_points():
    pts = daily([75.0, 74.0, 73.0])
    assert a.trend_at(pts, T0) is None
    assert a.trend_at(pts, T0 + DAY) == 75.0


# --- outliers --------------------------------------------------------------

STEADY = daily([74.4, 74.6, 74.3, 74.5, 74.2, 74.4])


def test_no_outlier_detection_with_little_history():
    assert a.detect_outlier(STEADY[:4], T0 + 10 * DAY, 30.0) is None


def test_child_on_scale_is_outlier():
    reason = a.detect_outlier(STEADY, T0 + 7 * DAY, 32.5)
    assert reason is not None and "-4" in reason


def test_holding_a_bag_is_outlier():
    assert a.detect_outlier(STEADY, T0 + 7 * DAY, 79.0) is not None


def test_normal_fluctuation_is_not_outlier():
    assert a.detect_outlier(STEADY, T0 + 7 * DAY, 75.3) is None
    assert a.detect_outlier(STEADY, T0 + 7 * DAY, 73.6) is None


def test_threshold_adapts_to_noisy_history():
    noisy = daily([74, 77, 73, 78, 72, 77, 73])
    assert a.detect_outlier(noisy, T0 + 8 * DAY, 78.5) is None


def test_merge_targets_within_window_only():
    rows = [
        row(1, T0, 74.5),
        row(2, T0 + 500, 74.4),
        row(3, T0 + 550, 74.3, status="outlier"),
        row(4, T0 + 560, 74.3, manual=True),
    ]
    assert a.merge_targets(rows, T0 + 700) == [2]


# --- pace / eta ------------------------------------------------------------


def test_pace_negative_when_losing():
    pts = daily([75 - 0.1 * i for i in range(14)])
    pace = a.pace_kg_per_week(pts, pts[-1][0])
    assert pace is not None and pace < 0


def test_pace_needs_span_of_days():
    pts = [(T0, 75.0), (T0 + DAY, 74.8)]
    assert a.pace_kg_per_week(pts, T0 + DAY) is None


def test_eta_only_when_heading_to_goal():
    now = T0
    assert a.eta_ts(75.0, 70.0, -0.5, now) == now + 10 * 7 * DAY
    assert a.eta_ts(75.0, 70.0, 0.2, now) is None
    assert a.eta_ts(69.0, 70.0, -0.5, now) is None
    assert a.eta_ts(75.0, None, -0.5, now) is None


# --- streaks ---------------------------------------------------------------


def test_streak_counts_until_gap():
    d = date(2026, 10, 10)
    days = {date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 6)}
    assert a.streak_days(days, d) == 3


def test_streak_alive_if_not_weighed_yet_today():
    days = {date(2026, 10, 8), date(2026, 10, 9)}
    assert a.streak_days(days, date(2026, 10, 10)) == 2
    assert a.streak_days(days, date(2026, 10, 11)) == 0


# --- milestones / summary --------------------------------------------------


def test_milestones_new_low_and_kg_lost():
    prior = daily([75.0, 74.6, 74.3, 74.1])
    latest = row(9, T0 + 5 * DAY, 73.9)
    kinds = [m.kind for m in a.milestones_for(latest, prior, 75.0, 70.0, 5, True)]
    assert kinds == ["lost_kg", "new_low"]


def test_goal_milestone_replaces_new_low():
    prior = daily([71.0, 70.6, 70.3, 70.1])
    latest = row(9, T0 + 5 * DAY, 69.9)
    kinds = [m.kind for m in a.milestones_for(latest, prior, 70.5, 70.0, 1, True)]
    assert "goal" in kinds and "new_low" not in kinds


def test_streak_milestone_only_on_first_weigh_in_of_day():
    prior = daily([75.0] * 6)
    latest = row(9, T0 + 6 * DAY, 75.0)
    assert [m.kind for m in a.milestones_for(latest, prior, None, None, 7, True)] == ["streak"]
    assert a.milestones_for(latest, prior, None, None, 7, False) == []


def test_summary_empty():
    s = a.summarize([], {}, T0)
    assert s["latest"] is None and s["count"] == 0 and s["comment"]


def test_summary_basic_fields():
    rows = [row(i + 1, ts, w) for i, (ts, w) in enumerate(daily([75.0, 74.8, 74.9]))]
    now = rows[-1]["ts"]
    s = a.summarize(rows, {"height_cm": 170, "goal_kg": 70.0}, now)
    assert s["delta_prev"] == pytest.approx(0.1)
    assert s["start_kg"] == 75.0
    assert s["delta_start"] == pytest.approx(-0.1)
    assert s["bmi"] == pytest.approx(74.9 / 1.7**2)
    assert s["streak_days"] == 3
    assert s["lowest_kg"] == 74.8


def test_summary_outlier_latest_excluded_from_stats():
    rows = [row(i + 1, ts, w) for i, (ts, w) in enumerate(daily([75.0, 74.8]))]
    rows.append(row(3, T0 + 2 * DAY, 30.0, status="outlier"))
    s = a.summarize(rows, {}, T0 + 2 * DAY)
    assert s["latest"]["status"] == "outlier"
    assert s["delta_prev"] is None and s["milestones"] == []
    assert "除外" in s["comment"]
    assert s["count"] == 2


def test_comment_variants():
    base = {"latest": {"status": "ok", "weight_kg": 74.0}, "milestones": []}
    assert "記録スタート" in a.comment_for({**base, "delta_prev": None, "pace_kg_per_week": None})
    assert "順調" in a.comment_for({**base, "delta_prev": 0.2, "pace_kg_per_week": -0.3})
    assert "下降中" in a.comment_for({**base, "delta_prev": -0.2, "pace_kg_per_week": -0.3})
    assert "立て直し" in a.comment_for({**base, "delta_prev": 0.2, "pace_kg_per_week": 0.3})
    assert "横ばい" in a.comment_for({**base, "delta_prev": 0.0, "pace_kg_per_week": 0.0})


def test_with_trend_carries_trend_over_excluded():
    rows = [row(1, T0, 75.0), row(2, T0 + DAY, 30.0, status="outlier"), row(3, T0 + 2 * DAY, 74.0)]
    out = a.with_trend(rows)
    assert out[0]["trend_kg"] == 75.0
    assert out[1]["trend_kg"] == 75.0
    assert 74.0 < out[2]["trend_kg"] < 75.0
