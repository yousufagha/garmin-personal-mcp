"""Aggregate raw Garmin range responses into per-week training and recovery totals.

Pure functions: inputs are the raw JSON lists from the activity search, daily summaries v2,
sleep summaries and HRV range endpoints. Weeks are ISO weeks (Monday start).
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

Json = dict[str, Any]


def _is_run(a: Json) -> bool:
    return "run" in ((a.get("activityType") or {}).get("typeKey") or "")


def _day(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _week(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _avg(xs: list[Any], nd: int = 1) -> Any:
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(mean(xs), nd) if xs else None


def _pace(metres: float, seconds: float) -> str | None:
    if metres <= 0 or seconds <= 0:
        return None
    secs = round(seconds / (metres / 1000))
    return f"{secs // 60}:{secs % 60:02d} /km"


def _pct(part: float, whole: float) -> Any:
    return round(100 * part / whole) if whole > 0 else None


def _clean(d: Json) -> Json:
    return {k: v for k, v in d.items() if v is not None and v != {} and v != []}


def _training(acts: list[Json]) -> Json:
    runs = [a for a in acts if _is_run(a)]
    run_m = sum(a.get("distance") or 0 for a in runs)
    run_s = sum(a.get("duration") or 0 for a in runs)
    hr_w = [(a.get("averageHR"), a.get("duration") or 0) for a in runs if a.get("averageHR")]
    zones = [sum(a.get(f"hrTimeInZone_{i}") or 0 for a in acts) / 60 for i in range(1, 6)]
    ztot = sum(zones)
    return _clean(
        {
            "activities": len(acts),
            "by_type": dict(Counter((a.get("activityType") or {}).get("typeKey") for a in acts).most_common()),
            "training_load": round(sum(a.get("activityTrainingLoad") or 0 for a in acts), 1),
            "total_time_min": round(sum(a.get("duration") or 0 for a in acts) / 60, 1),
            "run": _clean(
                {
                    "count": len(runs),
                    "km": round(run_m / 1000, 2),
                    "time_min": round(run_s / 60, 1),
                    "avg_pace": _pace(run_m, run_s),
                    "longest_km": round(max((a.get("distance") or 0 for a in runs), default=0) / 1000, 2),
                    "avg_hr_bpm": round(sum(h * w for h, w in hr_w) / sum(w for _, w in hr_w)) if hr_w and sum(w for _, w in hr_w) else None,
                }
            )
            if runs
            else None,
            "hr_zone_min": {f"z{i + 1}": round(z, 1) for i, z in enumerate(zones)} if ztot else None,
            "easy_pct_z1_z2": _pct(zones[0] + zones[1], ztot),
            "hard_pct_z4_z5": _pct(zones[3] + zones[4], ztot),
        }
    )


def _recovery(days: list[Json], sleeps: list[Json], hrvs: list[Json]) -> Json:
    return _clean(
        {
            "days_with_data": len(days) or None,
            "resting_hr_avg_bpm": _avg([(d.get("heartRate") or {}).get("restingValue") for d in days]),
            "stress_avg": _avg([(d.get("stress") or {}).get("avgLevel") for d in days]),
            "body_battery_max_avg": _avg([(d.get("bodyBattery") or {}).get("maxValue") for d in days]),
            "steps_avg": _avg([((d.get("movement") or {}).get("steps") or {}).get("value") for d in days], 0),
            "sleep_h_avg": _avg([(s.get("sleepTimeSeconds") or 0) / 3600 for s in sleeps if s.get("sleepTimeSeconds")], 2),
            "sleep_score_avg": _avg([((s.get("sleepScores") or {}).get("overall") or {}).get("value") for s in sleeps]),
            "hrv_last_night_avg_ms": _avg([h.get("lastNightAvg") for h in hrvs]),
            "hrv_status_days": dict(Counter(h.get("status") for h in hrvs if h.get("status"))) or None,
        }
    )


def weekly_summary(
    start: dt.date, end: dt.date, acts: list[Json], days: list[Json], sleeps: list[Json], hrvs: list[Json]
) -> Json:
    buckets: dict[dt.date, dict[str, list[Json]]] = defaultdict(lambda: {"a": [], "d": [], "s": [], "h": []})
    for key, items, date_field in (("a", acts, "startTimeLocal"), ("d", days, "calendarDate"), ("s", sleeps, "calendarDate"), ("h", hrvs, "calendarDate")):
        for x in items or []:
            d = _day(x.get(date_field))
            if d and start <= d <= end:
                buckets[_week(d)][key].append(x)

    weeks = []
    w = _week(start)
    while w <= end:
        b = buckets[w]
        weeks.append(
            {
                "week_start": w.isoformat(),
                "week_end": min(w + dt.timedelta(days=6), end).isoformat(),
                "partial": w < start or w + dt.timedelta(days=6) > end,
                "training": _training(b["a"]),
                "recovery": _recovery(b["d"], b["s"], b["h"]),
            }
        )
        w += dt.timedelta(days=7)

    for prev, cur in zip(weeks, weeks[1:]):
        p, c = prev["training"], cur["training"]
        cur["change_vs_prev_week"] = _clean(
            {
                "run_km": round((c.get("run", {}).get("km") or 0) - (p.get("run", {}).get("km") or 0), 2),
                "training_load": round((c.get("training_load") or 0) - (p.get("training_load") or 0), 1),
            }
        )

    in_range = [a for a in acts or [] if (d := _day(a.get("startTimeLocal"))) and start <= d <= end]
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "totals": _training(in_range),
        "weeks": weeks,
    }
