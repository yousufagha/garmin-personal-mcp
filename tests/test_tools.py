import json
import logging
import time

import httpx
import pytest
import respx

from garmin_personal_mcp import server
from garmin_personal_mcp.config import BASE_URL, TOKEN_PATH

from .conftest import FAKE_KEY, make_jwt, sample

B = BASE_URL


@pytest.fixture
def api(home, caplog):
    caplog.set_level(logging.DEBUG)
    server._client.cache_clear()
    with respx.mock(assert_all_called=False) as r:
        r.post(B + TOKEN_PATH).mock(return_value=httpx.Response(200, text=make_jwt(time.time() + 86400)))
        yield r
    server._client.cache_clear()
    assert FAKE_KEY not in caplog.text


def test_list_activities_trims(api):
    route = api.get(B + "/activitylist-service/activities/search/activities").mock(
        return_value=httpx.Response(200, json=sample("activities.json")))
    out = server.list_activities("2026-11-01", "2026-11-07", limit=5)
    q = route.calls[0].request.url.params
    assert (q["startDate"], q["endDate"], q["limit"]) == ("2026-11-01", "2026-11-07", "5")
    run = out[0]
    assert run["distance_km"] == 8.01 and run["type"] == "running"
    assert run["avg_pace"] == "5:41 /km"
    assert run["hr_zones"]["z3_min"] == 25.0
    assert "ownerFullName" not in json.dumps(out) and "startLatitude" not in json.dumps(out)


def test_get_activity_has_splits_hr_and_zone_floors(api):
    api.get(B + "/activity-service/activity/20811111111").mock(return_value=httpx.Response(200, json=sample("activity_detail.json")))
    search = api.get(B + "/activitylist-service/activities/search/activities").mock(
        return_value=httpx.Response(200, json=sample("activities.json")))
    api.get(B + "/biometric-service/heartRateZones/v2").mock(return_value=httpx.Response(200, json=sample("hr_zones.json")))
    out = server.get_activity(20811111111)
    assert search.calls[0].request.url.params["startDate"] == "2026-11-07"
    hr = out["heart_rate"]
    assert (hr["avg_bpm"], hr["max_bpm"], hr["min_bpm"]) == (152.0, 171.0, 96.0)
    assert hr["zones"]["z4_min"] == 9.3
    assert hr["zone_floors_bpm"]["z1"] == 100  # RUNNING zones chosen over DEFAULT
    assert [s["type"] for s in out["splits"]] == ["RWD_RUN", "RWD_WALK"]


def test_daily_sleep_hrv(api):
    api.get(B + "/usersummary-service/usersummary/daily").mock(return_value=httpx.Response(200, json=sample("daily_summary.json")))
    api.get(B + "/sleep-service/sleep/dailySleep").mock(return_value=httpx.Response(200, json=sample("sleep.json")))
    api.get(B + "/hrv-service/hrv/2026-11-07").mock(return_value=httpx.Response(200, json=sample("hrv.json")))
    d = server.daily_summary("2026-11-07")
    assert d["resting_hr_bpm"] == 49 and d["body_battery"]["at_wake"] == 86 and "displayName" not in d
    s = server.sleep("2026-11-07")
    assert s["total_h"] == 7.35 and s["score"] == 82 and s["deep_min"] == 87.0
    h = server.hrv("2026-11-07")
    assert h["last_night_avg_ms"] == 61 and h["status"] == "BALANCED" and h["baseline"]["balancedLow"] == 53


def test_sleep_epoch_ms_and_te_rounding():
    from garmin_personal_mcp import trim
    # observed live: local sleep timestamps arrive as epoch ms, TE as float32 noise
    s = trim.sleep({"calendarDate": "2026-11-07", "sleepStartTimestampLocal": 1794012137000, "sleepTimeSeconds": 3600})
    assert s["start_local"] == "2026-11-07T00:42:17"
    a = trim.activity_list_item({"activityId": 1, "aerobicTrainingEffect": 3.5999999046325684})
    assert a["aerobic_te"] == 3.6


def test_hrv_no_content_is_unavailable(api):
    api.get(B + "/hrv-service/hrv/2026-11-07").mock(return_value=httpx.Response(204))
    assert server.hrv("2026-11-07") == {"date": "2026-11-07", "available": False}


def test_401_reexchanges_token_once(api):
    route = api.get(B + "/usersummary-service/usersummary/daily").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=sample("daily_summary.json"))])
    assert server.daily_summary("2026-11-07")["steps"] == 14210
    assert route.call_count == 2
    assert api.routes[0].call_count == 2  # token endpoint hit again after the 401


def test_http_error_hides_credentials(api):
    api.get(B + "/sleep-service/sleep/dailySleep").mock(return_value=httpx.Response(500, text=FAKE_KEY))
    with pytest.raises(Exception) as exc:
        server.sleep("2026-11-07")
    assert "500" in str(exc.value) and FAKE_KEY not in str(exc.value) and "Bearer" not in str(exc.value)


@pytest.mark.parametrize("args", [("2026-11-08", "2026-11-01"), ("07/11/2026", "2026-11-07"), ("2026-01-01", "2026-12-31")])
def test_bad_ranges_rejected(home, args):
    with pytest.raises(ValueError):
        server.list_activities(*args)
