# Developer Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dev-mode capability to the picsure adapter that captures HTTP, function, and connect events for maintainer diagnostics, with redaction of sensitive payloads and zero overhead when off.

**Architecture:** A `DevConfig` object resolved at `connect()` time owns the enabled flag, a capped FIFO `EventBuffer`, and an `emit(event)` entry point. The transport client and session share the same `DevConfig`. HTTP events come from `PicSureClient._request()`; function events come from a `@timed` decorator applied to public `Session` methods. Output goes to the `picsure` stdlib logger (default stderr handler installed only if dev mode is on and the logger has no existing handlers) and to the in-memory buffer surfaced via `session.dev_events()` / `session.dev_stats()`.

**Tech Stack:** Python 3.10+, `httpx`, `pandas`, `respx` (HTTP mocks in tests), `pytest`, stdlib `logging`/`dataclasses`/`threading`.

**Spec:** `docs/superpowers/specs/2026-04-20-developer-mode-design.md`

---

## File Structure

**New files (implementation):**
- `src/picsure/_dev/__init__.py` — re-exports `DevConfig`, `Event`, `install_logger`
- `src/picsure/_dev/events.py` — `Event` dataclass
- `src/picsure/_dev/buffer.py` — thread-safe, capped FIFO
- `src/picsure/_dev/config.py` — `DevConfig` with `emit()` + `from_env(override)`
- `src/picsure/_dev/redaction.py` — `redact_headers()`, `redact_for_log(path, method, body)`
- `src/picsure/_dev/reporting.py` — `events_to_df()`, `stats_to_df()`
- `src/picsure/_dev/timing.py` — `@timed(name)` method decorator

**New files (tests):**
- `tests/unit/dev/__init__.py`
- `tests/unit/dev/test_events.py`
- `tests/unit/dev/test_buffer.py`
- `tests/unit/dev/test_config.py`
- `tests/unit/dev/test_redaction.py`
- `tests/unit/dev/test_reporting.py`
- `tests/unit/dev/test_timing.py`
- `tests/unit/dev/test_client_events.py` — HTTP event emission in `PicSureClient`
- `tests/unit/dev/test_session_dev.py` — Session dev API end-to-end
- `tests/unit/dev/test_connect_dev.py` — `connect()` wires dev mode correctly
- `tests/unit/dev/test_off_path.py` — zero-event / zero-overhead when off

**Modified files:**
- `src/picsure/_transport/client.py` — accept optional `DevConfig`, emit HTTP events in `_request()`
- `src/picsure/_models/session.py` — hold `DevConfig`, wrap public methods with `@timed`, add `dev_mode`, `dev_events()`, `dev_stats()`, `dev_clear()`
- `src/picsure/_services/connect.py` — resolve `DevConfig`, install logger, accept `dev_mode` parameter, record connect event
- `src/picsure/__init__.py` — export `set_dev_mode`

---

## Task 1: `Event` dataclass

**Files:**
- Create: `src/picsure/_dev/__init__.py`
- Create: `src/picsure/_dev/events.py`
- Create: `tests/unit/dev/__init__.py`
- Create: `tests/unit/dev/test_events.py`

- [ ] **Step 1: Create empty package markers**

```python
# src/picsure/_dev/__init__.py
"""Developer-mode internals: config, events, buffer, redaction, reporting, timing."""
```

```python
# tests/unit/dev/__init__.py
```

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/dev/test_events.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'picsure._dev.events'`

- [ ] **Step 4: Implement `Event`**

```python
# src/picsure/_dev/events.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """A single dev-mode event: HTTP call, function call, connect diagnostic, or error."""

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/dev/test_events.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/picsure/_dev/__init__.py src/picsure/_dev/events.py \
        tests/unit/dev/__init__.py tests/unit/dev/test_events.py
git commit -m "feat(dev): add Event dataclass for dev-mode telemetry"
```

---

## Task 2: `EventBuffer` (thread-safe, capped FIFO)

**Files:**
- Create: `src/picsure/_dev/buffer.py`
- Create: `tests/unit/dev/test_buffer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_buffer.py
import threading
from datetime import datetime, timezone

from picsure._dev.buffer import EventBuffer
from picsure._dev.events import Event


def _make_event(name: str = "x") -> Event:
    return Event(
        timestamp=datetime.now(timezone.utc),
        kind="http",
        name=name,
        duration_ms=1.0,
        bytes_in=0,
        bytes_out=0,
        status=200,
        retry=0,
        error=None,
        metadata={},
    )


def test_append_and_list():
    buf = EventBuffer(max_events=10)
    buf.append(_make_event("a"))
    buf.append(_make_event("b"))
    names = [e.name for e in buf.snapshot()]
    assert names == ["a", "b"]


def test_append_over_cap_drops_oldest():
    buf = EventBuffer(max_events=3)
    for n in ["a", "b", "c", "d", "e"]:
        buf.append(_make_event(n))
    names = [e.name for e in buf.snapshot()]
    assert names == ["c", "d", "e"]


def test_clear_empties_buffer():
    buf = EventBuffer(max_events=10)
    buf.append(_make_event("a"))
    buf.clear()
    assert buf.snapshot() == []


def test_concurrent_appends_do_not_lose_or_corrupt():
    buf = EventBuffer(max_events=10000)
    threads = []
    per_thread = 200
    thread_count = 10

    def worker(tag: str) -> None:
        for i in range(per_thread):
            buf.append(_make_event(f"{tag}-{i}"))

    for t in range(thread_count):
        thr = threading.Thread(target=worker, args=(f"t{t}",))
        threads.append(thr)
        thr.start()
    for thr in threads:
        thr.join()

    events = buf.snapshot()
    assert len(events) == per_thread * thread_count
    for e in events:
        assert isinstance(e, Event)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_buffer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `EventBuffer`**

```python
# src/picsure/_dev/buffer.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/dev/test_buffer.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/picsure/_dev/buffer.py tests/unit/dev/test_buffer.py
git commit -m "feat(dev): add thread-safe capped EventBuffer"
```

---

## Task 3: `DevConfig` + `from_env` resolution + `emit`

**Files:**
- Create: `src/picsure/_dev/config.py`
- Create: `tests/unit/dev/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_config.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `DevConfig`**

```python
# src/picsure/_dev/config.py
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
    """Resolved developer-mode configuration shared by transport and session layers."""

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
        """Record an event. No-op when dev mode is disabled. Never raises."""
        if not self.enabled:
            return
        try:
            self.buffer.append(event)
            _logger_for(event.kind).debug(_format_event(event))
        except Exception as exc:  # pragma: no cover — defensive
            _DEV_WARNING_LOGGER.warning("dev-mode emit failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/dev/test_config.py -v`
Expected: PASS (all parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add src/picsure/_dev/config.py tests/unit/dev/test_config.py
git commit -m "feat(dev): add DevConfig with env resolution and emit"
```

---

## Task 4: Redaction

**Files:**
- Create: `src/picsure/_dev/redaction.py`
- Create: `tests/unit/dev/test_redaction.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_redaction.py
from picsure._dev.redaction import redact_for_log, redact_headers


def test_redact_headers_masks_authorization():
    headers = {"Authorization": "Bearer secret-abc123", "Content-Type": "application/json"}
    out = redact_headers(headers)
    assert out["Authorization"] == "Bearer ***"
    assert out["Content-Type"] == "application/json"


def test_redact_headers_case_insensitive():
    headers = {"authorization": "Bearer x"}
    out = redact_headers(headers)
    assert out["authorization"] == "Bearer ***"


def test_redact_headers_preserves_when_no_auth():
    headers = {"Content-Type": "application/json"}
    assert redact_headers(headers) == headers


def test_redact_search_body_is_preserved():
    body = {"query": "blood pressure", "searchQueryType": "ALL"}
    out = redact_for_log("/picsure/search/abc", "POST", body)
    assert out is not None
    assert "blood pressure" in out


def test_redact_psama_body_strips_email():
    body = {"email": "user@example.com", "expirationDate": "2026-06-15"}
    out = redact_for_log("/psama/user/me", "GET", body)
    assert out is not None
    assert "user@example.com" not in out
    assert "***" in out


def test_redact_participant_query_returns_none():
    body = {"query": {"expectedResultType": "DATAFRAME", "fields": []}}
    out = redact_for_log("/picsure/query/sync", "POST", body)
    assert out is None


def test_redact_timestamp_query_returns_none():
    body = {"query": {"expectedResultType": "DATAFRAME_TIMESERIES", "fields": []}}
    out = redact_for_log("/picsure/query/sync", "POST", body)
    assert out is None


def test_redact_count_query_is_preserved():
    body = {"query": {"expectedResultType": "COUNT", "fields": []}}
    out = redact_for_log("/picsure/query/sync", "POST", body)
    assert out is not None
    assert "COUNT" in out


def test_redact_empty_body_returns_empty_string():
    out = redact_for_log("/picsure/search/abc", "POST", None)
    assert out == ""


def test_redact_pfb_export_returns_none():
    body = {"query": {"expectedResultType": "DATAFRAME_PFB"}}
    out = redact_for_log("/picsure/query/sync", "POST", body)
    assert out is None


def test_redact_info_resources_is_preserved():
    body = {"uuid-1": "hpds"}
    out = redact_for_log("/picsure/info/resources", "GET", body)
    assert out is not None
    assert "hpds" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_redaction.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement redaction**

```python
# src/picsure/_dev/redaction.py
from __future__ import annotations

import json
from typing import Any

_SENSITIVE_RESULT_TYPES = {
    "DATAFRAME",
    "DATAFRAME_TIMESERIES",
    "DATAFRAME_PFB",
}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with Authorization masked."""
    out = dict(headers)
    for key in list(out.keys()):
        if key.lower() == "authorization":
            out[key] = "Bearer ***"
    return out


def redact_for_log(
    path: str,
    method: str,
    body: dict[str, Any] | list[Any] | None,
) -> str | None:
    """Return a safe string repr of a request/response body, or None if it must not be logged.

    Returning None signals "body is sensitive — log size only."
    """
    if body is None:
        return ""

    if _is_psama_path(path):
        return json.dumps(_redact_email(body))

    if _is_query_sync_path(path) and _body_is_participant_like(body):
        return None

    # Default: safe to log
    return json.dumps(body, default=str)


def _is_psama_path(path: str) -> bool:
    return path.startswith("/psama/")


def _is_query_sync_path(path: str) -> bool:
    # Matches both /picsure/query/sync and /picsure/v3/query/sync.
    return path.endswith("/query/sync")


def _body_is_participant_like(body: Any) -> bool:
    query = body.get("query") if isinstance(body, dict) else None
    if not isinstance(query, dict):
        return False
    result_type = query.get("expectedResultType")
    return result_type in _SENSITIVE_RESULT_TYPES


def _redact_email(body: Any) -> Any:
    if isinstance(body, dict):
        return {
            k: ("***" if k == "email" and isinstance(v, str) else _redact_email(v))
            for k, v in body.items()
        }
    if isinstance(body, list):
        return [_redact_email(item) for item in body]
    return body
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/dev/test_redaction.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/picsure/_dev/redaction.py tests/unit/dev/test_redaction.py
git commit -m "feat(dev): add redaction helpers for headers and bodies"
```

---

## Task 5: Reporting DataFrame builders

**Files:**
- Create: `src/picsure/_dev/reporting.py`
- Create: `tests/unit/dev/test_reporting.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_reporting.py
from datetime import datetime, timezone

import pandas as pd

from picsure._dev.events import Event
from picsure._dev.reporting import events_to_df, stats_to_df

_EVENT_COLS = [
    "timestamp",
    "kind",
    "name",
    "duration_ms",
    "bytes_in",
    "bytes_out",
    "status",
    "retry",
    "error",
    "metadata",
]

_STATS_COLS = [
    "kind",
    "name",
    "calls",
    "total_ms",
    "avg_ms",
    "min_ms",
    "max_ms",
    "bytes_in_total",
    "bytes_out_total",
    "retries",
    "errors",
]


def _event(kind="http", name="/a", duration=10.0, retry=0, error=None,
           bytes_in=100, bytes_out=200, status=200):
    return Event(
        timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        kind=kind,
        name=name,
        duration_ms=duration,
        bytes_in=bytes_in,
        bytes_out=bytes_out,
        status=status,
        retry=retry,
        error=error,
        metadata={},
    )


def test_events_to_df_empty_has_columns():
    df = events_to_df([])
    assert list(df.columns) == _EVENT_COLS
    assert len(df) == 0


def test_events_to_df_one_row_per_event():
    df = events_to_df([_event(name="/a"), _event(name="/b")])
    assert len(df) == 2
    assert list(df["name"]) == ["/a", "/b"]


def test_stats_to_df_empty_has_columns():
    df = stats_to_df([])
    assert list(df.columns) == _STATS_COLS
    assert len(df) == 0


def test_stats_to_df_aggregates_by_kind_and_name():
    events = [
        _event(kind="http", name="/a", duration=10.0, bytes_in=100, bytes_out=200),
        _event(kind="http", name="/a", duration=20.0, bytes_in=50,  bytes_out=400),
        _event(kind="http", name="/b", duration=5.0,  bytes_in=10,  bytes_out=20),
    ]
    df = stats_to_df(events)
    a = df[df["name"] == "/a"].iloc[0]
    assert a["calls"] == 2
    assert a["total_ms"] == 30.0
    assert a["avg_ms"] == 15.0
    assert a["min_ms"] == 10.0
    assert a["max_ms"] == 20.0
    assert a["bytes_in_total"] == 150
    assert a["bytes_out_total"] == 600


def test_stats_counts_retries_and_errors():
    events = [
        _event(kind="http", name="/a", retry=0, error=None),
        _event(kind="http", name="/a", retry=1, error=None),
        _event(kind="http", name="/a", retry=0, error="TransportServerError"),
    ]
    df = stats_to_df(events)
    row = df[df["name"] == "/a"].iloc[0]
    assert row["retries"] == 1
    assert row["errors"] == 1


def test_stats_handles_none_bytes():
    events = [
        _event(kind="function", name="session.search", bytes_in=None, bytes_out=None),
    ]
    df = stats_to_df(events)
    assert df.iloc[0]["bytes_in_total"] == 0
    assert df.iloc[0]["bytes_out_total"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_reporting.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement reporting**

```python
# src/picsure/_dev/reporting.py
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from picsure._dev.events import Event

_EVENT_COLS = [
    "timestamp",
    "kind",
    "name",
    "duration_ms",
    "bytes_in",
    "bytes_out",
    "status",
    "retry",
    "error",
    "metadata",
]

_STATS_COLS = [
    "kind",
    "name",
    "calls",
    "total_ms",
    "avg_ms",
    "min_ms",
    "max_ms",
    "bytes_in_total",
    "bytes_out_total",
    "retries",
    "errors",
]


def events_to_df(events: list[Event]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=_EVENT_COLS)
    return pd.DataFrame([asdict(e) for e in events], columns=_EVENT_COLS)


def stats_to_df(events: list[Event]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=_STATS_COLS)

    groups: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in events:
        groups[(event.kind, event.name)].append(event)

    rows = []
    for (kind, name), batch in groups.items():
        durations = [e.duration_ms for e in batch]
        rows.append(
            {
                "kind": kind,
                "name": name,
                "calls": len(batch),
                "total_ms": sum(durations),
                "avg_ms": sum(durations) / len(batch),
                "min_ms": min(durations),
                "max_ms": max(durations),
                "bytes_in_total": sum((e.bytes_in or 0) for e in batch),
                "bytes_out_total": sum((e.bytes_out or 0) for e in batch),
                "retries": sum(1 for e in batch if e.retry > 0),
                "errors": sum(1 for e in batch if e.error is not None),
            }
        )
    return pd.DataFrame(rows, columns=_STATS_COLS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/dev/test_reporting.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/picsure/_dev/reporting.py tests/unit/dev/test_reporting.py
git commit -m "feat(dev): add DataFrame builders for events and stats"
```

---

## Task 6: `@timed` method decorator

**Files:**
- Create: `src/picsure/_dev/timing.py`
- Create: `tests/unit/dev/test_timing.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_timing.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_timing.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `@timed`**

```python
# src/picsure/_dev/timing.py
from __future__ import annotations

import functools
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from picsure._dev.events import Event

if TYPE_CHECKING:
    from picsure._dev.config import DevConfig

F = TypeVar("F", bound=Callable[..., Any])


def timed(name: str) -> Callable[[F], F]:
    """Method decorator that emits a 'function' event on success or an 'error' event on exception.

    The wrapped object must expose `self._dev_config: DevConfig | None`.
    When the attribute is missing or the config is disabled, the decorator is a no-op.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            cfg: DevConfig | None = getattr(self, "_dev_config", None)
            if cfg is None or not cfg.enabled:
                return func(self, *args, **kwargs)

            start = time.monotonic()
            try:
                result = func(self, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                cfg.emit(
                    Event(
                        timestamp=datetime.now(timezone.utc),
                        kind="error",
                        name=name,
                        duration_ms=duration_ms,
                        bytes_in=None,
                        bytes_out=None,
                        status=None,
                        retry=0,
                        error=type(exc).__name__,
                        metadata={},
                    )
                )
                raise

            duration_ms = (time.monotonic() - start) * 1000.0
            cfg.emit(
                Event(
                    timestamp=datetime.now(timezone.utc),
                    kind="function",
                    name=name,
                    duration_ms=duration_ms,
                    bytes_in=None,
                    bytes_out=_bytes_out_for(result),
                    status=None,
                    retry=0,
                    error=None,
                    metadata=_metadata_for(result),
                )
            )
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def _bytes_out_for(result: Any) -> int | None:
    # Best-effort: DataFrames don't expose a byte count cheaply, and we do not
    # want to serialize large payloads just to measure them. Leave None.
    return None


def _metadata_for(result: Any) -> dict[str, Any]:
    try:
        import pandas as pd
    except Exception:  # pragma: no cover — pandas is a hard dep
        return {}
    if isinstance(result, pd.DataFrame):
        return {"df_rows": int(result.shape[0]), "df_cols": int(result.shape[1])}
    if isinstance(result, int):
        return {"result_type": "int"}
    return {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/dev/test_timing.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/picsure/_dev/timing.py tests/unit/dev/test_timing.py
git commit -m "feat(dev): add @timed method decorator"
```

---

## Task 7: Wire `DevConfig` into `PicSureClient`

**Files:**
- Modify: `src/picsure/_transport/client.py`
- Create: `tests/unit/dev/test_client_events.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_client_events.py
import httpx
import pytest
import respx

from picsure._dev.config import DevConfig
from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportConnectionError,
    TransportServerError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token-abc"


@respx.mock
def test_get_json_emits_http_event_when_enabled():
    respx.get(f"{BASE_URL}/picsure/info/resources").mock(
        return_value=httpx.Response(200, json={"uuid-1": "hpds"})
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.get_json("/picsure/info/resources")

    events = cfg.buffer.snapshot()
    assert len(events) == 1
    e = events[0]
    assert e.kind == "http"
    assert e.name == "/picsure/info/resources"
    assert e.status == 200
    assert e.retry == 0
    assert e.error is None
    assert e.bytes_out is not None and e.bytes_out > 0


@respx.mock
def test_post_json_emits_http_event_with_bytes_in():
    respx.post(f"{BASE_URL}/picsure/search/abc").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.post_json("/picsure/search/abc", body={"query": "x"})

    events = cfg.buffer.snapshot()
    assert len(events) == 1
    assert events[0].bytes_in is not None and events[0].bytes_in > 0


@respx.mock
def test_retry_emits_two_events():
    respx.get(f"{BASE_URL}/flaky").mock(
        side_effect=[
            httpx.Response(500, text="err"),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.get_json("/flaky")

    events = cfg.buffer.snapshot()
    assert [e.retry for e in events] == [0, 1]
    assert [e.status for e in events] == [500, 200]


@respx.mock
def test_connection_error_emits_error_event_then_raises():
    respx.get(f"{BASE_URL}/down").mock(
        side_effect=httpx.ConnectError("refused")
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    with pytest.raises(TransportConnectionError):
        client.get_json("/down")

    events = cfg.buffer.snapshot()
    assert any(e.kind == "error" and e.error == "ConnectError" for e in events)


@respx.mock
def test_server_error_after_retries_emits_events_for_each_attempt():
    respx.get(f"{BASE_URL}/bad").mock(
        return_value=httpx.Response(500, text="boom")
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    with pytest.raises(TransportServerError):
        client.get_json("/bad")

    events = cfg.buffer.snapshot()
    # Two HTTP events (attempt 0 and 1), both 500.
    http_events = [e for e in events if e.kind == "http"]
    assert [e.retry for e in http_events] == [0, 1]
    assert all(e.status == 500 for e in http_events)


@respx.mock
def test_no_events_when_disabled():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))
    cfg = DevConfig(enabled=False, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.get_json("/x")
    assert cfg.buffer.snapshot() == []


@respx.mock
def test_no_events_when_dev_config_is_none():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))
    client = PicSureClient(base_url=BASE_URL, token=TOKEN)  # default: no dev_config
    client.get_json("/x")  # Must not raise.


@respx.mock
def test_participant_query_body_not_logged():
    # We're testing that the in-buffer event has metadata indicating redaction,
    # even though the raw bytes are still counted.
    respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
        return_value=httpx.Response(
            200, content=b"patient_id,sex\nP1,M\n"
        )
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.post_raw(
        "/picsure/v3/query/sync",
        body={"query": {"expectedResultType": "DATAFRAME", "fields": []}},
    )

    events = cfg.buffer.snapshot()
    http_events = [e for e in events if e.kind == "http"]
    assert http_events[-1].metadata.get("redacted") == "participant"
    assert http_events[-1].bytes_out is not None and http_events[-1].bytes_out > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_client_events.py -v`
Expected: FAIL (most with `TypeError: got an unexpected keyword argument 'dev_config'` or assertion failures)

- [ ] **Step 3: Modify `PicSureClient` to accept `DevConfig` and emit events**

Replace the contents of `src/picsure/_transport/client.py` with:

```python
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from picsure._dev.events import Event
from picsure._dev.redaction import redact_for_log
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportServerError,
)

if TYPE_CHECKING:
    from picsure._dev.config import DevConfig

_MAX_RETRIES = 1
_TIMEOUT_SECONDS = 30.0


class PicSureClient:
    """HTTP client for PIC-SURE API calls.

    Wraps httpx.Client with Bearer token auth, retries on 5xx and
    connection errors, and translation to internal transport exceptions.
    """

    def __init__(
        self,
        base_url: str,
        token: str = "",
        dev_config: DevConfig | None = None,
    ) -> None:
        headers = {
            "Content-Type": "application/json",
            "request-source": "Authorized" if token else "Open",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
        self._dev_config = dev_config

    def get_json(self, path: str) -> dict:  # type: ignore[type-arg]
        response = self._request("GET", path, body=None)
        return response.json()  # type: ignore[no-any-return]

    def post_json(self, path: str, body: dict | None = None) -> dict:  # type: ignore[type-arg]
        response = self._request("POST", path, body=body)
        return response.json()  # type: ignore[no-any-return]

    def post_raw(self, path: str, body: dict | None = None) -> bytes:  # type: ignore[type-arg]
        response = self._request("POST", path, body=body)
        return response.content

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None,  # type: ignore[type-arg]
    ) -> httpx.Response:
        last_exc: Exception | None = None
        kwargs: dict[str, object] = {}
        if body is not None:
            kwargs["json"] = body

        for attempt in range(_MAX_RETRIES + 1):
            start = time.monotonic()
            try:
                response = self._http.request(method, path, **kwargs)  # type: ignore[arg-type]
            except httpx.ConnectError as exc:
                last_exc = exc
                self._emit_error(method, path, attempt, start, type(exc).__name__)
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                last_exc = exc
                self._emit_error(method, path, attempt, start, type(exc).__name__)
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(f"Request timed out: {exc}") from exc

            self._emit_http(method, path, body, response, attempt, start)

            if response.status_code in (401, 403):
                raise TransportAuthenticationError(response.status_code, response.text)

            if response.status_code >= 500:
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportServerError(response.status_code, response.text)

            return response

        raise TransportConnectionError("Request failed after retries") from last_exc

    def close(self) -> None:
        self._http.close()

    # --- dev-mode helpers -------------------------------------------------

    def _emit_http(
        self,
        method: str,
        path: str,
        body: dict | None,  # type: ignore[type-arg]
        response: httpx.Response,
        attempt: int,
        start: float,
    ) -> None:
        cfg = self._dev_config
        if cfg is None or not cfg.enabled:
            return

        duration_ms = (time.monotonic() - start) * 1000.0
        bytes_in = len(response.request.content or b"") if response.request else _estimate_bytes(body)
        bytes_out = len(response.content or b"")
        metadata: dict[str, object] = {}

        if redact_for_log(path, method, body) is None:
            metadata["redacted"] = "participant"

        cfg.emit(
            Event(
                timestamp=datetime.now(timezone.utc),
                kind="http",
                name=path,
                duration_ms=duration_ms,
                bytes_in=bytes_in,
                bytes_out=bytes_out,
                status=response.status_code,
                retry=attempt,
                error=None,
                metadata=metadata,
            )
        )

    def _emit_error(
        self,
        method: str,
        path: str,
        attempt: int,
        start: float,
        error_name: str,
    ) -> None:
        cfg = self._dev_config
        if cfg is None or not cfg.enabled:
            return

        duration_ms = (time.monotonic() - start) * 1000.0
        cfg.emit(
            Event(
                timestamp=datetime.now(timezone.utc),
                kind="error",
                name=path,
                duration_ms=duration_ms,
                bytes_in=None,
                bytes_out=None,
                status=None,
                retry=attempt,
                error=error_name,
                metadata={"method": method},
            )
        )


def _estimate_bytes(body: dict | None) -> int | None:  # type: ignore[type-arg]
    if body is None:
        return 0
    import json as _json

    try:
        return len(_json.dumps(body).encode("utf-8"))
    except Exception:  # pragma: no cover — extremely defensive
        return None
```

- [ ] **Step 4: Run the new tests and the pre-existing client tests**

Run: `uv run pytest tests/unit/dev/test_client_events.py tests/unit/test_client.py -v`
Expected: PASS for all client tests plus the new dev-mode tests. The pre-existing tests should still pass since `dev_config` defaults to `None`.

- [ ] **Step 5: Commit**

```bash
git add src/picsure/_transport/client.py tests/unit/dev/test_client_events.py
git commit -m "feat(dev): emit HTTP events from PicSureClient"
```

---

## Task 8: Wire `DevConfig` into `Session` (+ dev API)

**Files:**
- Modify: `src/picsure/_models/session.py`
- Create: `tests/unit/dev/test_session_dev.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_session_dev.py
from __future__ import annotations

import httpx
import pandas as pd
import respx

from picsure._dev.config import DevConfig
from picsure._models.resource import Resource
from picsure._models.session import Session
from picsure._transport.client import PicSureClient

BASE_URL = "https://test.example.com"
RESOURCE_UUID = "uuid-1"


def _make_session(dev_enabled: bool) -> Session:
    cfg = DevConfig(enabled=dev_enabled, max_events=100)
    client = PicSureClient(base_url=BASE_URL, token="t", dev_config=cfg)
    return Session(
        client=client,
        user_email="u@e",
        token_expiration="N/A",
        resources=[Resource(uuid=RESOURCE_UUID, name="hpds", description="")],
        resource_uuid=RESOURCE_UUID,
        consents=[],
        total_concepts=100,
        dev_config=cfg,
    )


def test_dev_mode_property_reflects_config():
    on = _make_session(dev_enabled=True)
    off = _make_session(dev_enabled=False)
    assert on.dev_mode is True
    assert off.dev_mode is False


def test_dev_events_empty_when_off_has_columns():
    off = _make_session(dev_enabled=False)
    df = off.dev_events()
    assert len(df) == 0
    assert "timestamp" in df.columns and "kind" in df.columns


def test_dev_stats_empty_when_off_has_columns():
    off = _make_session(dev_enabled=False)
    df = off.dev_stats()
    assert len(df) == 0
    assert "calls" in df.columns


def test_dev_clear_is_noop_when_off():
    off = _make_session(dev_enabled=False)
    off.dev_clear()  # Must not raise.


@respx.mock
def test_runquery_count_emits_http_and_function_events():
    respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
        return_value=httpx.Response(200, content=b"42")
    )
    session = _make_session(dev_enabled=True)

    from picsure._models.clause import Clause, ClauseType

    clause = Clause(r"\phs1\sex\", type=ClauseType.FILTER, categories=["Male"])
    session.runQuery(clause, type="count")

    events = session.dev_events()
    kinds = list(events["kind"])
    assert "http" in kinds and "function" in kinds
    fn_rows = events[events["kind"] == "function"]
    assert any(fn_rows["name"] == "session.runQuery")


@respx.mock
def test_dev_stats_aggregates_from_live_calls():
    respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
        return_value=httpx.Response(200, content=b"42")
    )
    session = _make_session(dev_enabled=True)

    from picsure._models.clause import Clause, ClauseType

    clause = Clause(r"\phs1\sex\", type=ClauseType.FILTER, categories=["Male"])
    session.runQuery(clause, type="count")
    session.runQuery(clause, type="count")

    stats = session.dev_stats()
    fn = stats[(stats["kind"] == "function") & (stats["name"] == "session.runQuery")]
    assert len(fn) == 1
    assert fn.iloc[0]["calls"] == 2


@respx.mock
def test_dev_clear_empties_buffer():
    respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
        return_value=httpx.Response(200, content=b"1")
    )
    session = _make_session(dev_enabled=True)

    from picsure._models.clause import Clause, ClauseType

    clause = Clause(r"\phs1\sex\", type=ClauseType.FILTER, categories=["Male"])
    session.runQuery(clause, type="count")
    assert len(session.dev_events()) > 0

    session.dev_clear()
    assert len(session.dev_events()) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_session_dev.py -v`
Expected: FAIL — `Session.__init__() got an unexpected keyword argument 'dev_config'`, plus missing dev methods.

- [ ] **Step 3: Modify `Session` — add `dev_config` param, dev properties/methods, wrap public methods with `@timed`**

Edit `src/picsure/_models/session.py` to:

1. Add to imports (top of file, alongside existing imports):

```python
from picsure._dev.config import DevConfig
from picsure._dev.reporting import events_to_df, stats_to_df
from picsure._dev.timing import timed
```

2. Change `__init__` to accept `dev_config: DevConfig | None = None`, store it, and default to a disabled config when `None`:

```python
def __init__(
    self,
    client: PicSureClient,
    user_email: str,
    token_expiration: str,
    resources: list[Resource],
    resource_uuid: str | None = None,
    consents: list[str] | None = None,
    total_concepts: int = 0,
    dev_config: DevConfig | None = None,
) -> None:
    self._client = client
    self._user_email = user_email
    self._token_expiration = token_expiration
    self._resources = resources
    self._resource_uuid = resource_uuid
    self._consents: list[str] = list(consents) if consents else []
    self._total_concepts = total_concepts
    self._dev_config = dev_config if dev_config is not None else DevConfig(
        enabled=False, max_events=1
    )
```

3. Add `@timed(...)` above each public data-fetching method. Specifically, decorate these existing methods (do NOT change their bodies):

- `search` → `@timed("session.search")`
- `facets` → `@timed("session.facets")`
- `showAllFacets` → `@timed("session.showAllFacets")`
- `runQuery` → `@timed("session.runQuery")`
- `exportPFB` → `@timed("session.exportPFB")`
- `exportCSV` → `@timed("session.exportCSV")`
- `exportTSV` → `@timed("session.exportTSV")`

4. Append the new dev-mode surface at the end of the class:

```python
# --- dev-mode surface ---------------------------------------------------

@property
def dev_mode(self) -> bool:
    """True if developer mode is enabled for this session."""
    return self._dev_config.enabled

def dev_events(self) -> pd.DataFrame:
    """Return the raw event log as a DataFrame (one row per event)."""
    return events_to_df(self._dev_config.buffer.snapshot())

def dev_stats(self) -> pd.DataFrame:
    """Return aggregated per-(kind, name) stats as a DataFrame."""
    return stats_to_df(self._dev_config.buffer.snapshot())

def dev_clear(self) -> None:
    """Empty the event buffer. No-op when dev mode is disabled."""
    self._dev_config.buffer.clear()
```

- [ ] **Step 4: Run the new tests plus the pre-existing session tests**

Run: `uv run pytest tests/unit/dev/test_session_dev.py tests/unit/test_session.py -v`
Expected: PASS for all. Pre-existing session tests still pass because `dev_config` defaults to `None` (→ disabled config).

- [ ] **Step 5: Commit**

```bash
git add src/picsure/_models/session.py tests/unit/dev/test_session_dev.py
git commit -m "feat(dev): wire DevConfig into Session and expose dev API"
```

---

## Task 9: Wire `connect()` — dev_mode parameter + logger install + connect event

**Files:**
- Modify: `src/picsure/_services/connect.py`
- Create: `tests/unit/dev/test_connect_dev.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_connect_dev.py
import logging

import httpx
import pytest
import respx

from picsure import connect
from picsure._transport.platforms import Platform

CUSTOM_URL = "https://test.example.com"


def _mock_platform_endpoints():
    # Mocks the three endpoints `connect()` hits for a custom URL
    # with include_consents=False (the default for custom URLs).
    respx.get(f"{CUSTOM_URL}/psama/user/me").mock(
        return_value=httpx.Response(
            200, json={"email": "u@e", "expirationDate": "2026-06-15"}
        )
    )
    respx.get(f"{CUSTOM_URL}/picsure/info/resources").mock(
        return_value=httpx.Response(200, json={"uuid-1": "hpds"})
    )
    respx.post(
        f"{CUSTOM_URL}/picsure/proxy/dictionary-api/concepts"
        "?page_number=0&page_size=1"
    ).mock(
        return_value=httpx.Response(
            200, json={"content": [], "totalElements": 57}
        )
    )


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PICSURE_DEV_MODE", raising=False)
    monkeypatch.delenv("PICSURE_DEV_MAX_EVENTS", raising=False)


@pytest.fixture(autouse=True)
def _reset_picsure_logger():
    logger = logging.getLogger("picsure")
    saved = list(logger.handlers)
    logger.handlers.clear()
    yield
    logger.handlers.clear()
    logger.handlers.extend(saved)


@respx.mock
def test_dev_mode_none_respects_env_true(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "1")
    _mock_platform_endpoints()
    session = connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1")
    assert session.dev_mode is True


@respx.mock
def test_dev_mode_none_respects_env_unset():
    _mock_platform_endpoints()
    session = connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1")
    assert session.dev_mode is False


@respx.mock
def test_dev_mode_true_overrides_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "0")
    _mock_platform_endpoints()
    session = connect(
        platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=True
    )
    assert session.dev_mode is True


@respx.mock
def test_dev_mode_false_overrides_env(monkeypatch):
    monkeypatch.setenv("PICSURE_DEV_MODE", "1")
    _mock_platform_endpoints()
    session = connect(
        platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=False
    )
    assert session.dev_mode is False


@respx.mock
def test_dev_mode_records_connect_event():
    _mock_platform_endpoints()
    session = connect(
        platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=True
    )
    events = session.dev_events()
    connect_rows = events[events["kind"] == "connect"]
    assert len(connect_rows) == 1
    assert connect_rows.iloc[0]["name"] == "connect"
    md = connect_rows.iloc[0]["metadata"]
    assert md["resources"] == 1
    assert md["requires_auth"] is True


@respx.mock
def test_dev_mode_installs_default_handler_when_none():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    assert logger.handlers == []
    connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=True)
    assert len(logger.handlers) >= 1


@respx.mock
def test_dev_mode_skips_default_handler_when_user_configured():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    user_handler = logging.StreamHandler()
    logger.addHandler(user_handler)
    try:
        connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=True)
        assert logger.handlers == [user_handler]
    finally:
        logger.removeHandler(user_handler)


@respx.mock
def test_dev_mode_off_does_not_install_handler():
    _mock_platform_endpoints()
    logger = logging.getLogger("picsure")
    connect(platform=CUSTOM_URL, token="t", resource_uuid="uuid-1", dev_mode=False)
    assert logger.handlers == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_connect_dev.py -v`
Expected: FAIL — `connect()` has no `dev_mode` parameter and `session.dev_mode` will assert incorrectly, etc.

- [ ] **Step 3: Modify `connect()` — resolve config, install logger, record event, pass to Session**

Replace the contents of `src/picsure/_services/connect.py` with:

```python
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from picsure._dev.config import DevConfig
from picsure._dev.events import Event
from picsure._models.resource import Resource
from picsure._models.session import Session
from picsure._services.consents import fetch_consents
from picsure._services.search import fetch_total_concepts
from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportError,
    TransportServerError,
)
from picsure._transport.platforms import Platform, resolve_platform
from picsure.errors import PicSureAuthError, PicSureConnectionError

_PSAMA_PROFILE_PATH = "/psama/user/me"
_PICSURE_RESOURCES_PATH = "/picsure/info/resources"

_ANONYMOUS_EMAIL = "anonymous"
_ANONYMOUS_EXPIRATION = "N/A"

_LOGGER_NAME = "picsure"


def connect(
    platform: Platform | str,
    token: str = "",
    resource_uuid: str | None = None,
    *,
    include_consents: bool | None = None,
    requires_auth: bool | None = None,
    dev_mode: bool | None = None,
) -> Session:
    """Connect to a PIC-SURE instance and return a Session.

    See module docstring for full parameter docs. `dev_mode`:

    - ``None`` (default): defer to ``PICSURE_DEV_MODE`` env var.
    - ``True`` / ``False``: explicit override.

    When dev mode is on, events for every HTTP call and public Session
    method are captured in an in-memory buffer, and a default stderr
    handler is attached to the ``picsure`` logger (unless one already
    exists).
    """
    info = resolve_platform(
        platform,
        include_consents=include_consents,
        requires_auth=requires_auth,
    )
    display_name = platform.label if isinstance(platform, Platform) else platform

    dev_config = DevConfig.from_env(override=dev_mode)
    if dev_config.enabled:
        _install_default_handler()

    client = PicSureClient(base_url=info.url, token=token, dev_config=dev_config)

    if info.requires_auth:
        profile = _fetch_profile(client, display_name, info.url)
        email = str(profile.get("email", "unknown"))
        expiration = str(profile.get("expirationDate", "unknown"))
    else:
        email = _ANONYMOUS_EMAIL
        expiration = _ANONYMOUS_EXPIRATION

    resources = _fetch_resources(client, display_name, info.requires_auth)
    consents = fetch_consents(client) if info.include_consents else []
    total_concepts = fetch_total_concepts(client, consents=consents)

    effective_uuid = resource_uuid if resource_uuid is not None else info.resource_uuid

    if info.requires_auth:
        print(f"You're successfully connected to {display_name} as user {email}!")
        print(f"Your token expires on {expiration}.")
    else:
        print(f"You're successfully connected to {display_name} (open access).")

    if effective_uuid is None and resources:
        print("\nAvailable resources:")
        for r in resources:
            print(f"  {r.uuid}  {r.name}")
        print(
            "\nNo resource selected. Use session.setResourceID(uuid) "
            "to choose a resource before searching or querying."
        )

    if dev_config.enabled:
        dev_config.emit(
            Event(
                timestamp=datetime.now(timezone.utc),
                kind="connect",
                name="connect",
                duration_ms=0.0,
                bytes_in=None,
                bytes_out=None,
                status=None,
                retry=0,
                error=None,
                metadata={
                    "resources": len(resources),
                    "consents": len(consents),
                    "total_concepts": total_concepts,
                    "requires_auth": info.requires_auth,
                },
            )
        )

    return Session(
        client=client,
        user_email=email,
        token_expiration=expiration,
        resources=resources,
        resource_uuid=effective_uuid,
        consents=consents,
        total_concepts=total_concepts,
        dev_config=dev_config,
    )


def _install_default_handler() -> None:
    """Attach a stderr handler to the picsure logger if no handlers exist.

    Idempotent: repeat calls do nothing once a handler is present.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


def _fetch_profile(
    client: PicSureClient, display_name: str, base_url: str
) -> dict[str, object]:
    try:
        return client.get_json(_PSAMA_PROFILE_PATH)
    except TransportAuthenticationError as exc:
        raise PicSureAuthError(
            "Your token is invalid or expired. Generate a new one at "
            f"{base_url} and pass it to picsure.connect()."
        ) from exc
    except (TransportConnectionError, TransportServerError) as exc:
        raise PicSureConnectionError(
            f"Could not reach {display_name} ({base_url}). Check your internet "
            "connection, or try a different platform."
        ) from exc


def _fetch_resources(
    client: PicSureClient, display_name: str, requires_auth: bool
) -> list[Resource]:
    try:
        data = client.get_json(_PICSURE_RESOURCES_PATH)
    except TransportAuthenticationError:
        if not requires_auth:
            return []
        raise
    except TransportError as exc:
        raise PicSureConnectionError(
            f"Connected to {display_name} but could not fetch resources. "
            "The server may be temporarily unavailable."
        ) from exc

    if isinstance(data, dict):
        return [
            Resource(uuid=uuid, name=str(name), description="")
            for uuid, name in data.items()
        ]

    return [Resource.from_dict(r) for r in data]
```

- [ ] **Step 4: Run the new tests and the pre-existing connect tests**

Run: `uv run pytest tests/unit/dev/test_connect_dev.py tests/unit/test_connect.py -v`
Expected: PASS for all.

- [ ] **Step 5: Commit**

```bash
git add src/picsure/_services/connect.py tests/unit/dev/test_connect_dev.py
git commit -m "feat(dev): wire dev_mode into connect() with logger and connect event"
```

---

## Task 10: Top-level `set_dev_mode` + export

**Files:**
- Modify: `src/picsure/__init__.py`
- Create: `tests/unit/dev/test_set_dev_mode.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_set_dev_mode.py
import os

import pytest

import picsure


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PICSURE_DEV_MODE", raising=False)


def test_set_dev_mode_true_sets_env():
    picsure.set_dev_mode(True)
    assert os.environ["PICSURE_DEV_MODE"] == "1"


def test_set_dev_mode_false_unsets_env():
    os.environ["PICSURE_DEV_MODE"] = "1"
    picsure.set_dev_mode(False)
    assert "PICSURE_DEV_MODE" not in os.environ


def test_set_dev_mode_false_when_already_unset_is_noop():
    picsure.set_dev_mode(False)
    assert "PICSURE_DEV_MODE" not in os.environ


def test_set_dev_mode_is_exported_from_package():
    assert "set_dev_mode" in picsure.__all__
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/dev/test_set_dev_mode.py -v`
Expected: FAIL — `AttributeError: module 'picsure' has no attribute 'set_dev_mode'`.

- [ ] **Step 3: Add `set_dev_mode` and export**

Replace the contents of `src/picsure/__init__.py` with:

```python
"""PIC-SURE Python API adapter."""

import os

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.facet import FacetSet
from picsure._models.query import Query
from picsure._models.session import Session
from picsure._services.connect import connect
from picsure._services.query_build import buildClauseGroup, createClause
from picsure._transport.platforms import Platform
from picsure.errors import PicSureError


def set_dev_mode(enabled: bool) -> None:
    """Set the ``PICSURE_DEV_MODE`` environment variable.

    Affects the **next** call to :func:`connect`. Existing ``Session``
    objects are not mutated; reconnect to pick up the change.
    """
    if enabled:
        os.environ["PICSURE_DEV_MODE"] = "1"
    else:
        os.environ.pop("PICSURE_DEV_MODE", None)


__all__ = [
    "buildClauseGroup",
    "connect",
    "createClause",
    "set_dev_mode",
    "Clause",
    "ClauseGroup",
    "ClauseType",
    "FacetSet",
    "GroupOperator",
    "PicSureError",
    "Platform",
    "Query",
    "Session",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/dev/test_set_dev_mode.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/picsure/__init__.py tests/unit/dev/test_set_dev_mode.py
git commit -m "feat(dev): expose set_dev_mode top-level helper"
```

---

## Task 11: Off-path test — no events, no handler, negligible overhead

**Files:**
- Create: `tests/unit/dev/test_off_path.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/dev/test_off_path.py
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
```

- [ ] **Step 2: Run tests (should pass immediately — off path is already implemented)**

Run: `uv run pytest tests/unit/dev/test_off_path.py -v`
Expected: PASS (3 tests).

If any test fails, the problem is a bug in the off-path short-circuit (`DevConfig.emit` early return, or the client / timing decorator's guard). Fix the offending short-circuit; do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/dev/test_off_path.py
git commit -m "test(dev): guard against off-path regressions"
```

---

## Task 12: Full regression sweep

**Files:** none created.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v`
Expected: All unit tests pass, including pre-existing tests (`test_client.py`, `test_session.py`, `test_connect.py`, etc.).

- [ ] **Step 2: Run lint + type check**

Run: `uv run ruff check src/picsure tests && uv run mypy src/picsure`
Expected: Both clean. Fix any reported issues inline, then re-run.

- [ ] **Step 3: Final commit (only if something needed a touch-up)**

If any fix was needed in this task:

```bash
git add -p  # review each hunk
git commit -m "chore(dev): lint and type fixes for developer mode"
```

Otherwise, skip this step — the feature is complete.

---

## Done

After Task 12, the feature meets the spec: env-var / override activation, HTTP + function + connect + error event capture, redaction of Authorization / PSAMA email / participant and PFB bodies, logger and in-memory surfacing, and no-op behavior when off. The cross-adapter contract (env var names, event fields, `dev_events`/`dev_stats` column names) is locked in for the R rewrite to mirror.
