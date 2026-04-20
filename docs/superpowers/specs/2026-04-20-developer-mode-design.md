# Developer Mode Design

**Date:** 2026-04-20
**Status:** Draft
**Scope:** `pic-sure-python-adapter-hpds` (Python), with a cross-adapter contract the R rewrite will mirror.

## Problem

Maintainers of the PIC-SURE adapters currently have no built-in way to observe what the adapter is doing: which requests are sent, how long they take, how payloads are shaped, whether retries fired, or how client-side work (DataFrame construction, export serialization) contributes to latency. Diagnosing a "slow notebook" or a backend regression means sprinkling `print()` calls or attaching a debugger.

Developer mode adds a single, opt-in toggle that captures structured events for HTTP calls, public API functions, and connection diagnostics, exposes them through both logs and an in-memory buffer, and redacts sensitive data by default.

## Audience

Adapter maintainers diagnosing bugs in the adapter itself or in the backend. End users are not the target — the defaults favor detail over polish, and the output is assumed to be read by someone who knows the codebase.

## Non-Goals

- Client-side profiling down to function-call granularity (use `cProfile` or `py-spy` for that).
- Persistent telemetry or log shipping.
- Runtime toggling mid-session — dev mode is locked at `connect()` time. Reconnect to change it.
- Surfacing dev-mode output in a pretty UI. Output is a stderr log and pandas DataFrames.

## Activation & Configuration

Dev mode is controlled by two inputs, resolved once at `connect()`:

- **Environment variable:** `PICSURE_DEV_MODE`. Truthy values (`1`, `true`, `yes`, case-insensitive) enable it. Empty, unset, or any other value disables it.
- **Connect override:** `picsure.connect(..., dev_mode=None)`. `None` (default) defers to the env var. `True` / `False` overrides it explicitly.

Additional env var:

- **`PICSURE_DEV_MAX_EVENTS`** — buffer cap. Default `1000`. Rolling FIFO: when full, the oldest event is dropped.

The resolved `DevConfig` and its `EventBuffer` live on the `Session`. They do not leak across sessions. The `PicSureClient` receives a reference to the same `DevConfig` so it can emit HTTP events.

A top-level helper is exposed for discoverability in a notebook:

```python
picsure.set_dev_mode(enabled: bool) -> None
```

This sets `PICSURE_DEV_MODE` in `os.environ`. It affects the **next** `connect()` call; existing `Session` objects are not mutated. Documented accordingly.

## Architecture

All new internal code lives under `src/picsure/_dev/`:

```
src/picsure/_dev/
  __init__.py          # public surface: DevConfig, Event, install()
  config.py            # DevConfig.from_env(override)
  events.py            # Event dataclass
  buffer.py            # EventBuffer — thread-safe, FIFO-capped
  redaction.py         # redact_headers(), redact_for_log(path, method, body)
  reporting.py         # dev_stats() and dev_events() DataFrame builders
  timing.py            # @timed decorator and timed_block() context manager
```

Integration points in existing code:

- **`_transport/client.py`** — `PicSureClient.__init__` takes an optional `DevConfig`. `_request()` times each attempt, records an HTTP event on both success and error, applies redaction, and preserves existing retry bookkeeping.
- **`_models/session.py`** — holds the `DevConfig` and `EventBuffer`; public methods (`search`, `runQuery`, `facets`, `showAllFacets`, `exportPFB`, `exportCSV`, `exportTSV`) are wrapped with `@timed` so their end-to-end duration becomes a "function" event. Adds `dev_events()`, `dev_stats()`, `dev_clear()`, and `dev_mode` (read-only).
- **`_services/connect.py`** — resolves the `DevConfig`, installs the default logging handler if dev mode is on and the `picsure` logger has no handlers yet, and records a "connect" event with resource count, consent count, total_concepts, and `requires_auth`.

Logger setup rules:

- Logger name: `picsure`. HTTP events go to `picsure.http`; function events to `picsure.fn`; connect diagnostics to `picsure.connect`; internal dev-mode warnings to `picsure.dev`.
- If dev mode is on and `picsure` has no existing handlers, install a `StreamHandler` on stderr at `DEBUG` with a concise single-line formatter.
- If handlers are already attached (user configured their own), skip the default install to avoid double-logging.
- Setup is idempotent — repeated `connect()` calls do not stack handlers.

## Event Schema

```python
@dataclass(frozen=True, slots=True)
class Event:
    timestamp: datetime          # UTC, event creation time
    kind: str                    # "http" | "function" | "connect" | "error"
    name: str                    # endpoint path or function name
    duration_ms: float           # wall-clock elapsed
    bytes_in: int | None         # request body size (http) or None
    bytes_out: int | None        # response body size (http) / export size (function)
    status: int | None           # HTTP status code (http only)
    retry: int                   # retry attempt number, 0 for first try
    error: str | None            # exception class name if failed, else None
    metadata: dict[str, Any]     # kind-specific extras (e.g. DataFrame shape, consent count)
```

`metadata` conventions:

- `kind="function"` for `runQuery`: `{"query_type": "count" | "participant" | "timestamp", "df_rows": int, "df_cols": int}`.
- `kind="function"` for `search`: `{"term": "<echoed>", "has_facets": bool, "df_rows": int, "df_cols": int}`.
- `kind="function"` for `exportPFB`: `{"output_path": "<path>", "file_bytes": int}`.
- `kind="connect"`: `{"resources": int, "consents": int, "total_concepts": int, "requires_auth": bool}`.
- `kind="http"` for participant queries: `{"redacted": "participant"}` and `bytes_out` set from the raw response.

## Redaction Policy

Applied before any emission (log line or buffer append). Implemented in `_dev/redaction.py` — transport layer never logs raw bodies directly.

| Source | Rule |
|---|---|
| `Authorization` header | Replaced with `"Bearer ***"` |
| Request/response body on `/psama/*` | `email` field replaced with `"***"` |
| Response body on `/picsure/v3/query/sync` with `type=participant` or `type=timestamp` | Body never logged. `bytes_out` + DataFrame shape recorded in metadata. |
| PFB export response | Body never logged. `bytes_out` recorded. |
| All other endpoints (search, facets, info, dictionary, count queries) | Full body logged. |

`redact_for_log(path, method, body) -> str | None` returns a safe string repr, or `None` to signal "size only, body unsafe."

Example log lines:

```
picsure.http POST /picsure/search/<uuid> 200 312ms in=187B out=42.1KB retry=0
picsure.fn   session.runQuery(type=count) 412ms
picsure.http POST /picsure/v3/query/sync 200 4.2s in=291B out=18.3MB retry=0 [body redacted: participant]
```

## Data Flow

Flow for `session.runQuery(q, type="count")` with dev mode on:

1. `@timed("session.runQuery")` starts a monotonic timer and calls through.
2. `run_query` service builds the request and calls `client.post_json()`.
3. `PicSureClient._request()` starts its own timer, makes the HTTP call.
4. On response, the client builds an HTTP `Event` (redacted) and emits it via logger + buffer.
5. If retry triggers, each attempt emits its own event with `retry=N`.
6. On return to `@timed`, the wrapper builds a "function" `Event` and emits it. Function duration includes retries and DataFrame construction.
7. Buffer append is O(1). If over cap, the oldest entry pops.

When dev mode is off, the transport and session code short-circuit: no timing, no event construction, no logger calls. Target overhead < 1 µs per call; a microbenchmark test enforces this.

## Public API

```python
# Session attributes / methods
session.dev_mode: bool                   # read-only

session.dev_events() -> pd.DataFrame
# Raw event log, one row per event. Columns mirror the Event dataclass:
# timestamp, kind, name, duration_ms, bytes_in, bytes_out,
# status, retry, error, metadata (dict column).

session.dev_stats() -> pd.DataFrame
# Aggregated by (kind, name). Columns:
# kind, name, calls, total_ms, avg_ms, min_ms, max_ms,
# bytes_in_total, bytes_out_total, retries, errors.

session.dev_clear() -> None
# Empty the buffer.

# Module-level helper
picsure.set_dev_mode(enabled: bool) -> None
# Sets PICSURE_DEV_MODE in os.environ. Affects the NEXT connect().
```

When `dev_mode` is `False`, `dev_events()` and `dev_stats()` return empty DataFrames with the correct columns rather than raising. `dev_clear()` is a no-op.

## Error Handling

- Dev-mode code paths must never crash a real call. Every emit site is wrapped: if redaction or buffer append raises, log a one-line warning to `picsure.dev` and continue. The primary call path is unaffected.
- Transport exceptions still raise as they do today. Before the exception propagates, an `Event(kind="error", name=<path or function>, error=<ExceptionClass>, ...)` is recorded so `dev_stats()` can show error counts per endpoint.
- Logger setup is idempotent: repeated `connect()` calls do not stack handlers.
- Thread safety: `EventBuffer` uses a `threading.Lock` around append and drop. Users may fire requests from multiple threads (`httpx.Client` is thread-safe); the buffer must not corrupt.

## Testing

All tests use `respx` to mock HTTP, following the existing `tests/unit/` and `tests/integration/` conventions. No changes needed to integration tests — dev mode is transparent to backend behavior.

- `tests/unit/dev/test_config.py` — env var parsing (truthy forms, empty, unset, garbage), override precedence (`None` vs `True`/`False`), max-events cap parsing.
- `tests/unit/dev/test_redaction.py` — Authorization stripped; email stripped on `/psama/*`; participant and timestamp bodies dropped; PFB export body dropped; search / facets / info / dictionary / count bodies preserved.
- `tests/unit/dev/test_buffer.py` — FIFO cap enforced; thread safety under concurrent append.
- `tests/unit/dev/test_events.py` — mocked HTTP calls produce expected events; retries produce one event per attempt; transport errors produce an `error` event before raising.
- `tests/unit/dev/test_reporting.py` — `dev_stats()` aggregates per `(kind, name)` correctly; empty DataFrames with correct columns when off or buffer empty.
- `tests/unit/dev/test_off_path.py` — dev mode off: no events emitted, no logger handler installed, overhead < 1 µs per call (microbenchmark).
- `tests/unit/test_session_dev.py` — `session.dev_events()`, `dev_stats()`, `dev_clear()`, `dev_mode` work end-to-end through mocked calls.

## Cross-Adapter Contract

The R adapter rewrite (`pic-sure-r-adapter-hpds`) will mirror:

- Env var name: `PICSURE_DEV_MODE`.
- Env var name: `PICSURE_DEV_MAX_EVENTS`.
- Event field names: `timestamp`, `kind`, `name`, `duration_ms`, `bytes_in`, `bytes_out`, `status`, `retry`, `error`, `metadata`.
- `kind` values: `"http"`, `"function"`, `"connect"`, `"error"`.
- Redaction rules (Authorization, `/psama/*` email, participant / timestamp / PFB body suppression).
- Public method names: `dev_events()`, `dev_stats()`, `dev_clear()`, `dev_mode`.
- `dev_stats()` column names.

Implementation in R uses the `logger` package equivalent; the contract stays identical so a maintainer who learns one adapter knows the other.

## File Touch List

New:

- `src/picsure/_dev/__init__.py`
- `src/picsure/_dev/config.py`
- `src/picsure/_dev/events.py`
- `src/picsure/_dev/buffer.py`
- `src/picsure/_dev/redaction.py`
- `src/picsure/_dev/reporting.py`
- `src/picsure/_dev/timing.py`
- `tests/unit/dev/__init__.py`
- `tests/unit/dev/test_config.py`
- `tests/unit/dev/test_redaction.py`
- `tests/unit/dev/test_buffer.py`
- `tests/unit/dev/test_events.py`
- `tests/unit/dev/test_reporting.py`
- `tests/unit/dev/test_off_path.py`
- `tests/unit/test_session_dev.py`

Modified:

- `src/picsure/__init__.py` — export `set_dev_mode`.
- `src/picsure/_transport/client.py` — optional `DevConfig` parameter, event emission in `_request()`.
- `src/picsure/_models/session.py` — holds `DevConfig`+`EventBuffer`; wraps public methods with `@timed`; adds dev methods/property.
- `src/picsure/_services/connect.py` — resolves `DevConfig`, installs logger, records connect event, accepts `dev_mode` parameter.
