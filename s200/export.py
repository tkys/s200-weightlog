"""CSV exports for Google Drive and other tools (pure functions, no I/O).

Column names are English snake_case so spreadsheets, scripts and AI tools can
rely on them; `daily.csv` is keyed by `date` for joining with meal or step logs.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import datetime

from s200 import analysis

READING_COLUMNS = (
    "id",
    "datetime",
    "date",
    "weight_kg",
    "trend_kg",
    "status",
    "reason",
    "profile_id",
)
DAILY_COLUMNS = ("date", "weight_kg", "trend_kg", "count", "note", "tags")


def _kg(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _csv(columns: Sequence[str], rows: Sequence[Sequence]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buf.getvalue()


def readings_csv(rows: Sequence[dict]) -> str:
    """Every weigh-in, oldest first, including excluded ones (see `status`)."""
    out = []
    for r in analysis.with_trend(rows):
        when = datetime.fromtimestamp(r["ts"]).astimezone()
        out.append(
            (
                r["id"],
                when.isoformat(timespec="seconds"),
                when.date().isoformat(),
                _kg(r["weight_kg"]),
                _kg(r["trend_kg"]),
                r["status"],
                r["reason"] or "",
                r["profile_id"],
            )
        )
    return _csv(READING_COLUMNS, out)


def daily_csv(rows: Sequence[dict], notes: Sequence[dict]) -> str:
    """One row per day with a weigh-in or a note.

    `weight_kg` / `trend_kg` come from the day's last included weigh-in;
    excluded readings (outlier, merged) are not counted.
    """
    days: dict[str, dict] = {}
    for r in analysis.with_trend(rows):
        if r["status"] != "ok":
            continue
        day = days.setdefault(analysis.local_date(r["ts"]).isoformat(), {"count": 0})
        day.update(weight_kg=r["weight_kg"], trend_kg=r["trend_kg"])
        day["count"] += 1
    for n in notes:
        day = days.setdefault(n["date"], {"count": 0})
        day.update(note=n["note"], tags=n["tags"])

    out = []
    for date in sorted(days):
        d = days[date]
        out.append(
            (
                date,
                _kg(d.get("weight_kg")),
                _kg(d.get("trend_kg")),
                d["count"],
                d.get("note", ""),
                ";".join(d.get("tags", [])),
            )
        )
    return _csv(DAILY_COLUMNS, out)
