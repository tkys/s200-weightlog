"""HTTP API for the apps: JSON endpoints + a Server-Sent Events stream."""

from __future__ import annotations

import json
import queue
import re
import sys
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from s200 import analysis
from s200.mibeacon import Reading
from s200.store import Store

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
READING_RE = re.compile(r"^/api/readings/(\d+)$")
NOTE_RE = re.compile(r"^/api/notes/(\d{4}-\d{2}-\d{2})$")
PING_INTERVAL_S = 15.0


class EventHub:
    """Fan-out of events to every connected SSE client."""

    def __init__(self) -> None:
        self._subs: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    def publish(self, event: str, data: dict) -> None:
        payload = (event, json.dumps(data, ensure_ascii=False))
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(payload)
            except queue.Full:  # a stuck client; drop rather than block the scanner
                pass


class WeightApp:
    """Shared state for the API and the scanner callback."""

    def __init__(
        self, store: Store, *, profile_id: int | None = None, defaults: dict | None = None
    ) -> None:
        self.store = store
        self.hub = EventHub()
        self.profile_id = profile_id
        self.defaults = defaults or {}
        # Replaced by the Drive worker's status() when uploading is on.
        self.drive_status: Callable[[], dict] = lambda: {"enabled": False}

    def settings(self) -> dict:
        return self.store.get_settings(self.defaults)

    def summary(self, now: int | None = None) -> dict:
        rows = self.store.list(profile_id=self.profile_id)
        return analysis.summarize(rows, self.settings(), int(now or time.time()))

    def readings(self, since: int | None = None) -> list[dict]:
        rows = analysis.with_trend(self.store.list(profile_id=self.profile_id))
        return [r for r in rows if since is None or r["ts"] >= since]

    def ingest(self, reading: Reading) -> dict | None:
        """Store a weigh-in from the scanner and push it to connected apps."""
        if self.profile_id is not None and reading.profile_id != self.profile_id:
            return None
        row = self.store.ingest(reading)
        if row is not None:
            self.hub.publish("reading", {"reading": row, "summary": self.summary()})
        return row

    def changed(self) -> None:
        self.hub.publish("changed", {"summary": self.summary()})


class _Server(ThreadingHTTPServer):
    daemon_threads = True  # open SSE streams must not block shutdown

    def handle_error(self, request, client_address):
        # Clients dropping idle keep-alive connections is normal, not an error.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


def make_server(app: WeightApp, host: str = "127.0.0.1", port: int = 8200) -> ThreadingHTTPServer:
    index_html = resources.files("s200").joinpath("static/index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # --- routing -------------------------------------------------------

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            path = url.path
            if path == "/":
                self._send(200, index_html, "text/html; charset=utf-8")
            elif path == "/api/summary":
                self._json(200, app.summary())
            elif path == "/api/readings":
                since = self._int_param(query, "since")
                if since is False:
                    return
                self._json(200, {"readings": app.readings(since), "settings": app.settings()})
            elif path == "/api/notes":
                start, end = query.get("from", [None])[0], query.get("to", [None])[0]
                if any(d and not DATE_RE.match(d) for d in (start, end)):
                    self._error(400, "from/to must be YYYY-MM-DD")
                    return
                self._json(200, {"notes": app.store.list_notes(start, end)})
            elif m := NOTE_RE.match(path):
                self._json(200, app.store.get_note(m.group(1)))
            elif path == "/api/settings":
                self._json(200, app.settings())
            elif path == "/api/drive":
                self._json(200, app.drive_status())
            elif path == "/api/stream":
                self._stream()
            else:
                self._error(404, "not found")

        def do_PATCH(self):
            m = READING_RE.match(urlparse(self.path).path)
            if not m:
                self._error(404, "not found")
                return
            body = self._body()
            if body is None:
                return
            try:
                row = app.store.set_status(int(m.group(1)), body.get("status"))
            except ValueError as e:
                self._error(400, str(e))
                return
            if row is None:
                self._error(404, "no such reading")
                return
            app.changed()
            self._json(200, row)

        def do_PUT(self):
            path = urlparse(self.path).path
            body = self._body()
            if body is None:
                return
            if m := NOTE_RE.match(path):
                note, tags = body.get("note", ""), body.get("tags", [])
                if not isinstance(note, str) or not isinstance(tags, list):
                    self._error(400, "note must be a string and tags a list")
                    return
                self._json(200, app.store.put_note(m.group(1), note, [str(t) for t in tags]))
                app.changed()
            elif path == "/api/settings":
                try:
                    app.store.put_settings(body)
                except ValueError as e:
                    self._error(400, str(e))
                    return
                app.changed()
                self._json(200, app.settings())
            else:
                self._error(404, "not found")

        # --- SSE -----------------------------------------------------------

        def _stream(self):
            q = app.hub.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        event, data = q.get(timeout=PING_INTERVAL_S)
                        self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                app.hub.unsubscribe(q)
                self.close_connection = True

        # --- helpers -------------------------------------------------------

        def _int_param(self, query: dict, name: str):
            if name not in query:
                return None
            try:
                return int(query[name][0])
            except ValueError:
                self._error(400, f"{name} must be an integer")
                return False

        def _body(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._error(400, "invalid JSON")
                return None
            if not isinstance(body, dict):
                self._error(400, "body must be a JSON object")
                return None
            return body

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"error": message})

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # keep the daemon log quiet
            pass

    return _Server((host, port), Handler)
