from s200.mibeacon import Reading
from s200.store import Store


def test_add_dedupes_repeated_broadcasts(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    r = Reading(profile_id=1, weight_kg=70.5, timestamp=1000)
    assert store.add(r) is True
    assert store.add(r) is False
    assert store.list() == [{"ts": 1000, "profile_id": 1, "weight_kg": 70.5}]


def test_list_filters_and_orders(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    store.add(Reading(1, 71.0, 3000))
    store.add(Reading(2, 55.0, 2000))
    store.add(Reading(1, 70.0, 1000))
    assert [r["ts"] for r in store.list()] == [1000, 2000, 3000]
    assert [r["ts"] for r in store.list(profile_id=1)] == [1000, 3000]
    assert [r["ts"] for r in store.list(since=2000)] == [2000, 3000]


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "w.sqlite3"
    Store(path).add(Reading(1, 70.0, 1000))
    assert len(Store(path).list()) == 1
