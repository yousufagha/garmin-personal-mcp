import base64
import json
import os
from pathlib import Path

import pytest

SAMPLES = Path(__file__).parent / "samples"
FAKE_KEY = "pk_test_SECRET_KEY_value_1234567890"


def sample(name: str):
    return json.loads((SAMPLES / name).read_text())


def make_jwt(exp: float) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'none'})}.{enc({'exp': exp, 'sub': 'me'})}.SIGNATURE_SECRET"


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / ".garmin-mcp"
    h.mkdir(mode=0o700)
    env = h / ".env"
    env.write_text(f"GARMIN_PERSONAL_API_KEY={FAKE_KEY}\n")
    os.chmod(env, 0o600)
    monkeypatch.setenv("GARMIN_MCP_HOME", str(h))
    monkeypatch.delenv("GARMIN_PERSONAL_API_KEY", raising=False)
    return h
