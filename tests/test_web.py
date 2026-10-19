import json
import threading
import urllib.error
import urllib.request

import pytest

from s200.mibeacon import Reading
from s200.store import Store
from s200.web import make_server


@pytest.fixture
def server(tmp_path):
    store = Store(tmp_path / "w.sqlite3")
    store.add(Reading(1, 70.0, 1000))
    store.add(Reading(2, 55.0, 2000))
    srv = make_server(store, port=0, profile_id=1, height_cm=170, goal_kg=65.0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url) as res:
        return res.status, res.headers["Content-Type"], res.read()


def test_api_readings_filters_profile(server):
    status, ctype, body = get(server + "/api/readings")
    assert status == 200 and ctype == "application/json"
    data = json.loads(body)
    assert data == {
        "readings": [{"ts": 1000, "profile_id": 1, "weight_kg": 70.0}],
        "height_cm": 170,
        "goal_kg": 65.0,
    }


def test_api_since_validation(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(server + "/api/readings?since=abc")
    assert exc.value.code == 400


def test_index_served(server):
    status, ctype, body = get(server + "/")
    assert status == 200 and ctype.startswith("text/html")
    assert "体重ログ".encode() in body


def test_unknown_path_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(server + "/nope")
    assert exc.value.code == 404
