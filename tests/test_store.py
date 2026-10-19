import sqlite3

import pytest

from s200.mibeacon import Reading
from s200.store import Store

DAY = 86400
T0 = 1_792_000_000


def seed(store, weights, start=T0):
    for i, w in enumerate(weights):
        store.ingest(Reading(1, w, start + i * DAY))


def test_add_dedupes_repeated_broadcasts(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    r = Reading(profile_id=1, weight_kg=70.5, timestamp=1000)
    assert store.add(r) is True
    assert store.add(r) is False
    [row] = store.list()
    assert (row["ts"], row["weight_kg"], row["status"], row["manual"]) == (1000, 70.5, "ok", False)


def test_list_filters_and_orders(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    store.add(Reading(1, 71.0, 3000))
    store.add(Reading(2, 55.0, 2000))
    store.add(Reading(1, 70.0, 1000))
    assert [r["ts"] for r in store.list()] == [1000, 2000, 3000]
    assert [r["ts"] for r in store.list(profile_id=1)] == [1000, 3000]
    assert [r["ts"] for r in store.list(since=2000)] == [2000, 3000]


def test_migrates_v1_database_keeping_rows(tmp_path):
    path = tmp_path / "v1.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE readings (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL,"
        " profile_id INTEGER NOT NULL, weight_kg REAL NOT NULL, received_at INTEGER NOT NULL,"
        " UNIQUE (ts, profile_id));"
        "INSERT INTO readings VALUES (1, 1792402347, 1, 74.4, 1792402348);"
    )
    conn.commit()
    conn.close()

    store = Store(path)
    [row] = store.list()
    assert row["weight_kg"] == 74.4 and row["status"] == "ok"
    assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 2
    Store(path)  # re-opening is a no-op


def test_ingest_flags_outlier_but_keeps_it(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    seed(store, [74.4, 74.6, 74.3, 74.5, 74.2])
    row = store.ingest(Reading(1, 31.0, T0 + 5 * DAY))
    assert row["status"] == "outlier" and "トレンド" in row["reason"]
    assert len(store.list()) == 6
    assert len(store.list(only_ok=True)) == 5


def test_ingest_merges_quick_reweigh(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    store.ingest(Reading(1, 74.6, T0))
    store.ingest(Reading(1, 74.4, T0 + 120))
    first, second = store.list()
    assert first["status"] == "merged" and second["status"] == "ok"


def test_outlier_does_not_merge_previous(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    seed(store, [74.4, 74.6, 74.3, 74.5, 74.2])
    store.ingest(Reading(1, 31.0, T0 + 4 * DAY + 60))
    assert store.list()[4]["status"] == "ok"


def test_manual_override_is_respected(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    store.ingest(Reading(1, 74.6, T0))
    rid = store.list()[0]["id"]
    row = store.set_status(rid, "outlier")
    assert row["status"] == "outlier" and row["manual"] is True
    assert store.set_status(rid, "ok")["reason"] is None
    store.ingest(Reading(1, 74.4, T0 + 60))  # would normally merge rid
    assert store.get(rid)["status"] == "ok"
    with pytest.raises(ValueError):
        store.set_status(rid, "deleted")


def test_notes_roundtrip_and_clear(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    assert store.get_note("2026-10-19") == {"date": "2026-10-19", "note": "", "tags": []}
    store.put_note("2026-10-19", "焼肉", ["飲み会", " "])
    store.put_note("2026-10-20", "", ["運動"])
    assert store.get_note("2026-10-19") == {
        "date": "2026-10-19",
        "note": "焼肉",
        "tags": ["飲み会"],
    }
    assert [n["date"] for n in store.list_notes("2026-10-20")] == ["2026-10-20"]
    store.put_note("2026-10-19", "  ", [])
    assert [n["date"] for n in store.list_notes()] == ["2026-10-20"]


def test_settings_defaults_and_override(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    assert store.get_settings({"height_cm": 170}) == {
        "height_cm": 170,
        "goal_kg": None,
        "start_kg": None,
    }
    store.put_settings({"goal_kg": 68.0, "height_cm": 172})
    assert store.get_settings({"height_cm": 170})["height_cm"] == 172
    with pytest.raises(ValueError):
        store.put_settings({"nickname": 1})
    with pytest.raises(ValueError):
        store.put_settings({"goal_kg": "68"})


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "w.sqlite3"
    Store(path).add(Reading(1, 70.0, 1000))
    assert len(Store(path).list()) == 1
