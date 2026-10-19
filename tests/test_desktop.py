import json
import threading
import urllib.request

from s200.config import Config
from s200.desktop import daemon_alive, resolve_url
from s200.mibeacon import Reading
from s200.store import Store
from s200.web import make_server


def _config(tmp_path, port):
    return Config(
        bindkey=bytes(16),
        mac=bytes(6),
        profile_id=None,
        height_cm=170,
        goal_kg=65.0,
        db_path=tmp_path / "w.sqlite3",
        port=port,
    )


def test_daemon_alive_false_when_nothing_listens():
    assert daemon_alive("http://127.0.0.1:9", timeout=0.2) is False


def test_resolve_url_prefers_running_daemon(tmp_path):
    srv = make_server(Store(tmp_path / "d.sqlite3"), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        assert resolve_url(_config(tmp_path, port)) == f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()


def test_resolve_url_falls_back_to_local_db(tmp_path):
    Store(tmp_path / "w.sqlite3").add(Reading(1, 74.4, 1000))
    url = resolve_url(_config(tmp_path, 9))
    assert not url.endswith(":9")
    with urllib.request.urlopen(url + "/api/readings") as res:
        assert json.loads(res.read())["readings"][0]["weight_kg"] == 74.4
