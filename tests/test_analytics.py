import datetime as dt

import httpx

from garmin_personal_mcp import analytics, server
from garmin_personal_mcp.config import BASE_URL as B

from .conftest import sample
from .test_tools import api  # noqa: F401  (fixture)


def _act(day, type_key, km, mins, load, hr=None, zones=(0, 0, 0, 0, 0)):
    a = {"startTimeLocal": f"{day} 07:00:00", "activityType": {"typeKey": type_key}, "distance": km * 1000,
         "duration": mins * 60, "activityTrainingLoad": load, "averageHR": hr}
    a.update({f"hrTimeInZone_{i + 1}": z * 60 for i, z in enumerate(zones)})
    return a


ACTS = [
    _act("2026-11-03", "running", 5, 30, 60, 150, (5, 15, 5, 5, 0)),       # Tue, week of 2 Nov
    _act("2026-11-05", "treadmill_running", 3, 20, 30, 140, (0, 20, 0, 0, 0)),
    _act("2026-11-04", "strength_training", 0, 40, 5),
    _act("2026-10-28", "running", 4, 26, 50, 155, (0, 10, 10, 6, 0)),       # week of 26 Oct
    _act("2026-10-20", "running", 10, 60, 99),                              # outside range
]
DAYS = [{"calendarDate": "2026-11-03", "heartRate": {"restingValue": 56}, "stress": {"avgLevel": 30}},
        {"calendarDate": "2026-11-04", "heartRate": {"restingValue": 58}, "stress": {"avgLevel": 40}}]
SLEEPS = [{"calendarDate": "2026-11-03", "sleepTimeSeconds": 7 * 3600, "sleepScores": {"overall": {"value": 80}}},
          {"calendarDate": "2026-11-04", "sleepTimeSeconds": 6 * 3600, "sleepScores": {"overall": {"value": 70}}}]
HRVS = [{"calendarDate": "2026-11-03", "lastNightAvg": 50, "status": "BALANCED"},
        {"calendarDate": "2026-11-04", "lastNightAvg": 60, "status": "UNBALANCED"}]


def test_weekly_buckets_and_totals():
    out = analytics.weekly_summary(dt.date(2026, 10, 26), dt.date(2026, 11, 7), ACTS, DAYS, SLEEPS, HRVS)
    assert [w["week_start"] for w in out["weeks"]] == ["2026-10-26", "2026-11-02"]
    wk = out["weeks"][1]
    t, r = wk["training"], wk["recovery"]
    assert t["activities"] == 3 and t["by_type"]["running"] == 1
    assert t["run"]["km"] == 8.0 and t["run"]["count"] == 2 and t["run"]["longest_km"] == 5.0
    assert t["run"]["avg_pace"] == "6:15 /km"          # 50 min over 8 km
    assert t["run"]["avg_hr_bpm"] == 146               # time-weighted: (150*30 + 140*20) / 50
    assert t["training_load"] == 95.0
    assert t["easy_pct_z1_z2"] == 80 and t["hard_pct_z4_z5"] == 10
    assert r["resting_hr_avg_bpm"] == 57.0 and r["sleep_h_avg"] == 6.5 and r["sleep_score_avg"] == 75.0
    assert r["hrv_last_night_avg_ms"] == 55.0 and r["hrv_status_days"] == {"BALANCED": 1, "UNBALANCED": 1}
    assert wk["partial"] is True                       # range ends Saturday
    assert wk["change_vs_prev_week"] == {"run_km": 4.0, "training_load": 45.0}
    assert out["totals"]["activities"] == 4            # 20 Oct run excluded


def test_empty_range_is_safe():
    out = analytics.weekly_summary(dt.date(2026, 11, 2), dt.date(2026, 11, 8), [], [], [], [])
    assert out["weeks"][0]["training"]["activities"] == 0 and out["weeks"][0]["recovery"] == {}


def test_chunks_cover_range_without_gaps():
    ch = server._chunks("2026-10-05", "2026-11-07", 28)
    assert ch == [("2026-10-05", "2026-11-01"), ("2026-11-02", "2026-11-07")]


def test_training_summary_tool_paginates_and_calls_range_endpoints(api):  # noqa: F811
    page1 = [ACTS[0]] * 100
    search = api.get(B + "/activitylist-service/activities/search/activities").mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=[ACTS[1]])])
    api.get(B + "/usersummary-service/v2/dailysummaries").mock(return_value=httpx.Response(200, json={"data": DAYS}))
    api.get(B + "/sleep-service/sleep/dailySleepSummariesByDate").mock(return_value=httpx.Response(200, json=SLEEPS))
    api.get(B + "/hrv-service/hrv/daily/2026-11-02/2026-11-08").mock(return_value=httpx.Response(200, json={"hrvSummaries": HRVS}))
    out = server.training_summary("2026-11-02", "2026-11-08")
    assert search.call_count == 2 and search.calls[1].request.url.params["start"] == "100"
    assert out["totals"]["activities"] == 101
    assert out["weeks"][0]["recovery"]["days_with_data"] == 2
