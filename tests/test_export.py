import csv
import io
import time

import pytest

from s200.export import DAILY_COLUMNS, READING_COLUMNS, daily_csv, readings_csv

# 2026-11-06 07:45:15 JST
T0 = 1_793_918_715


@pytest.fixture(autouse=True)
def tokyo(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def row(id, ts, kg, status="ok", reason=None):
    return {
        "id": id,
        "ts": ts,
        "profile_id": 1,
        "weight_kg": kg,
        "status": status,
        "reason": reason,
        "manual": False,
    }


def parse(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_readings_csv_columns_and_values():
    text = readings_csv(
        [row(1, T0, 71.2), row(2, T0 + 3600, 80.0, "outlier", "トレンドから +8.8 kg")]
    )
    assert text.splitlines()[0] == ",".join(READING_COLUMNS)
    first, second = parse(text)
    assert first == {
        "id": "1",
        "datetime": "2026-11-06T07:45:15+09:00",
        "date": "2026-11-06",
        "weight_kg": "71.20",
        "trend_kg": "71.20",
        "status": "ok",
        "reason": "",
        "profile_id": "1",
    }
    # Excluded readings are kept, and they don't move the trend.
    assert (second["status"], second["trend_kg"]) == ("outlier", "71.20")
    assert second["reason"] == "トレンドから +8.8 kg"


def test_readings_csv_empty_has_header_only():
    assert readings_csv([]) == ",".join(READING_COLUMNS) + "\n"


def test_daily_uses_last_included_weigh_in_per_day():
    rows = [
        row(1, T0, 71.6),  # 11-06 morning
        row(2, T0 + 3 * 3600, 71.2),  # 11-06 later: the day's value
        row(3, T0 + 4 * 3600, 90.0, "outlier"),  # excluded: ignored
        row(4, T0 + 86400, 71.0),  # 11-07
    ]
    days = parse(daily_csv(rows, []))
    assert [d["date"] for d in days] == ["2026-11-06", "2026-11-07"]
    assert (days[0]["weight_kg"], days[0]["count"]) == ("71.20", "2")
    assert days[1]["count"] == "1"
    assert float(days[0]["trend_kg"]) == pytest.approx(71.6 + (71.2 - 71.6) * 0.0124, abs=0.01)


def test_daily_joins_notes_including_days_without_weigh_in():
    rows = [row(1, T0, 71.2)]
    notes = [
        {"date": "2026-11-06", "note": "飲み会", "tags": ["飲み会", "外食"]},
        {"date": "2026-11-08", "note": "体調不良", "tags": []},
    ]
    days = parse(daily_csv(rows, notes))
    assert days[0] == {
        "date": "2026-11-06",
        "weight_kg": "71.20",
        "trend_kg": "71.20",
        "count": "1",
        "note": "飲み会",
        "tags": "飲み会;外食",
    }
    assert days[1] == {
        "date": "2026-11-08",
        "weight_kg": "",
        "trend_kg": "",
        "count": "0",
        "note": "体調不良",
        "tags": "",
    }


def test_daily_skips_days_with_only_excluded_readings():
    days = parse(daily_csv([row(1, T0, 90.0, "outlier")], []))
    assert days == []
    assert daily_csv([], []).splitlines() == [",".join(DAILY_COLUMNS)]
