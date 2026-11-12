"""Load config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from s200.mibeacon import parse_mac


@dataclass(frozen=True)
class DriveConfig:
    enabled: bool = False
    folder: str = "体重ログ"
    backup_keep: int = 30
    debounce_seconds: float = 60
    # client_secret.json, token.json and state.json live here (git-ignored)
    dir: Path = Path(".drive")

    @property
    def client_secret(self) -> Path:
        return self.dir / "client_secret.json"

    @property
    def token(self) -> Path:
        return self.dir / "token.json"

    @property
    def state(self) -> Path:
        return self.dir / "state.json"


@dataclass(frozen=True)
class Config:
    bindkey: bytes
    mac: bytes
    profile_id: int | None
    height_cm: float | None
    goal_kg: float | None
    db_path: Path
    port: int
    drive: DriveConfig = DriveConfig()


def load(path: str | Path) -> Config:
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)
    scale = raw.get("scale", {})
    user = raw.get("user", {})
    server = raw.get("server", {})
    drive = raw.get("drive", {})

    bindkey = bytes.fromhex(scale.get("bindkey", ""))
    if len(bindkey) != 16:
        raise ValueError("scale.bindkey must be 32 hex characters (the BLE KEY, not the TOKEN)")

    db_path = Path(server.get("db_path", "weights.sqlite3"))
    if not db_path.is_absolute():
        db_path = path.parent / db_path

    drive_dir = Path(drive.get("dir", ".drive"))
    if not drive_dir.is_absolute():
        drive_dir = path.parent / drive_dir

    return Config(
        bindkey=bindkey,
        mac=parse_mac(scale.get("mac", "")),
        profile_id=scale.get("profile_id"),
        height_cm=user.get("height_cm"),
        goal_kg=user.get("goal_kg"),
        db_path=db_path,
        port=int(server.get("port", 8200)),
        drive=DriveConfig(
            enabled=bool(drive.get("enabled", False)),
            folder=str(drive.get("folder", "体重ログ")),
            backup_keep=int(drive.get("backup_keep", 30)),
            debounce_seconds=float(drive.get("debounce_seconds", 60)),
            dir=drive_dir,
        ),
    )
