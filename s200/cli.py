"""Command line entry point: `s200 scan`, `s200 run` and `s200 drive ...`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import threading
from datetime import datetime

from s200 import config as config_mod
from s200 import drive, scanner, web
from s200.mibeacon import Reading
from s200.store import Store

log = logging.getLogger("s200")


def cmd_scan(args: argparse.Namespace) -> None:
    print(f"Scanning {args.seconds:.0f}s for Xiaomi (0xFE95) advertisements... step on the scale.")
    asyncio.run(scanner.dump(args.seconds))


def cmd_run(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    store = Store(cfg.db_path)
    app = web.WeightApp(
        store,
        profile_id=cfg.profile_id,
        defaults={"height_cm": cfg.height_cm, "goal_kg": cfg.goal_kg},
    )

    drive_sync = start_drive_sync(cfg, store, app)

    server = web.make_server(app, args.host, cfg.port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("api: http://%s:%d/", args.host, cfg.port)

    def on_reading(reading: Reading) -> None:
        row = app.ingest(reading)
        if row is not None:
            when = datetime.fromtimestamp(reading.timestamp).isoformat(sep=" ")
            log.info(
                "recorded %.2f kg (profile %d) at %s [%s%s]",
                reading.weight_kg,
                reading.profile_id,
                when,
                row["status"],
                f": {row['reason']}" if row["reason"] else "",
            )

    log.info("listening for S200 broadcasts...")
    try:
        asyncio.run(scanner.watch(cfg.bindkey, cfg.mac, on_reading))
    except KeyboardInterrupt:
        pass
    finally:
        if drive_sync:
            drive_sync.stop()
        server.shutdown()
        store.close()


def _syncer(cfg: config_mod.Config, store: Store) -> drive.Syncer:
    client = drive.DriveClient(drive.session(cfg.drive.token))
    return drive.Syncer(
        store,
        client,
        drive.State(cfg.drive.state),
        profile_id=cfg.profile_id,
        folder=cfg.drive.folder,
        backup_keep=cfg.drive.backup_keep,
    )


def start_drive_sync(
    cfg: config_mod.Config, store: Store, app: web.WeightApp
) -> drive.DriveSync | None:
    if not cfg.drive.enabled:
        log.info("drive sync: disabled in config")
        return None
    if not cfg.drive.token.exists():
        log.warning("drive sync: no token, run `s200 drive auth` first")
        app.drive_status = lambda: {"enabled": True, "last_error": "未認証: s200 drive auth"}
        return None
    try:
        syncer = _syncer(cfg, store)
    except Exception as e:  # revoked or broken token: keep recording without Drive
        log.warning("drive sync: cannot authorize: %s", e)
        status = {"enabled": True, "last_error": f"認証エラー: {e}"}
        app.drive_status = lambda: status
        return None
    worker = drive.DriveSync(syncer, app.hub, debounce=cfg.drive.debounce_seconds)
    app.drive_status = worker.status
    worker.start()
    log.info("drive sync: uploading to My Drive/%s", cfg.drive.folder)
    return worker


def cmd_drive_auth(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    if not cfg.drive.client_secret.exists():
        raise SystemExit(
            f"{cfg.drive.client_secret} がありません。"
            "Google Cloud で作った OAuth クライアント（デスクトップアプリ）の JSON を置いてください"
        )
    drive.authorize(cfg.drive.client_secret, cfg.drive.token)
    print(f"認証できました: {cfg.drive.token}")
    if not cfg.drive.enabled:
        print("config.toml の [drive] enabled = true にして、常駐プログラムを再起動してください")


def cmd_drive_sync(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    store = Store(cfg.db_path)
    try:
        for name in _syncer(cfg, store).sync():
            print(f"uploaded {cfg.drive.folder}/{name}")
    finally:
        store.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="s200", description="Xiaomi S200 weight logger")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="dump raw MiBeacon advertisements")
    p_scan.add_argument("--seconds", type=float, default=60)
    p_scan.set_defaults(func=cmd_scan)

    p_run = sub.add_parser("run", help="record weigh-ins and serve the dashboard")
    p_run.add_argument("--config", default="config.toml")
    p_run.add_argument("--host", default="127.0.0.1")
    p_run.set_defaults(func=cmd_run)

    p_drive = sub.add_parser("drive", help="Google Drive upload")
    drive_sub = p_drive.add_subparsers(dest="drive_command", required=True)
    for name, func, help_text in (
        ("auth", cmd_drive_auth, "authorize access to Google Drive (opens a browser)"),
        ("sync", cmd_drive_sync, "upload everything now"),
    ):
        p = drive_sub.add_parser(name, help=help_text)
        p.add_argument("--config", default="config.toml")
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
