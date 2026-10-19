"""Weight analytics: trend, outliers, pace, streaks, milestones, comments.

Pure functions over plain data so they are easy to test. A "point" is a
(ts, weight_kg) pair; only readings with status "ok" feed the trend.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

DAY = 86400
TREND_TAU_DAYS = 10.0
MERGE_WINDOW_S = 600  # weigh-ins this close together count as one
OUTLIER_MIN_HISTORY = 5
OUTLIER_FLOOR_KG = 2.0
OUTLIER_MAD_K = 4.0
PACE_WINDOW_DAYS = 14
STREAK_MILESTONES = (7, 30, 100, 365)

Point = tuple[int, float]


# --- trend -----------------------------------------------------------------


def trend_series(points: Sequence[Point], tau_days: float = TREND_TAU_DAYS) -> list[float]:
    """Time-aware exponential moving average (irregular sampling safe)."""
    out: list[float] = []
    for i, (ts, w) in enumerate(points):
        if i == 0:
            out.append(w)
            continue
        dt = max(ts - points[i - 1][0], 0)
        alpha = 1 - math.exp(-dt / (tau_days * DAY))
        out.append(out[-1] + alpha * (w - out[-1]))
    return out


def trend_at(points: Sequence[Point], ts: int, tau_days: float = TREND_TAU_DAYS) -> float | None:
    """Trend value just before `ts`, from points strictly earlier than ts."""
    prior = [p for p in points if p[0] < ts]
    if not prior:
        return None
    return trend_series(prior, tau_days)[-1]


# --- outliers --------------------------------------------------------------


def _median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def detect_outlier(history: Sequence[Point], ts: int, weight_kg: float) -> str | None:
    """Return a reason string if `weight_kg` is far off the trend, else None.

    `history` are earlier ok points. Needs OUTLIER_MIN_HISTORY of them; the
    threshold adapts to the user's own day-to-day noise (MAD of residuals).
    """
    prior = [p for p in history if p[0] < ts]
    if len(prior) < OUTLIER_MIN_HISTORY:
        return None
    trend = trend_series(prior)
    residuals = [abs(w - trend[i - 1]) for i, (_, w) in enumerate(prior) if i > 0]
    threshold = max(OUTLIER_FLOOR_KG, OUTLIER_MAD_K * _median(residuals))
    diff = weight_kg - trend[-1]
    if abs(diff) > threshold:
        return f"トレンド ({trend[-1]:.1f} kg) から {diff:+.1f} kg 離れています"
    return None


def merge_targets(rows: Sequence[dict], ts: int) -> list[int]:
    """Ids of ok, non-manual readings within MERGE_WINDOW_S before `ts`."""
    return [
        r["id"]
        for r in rows
        if r["status"] == "ok" and not r["manual"] and 0 < ts - r["ts"] <= MERGE_WINDOW_S
    ]


# --- pace / eta ------------------------------------------------------------


def pace_kg_per_week(points: Sequence[Point], now: int) -> float | None:
    """Least-squares slope of the trend over the last PACE_WINDOW_DAYS."""
    if len(points) < 2:
        return None
    trend = trend_series(points)
    window = [
        (ts, t)
        for (ts, _), t in zip(points, trend, strict=True)
        if ts >= now - PACE_WINDOW_DAYS * DAY
    ]
    if len(window) < 2 or window[-1][0] - window[0][0] < 3 * DAY:
        return None
    n = len(window)
    mx = sum(x for x, _ in window) / n
    my = sum(y for _, y in window) / n
    var = sum((x - mx) ** 2 for x, _ in window)
    if var == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in window) / var  # kg per second
    return slope * 7 * DAY


def eta_ts(trend_kg: float, goal_kg: float | None, pace: float | None, now: int) -> int | None:
    """When the trend reaches the goal at the current pace (only if heading there)."""
    if goal_kg is None or pace is None:
        return None
    gap = trend_kg - goal_kg
    if gap <= 0 or pace >= -0.01:
        return None
    weeks = gap / -pace
    if weeks > 520:  # more than ~10 years is not a forecast
        return None
    return int(now + weeks * 7 * DAY)


# --- streaks ---------------------------------------------------------------


def local_date(ts: int) -> date:
    return datetime.fromtimestamp(ts).date()


def streak_days(days: set[date], today: date) -> int:
    """Consecutive weigh-in days ending today (or yesterday, if not weighed yet today)."""
    cur = today if today in days else today - timedelta(days=1)
    n = 0
    while cur in days:
        n += 1
        cur -= timedelta(days=1)
    return n


# --- summary ---------------------------------------------------------------


@dataclass(frozen=True)
class Milestone:
    kind: str
    title: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title}


def milestones_for(
    latest: dict,
    prior_ok: Sequence[Point],
    start_kg: float | None,
    goal_kg: float | None,
    streak: int,
    first_today: bool,
) -> list[Milestone]:
    """Milestones the latest (ok) reading just achieved, relative to earlier ok readings."""
    if latest["status"] != "ok" or not prior_ok:
        return []
    w = latest["weight_kg"]
    best_before = min(p[1] for p in prior_ok)
    out: list[Milestone] = []
    if goal_kg is not None and w <= goal_kg < best_before:
        out.append(Milestone("goal", "目標達成！"))
    if start_kg is not None:
        lost_now = math.floor(start_kg - w)
        lost_before = math.floor(start_kg - best_before)
        if lost_now >= 1 and lost_now > lost_before:
            out.append(Milestone("lost_kg", f"スタートから -{lost_now} kg 達成"))
    if len(prior_ok) >= 3 and w < best_before and not any(m.kind == "goal" for m in out):
        out.append(Milestone("new_low", "最安値を更新"))
    if first_today and streak in STREAK_MILESTONES:
        out.append(Milestone("streak", f"{streak} 日連続で記録"))
    return out


def comment_for(s: dict) -> str:
    latest = s["latest"]
    if latest is None:
        return "体重計に乗ると、ここに結果が出ます"
    if latest["status"] == "outlier":
        return (
            f"いつもと大きく違う値なので除外しました（{latest['weight_kg']:.2f} kg）。"
            "間違いならグラフから戻せます"
        )
    if s["milestones"]:
        return s["milestones"][0]["title"] + "！ この調子です"
    d, pace = s["delta_prev"], s["pace_kg_per_week"]
    if d is None:
        return "記録スタート！ ここから毎日の変化を追いかけます"
    if pace is None:
        return f"前回から {d:+.2f} kg。もう数日記録するとトレンドが見えてきます"
    if pace <= -0.1:
        if d > 0:
            return f"前回比 {d:+.2f} kg。でもトレンドは {pace:+.2f} kg/週で順調です"
        return f"前回比 {d:+.2f} kg！ トレンドも {pace:+.2f} kg/週で下降中"
    if pace >= 0.1:
        return f"トレンドは {pace:+.2f} kg/週。ここから立て直しましょう"
    return f"前回比 {d:+.2f} kg。ほぼ横ばいでキープできています"


def summarize(rows: Sequence[dict], settings: dict, now: int) -> dict:
    """Build the dashboard summary from all readings (any status), oldest first."""
    ok = [r for r in rows if r["status"] == "ok"]
    points: list[Point] = [(r["ts"], r["weight_kg"]) for r in ok]
    goal_kg = settings.get("goal_kg")
    height_cm = settings.get("height_cm")
    start_kg = settings.get("start_kg") or (points[0][1] if points else None)

    latest = dict(rows[-1]) if rows else None
    summary: dict = {
        "latest": latest,
        "count": len(ok),
        "goal_kg": goal_kg,
        "height_cm": height_cm,
        "start_kg": start_kg,
        "trend_kg": None,
        "delta_prev": None,
        "delta_start": None,
        "delta_trend_week": None,
        "pace_kg_per_week": None,
        "eta_ts": None,
        "bmi": None,
        "lowest_kg": min((p[1] for p in points), default=None),
        "streak_days": 0,
        "milestones": [],
    }
    if latest is None:
        summary["comment"] = comment_for(summary)
        return summary

    days = {local_date(ts) for ts, _ in points}
    summary["streak_days"] = streak_days(days, local_date(now))

    if points:
        trend = trend_series(points)
        summary["trend_kg"] = trend[-1]
        week_ago = [t for (ts, _), t in zip(points, trend, strict=True) if ts <= now - 7 * DAY]
        if week_ago:
            summary["delta_trend_week"] = trend[-1] - week_ago[-1]
        pace = pace_kg_per_week(points, now)
        summary["pace_kg_per_week"] = pace
        summary["eta_ts"] = eta_ts(trend[-1], goal_kg, pace, now)
        if height_cm:
            summary["bmi"] = points[-1][1] / (height_cm / 100) ** 2

    if latest["status"] == "ok":
        prior_ok = [p for p in points if p[0] < latest["ts"]]
        if prior_ok:
            summary["delta_prev"] = latest["weight_kg"] - prior_ok[-1][1]
        if start_kg is not None:
            summary["delta_start"] = latest["weight_kg"] - start_kg
        first_today = not any(local_date(ts) == local_date(latest["ts"]) for ts, _ in prior_ok)
        summary["milestones"] = [
            m.to_dict()
            for m in milestones_for(
                latest, prior_ok, start_kg, goal_kg, summary["streak_days"], first_today
            )
        ]
    summary["comment"] = comment_for(summary)
    return summary


def with_trend(rows: Sequence[dict]) -> list[dict]:
    """Attach the trend value at each reading's time (ok readings drive the trend)."""
    out = []
    trend: float | None = None
    last_ts: int | None = None
    for r in rows:
        if r["status"] == "ok":
            if trend is None or last_ts is None:
                trend = r["weight_kg"]
            else:
                alpha = 1 - math.exp(-max(r["ts"] - last_ts, 0) / (TREND_TAU_DAYS * DAY))
                trend += alpha * (r["weight_kg"] - trend)
            last_ts = r["ts"]
        out.append({**r, "trend_kg": trend})
    return out
