# PLAN: garmin-personal-mcp

Local, read-only MCP server (stdio) over the official Garmin Connect Personal API.
Source of truth: `docs/openapi.json`, extracted verbatim from
developer.garmin.com/gc-developer-program/personal/swagger-docs/ (OpenAPI 3.0.1),
plus the Personal API page and FAQ.

## Facts from official docs
- Token: `POST https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token`,
  header `Authorization: ApiKey <key>`. Response body is the raw JWT (per Garmin's official
  Apache-2.0 client `garmin/connect-personal-api-python`); expiry is the JWT `exp` claim.
- Token valid 24 h or until key expiry. No refresh tokens: re-POST the key.
- Data calls: `Authorization: Bearer <jwt>`, `Accept: application/json`, base `https://personal.connectapi.garmin.com`.
- No training-readiness endpoint in the spec. HRV is exposed.
- Activity detail returns `splitSummaries` (per split *type*, e.g. run/walk/interval), not per-km laps.
  No HR time series per activity (only the FIT download). Avg/max/min HR + HR time in zones are available.

## Layout
- `src/garmin_personal_mcp/config.py`  : load key from `~/.garmin-mcp/.env` (override `GARMIN_MCP_HOME`), warn if perms not 600.
- `src/garmin_personal_mcp/auth.py`    : TokenManager. Cache `{fingerprint, access_token, expires_at}` in `~/.garmin-mcp/token.json` (0600).
  Refresh when < 1 h left, or on a 401 (one retry). Fingerprint = sha256(key)[:16], so a new key invalidates the cache.
- `src/garmin_personal_mcp/client.py`  : httpx GET wrapper; errors never include the key or token.
- `src/garmin_personal_mcp/trim.py`    : pure functions that trim raw JSON to review-relevant fields; drop nulls.
- `src/garmin_personal_mcp/server.py`  : FastMCP tools:
  - `list_activities(start, end, limit=20)` -> `/activitylist-service/activities/search/activities?startDate&endDate&limit`
  - `get_activity(activity_id)` -> `/activity-service/activity/{id}` + HR zones from list item for that day
  - `daily_summary(date)` -> `/usersummary-service/usersummary/daily?calendarDate`
  - `sleep(date)` -> `/sleep-service/sleep/dailySleep?date`
  - `hrv(date)` -> `/hrv-service/hrv/{date}`
  - `training_readiness`: not exposed, not implemented; documented in README.
- `tests/` : pytest with saved sample responses (schema-shaped fixtures), respx mocks for HTTP,
  a test asserting the key never appears in logs or error messages, token-cache expiry tests.

## Edge cases
- Dates validated as YYYY-MM-DD; start <= end; list limit capped at 100.
- Empty `.env` value -> clear error telling the user to paste the key into the file.
- 401 on data call -> drop cache, re-exchange once, then fail.
- 429/5xx -> surface status code only.
- Logging goes to stderr (stdout is the MCP stdio channel).

## Registration
Back up `claude_desktop_config.json` with a timestamp, merge `mcpServers.garmin-personal`
(`uv --directory <repo> run garmin-personal-mcp`), keep every other key. Absolute path to `uv`.
