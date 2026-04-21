import pytest

from picsure._dev.config import DevConfig
from picsure._dev.timing import timed


class _Fake:
    def __init__(self, cfg: DevConfig):
        self._dev_config = cfg

    @timed("fake.method")
    def method(self, x):
        return x * 2

    @timed("fake.raiser")
    def raiser(self):
        raise ValueError("nope")


def test_timed_emits_function_event_when_enabled():
    cfg = DevConfig(enabled=True, max_events=10)
    obj = _Fake(cfg)
    assert obj.method(3) == 6

    events = cfg.buffer.snapshot()
    assert len(events) == 1
    assert events[0].kind == "function"
    assert events[0].name == "fake.method"
    assert events[0].duration_ms >= 0
    assert events[0].error is None


def test_timed_no_event_when_disabled():
    cfg = DevConfig(enabled=False, max_events=10)
    obj = _Fake(cfg)
    assert obj.method(3) == 6
    assert cfg.buffer.snapshot() == []


def test_timed_records_error_and_reraises():
    cfg = DevConfig(enabled=True, max_events=10)
    obj = _Fake(cfg)
    with pytest.raises(ValueError):
        obj.raiser()

    events = cfg.buffer.snapshot()
    assert len(events) == 1
    assert events[0].kind == "error"
    assert events[0].name == "fake.raiser"
    assert events[0].error == "ValueError"


def test_timed_returns_value_unchanged():
    cfg = DevConfig(enabled=True, max_events=10)
    obj = _Fake(cfg)
    assert obj.method(7) == 14


def test_timed_tolerates_missing_dev_config():
    class _NoDev:
        @timed("x")
        def method(self):
            return "ok"

    assert _NoDev().method() == "ok"
