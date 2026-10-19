"""Load config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from s200.mibeacon import parse_mac


@dataclass(frozen=True)
class Config:
    bindkey: bytes
    mac: bytes
    profile_id: int | None
    height_cm: float | None
    goal_kg: float | None
    db_path: Path
    port: int


def load(path: str | Path) -> Config:
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)
    scale = raw.get("scale", {})
    user = raw.get("user", {})
    server = raw.get("server", {})

    bindkey = bytes.fromhex(scale.get("bindkey", ""))
    if len(bindkey) != 16:
        raise ValueError("scale.bindkey must be 32 hex characters (the BLE KEY, not the TOKEN)")

    db_path = Path(server.get("db_path", "weights.sqlite3"))
    if not db_path.is_absolute():
        db_path = path.parent / db_path

    return Config(
        bindkey=bindkey,
        mac=parse_mac(scale.get("mac", "")),
        profile_id=scale.get("profile_id"),
        height_cm=user.get("height_cm"),
        goal_kg=user.get("goal_kg"),
        db_path=db_path,
        port=int(server.get("port", 8200)),
    )
