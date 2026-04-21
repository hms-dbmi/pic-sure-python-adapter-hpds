import logging
from datetime import datetime, timezone

import pytest

from picsure._dev.config import DevConfig
from picsure._dev.events import Event


def _make_event(kind: str = "http", name: str = "x") -> Event:
    return Event(
        timestamp=datetime.now(timezone.utc),
        kind=kind,
        name=name,
        duration_ms=1.0,
        bytes_in=0,
        bytes_out=0,
        status=200,
        retry=0,
        error=None,
        metadata={},
    )


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PICSURE_DEV_MODE", raising=False)
    monkeypatch.delenv("PICSURE_DEV_MAX_EVENTS", raising=False)


def test_from_env_unset_is_disabled():
    cfg = DevConfig.from_env(override=None)
    assert cfg.enabled is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "Yes"])
def test_from_env_truthy_values_enable(monkeypatch, val):
    monkeypatch.setenv("PICSURE_DEV_MODE", val)
    cfg = DevConfig.from_env(override=None)
    assert cfg.enabled is True


@pytest.mark.parametrize("val", ["", "0", "false", "no", "garbage"])
def test_from_env_other_values_disabled(monkeypatch, val):
    monkeypatch.setenv("PICSURE_DEV_MODE", val)
    cfg = DevConfig.from_env(override=None)
    assert cfg.enabled is False


def test_override_true_wins_over_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "0")
    cfg = DevConfig.from_env(override=True)
    assert cfg.enabled is True


def test_override_false_wins_over_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "1")
    cfg = DevConfig.from_env(override=False)
    assert cfg.enabled is False


def test_max_events_default():
    cfg = DevConfig.from_env(override=True)
    assert cfg.max_events == 1000


def test_max_events_from_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MAX_EVENTS", "50")
    cfg = DevConfig.from_env(override=True)
    assert cfg.max_events == 50


def test_max_events_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MAX_EVENTS", "not-a-number")
    cfg = DevConfig.from_env(override=True)
    assert cfg.max_events == 1000


def test_emit_when_disabled_is_noop():
    cfg = DevConfig(enabled=False, max_events=10)
    cfg.emit(_make_event())
    assert cfg.buffer.snapshot() == []


def test_emit_when_enabled_appends_and_logs(caplog):
    cfg = DevConfig(enabled=True, max_events=10)
    with caplog.at_level(logging.DEBUG, logger="picsure"):
        cfg.emit(_make_event(name="/picsure/search/abc"))
    assert len(cfg.buffer.snapshot()) == 1
    # A log record was emitted under the picsure.* hierarchy.
    assert any(r.name.startswith("picsure") for r in caplog.records)


def test_emit_swallows_buffer_errors(monkeypatch):
    cfg = DevConfig(enabled=True, max_events=10)

    def boom(_event):
        raise RuntimeError("buffer exploded")

    monkeypatch.setattr(cfg.buffer, "append", boom)
    # Must not raise.
    cfg.emit(_make_event())
