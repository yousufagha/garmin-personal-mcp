import logging
import os
import stat
import time

import httpx
import pytest
import respx

from garmin_personal_mcp.auth import AuthError, TokenManager
from garmin_personal_mcp.config import BASE_URL, TOKEN_PATH, ConfigError, load_api_key

from .conftest import FAKE_KEY, make_jwt

TOKEN_URL = BASE_URL + TOKEN_PATH


def test_load_key(home):
    assert load_api_key() == FAKE_KEY


def test_empty_key_message_is_helpful(home):
    (home / ".env").write_text("GARMIN_PERSONAL_API_KEY=\n")
    with pytest.raises(ConfigError, match="paste your Personal API key"):
        load_api_key()


@respx.mock
def test_exchange_sends_apikey_header_and_caches_0600(home):
    jwt = make_jwt(time.time() + 24 * 3600)
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, text=jwt))
    tm = TokenManager(FAKE_KEY, httpx.Client())
    assert tm.token() == jwt
    assert route.calls[0].request.headers["Authorization"] == f"ApiKey {FAKE_KEY}"
    cache = home / "token.json"
    assert stat.S_IMODE(os.stat(cache).st_mode) == 0o600
    assert FAKE_KEY not in cache.read_text()  # only a fingerprint of the key is stored
    # second manager reuses the cache without a network call
    assert TokenManager(FAKE_KEY, httpx.Client()).token() == jwt
    assert route.call_count == 1


@respx.mock
def test_refreshes_when_near_expiry(home):
    now = [1_000_000.0]
    first, second = make_jwt(now[0] + 24 * 3600), make_jwt(now[0] + 48 * 3600)
    route = respx.post(TOKEN_URL).mock(side_effect=[httpx.Response(200, text=first), httpx.Response(200, text=second)])
    tm = TokenManager(FAKE_KEY, httpx.Client(), clock=lambda: now[0])
    assert tm.token() == first
    now[0] += 23.5 * 3600  # inside the 1 h refresh window
    assert tm.token() == second
    assert route.call_count == 2


@respx.mock
def test_new_key_ignores_old_cache(home):
    respx.post(TOKEN_URL).mock(side_effect=[httpx.Response(200, text=make_jwt(time.time() + 86400)),
                                            httpx.Response(200, text=make_jwt(time.time() + 90000))])
    a = TokenManager(FAKE_KEY, httpx.Client()).token()
    b = TokenManager("another-key", httpx.Client()).token()
    assert a != b


@respx.mock
def test_non_jwt_falls_back_to_23h(home):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, text="opaque-token"))
    tm = TokenManager(FAKE_KEY, httpx.Client(), clock=lambda: 0.0)
    assert tm.token() == "opaque-token"
    assert tm._expires_at == 23 * 3600


@respx.mock
def test_key_never_logged_or_in_errors(home, caplog):
    caplog.set_level(logging.DEBUG)
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401, text=f"bad key {FAKE_KEY}"))
    tm = TokenManager(FAKE_KEY, httpx.Client())
    with pytest.raises(AuthError) as exc:
        tm.token()
    assert FAKE_KEY not in str(exc.value)
    assert FAKE_KEY not in repr(tm)
    assert FAKE_KEY not in caplog.text
    assert "401" in str(exc.value)
