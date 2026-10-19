"""Command line entry point: `s200 scan` and `s200 run`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import threading
from datetime import datetime

from s200 import config as config_mod
from s200 import scanner, web
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
        server.shutdown()
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

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
