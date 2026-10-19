import pytest

from s200.config import load

VALID = """
[scale]
bindkey = "653b1b10e1cb35e4ac5e60fa45f3bf29"
mac = "D0:7B:6F:27:D7:29"
profile_id = 1
[user]
height_cm = 170
goal_kg = 65.0
[server]
db_path = "w.sqlite3"
port = 9000
"""


def test_load_valid(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID)
    cfg = load(path)
    assert cfg.bindkey == bytes.fromhex("653b1b10e1cb35e4ac5e60fa45f3bf29")
    assert cfg.mac == bytes.fromhex("D07B6F27D729")
    assert cfg.profile_id == 1
    assert cfg.db_path == tmp_path / "w.sqlite3"
    assert cfg.port == 9000


def test_rejects_token_in_bindkey_slot(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID.replace("653b1b10e1cb35e4ac5e60fa45f3bf29", "0123456789abcdef01234567"))
    with pytest.raises(ValueError, match="BLE KEY"):
        load(path)


def test_example_config_parses():
    assert load("config.example.toml").port == 8200
