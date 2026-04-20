from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from picsure._dev.buffer import EventBuffer
from picsure._dev.events import Event

_ENV_MODE = "PICSURE_DEV_MODE"
_ENV_MAX_EVENTS = "PICSURE_DEV_MAX_EVENTS"
_DEFAULT_MAX_EVENTS = 1000
_TRUTHY = {"1", "true", "yes"}

_HTTP_LOGGER = logging.getLogger("picsure.http")
_FN_LOGGER = logging.getLogger("picsure.fn")
_CONNECT_LOGGER = logging.getLogger("picsure.connect")
_ERROR_LOGGER = logging.getLogger("picsure.error")
_DEV_WARNING_LOGGER = logging.getLogger("picsure.dev")


def _env_truthy(raw: str | None) -> bool:
    return raw is not None and raw.strip().lower() in _TRUTHY


def _env_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _logger_for(kind: str) -> logging.Logger:
    if kind == "http":
        return _HTTP_LOGGER
    if kind == "function":
        return _FN_LOGGER
    if kind == "connect":
        return _CONNECT_LOGGER
    return _ERROR_LOGGER


def _format_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / (1024 * 1024):.1f}MB"


def _format_event(event: Event) -> str:
    parts: list[str] = []
    if event.kind == "http":
        status = event.status if event.status is not None else "-"
        parts.append(f"{event.name} {status} {event.duration_ms:.0f}ms")
        parts.append(f"in={_format_bytes(event.bytes_in)}")
        parts.append(f"out={_format_bytes(event.bytes_out)}")
        parts.append(f"retry={event.retry}")
        if event.metadata.get("redacted"):
            parts.append(f"[body redacted: {event.metadata['redacted']}]")
    else:
        parts.append(f"{event.name} {event.duration_ms:.0f}ms")
        if event.error:
            parts.append(f"error={event.error}")
    return " ".join(parts)


@dataclass
class DevConfig:
    """Resolved developer-mode config shared by transport and session layers."""

    enabled: bool
    max_events: int
    buffer: EventBuffer = field(init=False)

    def __post_init__(self) -> None:
        self.buffer = EventBuffer(self.max_events)

    @classmethod
    def from_env(cls, override: bool | None) -> DevConfig:
        if override is None:
            enabled = _env_truthy(os.environ.get(_ENV_MODE))
        else:
            enabled = override
        max_events = _env_int(os.environ.get(_ENV_MAX_EVENTS), _DEFAULT_MAX_EVENTS)
        return cls(enabled=enabled, max_events=max_events)

    def emit(self, event: Event) -> None:
        """Record an event. No-op when disabled. Never raises."""
        if not self.enabled:
            return
        try:
            self.buffer.append(event)
            _logger_for(event.kind).debug(_format_event(event))
        except Exception as exc:  # pragma: no cover — defensive
            _DEV_WARNING_LOGGER.warning("dev-mode emit failed: %s", exc)
