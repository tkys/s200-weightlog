"""Tiny HTTP server: dashboard page + JSON API."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from s200.store import Store


def make_server(
    store: Store,
    host: str = "127.0.0.1",
    port: int = 8200,
    *,
    profile_id: int | None = None,
    height_cm: float | None = None,
    goal_kg: float | None = None,
) -> ThreadingHTTPServer:
    index_html = resources.files("s200").joinpath("static/index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                self._send(200, "text/html; charset=utf-8", index_html)
            elif url.path == "/api/readings":
                query = parse_qs(url.query)
                try:
                    since = int(query["since"][0]) if "since" in query else None
                except ValueError:
                    self._send(400, "application/json", b'{"error":"since must be an integer"}')
                    return
                body = {
                    "readings": store.list(profile_id=profile_id, since=since),
                    "height_cm": height_cm,
                    "goal_kg": goal_kg,
                }
                self._send(200, "application/json", json.dumps(body).encode())
            else:
                self._send(404, "text/plain", b"not found")

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # keep the daemon log quiet
            pass

    return ThreadingHTTPServer((host, port), Handler)
