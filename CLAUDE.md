# garmin-personal-mcp decisions

- 2026-11-07: Endpoints and field names come only from docs/openapi.json (Garmin official spec, extracted from the swagger-docs page bundle).
- 2026-11-07: Token body treated as raw JWT, expiry from `exp` (per Garmin's official Python client); 23 h fallback if not a JWT.
- 2026-11-07: Key lives in ~/.garmin-mcp/.env (0600), never in claude_desktop_config.json env.
- 2026-11-07: mcp pinned to 2.x (FastMCP renamed MCPServer in 2.0).
- 2026-11-07: Training readiness not implemented: no endpoint in the Personal API spec.
- 2026-11-07: get_activity joins list-endpoint HR zone minutes and /heartRateZones/v2 floors (detail DTO lacks them).
- 2026-11-07: training_summary aggregates by ISO week from range endpoints; range calls chunked at 28 days (sleep range 400s at 34 days, observed live).
- 2026-11-07: Sleep *Local timestamps arrive as epoch ms (spec says string); formatted in UTC to keep wall-clock time.
