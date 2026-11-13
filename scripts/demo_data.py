"""Write demo API responses (JSON) for screenshots, computed by the real backend.

    uv run python scripts/demo_data.py OUT_DIR

About three months of plausible weigh-ins ending now: a slow downward trend
with daily noise, weekend bumps, a family member stepping on the scale
(auto-excluded), a quick re-weigh (merged) and a few day notes. Nothing
touches the real database.
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from s200.mibeacon import Reading
from s200.store import Store
from s200.web import WeightApp

DAYS = 92
START_KG = 78.6
END_KG = 72.4

NOTES = {
    3: ("同僚と焼肉", ["飲み会", "外食"]),
    12: ("ジム 45 分", ["運動"]),
    19: ("", ["運動"]),
    27: ("風邪気味で早寝", ["体調不良"]),
    41: ("結婚式。食べすぎた", ["外食", "飲み会"]),
    55: ("10 km ラン", ["運動"]),
    68: ("", ["運動"]),
    80: ("出張で外食続き", ["外食"]),
    88: ("ジム", ["運動"]),
}


def weigh_ins(now: datetime) -> list[Reading]:
    rng = random.Random(200)
    first = (now - timedelta(days=DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for d in range(DAYS + 1):
        day = first + timedelta(days=d)
        # Skips are common early on, then the habit sticks (a streak of 3+ weeks).
        if d < DAYS - 24 and rng.random() < 0.22:
            continue
        progress = d / DAYS
        base = START_KG + (END_KG - START_KG) * (1 - (1 - progress) ** 1.4)
        if day.weekday() in (5, 6):
            base += 0.35
        if d in NOTES and "飲み会" in NOTES[d][1]:
            base += 0.6
        morning = day.replace(hour=7, minute=rng.randint(0, 40), second=rng.randint(0, 59))
        if morning > now:
            continue
        out.append(Reading(1, round(base + rng.gauss(0, 0.28), 1), int(morning.timestamp())))
        if rng.random() < 0.3:  # an evening weigh-in now and then
            evening = day.replace(hour=21, minute=rng.randint(0, 50))
            if evening < now:
                out.append(
                    Reading(1, round(base + 0.6 + rng.gauss(0, 0.2), 1), int(evening.timestamp()))
                )
    # Someone else steps on the scale: far off the trend, so it gets excluded.
    guest = first + timedelta(days=DAYS - 9, hours=19, minutes=12)
    out.append(Reading(1, 54.8, int(guest.timestamp())))
    # Stepped on twice within a few minutes: the first one is merged away.
    redo = first + timedelta(days=DAYS - 5, hours=7, minutes=55)
    out.append(Reading(1, 73.4, int(redo.timestamp())))
    out.append(Reading(1, 73.1, int(redo.timestamp()) + 140))
    return sorted(out, key=lambda r: r.timestamp)


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now().replace(microsecond=0)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "demo.sqlite3")
        for reading in weigh_ins(now):
            store.ingest(reading)
        first_day = datetime.fromtimestamp(store.list()[0]["ts"]).date()
        for offset, (note, tags) in NOTES.items():
            store.put_note((first_day + timedelta(days=offset)).isoformat(), note, tags)
        app = WeightApp(store, profile_id=1, defaults={"height_cm": 172, "goal_kg": 70.0})

        readings = app.readings()
        latest = next(r for r in reversed(readings) if r["status"] == "ok")
        previous = next(
            r for r in reversed(readings) if r["status"] == "ok" and r["ts"] < latest["ts"]
        )
        payloads = {
            "summary.json": app.summary(int(time.time())),
            "readings.json": {"readings": readings, "settings": app.settings()},
            "notes.json": {"notes": store.list_notes()},
            # What the reaction banner shows right after stepping on the scale.
            "reaction.json": {"reading": latest, "previous_kg": previous["weight_kg"]},
        }
        for name, payload in payloads.items():
            (out / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        store.close()

    statuses = {s: sum(r["status"] == s for r in readings) for s in ("ok", "outlier", "merged")}
    print(f"wrote {len(payloads)} files to {out}: {len(readings)} readings {statuses}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo")
