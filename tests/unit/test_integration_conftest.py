"""Tests for the integration suite's own configuration helpers.

The integration ``conftest.py`` reads its environment at import time, so
it is loaded once from its file path and its module-level settings are
patched per test.
"""

import importlib.util
from pathlib import Path

import pytest

_CONFTEST = Path(__file__).resolve().parents[1] / "integration" / "conftest.py"


@pytest.fixture(scope="module")
def integration_conftest():
    spec = importlib.util.spec_from_file_location("integration_conftest", _CONFTEST)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestResolveTestPlatform:
    def test_an_https_url_is_accepted(self, integration_conftest, monkeypatch):
        monkeypatch.setattr(
            integration_conftest, "PICSURE_TEST_PLATFORM", "https://pic-sure.example"
        )
        assert (
            integration_conftest._resolve_test_platform() == "https://pic-sure.example"
        )

    def test_a_plaintext_http_url_is_refused(self, integration_conftest, monkeypatch):
        monkeypatch.setattr(
            integration_conftest, "PICSURE_TEST_PLATFORM", "http://pic-sure.example"
        )
        assert integration_conftest._resolve_test_platform() is None

    def test_the_skip_message_says_https_only(self, integration_conftest, monkeypatch):
        monkeypatch.setattr(
            integration_conftest, "PICSURE_TEST_PLATFORM", "http://pic-sure.example"
        )
        reason = integration_conftest._unconfigured_reason()
        assert reason is not None
        assert "https://" in reason
        assert "http(s)" not in reason
