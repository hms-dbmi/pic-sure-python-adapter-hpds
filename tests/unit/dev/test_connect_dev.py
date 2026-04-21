import logging

import httpx
import pytest
import respx

from picsure import connect

CUSTOM_URL = "https://test.example.com"


def _mock_platform_endpoints():
    # Mocks the three endpoints `connect()` hits for a custom URL
    # with include_consents=False (the default for custom URLs).
    respx.get(f"{CUSTOM_URL}/psama/user/me").mock(
        return_value=httpx.Response(
            200, json={"email": "u@e", "expirationDate": "2026-06-15"}
        )
    )
    respx.get(f"{CUSTOM_URL}/picsure/info/resources").mock(
        return_value=httpx.Response(200, json={"uuid-1": "hpds"})
    )
    respx.post(
        f"{CUSTOM_URL}/picsure/proxy/dictionary-api/concepts?page_number=0&page_size=1"
    ).mock(return_value=httpx.Response(200, json={"content": [], "totalElements": 57}))


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
    session = connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1")
    assert session.dev_mode is True


@respx.mock
def test_dev_mode_none_respects_env_unset():
    _mock_platform_endpoints()
    session = connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1")
    assert session.dev_mode is False


@respx.mock
def test_dev_mode_true_overrides_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "0")
    _mock_platform_endpoints()
    session = connect(
        platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=True
    )
    assert session.dev_mode is True


@respx.mock
def test_dev_mode_false_overrides_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "1")
    _mock_platform_endpoints()
    session = connect(
        platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=False
    )
    assert session.dev_mode is False


@respx.mock
def test_dev_mode_records_connect_event():
    _mock_platform_endpoints()
    session = connect(
        platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=True
    )
    events = session.dev_events()
    connect_rows = events[events["kind"] == "connect"]
    assert len(connect_rows) == 1
    assert connect_rows.iloc[0]["name"] == "connect"
    md = connect_rows.iloc[0]["metadata"]
    assert md["resources"] == 1
    assert md["requires_auth"] is True


@respx.mock
def test_dev_mode_installs_default_handler_when_none():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    assert logger.handlers == []
    connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=True)
    assert len(logger.handlers) >= 1


@respx.mock
def test_dev_mode_skips_default_handler_when_user_configured():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    user_handler = logging.StreamHandler()
    logger.addHandler(user_handler)
    try:
        connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=True)
        assert logger.handlers == [user_handler]
    finally:
        logger.removeHandler(user_handler)


@respx.mock
def test_dev_mode_off_does_not_install_handler():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=False)
    assert logger.handlers == []
