"""Upload the weight log to Google Drive (Drive API v3, `drive.file` scope).

Layout in My Drive/<folder>/:
  weights, daily          Google Sheets, replaced on every sync (URL stays the same)
  weights.csv, daily.csv  plain CSV for scripts and AI tools
  backups/weights-YYYY-MM-DD.sqlite3   one database snapshot per day, last N kept

File ids live in a local state file, so the same files are updated in place;
a file the user deleted or trashed in Drive is simply created again.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from s200 import export
from s200.store import Store

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
BACKUP_RE = re.compile(r"^weights-\d{4}-\d{2}-\d{2}\.sqlite3$")


class DriveError(Exception):
    pass


class NotFound(DriveError):
    pass


# --- auth -------------------------------------------------------------------


def authorize(client_secret: Path, token_path: Path) -> None:
    """Run the one-time browser consent and save the refresh token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    _write_private(token_path, creds.to_json())


def session(token_path: Path):
    """An authorized requests session; refreshed tokens are written back."""
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        _write_private(token_path, creds.to_json())
    return AuthorizedSession(creds)


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


# --- REST client ------------------------------------------------------------


class DriveClient:
    """Just the Drive v3 calls we need, over a requests-compatible session."""

    def __init__(self, session) -> None:
        self.session = session

    def _call(self, method: str, url: str, **kwargs) -> dict:
        resp = self.session.request(method, url, timeout=60, **kwargs)
        if resp.status_code == 404:
            raise NotFound(url)
        if resp.status_code >= 400:
            raise DriveError(f"{method} {url} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    def is_live(self, file_id: str) -> bool:
        """True if the file exists and is not in the trash."""
        try:
            meta = self._call("GET", f"{API}/files/{file_id}", params={"fields": "id,trashed"})
        except NotFound:
            return False
        return not meta.get("trashed", False)

    def create_folder(self, name: str, parent: str | None = None) -> str:
        meta = {"name": name, "mimeType": FOLDER_MIME}
        if parent:
            meta["parents"] = [parent]
        return self._call("POST", f"{API}/files", params={"fields": "id"}, json=meta)["id"]

    def create(
        self, name: str, parent: str, data: bytes, mime: str, convert_to: str | None = None
    ) -> str:
        meta = {"name": name, "parents": [parent]}
        if convert_to:
            meta["mimeType"] = convert_to
        boundary = uuid.uuid4().hex
        body = (
            (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
            ).encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        return self._call(
            "POST",
            f"{UPLOAD}/files",
            params={"uploadType": "multipart", "fields": "id"},
            data=body,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        )["id"]

    def update(self, file_id: str, data: bytes, mime: str) -> bool:
        """Replace the content (a Google Sheet is re-converted). False if trashed."""
        meta = self._call(
            "PATCH",
            f"{UPLOAD}/files/{file_id}",
            params={"uploadType": "media", "fields": "id,trashed"},
            data=data,
            headers={"Content-Type": mime},
        )
        return not meta.get("trashed", False)

    def list_children(self, parent: str) -> list[dict]:
        q = f"'{parent}' in parents and trashed = false"
        res = self._call(
            "GET", f"{API}/files", params={"q": q, "fields": "files(id,name)", "pageSize": 1000}
        )
        return res.get("files", [])

    def delete(self, file_id: str) -> None:
        try:
            self._call("DELETE", f"{API}/files/{file_id}")
        except NotFound:
            pass


# --- sync -------------------------------------------------------------------


class State:
    """File ids and the last backup date, persisted as JSON."""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            self.data = json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            self.data = {}
        self.data.setdefault("files", {})

    def save(self) -> None:
        _write_private(self.path, json.dumps(self.data, indent=2))


class Syncer:
    """One full upload of the exports (and today's backup if still missing)."""

    def __init__(
        self,
        store: Store,
        client: DriveClient,
        state: State,
        *,
        profile_id: int | None = None,
        folder: str = "体重ログ",
        backup_keep: int = 30,
    ) -> None:
        self.store = store
        self.client = client
        self.state = state
        self.profile_id = profile_id
        self.folder = folder
        self.backup_keep = backup_keep

    def backup_due(self, today: date) -> bool:
        return self.state.data.get("last_backup") != today.isoformat()

    def sync(self, today: date | None = None) -> list[str]:
        """Upload everything; returns the names written."""
        today = today or date.today()
        root = self._folder("folder", self.folder, None)
        rows = self.store.list(profile_id=self.profile_id)
        readings = export.readings_csv(rows).encode()
        daily = export.daily_csv(rows, self.store.list_notes()).encode()

        written = []
        for name, data, convert in (
            ("weights", readings, SHEET_MIME),
            ("weights.csv", readings, None),
            ("daily", daily, SHEET_MIME),
            ("daily.csv", daily, None),
        ):
            self._put(name, root, data, "text/csv", convert)
            written.append(name)

        if self.backup_due(today):
            backups = self._folder("backups", "backups", root)
            name = f"weights-{today.isoformat()}.sqlite3"
            self.client.create(name, backups, self._snapshot(), "application/x-sqlite3")
            self.state.data["last_backup"] = today.isoformat()
            self.state.save()
            self._prune(backups)
            written.append(f"backups/{name}")
        return written

    def _folder(self, key: str, name: str, parent: str | None) -> str:
        folder_id = self.state.data.get(key)
        if folder_id and self.client.is_live(folder_id):
            return folder_id
        folder_id = self.client.create_folder(name, parent)
        self.state.data[key] = folder_id
        if key == "folder":  # everything inside went with the old folder
            self.state.data["files"] = {}
            self.state.data.pop("backups", None)
            self.state.data.pop("last_backup", None)
        self.state.save()
        return folder_id

    def _put(self, name: str, parent: str, data: bytes, mime: str, convert: str | None) -> None:
        files = self.state.data["files"]
        if file_id := files.get(name):
            try:
                if self.client.update(file_id, data, mime):
                    return
            except NotFound:
                pass
        files[name] = self.client.create(name, parent, data, mime, convert)
        self.state.save()

    def _snapshot(self) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.sqlite3"
            self.store.snapshot(path)
            return path.read_bytes()

    def _prune(self, backups: str) -> None:
        files = [f for f in self.client.list_children(backups) if BACKUP_RE.match(f["name"])]
        files.sort(key=lambda f: f["name"], reverse=True)
        for f in files[self.backup_keep :]:
            self.client.delete(f["id"])


class DriveSync:
    """Background thread: sync after changes settle, back up daily, retry on failure.

    It listens on the app's EventHub like an SSE client, so recording never
    waits on the network.
    """

    def __init__(
        self,
        syncer: Syncer,
        hub,
        *,
        debounce: float = 60,
        retry_min: float = 60,
        retry_max: float = 1800,
        tick: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.syncer = syncer
        self.hub = hub
        self.debounce = debounce
        self.retry_min = retry_min
        self.retry_max = retry_max
        self.tick = tick
        self.clock = clock
        self.today = today
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._status: dict = {"enabled": True, "last_success": None, "last_error": None}
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def start(self) -> None:
        self._queue = self.hub.subscribe()
        self._thread = threading.Thread(target=self.run, name="drive-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def run(self) -> None:
        q = getattr(self, "_queue", None) or self.hub.subscribe()
        dirty, due, backoff = True, self.clock(), self.retry_min  # sync once at startup
        try:
            while not self.stop_event.is_set():
                try:
                    event, _ = q.get(timeout=self.tick)
                    if event in ("reading", "changed"):
                        dirty, due = True, self.clock() + self.debounce
                    continue
                except queue.Empty:
                    pass
                if not dirty and self.syncer.backup_due(self.today()):
                    dirty, due = True, self.clock()
                if not dirty or self.clock() < due:
                    continue
                try:
                    written = self.syncer.sync(self.today())
                except Exception as e:  # network, auth, quota: keep recording, retry later
                    log.warning("drive sync failed (retry in %.0f s): %s", backoff, e)
                    with self._lock:
                        self._status["last_error"] = str(e)
                    due, backoff = self.clock() + backoff, min(backoff * 2, self.retry_max)
                    continue
                log.info("drive sync: %s", ", ".join(written))
                with self._lock:
                    self._status["last_success"] = int(datetime.now().timestamp())
                    self._status["last_error"] = None
                dirty, backoff = False, self.retry_min
        finally:
            self.hub.unsubscribe(q)
