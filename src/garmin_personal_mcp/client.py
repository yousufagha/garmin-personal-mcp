"""Thin read-only HTTP client for the Garmin Connect Personal API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .auth import TokenManager
from .config import BASE_URL, load_api_key

log = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """A data request failed. Messages carry path and status only, never credentials."""


class GarminClient:
    def __init__(self, tokens: TokenManager, http: httpx.Client, base_url: str = BASE_URL) -> None:
        self._tokens = tokens
        self._http = http
        self._base_url = base_url

    @classmethod
    def from_env(cls) -> "GarminClient":
        http = httpx.Client(timeout=30.0)
        return cls(TokenManager(load_api_key(), http), http)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        for attempt in (1, 2):
            headers = {"Accept": "application/json", "Authorization": f"Bearer {self._tokens.token()}"}
            log.info("GET %s", path)
            try:
                resp = self._http.get(self._base_url + path, params=params, headers=headers)
            except httpx.HTTPError as exc:
                raise ApiError(f"GET {path} failed: {type(exc).__name__}") from None
            if resp.status_code == 401 and attempt == 1:
                self._tokens.invalidate()  # token revoked or expired early: re-exchange once
                continue
            break
        if resp.status_code == 204 or not resp.content:
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise ApiError(f"GET {path} returned HTTP {resp.status_code}")
        return resp.json()
