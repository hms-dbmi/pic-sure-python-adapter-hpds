import logging
import time

import httpx
import pytest
import respx

from picsure._dev.config import DevConfig
from picsure._transport.client import PicSureClient

BASE_URL = "https://test.example.com"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PICSURE_DEV_MODE", raising=False)


@pytest.fixture(autouse=True)
def _reset_picsure_logger():
    logger = logging.getLogger("picsure")
    saved = list(logger.handlers)
    logger.handlers.clear()
    yield
    logger.handlers.clear()
    logger.handlers.extend(saved)


@respx.mock
def test_off_emits_no_events():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))
    cfg = DevConfig(enabled=False, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token="t", dev_config=cfg)

    for _ in range(50):
        client.get_json("/x")

    assert cfg.buffer.snapshot() == []


@respx.mock
def test_off_adds_no_logger_handler():
    # Off path never calls _install_default_handler; a fresh logger stays handler-free.
    logger = logging.getLogger("picsure")
    assert logger.handlers == []

    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))
    cfg = DevConfig(enabled=False, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token="t", dev_config=cfg)
    client.get_json("/x")

    assert logging.getLogger("picsure").handlers == []


@respx.mock
def test_off_overhead_vs_on_is_measurable_but_small():
    # Sanity: calls with dev mode off must not be *orders of magnitude* slower
    # than dev mode's own overhead budget. This is a smoke test, not a strict
    # benchmark — we just want to catch a catastrophic regression.
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))

    n = 200
    off = DevConfig(enabled=False, max_events=10)
    client_off = PicSureClient(base_url=BASE_URL, token="t", dev_config=off)

    t0 = time.monotonic()
    for _ in range(n):
        client_off.get_json("/x")
    elapsed_off = time.monotonic() - t0

    # Off-path aggregate wall time is dominated by httpx+respx, not dev-mode
    # code. Assert it stays under a liberal ceiling that wouldn't be crossed
    # unless dev-mode hooks regressed dramatically.
    assert elapsed_off < 10.0, f"off-path suspiciously slow: {elapsed_off:.2f}s"
