import http.client
import json
import threading
import time

import pytest

from s200.mibeacon import Reading
from s200.store import Store
from s200.web import WeightApp, make_server

T0 = 1_792_000_000


@pytest.fixture
def app(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    store.add(Reading(1, 75.0, T0))
    store.add(Reading(2, 55.0, T0 + 10))
    store.add(Reading(1, 74.6, T0 + 86400))
    return WeightApp(store, profile_id=1, defaults={"height_cm": 170, "goal_kg": 70.0})


@pytest.fixture
def server(app):
    srv = make_server(app, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def call(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    data = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=data, headers={"Content-Type": "application/json"})
    res = conn.getresponse()
    raw = res.read()
    ctype = res.getheader("Content-Type")
    conn.close()
    return res.status, (json.loads(raw) if ctype == "application/json" else raw)


def test_summary(server):
    status, s = call(server, "GET", "/api/summary")
    assert status == 200
    assert s["latest"]["weight_kg"] == 74.6
    assert s["delta_prev"] == pytest.approx(-0.4)
    assert s["goal_kg"] == 70.0 and s["count"] == 2


def test_readings_filters_profile_and_has_trend(server):
    status, body = call(server, "GET", "/api/readings")
    assert status == 200
    assert [r["weight_kg"] for r in body["readings"]] == [75.0, 74.6]
    assert all("trend_kg" in r and "status" in r for r in body["readings"])
    assert body["settings"]["height_cm"] == 170


def test_readings_since_validation(server):
    assert call(server, "GET", "/api/readings?since=abc")[0] == 400
    _, body = call(server, "GET", f"/api/readings?since={T0 + 1}")
    assert len(body["readings"]) == 1


def test_patch_status_toggle(server, app):
    rid = app.store.list(profile_id=1)[0]["id"]
    status, row = call(server, "PATCH", f"/api/readings/{rid}", {"status": "outlier"})
    assert status == 200 and row["status"] == "outlier" and row["manual"] is True
    assert call(server, "PATCH", f"/api/readings/{rid}", {"status": "nope"})[0] == 400
    assert call(server, "PATCH", "/api/readings/9999", {"status": "ok"})[0] == 404


def test_notes_api(server):
    status, note = call(
        server, "PUT", "/api/notes/2026-10-19", {"note": "焼肉", "tags": ["飲み会"]}
    )
    assert status == 200 and note["tags"] == ["飲み会"]
    assert call(server, "GET", "/api/notes/2026-10-19")[1]["note"] == "焼肉"
    _, body = call(server, "GET", "/api/notes?from=2026-10-01&to=2026-10-31")
    assert [n["date"] for n in body["notes"]] == ["2026-10-19"]
    assert call(server, "GET", "/api/notes?from=yesterday")[0] == 400
    assert call(server, "PUT", "/api/notes/2026-10-19", {"note": 1})[0] == 400


def test_settings_api(server):
    status, s = call(server, "PUT", "/api/settings", {"goal_kg": 68.5})
    assert status == 200 and s["goal_kg"] == 68.5
    assert call(server, "GET", "/api/summary")[1]["goal_kg"] == 68.5
    assert call(server, "PUT", "/api/settings", {"bogus": 1})[0] == 400


def test_bad_json_and_unknown_paths(server):
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=5)
    conn.request("PUT", "/api/settings", body=b"{oops", headers={"Content-Length": "5"})
    assert conn.getresponse().status == 400
    assert call(server, "GET", "/nope")[0] == 404
    assert call(server, "PUT", "/api/nope", {})[0] == 404


def test_index_served(server):
    status, body = call(server, "GET", "/")
    assert status == 200 and "体重ログ".encode() in body


def test_sse_pushes_new_reading(server, app):
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=5)
    conn.request("GET", "/api/stream")
    res = conn.getresponse()
    assert res.status == 200 and res.getheader("Content-Type") == "text/event-stream"
    assert res.fp.readline() == b": connected\n"
    res.fp.readline()

    def push():
        time.sleep(0.2)
        app.ingest(Reading(1, 74.2, T0 + 2 * 86400))

    threading.Thread(target=push).start()
    assert res.fp.readline() == b"event: reading\n"
    data = json.loads(res.fp.readline().removeprefix(b"data: "))
    assert data["reading"]["weight_kg"] == 74.2
    assert data["summary"]["latest"]["weight_kg"] == 74.2
    conn.close()


def test_ingest_ignores_other_profiles(app):
    assert app.ingest(Reading(2, 50.0, T0 + 5)) is None
    assert app.ingest(Reading(1, 74.0, T0 + 3 * 86400))["status"] == "ok"
