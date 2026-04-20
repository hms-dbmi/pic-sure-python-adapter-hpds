from datetime import datetime, timezone

from picsure._dev.events import Event


def test_event_has_all_fields():
    ts = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
    event = Event(
        timestamp=ts,
        kind="http",
        name="/picsure/search/abc",
        duration_ms=312.4,
        bytes_in=187,
        bytes_out=42100,
        status=200,
        retry=0,
        error=None,
        metadata={"foo": "bar"},
    )
    assert event.timestamp == ts
    assert event.kind == "http"
    assert event.name == "/picsure/search/abc"
    assert event.duration_ms == 312.4
    assert event.bytes_in == 187
    assert event.bytes_out == 42100
    assert event.status == 200
    assert event.retry == 0
    assert event.error is None
    assert event.metadata == {"foo": "bar"}


def test_event_is_frozen():
    import dataclasses

    event = Event(
        timestamp=datetime.now(timezone.utc),
        kind="function",
        name="session.search",
        duration_ms=10.0,
        bytes_in=None,
        bytes_out=None,
        status=None,
        retry=0,
        error=None,
        metadata={},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.kind = "http"


import pytest  # noqa: E402 — keep at bottom so failing import is obvious
