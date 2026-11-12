import json
import re
import sqlite3
import threading
import time
from datetime import date

import pytest

from s200.drive import SHEET_MIME, DriveClient, DriveSync, State, Syncer
from s200.mibeacon import Reading
from s200.store import Store
from s200.web import EventHub

DAY1 = date(2026, 11, 6)
DAY2 = date(2026, 11, 7)


class FakeResponse:
    def __init__(self, status: int, body: dict | None = None):
        self.status_code = status
        self.content = json.dumps(body).encode() if body is not None else b""
        self.text = self.content.decode()
        self._body = body

    def json(self):
        return self._body


class FakeDrive:
    """In-memory Drive v3 that understands the calls DriveClient makes."""

    def __init__(self):
        self.files: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail = 0  # number of upcoming requests to fail with 500
        self.lock = threading.Lock()
        self._n = 0

    def _new(self, **meta) -> str:
        self._n += 1
        fid = f"id{self._n}"
        self.files[fid] = {"trashed": False, **meta}
        return fid

    def named(self, name: str) -> list[dict]:
        return [f for f in self.files.values() if f["name"] == name and not f["trashed"]]

    def request(self, method, url, params=None, json=None, data=None, headers=None, timeout=None):
        with self.lock:
            self.calls.append((method, url))
            if self.fail:
                self.fail -= 1
                return FakeResponse(500, {"error": "boom"})
            path = url.split("/drive/v3", 1)[1]
            if method == "POST" and path == "/files" and "upload" not in url:
                return FakeResponse(200, {"id": self._new(content=None, **json)})
            if method == "POST" and path == "/files":
                meta_json, content = self._multipart(data, headers["Content-Type"])
                return FakeResponse(200, {"id": self._new(content=content, **meta_json)})
            if method == "GET" and path == "/files":
                parent = re.match(r"'(\w+)' in parents", params["q"]).group(1)
                kids = [
                    {"id": fid, "name": f["name"]}
                    for fid, f in self.files.items()
                    if parent in f.get("parents", []) and not f["trashed"]
                ]
                return FakeResponse(200, {"files": kids})
            fid = path.removeprefix("/files/")
            if fid not in self.files:
                return FakeResponse(404, {"error": "notFound"})
            f = self.files[fid]
            if method == "GET":
                return FakeResponse(200, {"id": fid, "trashed": f["trashed"]})
            if method == "PATCH":
                f["content"] = data
                f["updates"] = f.get("updates", 0) + 1
                return FakeResponse(200, {"id": fid, "trashed": f["trashed"]})
            if method == "DELETE":
                del self.files[fid]
                return FakeResponse(204)
            raise AssertionError(f"unexpected {method} {url}")

    @staticmethod
    def _multipart(body: bytes, content_type: str):
        boundary = content_type.split("boundary=")[1].encode()
        parts = [p for p in body.split(b"--" + boundary) if p.strip(b"-\r\n")]
        meta = json.loads(parts[0].split(b"\r\n\r\n", 1)[1].strip())
        content = parts[1].split(b"\r\n\r\n", 1)[1][: -len(b"\r\n")]
        return meta, content


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "w.sqlite3")
    s.ingest(Reading(1, 71.2, 1_793_918_715))
    s.put_note("2026-11-06", "飲み会", ["飲み会"])
    yield s
    s.close()


def make(store, tmp_path, drive=None, keep=30):
    drive = drive or FakeDrive()
    state = State(tmp_path / ".drive" / "state.json")
    return drive, Syncer(store, DriveClient(drive), state, backup_keep=keep)


def test_first_sync_creates_folder_sheets_csvs_and_backup(store, tmp_path):
    drive, syncer = make(store, tmp_path)
    written = syncer.sync(DAY1)
    assert written == [
        "weights",
        "weights.csv",
        "daily",
        "daily.csv",
        "backups/weights-2026-11-06.sqlite3",
    ]
    [folder] = drive.named("体重ログ")
    [sheet] = drive.named("weights")
    [csv_file] = drive.named("weights.csv")
    assert folder["mimeType"] == "application/vnd.google-apps.folder"
    assert sheet["mimeType"] == SHEET_MIME  # converted to a Google Sheet
    assert "mimeType" not in csv_file  # plain CSV stays CSV
    assert csv_file["content"].decode().splitlines()[1].endswith(",71.20,71.20,ok,,1")
    assert "飲み会" in drive.named("daily.csv")[0]["content"].decode()

    [backup] = drive.named("weights-2026-11-06.sqlite3")
    restored = tmp_path / "restored.sqlite3"
    restored.write_bytes(backup["content"])
    assert sqlite3.connect(restored).execute("SELECT weight_kg FROM readings").fetchall() == [
        (71.2,)
    ]
    # ids are persisted privately for the next run
    state_path = tmp_path / ".drive" / "state.json"
    assert state_path.stat().st_mode & 0o777 == 0o600
    assert set(json.loads(state_path.read_text())["files"]) == {
        "weights",
        "weights.csv",
        "daily",
        "daily.csv",
    }


def test_second_sync_updates_in_place_without_new_backup(store, tmp_path):
    drive, syncer = make(store, tmp_path)
    syncer.sync(DAY1)
    count = len(drive.files)
    store.ingest(Reading(1, 70.8, 1_793_918_715 + 86400))

    # A fresh Syncer reads the saved state, as after a daemon restart.
    _, again = make(store, tmp_path, drive)
    assert again.sync(DAY1) == ["weights", "weights.csv", "daily", "daily.csv"]
    assert len(drive.files) == count
    [sheet] = drive.named("weights")
    assert sheet["updates"] == 1
    assert b"70.80" in sheet["content"]


def test_deleted_or_trashed_files_are_recreated(store, tmp_path):
    drive, syncer = make(store, tmp_path)
    syncer.sync(DAY1)
    [sheet_id] = [fid for fid, f in drive.files.items() if f["name"] == "weights"]
    [csv_id] = [fid for fid, f in drive.files.items() if f["name"] == "daily.csv"]
    del drive.files[sheet_id]
    drive.files[csv_id]["trashed"] = True

    syncer.sync(DAY1)
    assert len(drive.named("weights")) == 1
    assert len(drive.named("daily.csv")) == 1


def test_deleted_folder_starts_over(store, tmp_path):
    drive, syncer = make(store, tmp_path)
    syncer.sync(DAY1)
    drive.files.clear()
    written = syncer.sync(DAY1)
    assert "backups/weights-2026-11-06.sqlite3" in written
    assert len(drive.named("体重ログ")) == 1
    assert len(drive.named("backups")) == 1


def test_backups_rotate_keeping_newest(store, tmp_path):
    drive, syncer = make(store, tmp_path, keep=2)
    for d in range(1, 5):
        syncer.sync(date(2026, 11, d))
    names = sorted(f["name"] for f in drive.files.values() if f["name"].endswith(".sqlite3"))
    assert names == ["weights-2026-11-03.sqlite3", "weights-2026-11-04.sqlite3"]


def wait_for(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_worker_syncs_at_start_and_debounces_bursts(store, tmp_path):
    drive, syncer = make(store, tmp_path)
    hub = EventHub()
    worker = DriveSync(syncer, hub, debounce=0.2, tick=0.01, today=lambda: DAY1)
    worker.start()
    try:
        assert wait_for(lambda: worker.status()["last_success"] is not None)
        sheet = drive.named("weights")[0]
        for _ in range(5):
            hub.publish("reading", {})
            time.sleep(0.02)
        assert wait_for(lambda: sheet.get("updates") == 1)
        time.sleep(0.3)
        assert sheet["updates"] == 1  # five events, one upload
    finally:
        worker.stop()


def test_worker_retries_after_failure_and_reports_status(store, tmp_path):
    drive, syncer = make(store, tmp_path)
    drive.fail = 1
    worker = DriveSync(syncer, EventHub(), retry_min=0.1, tick=0.01, today=lambda: DAY1)
    worker.start()
    try:
        assert wait_for(lambda: worker.status()["last_error"] is not None)
        assert "500" in worker.status()["last_error"]
        assert wait_for(lambda: worker.status()["last_success"] is not None)
        assert worker.status()["last_error"] is None
        assert len(drive.named("weights")) == 1
    finally:
        worker.stop()


def test_worker_takes_backup_when_the_day_changes(store, tmp_path):
    drive, syncer = make(store, tmp_path)
    today = [DAY1]
    worker = DriveSync(syncer, EventHub(), tick=0.01, today=lambda: today[0])
    worker.start()
    try:
        assert wait_for(lambda: drive.named("weights-2026-11-06.sqlite3"))
        today[0] = DAY2
        assert wait_for(lambda: drive.named("weights-2026-11-07.sqlite3"))
    finally:
        worker.stop()
