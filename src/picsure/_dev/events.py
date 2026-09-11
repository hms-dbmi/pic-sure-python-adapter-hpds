from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """A single dev-mode event: HTTP call, function, connect, or error.

    ``bytes_sent`` is the request-body size and ``bytes_received`` the
    response-body size, both from the client's point of view; either is
    ``None`` for an event with no HTTP exchange to measure. The pair was
    previously called ``bytes_in`` / ``bytes_out``, which read as the
    reverse of what it held.
    """

    timestamp: datetime
    kind: str
    name: str
    duration_ms: float
    bytes_sent: int | None
    bytes_received: int | None
    status: int | None
    retry: int
    error: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
