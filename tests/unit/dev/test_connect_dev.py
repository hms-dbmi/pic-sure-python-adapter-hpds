import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from picsure import connect

CUSTOM_URL = "https://test.example.com"


def _make_token() -> str:
    """A well-formed, unexpired JWT.

    These tests are about developer-mode instrumentation, not about
    tokens, so the token needs to be plausible enough to get past
    connect()'s local checks and then stay out of the way.
    """
    exp = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())

    def segment(payload: dict) -> str:
        raw = json.dumps(payload).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = segment({"alg": "none", "typ": "JWT"})
    claims = segment({"sub": "dev-user", "email": "dev@example.com", "exp": exp})
    return f"{header}.{claims}.sig"


TOKEN = _make_token()


def _mock_platform_endpoints():
    # The two requests `connect()` makes for a custom URL with the
    # consent policy unstated: the credential check, then the
    # consent-scoping probe.
    respx.get(f"{CUSTOM_URL}/psama/user/me").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "e23d9260-3324-4528-8c2c-7bd3dcb4aa74",
                "email": "dev@example.com",
                "privileges": ["API_ACCESS"],
            },
        )
    )
    respx.get(f"{CUSTOM_URL}/psama/user/me/consents").mock(
        return_value=httpx.Response(200, json={"consents": {}})
    )


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PICSURE_DEV_MODE", raising=False)
    monkeypatch.delenv("PICSURE_DEV_MAX_EVENTS", raising=False)


@pytest.fixture(autouse=True)
def _reset_picsure_logger():
    logger = logging.getLogger("picsure")
    saved = list(logger.handlers)
    logger.handlers.clear()
    yield
    logger.handlers.clear()
    logger.handlers.extend(saved)


@respx.mock
def test_dev_mode_none_respects_env_true(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "1")
    _mock_platform_endpoints()
    session = connect(platform=CUSTOM_URL, token=TOKEN)
    assert session.dev_mode is True


@respx.mock
def test_dev_mode_none_respects_env_unset():
    _mock_platform_endpoints()
    session = connect(platform=CUSTOM_URL, token=TOKEN)
    assert session.dev_mode is False


@respx.mock
def test_dev_mode_true_overrides_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "0")
    _mock_platform_endpoints()
    session = connect(platform=CUSTOM_URL, token=TOKEN, dev_mode=True)
    assert session.dev_mode is True


@respx.mock
def test_dev_mode_false_overrides_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "1")
    _mock_platform_endpoints()
    session = connect(platform=CUSTOM_URL, token=TOKEN, dev_mode=False)
    assert session.dev_mode is False


@respx.mock
def test_dev_mode_records_connect_event():
    _mock_platform_endpoints()
    session = connect(platform=CUSTOM_URL, token=TOKEN, dev_mode=True)
    events = session.dev_events()
    connect_rows = events[events["kind"] == "connect"]
    assert len(connect_rows) == 1
    assert connect_rows.iloc[0]["name"] == "connect"
    md = connect_rows.iloc[0]["metadata"]
    # The resource registry was removed, so the connect event no longer
    # carries a "resources" count; it still records consents + auth.
    assert "resources" not in md
    assert md["consents"] == 0
    assert md["requires_auth"] is True


@respx.mock
def test_dev_mode_installs_default_handler_when_none():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    assert logger.handlers == []
    connect(platform=CUSTOM_URL, token=TOKEN, dev_mode=True)
    assert len(logger.handlers) >= 1


@respx.mock
def test_dev_mode_skips_default_handler_when_user_configured():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    user_handler = logging.StreamHandler()
    logger.addHandler(user_handler)
    try:
        connect(platform=CUSTOM_URL, token=TOKEN, dev_mode=True)
        assert logger.handlers == [user_handler]
    finally:
        logger.removeHandler(user_handler)


@respx.mock
def test_dev_mode_off_does_not_install_handler():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    connect(platform=CUSTOM_URL, token=TOKEN, dev_mode=False)
    assert logger.handlers == []
