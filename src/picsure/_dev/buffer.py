from __future__ import annotations

import threading
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picsure._dev.events import Event


class EventBuffer:
    """Thread-safe FIFO of dev-mode events with a fixed maximum size.

    When full, the oldest entry is dropped on append.
    """

    def __init__(self, max_events: int) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        self._deque: deque[Event] = deque(maxlen=max_events)
        self._lock = threading.Lock()

    def append(self, event: Event) -> None:
        with self._lock:
            self._deque.append(event)

    def snapshot(self) -> list[Event]:
        """Return a list copy of current events (snapshot at call time)."""
        with self._lock:
            return list(self._deque)

    def clear(self) -> None:
        with self._lock:
            self._deque.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._deque)
