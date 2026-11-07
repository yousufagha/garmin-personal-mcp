"""Pure functions that cut raw Garmin responses down to what a weekly training review needs.

Field names come from the official OpenAPI spec in docs/openapi.json. Units are made explicit
in the output keys (km, min, s, bpm). Missing values are dropped rather than returned as null.
"""

from __future__ import annotations

from typing import Any

Json = dict[str, Any]


def _clean(d: Json) -> Json:
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


def _r(x: Any, nd: int = 1) -> Any:
    return round(x, nd) if isinstance(x, (int, float)) else None


def _km(m: Any) -> Any:
    return _r(m / 1000, 2) if isinstance(m, (int, float)) else None


def _min(s: Any) -> Any:
    return _r(s / 60, 1) if isinstance(s, (int, float)) else None


def _ts(v: Any) -> Any:
    """Garmin returns some 'local' timestamps as epoch ms despite the spec saying string.
    Local timestamps are encoded as if UTC, so format them in UTC to keep wall-clock time."""
    if isinstance(v, (int, float)):
        import datetime as dt
        return dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return v


def _pace(speed_mps: Any) -> str | None:
    """m/s -> 'M:SS /km'."""
    if not isinstance(speed_mps, (int, float)) or speed_mps <= 0:
        return None
    secs = round(1000 / speed_mps)
    return f"{secs // 60}:{secs % 60:02d} /km"


def hr_zones(a: Json) -> Json:
    zones = {f"z{i}_min": _min(a.get(f"hrTimeInZone_{i}")) for i in range(1, 6)}
    return _clean(zones)


def zone_floors(zones: list[Json], activity_type: str | None) -> Json:
    """Pick HR zone floors for the activity's sport, falling back to the DEFAULT set."""
    if not isinstance(zones, list) or not zones:
        return {}
    sport = "RUNNING" if activity_type and "run" in activity_type else None
    chosen = next((z for z in zones if sport and z.get("sport") == sport), None)
    chosen = chosen or next((z for z in zones if z.get("sport") == "DEFAULT"), zones[0])
    return _clean({f"z{i}": chosen.get(f"zone{i}Floor") for i in range(1, 6)} | {"max": chosen.get("maxHeartRateUsed")})


def activity_list_item(a: Json) -> Json:
    t = a.get("activityType") or {}
    return _clean(
        {
            "id": a.get("activityId"),
            "name": a.get("activityName"),
            "type": t.get("typeKey"),
            "start_local": a.get("startTimeLocal"),
            "distance_km": _km(a.get("distance")),
            "duration_min": _min(a.get("duration")),
            "moving_min": _min(a.get("movingDuration")),
            "avg_pace": _pace(a.get("averageSpeed")),
            "avg_hr_bpm": a.get("averageHR"),
            "max_hr_bpm": a.get("maxHR"),
            "elev_gain_m": _r(a.get("elevationGain")),
            "avg_cadence_spm": _r(a.get("averageRunningCadenceInStepsPerMinute"), 0),
            "aerobic_te": _r(a.get("aerobicTrainingEffect")),
            "anaerobic_te": _r(a.get("anaerobicTrainingEffect")),
            "te_label": a.get("trainingEffectLabel"),
            "training_load": _r(a.get("activityTrainingLoad")),
            "vo2max": a.get("vO2MaxValue"),
            "calories": _r(a.get("calories"), 0),
            "hr_zones": hr_zones(a),
        }
    )


def split(s: Json) -> Json:
    return _clean(
        {
            "type": s.get("splitType"),
            "count": s.get("noOfSplits"),
            "distance_km": _km(s.get("distance")),
            "duration_min": _min(s.get("duration")),
            "avg_pace": _pace(s.get("averageSpeed")),
            "avg_hr_bpm": s.get("averageHR"),
            "max_hr_bpm": s.get("maxHR"),
            "avg_cadence_spm": _r(s.get("averageRunCadence"), 0),
            "elev_gain_m": _r(s.get("elevationGain")),
        }
    )


def activity_detail(d: Json, list_item: Json | None = None) -> Json:
    s = d.get("summaryDTO") or {}
    t = d.get("activityTypeDTO") or {}
    out = {
        "id": d.get("activityId"),
        "name": d.get("activityName"),
        "type": t.get("typeKey"),
        "start_local": s.get("startTimeLocal"),
        "distance_km": _km(s.get("distance")),
        "duration_min": _min(s.get("duration")),
        "moving_min": _min(s.get("movingDuration")),
        "avg_pace": _pace(s.get("averageSpeed")),
        "avg_moving_pace": _pace(s.get("averageMovingSpeed")),
        "avg_gap": _pace(s.get("avgGradeAdjustedSpeed")),
        "heart_rate": _clean(
            {
                "avg_bpm": s.get("averageHR"),
                "max_bpm": s.get("maxHR"),
                "min_bpm": s.get("minHR"),
                "recovery_bpm": s.get("recoveryHeartRate"),
                "lactate_threshold_bpm": s.get("lactateThresholdHeartRate"),
                "zones": hr_zones(list_item or {}),
            }
        ),
        "avg_cadence_spm": _r(s.get("averageRunCadence"), 0),
        "elev_gain_m": _r(s.get("elevationGain")),
        "aerobic_te": _r(s.get("trainingEffect")),
        "anaerobic_te": _r(s.get("anaerobicTrainingEffect")),
        "te_label": s.get("trainingEffectLabel"),
        "training_load": _r(s.get("activityTrainingLoad")),
        "calories": _r(s.get("calories"), 0),
        "splits": [split(x) for x in d.get("splitSummaries") or []],
    }
    return _clean(out)


def daily_summary(d: Json) -> Json:
    return _clean(
        {
            "date": d.get("calendarDate"),
            "steps": d.get("totalSteps"),
            "distance_km": _km(d.get("totalDistanceMeters")),
            "active_kcal": _r(d.get("activeKilocalories"), 0),
            "total_kcal": _r(d.get("totalKilocalories"), 0),
            "resting_hr_bpm": d.get("restingHeartRate"),
            "resting_hr_7d_avg_bpm": d.get("lastSevenDaysAvgRestingHeartRate"),
            "min_hr_bpm": d.get("minHeartRate"),
            "max_hr_bpm": d.get("maxHeartRate"),
            "moderate_intensity_min": d.get("moderateIntensityMinutes"),
            "vigorous_intensity_min": d.get("vigorousIntensityMinutes"),
            "avg_stress": d.get("averageStressLevel"),
            "max_stress": d.get("maxStressLevel"),
            "body_battery": _clean(
                {
                    "high": d.get("bodyBatteryHighestValue"),
                    "low": d.get("bodyBatteryLowestValue"),
                    "at_wake": d.get("bodyBatteryAtWakeTime"),
                    "charged": d.get("bodyBatteryChargedValue"),
                    "drained": d.get("bodyBatteryDrainedValue"),
                }
            ),
            "avg_spo2": d.get("averageSpo2"),
            "avg_waking_respiration": d.get("avgWakingRespirationValue"),
        }
    )


def sleep(d: Json) -> Json:
    scores = d.get("sleepScores") or {}
    overall = scores.get("overall") if isinstance(scores, dict) else None
    score = overall.get("value") if isinstance(overall, dict) else None
    return _clean(
        {
            "date": d.get("calendarDate"),
            "start_local": _ts(d.get("sleepStartTimestampLocal")),
            "end_local": _ts(d.get("sleepEndTimestampLocal")),
            "total_h": _r((d.get("sleepTimeSeconds") or 0) / 3600, 2) if d.get("sleepTimeSeconds") else None,
            "deep_min": _min(d.get("deepSleepSeconds")),
            "light_min": _min(d.get("lightSleepSeconds")),
            "rem_min": _min(d.get("remSleepSeconds")),
            "awake_min": _min(d.get("awakeSleepSeconds")),
            "awake_count": d.get("awakeCount"),
            "score": score,
            "score_feedback": d.get("sleepScoreFeedback"),
            "avg_hr_bpm": d.get("avgHeartRate"),
            "avg_stress": d.get("avgSleepStress"),
            "avg_respiration": d.get("averageRespirationValue"),
            "avg_spo2": d.get("averageSpO2Value"),
            "nap_min": _min(d.get("napTimeSeconds")),
        }
    )


def hrv(d: Json) -> Json:
    s = d.get("hrvSummary") or {}
    b = s.get("baseline") or {}
    return _clean(
        {
            "date": s.get("calendarDate"),
            "last_night_avg_ms": s.get("lastNightAvg"),
            "last_night_5min_high_ms": s.get("lastNight5MinHigh"),
            "weekly_avg_ms": s.get("weeklyAvg"),
            "status": s.get("status"),
            "feedback": s.get("feedbackPhrase"),
            "baseline": _clean({k: v for k, v in b.items()}) if isinstance(b, dict) else None,
            "readings": len(d.get("hrvReadings") or []) or None,
        }
    )
