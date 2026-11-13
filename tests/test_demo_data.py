import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "demo_data.py"


def load_script():
    spec = importlib.util.spec_from_file_location("demo_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_data_shows_off_every_feature(tmp_path, capsys):
    load_script().main(str(tmp_path))
    files = {p.name: json.loads(p.read_text()) for p in tmp_path.glob("*.json")}
    assert set(files) == {"summary.json", "readings.json", "notes.json", "reaction.json"}

    readings = files["readings.json"]["readings"]
    statuses = [r["status"] for r in readings]
    # The guest weigh-in is auto-excluded and the quick re-weigh is merged.
    assert statuses.count("outlier") == 1
    assert statuses.count("merged") == 1
    assert len(readings) > 60

    summary = files["summary.json"]
    assert summary["pace_kg_per_week"] < 0  # a downward trend to look at
    assert summary["streak_days"] >= 21
    assert summary["eta_ts"] is not None
    assert summary["comment"]
    assert len(files["notes.json"]["notes"]) >= 5
    assert files["reaction.json"]["reading"]["status"] == "ok"
    assert "wrote 4 files" in capsys.readouterr().out
