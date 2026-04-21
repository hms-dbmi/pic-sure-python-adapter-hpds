from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from picsure._dev.events import Event
from picsure._dev.redaction import redact_for_log
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportServerError,
    TransportValidationError,
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
        # BDC's API gateway routes auth based on a "request-source" header:
        # "Authorized" when a bearer token is present, "Open" otherwise.
        # Without it, authorized endpoints (e.g. /picsure/v3/query/sync) can
        # reject tokens that are otherwise valid on PSAMA or the data-dictionary.
        token = token.strip()
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
        """Send GET request and return parsed JSON."""
        response = self._request("GET", path)
        return response.json()  # type: ignore[no-any-return]

    def post_json(self, path: str, body: dict | None = None) -> dict:  # type: ignore[type-arg]
        """Send POST request with JSON body and return parsed JSON."""
        response = self._request("POST", path, json=body)
        return response.json()  # type: ignore[no-any-return]

    def post_raw(self, path: str, body: dict | None = None) -> bytes:  # type: ignore[type-arg]
        """Send POST request with JSON body and return raw response bytes.

        Use this for endpoints that return non-JSON data (CSV, PFB, etc.).
        """
        response = self._request("POST", path, json=body)
        return response.content

    @contextmanager
    def post_raw_stream(
        self,
        path: str,
        body: dict | None = None,  # type: ignore[type-arg]
    ) -> Iterator[httpx.Response]:
        """POST JSON body and stream the response without buffering it.

        Yields an :class:`httpx.Response` with an un-read body.  Callers
        iterate over ``response.iter_bytes()`` inside the ``with`` block;
        the response is closed on exit.

        Error handling matches :meth:`_request`: 4xx/5xx are translated
        to transport exceptions *before* the context manager yields, so
        callers don't need to re-check the status code.  The response
        body for the error mapping is read eagerly (it's small), but the
        success-path body is left as a live stream.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            stream_cm = self._http.stream("POST", path, json=body)
            try:
                response = stream_cm.__enter__()
            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(f"Request timed out: {exc}") from exc

            status = response.status_code

            if status >= 400:
                # Read the (presumably small) error body so the mapper
                # below can include a preview, then close the stream.
                try:
                    response.read()
                    body_text = response.text
                finally:
                    stream_cm.__exit__(None, None, None)
                if 400 <= status < 500:
                    _raise_for_status(status, body_text, response)
                # POST /stream is non-idempotent; do not retry on 5xx.
                raise TransportServerError(status, body_text)

            # Happy path: hand the live response to the caller.
            try:
                yield response
            finally:
                stream_cm.__exit__(None, None, None)
            return

        raise TransportConnectionError("Request failed after retries") from last_exc

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        last_exc: Exception | None = None
        raw_body = kwargs.get("json")
        body = raw_body if isinstance(raw_body, dict) else None

        for attempt in range(_MAX_RETRIES + 1):
            start = time.monotonic()
            try:
                response = self._http.request(method, path, **kwargs)  # type: ignore[arg-type]
            except httpx.ConnectError as exc:
                last_exc = exc
                self._emit_error(method, path, attempt, start, type(exc).__name__)
                # Connection errors are idempotent-safe: the request never
                # reached the server, so retrying can't double-execute.
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                last_exc = exc
                self._emit_error(method, path, attempt, start, type(exc).__name__)
                # Timeouts may or may not have reached the server, but
                # the convention in this client is to retry — see the
                # original TransportConnectionError path.
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(f"Request timed out: {exc}") from exc

            self._emit_http(method, path, body, response, attempt, start)

            status = response.status_code

            if 400 <= status < 500:
                try:
                    _raise_for_status(status, response.text, response)
                except TransportError as exc:
                    self._emit_error(method, path, attempt, start, type(exc).__name__)
                    raise

            if status >= 500:
                # POST is non-idempotent: a 5xx after the request reached
                # the server may have partially executed.  Only retry GETs.
                if method == "GET" and attempt < _MAX_RETRIES:
                    continue
                self._emit_error(method, path, attempt, start, "TransportServerError")
                raise TransportServerError(status, response.text)

            return response

        raise TransportConnectionError("Request failed after retries") from last_exc

    def close(self) -> None:
        """Close the underlying HTTP client.  Safe to call more than once."""
        # httpx.Client.close() is itself idempotent, but be explicit so
        # callers can rely on the Session-level contract.
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
        bytes_in = (
            len(response.request.content or b"")
            if response.request
            else _estimate_bytes(body)
        )
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


def _raise_for_status(status: int, body: str, response: httpx.Response) -> None:
    """Map a 4xx status to the appropriate transport exception.

    Shared between :meth:`PicSureClient._request` and the streaming path
    so the two surfaces translate 4xx identically.  Callers are
    responsible for handling 5xx themselves (the retry policy differs
    between GET and POST).
    """
    if status in (401, 403):
        raise TransportAuthenticationError(status, body)
    if status == 404:
        raise TransportNotFoundError(status, body)
    if status == 429:
        raise TransportRateLimitError(
            status, body, retry_after=_parse_retry_after(response)
        )
    if 400 <= status < 500:
        # 400, 422, and any other 4xx fall into the validation bucket.
        raise TransportValidationError(status, body)


def _parse_retry_after(response: httpx.Response) -> int | None:
    """Parse a ``Retry-After`` header as an integer number of seconds.

    Returns ``None`` for missing headers and for HTTP-date values that
    cannot be parsed as a plain integer.  We intentionally don't try to
    parse HTTP-date here: the value we want to surface is "seconds from
    now," and converting a date to that requires a wall-clock reference
    the caller can compute themselves if needed.
    """
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return None


def _estimate_bytes(body: dict | None) -> int | None:  # type: ignore[type-arg]
    if body is None:
        return 0
    import json as _json

    try:
        return len(_json.dumps(body).encode("utf-8"))
    except Exception:  # pragma: no cover — extremely defensive
        return None
