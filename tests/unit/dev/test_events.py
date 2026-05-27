from datetime import datetime, timezone

from picsure._dev.events import Event


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
