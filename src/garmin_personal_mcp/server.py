"""Read-only MCP server exposing Garmin Connect Personal API data for training review.

Endpoints are taken from Garmin's official Personal API OpenAPI spec (docs/openapi.json).
All tools return trimmed JSON. Credentials never appear in tool output or logs.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from functools import lru_cache
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import trim
from .client import GarminClient

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpcore", "mcp"):
    logging.getLogger(noisy).setLevel(logging.WARNING)  # httpx logs full URLs at INFO

mcp = MCPServer(
    "garmin-personal",
    instructions=(
        "Read-only access to the user's own Garmin Connect data via the official Personal API. "
        "Use for weekly training reviews. Training readiness is not exposed by the Personal API."
    ),
)

MAX_RANGE_DAYS = 92


@lru_cache(maxsize=1)
def _client() -> GarminClient:
    return GarminClient.from_env()


def _date(value: str, name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be YYYY-MM-DD, got {value!r}") from None


def _range(start: str, end: str) -> tuple[str, str]:
    s, e = _date(start, "start"), _date(end, "end")
    if s > e:
        raise ValueError("start must be on or before end")
    if (e - s).days > MAX_RANGE_DAYS:
        raise ValueError(f"range is limited to {MAX_RANGE_DAYS} days")
    return s.isoformat(), e.isoformat()


def _search(start: str, end: str, limit: int) -> list[dict[str, Any]]:
    return _client().get(
        "/activitylist-service/activities/search/activities",
        {"startDate": start, "endDate": end, "limit": limit, "start": 0},
    ) or []


@mcp.tool()
def list_activities(start: str, end: str, limit: int = 20) -> list[dict[str, Any]]:
    """List activities between two local dates (YYYY-MM-DD, inclusive), newest first.

    Returns distance (km), duration (min), pace, heart rate, training effect, load and
    time in each HR zone. Use get_activity for splits.
    """
    s, e = _range(start, end)
    limit = max(1, min(int(limit), 100))
    return [trim.activity_list_item(a) for a in _search(s, e, limit)]


@mcp.tool()
def get_activity(activity_id: int) -> dict[str, Any]:
    """One activity in detail: summary, heart rate (avg/max/min, recovery, time in zones with
    zone floors in bpm) and split summaries (grouped by split type, e.g. run/walk/interval).
    Per-km laps and second-by-second HR are not exposed by the Personal API."""
    c = _client()
    detail = c.get(f"/activity-service/activity/{int(activity_id)}")
    if not detail:
        raise ValueError(f"activity {activity_id} not found")
    day = ((detail.get("summaryDTO") or {}).get("startTimeLocal") or "")[:10]
    match = None
    if day:
        match = next((a for a in _search(day, day, 100) if a.get("activityId") == int(activity_id)), None)
    out = trim.activity_detail(detail, match)
    zones = c.get("/biometric-service/heartRateZones/v2") or []
    floors = trim.zone_floors(zones, (detail.get("activityTypeDTO") or {}).get("typeKey"))
    if floors and "heart_rate" in out:
        out["heart_rate"]["zone_floors_bpm"] = floors
    return out


@mcp.tool()
def daily_summary(date: str) -> dict[str, Any]:
    """Daily wellness summary for one date (YYYY-MM-DD): steps, resting HR, stress,
    Body Battery, intensity minutes, calories."""
    d = _date(date, "date").isoformat()
    raw = _client().get("/usersummary-service/usersummary/daily", {"calendarDate": d})
    return trim.daily_summary(raw) if raw else {"date": d, "available": False}


@mcp.tool()
def sleep(date: str) -> dict[str, Any]:
    """Sleep for one date (YYYY-MM-DD; Garmin files sleep under the wake-up day, unverified):
    duration, stages, score, overnight HR, stress, respiration, SpO2."""
    d = _date(date, "date").isoformat()
    raw = _client().get("/sleep-service/sleep/dailySleep", {"date": d})
    return trim.sleep(raw) if raw else {"date": d, "available": False}


@mcp.tool()
def hrv(date: str) -> dict[str, Any]:
    """Overnight HRV for one date (YYYY-MM-DD): last-night average, weekly average,
    baseline range and status. Returns available=false if the watch recorded none."""
    d = _date(date, "date").isoformat()
    raw = _client().get(f"/hrv-service/hrv/{d}")
    return trim.hrv(raw) if raw else {"date": d, "available": False}


@mcp.tool()
def hrv_range(start: str, end: str) -> list[dict[str, Any]]:
    """Daily HRV summaries across a date range (YYYY-MM-DD, inclusive, max 92 days)."""
    s, e = _range(start, end)
    raw = _client().get(f"/hrv-service/hrv/daily/{s}/{e}") or {}
    items = raw.get("hrvSummaries", []) if isinstance(raw, dict) else raw
    return [trim.hrv({"hrvSummary": x}) for x in items]


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
