"""Exchange the Personal API key for a bearer token, cache it, and renew it before expiry.

Per Garmin's Personal API FAQ, access tokens last 24 hours (or until the key expires) and
refresh tokens are not supported, so renewing means re-posting the key to the token endpoint.
The endpoint returns the JWT as the raw response body; expiry is read from its ``exp`` claim.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from .config import BASE_URL, TOKEN_PATH, home_dir

log = logging.getLogger(__name__)

REFRESH_WINDOW_SECONDS = 60 * 60  # renew when less than an hour is left


class AuthError(RuntimeError):
    """Token exchange failed. Messages never contain the key or token."""


def fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def jwt_expiry(token: str) -> float:
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(claims["exp"])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise AuthError("Token endpoint did not return a JWT with an exp claim.") from exc


class TokenManager:
    def __init__(
        self,
        api_key: str,
        http: httpx.Client,
        cache_file: Path | None = None,
        clock: Callable[[], float] = time.time,
        base_url: str = BASE_URL,
    ) -> None:
        self._key = api_key
        self._fp = fingerprint(api_key + "|" + base_url)
        self._http = http
        self._cache_file = cache_file or (home_dir() / "token.json")
        self._clock = clock
        self._base_url = base_url
        self._token: str | None = None
        self._expires_at: float = 0.0

    def __repr__(self) -> str:  # never leak secrets via repr
        return f"TokenManager(fingerprint={self._fp})"

    def _fresh(self) -> bool:
        return self._token is not None and self._expires_at - self._clock() > REFRESH_WINDOW_SECONDS

    def _read_cache(self) -> None:
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if data.get("fingerprint") == self._fp and isinstance(data.get("access_token"), str):
            self._token = data["access_token"]
            self._expires_at = float(data.get("expires_at", 0))

    def _write_cache(self) -> None:
        self._cache_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self._cache_file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"fingerprint": self._fp, "access_token": self._token, "expires_at": self._expires_at}, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._cache_file)

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0
        try:
            self._cache_file.unlink()
        except FileNotFoundError:
            pass

    def _exchange(self) -> None:
        log.info("Requesting a new access token")
        try:
            resp = self._http.post(
                self._base_url + TOKEN_PATH,
                headers={"Accept": "*/*", "Authorization": f"ApiKey {self._key}"},
            )
        except httpx.HTTPError as exc:
            raise AuthError(f"Token request failed: {type(exc).__name__}") from None
        if resp.status_code != 200:
            hint = " Check the key in ~/.garmin-mcp/.env; it may be expired or deleted." if resp.status_code in (401, 403) else ""
            raise AuthError(f"Token endpoint returned HTTP {resp.status_code}.{hint}")
        token = resp.text.strip().strip('"')
        try:
            self._expires_at = jwt_expiry(token)
        except AuthError:
            # Docs promise 24 h validity; be conservative if the body is not a JWT.
            log.warning("Token is not a JWT with exp; assuming 23 h validity")
            self._expires_at = self._clock() + 23 * 3600
        self._token = token
        self._write_cache()

    def token(self) -> str:
        if not self._fresh():
            self._read_cache()
        if not self._fresh():
            self._exchange()
        assert self._token is not None
        return self._token
