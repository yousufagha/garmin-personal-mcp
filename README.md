# garmin-personal-mcp

A small, read-only [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude read my own Garmin training and recovery data through Garmin's **official** [Connect Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api), so it can run a weekly training review with me.

No scraping, no unofficial libraries, no stored passwords. One API key, kept in a local file the code never prints.

## Why this exists

I train with a Garmin watch and wanted an assistant that reviews the week from real numbers (load, heart-rate zones, sleep, HRV), not from what I remember. Garmin opened a Personal API to individual users in 2026. This project turns it into tools an LLM can call safely.

## What it shows (for reviewers)

| Skill | Where to look |
|---|---|
| Working from a primary spec, not guesswork | `scripts/fetch_spec.py` pulls Garmin's OpenAPI 3.0.1 spec out of the official docs page into `docs/openapi.json` (not committed, as it is Garmin's content). Every endpoint and field name in the code traces back to it. |
| Secure credential handling | `auth.py`: key loaded from a `0600` file, exchanged for a 24 h bearer token, cached as a `0600` file holding only a key fingerprint, renewed an hour before expiry, re-exchanged once on `401`. Errors and logs carry status codes and paths only. |
| Data shaping for LLMs | `trim.py`: Garmin activity payloads have 190 to 230 fields. Each tool returns about 15 to 20, with units in the key names (`distance_km`, `avg_hr_bpm`, `avg_pace`). |
| Testing | 16 pytest tests on spec-shaped sample responses with mocked HTTP (`respx`), including tests that fail if the key ever appears in logs, errors, reprs or the token cache. |
| Honest scoping | Metrics the API does not expose are listed below rather than faked. |

## Tools

| Tool | Garmin endpoint | Returns |
|---|---|---|
| `list_activities(start, end, limit)` | `/activitylist-service/activities/search/activities` | Distance, time, pace, HR, training effect, load, VO2 max, minutes in each HR zone |
| `get_activity(activity_id)` | `/activity-service/activity/{id}` + list + `/biometric-service/heartRateZones/v2` | Summary, HR (avg, max, min, recovery, zones with bpm floors), split summaries |
| `daily_summary(date)` | `/usersummary-service/usersummary/daily` | Steps, resting HR and 7-day average, stress, Body Battery, intensity minutes |
| `sleep(date)` | `/sleep-service/sleep/dailySleep` | Duration, stages, sleep score, overnight HR, stress, respiration, SpO2 |
| `hrv(date)` | `/hrv-service/hrv/{date}` | Last-night and weekly HRV, baseline range, status |
| `hrv_range(start, end)` | `/hrv-service/hrv/daily/{from}/{to}` | Daily HRV summaries for trend review |

### Not available from the Personal API (as of Nov 2026)

- **Training readiness**: no endpoint in the published spec.
- **Per-km laps and second-by-second HR**: activity detail gives split summaries grouped by type (run, walk, interval), not laps. Raw streams are only in the FIT file (`/download-service/files/activity/{id}`), which this server does not parse yet.

## Architecture

```
Claude Desktop ──stdio/JSON-RPC──▶ server.py (MCPServer, 6 tools)
                                     │  validate dates, cap ranges (92 days)
                                     ▼
                                   client.py ── GET, Bearer token, 401 → re-exchange once
                                     │
                                   auth.py ── POST ApiKey → JWT, cache ~/.garmin-mcp/token.json (0600)
                                     │
                                   trim.py ── raw JSON → compact, unit-labelled JSON
```

## Setup

Free. Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and a Garmin Connect account.

1. In Garmin Connect web, open **Settings → Personal API Key** and create a key. It is shown once.
2. Put it in `~/.garmin-mcp/.env` (permissions `600`):
   ```
   GARMIN_PERSONAL_API_KEY=your-key
   ```
3. Install and test:
   ```bash
   uv sync && uv run pytest -q
   ```
4. Add to `~/Library/Application Support/Claude/claude_desktop_config.json` under `mcpServers`:
   ```json
   "garmin-personal": {
     "command": "/absolute/path/to/uv",
     "args": ["--directory", "/absolute/path/to/garmin-personal-mcp", "run", "--quiet", "--frozen", "garmin-personal-mcp"]
   }
   ```
   Quit Claude Desktop fully (Cmd+Q) and reopen it.

## Design decisions

- **Key in a file, not in the Claude config `env` block**: that file is synced and backed up by other tools; a `0600` file in the home directory is not.
- **Token renewal by re-exchange**: the FAQ states refresh tokens are not supported and access tokens last 24 h, so the server re-posts the key when under an hour remains.
- **Token response as raw JWT**: the token endpoint is not in the OpenAPI spec. Its format follows Garmin's own Apache-2.0 client ([garmin/connect-personal-api-python](https://github.com/garmin/connect-personal-api-python)); a 23 h fallback covers a non-JWT body.
- **stdout is protocol only**: all logging goes to stderr and `httpx` is held at WARNING, since it logs full URLs at INFO.
- **`--frozen` launch**: Claude Desktop starts the server with no network resolution step, so a lockfile change cannot stall the handshake.

## Licence

MIT. Garmin and Garmin Connect are trademarks of Garmin Ltd. This project is not affiliated with Garmin.
