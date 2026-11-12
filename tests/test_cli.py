from dataclasses import replace

from s200 import cli
from s200.config import DriveConfig, load
from s200.store import Store
from s200.web import WeightApp

CONFIG = """
[scale]
bindkey = "653b1b10e1cb35e4ac5e60fa45f3bf29"
mac = "D0:7B:6F:27:D7:29"
"""


def setup(tmp_path, **drive):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG)
    cfg = load(path)
    cfg = replace(cfg, drive=DriveConfig(dir=tmp_path / ".drive", **drive))
    store = Store(tmp_path / "w.sqlite3")
    return cfg, store, WeightApp(store)


def test_drive_disabled_by_default(tmp_path):
    cfg, store, app = setup(tmp_path)
    assert cli.start_drive_sync(cfg, store, app) is None
    assert app.drive_status() == {"enabled": False}


def test_drive_enabled_without_token_reports_it(tmp_path):
    cfg, store, app = setup(tmp_path, enabled=True)
    assert cli.start_drive_sync(cfg, store, app) is None
    status = app.drive_status()
    assert status["enabled"] is True
    assert "s200 drive auth" in status["last_error"]


def test_drive_broken_token_does_not_stop_the_daemon(tmp_path):
    cfg, store, app = setup(tmp_path, enabled=True)
    cfg.drive.dir.mkdir()
    cfg.drive.token.write_text("{not json")
    assert cli.start_drive_sync(cfg, store, app) is None
    assert app.drive_status()["last_error"].startswith("認証エラー")


def test_drive_subcommands_parse(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "cmd_drive_sync", lambda args: seen.append(args.config))
    # main() builds the parser with the functions bound at call time
    cli.main(["drive", "sync", "--config", "x.toml"])
    assert seen == ["x.toml"]
