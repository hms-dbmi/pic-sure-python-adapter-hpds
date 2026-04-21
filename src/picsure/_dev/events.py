from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """A single dev-mode event: HTTP call, function, connect, or error."""

    timestamp: datetime
    kind: str
    name: str
    duration_ms: float
    bytes_in: int | None
    bytes_out: int | None
    status: int | None
    retry: int
    error: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
