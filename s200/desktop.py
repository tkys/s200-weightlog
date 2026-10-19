"""Native desktop window around the dashboard (pywebview, macOS WKWebView).

Uses the running `s200 run` daemon if it answers; otherwise serves the dashboard
from the SQLite file itself (view only, no BLE).
"""

from __future__ import annotations

import argparse
import threading
import urllib.request

from s200 import config as config_mod
from s200 import web
from s200.store import Store


def daemon_alive(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url + "/api/readings", timeout=timeout) as res:
            return res.status == 200
    except OSError:
        return False


def resolve_url(cfg: config_mod.Config) -> str:
    """Return a dashboard URL, starting a local view-only server if needed."""
    url = f"http://127.0.0.1:{cfg.port}"
    if daemon_alive(url):
        return url
    server = web.make_server(
        Store(cfg.db_path),
        port=0,
        profile_id=cfg.profile_id,
        height_cm=cfg.height_cm,
        goal_kg=cfg.goal_kg,
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def main(argv: list[str] | None = None) -> None:
    import webview  # optional dependency: uv sync --extra desktop

    parser = argparse.ArgumentParser(prog="s200-desktop")
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args(argv)

    url = resolve_url(config_mod.load(args.config))
    webview.create_window("体重ログ", url, width=1040, height=820, min_size=(420, 600))
    webview.start()


if __name__ == "__main__":
    main()
