from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from picsure._dev.events import Event
from picsure._dev.redaction import body_is_sensitive
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

# Env var controlling TLS certificate verification, used only when the caller
# does not pass an explicit ``verify`` to connect()/PicSureClient. Accepts a
# CA-bundle path, or a boolean-ish string ("false"/"0"/"no" disables checking).
# Disabling verification is for local/self-signed deployments only.
_SSL_VERIFY_ENV = "PICSURE_SSL_VERIFY"


def _resolve_verify(verify: bool | str | None) -> bool | str:
    """Resolve the httpx ``verify`` argument.

    Precedence: an explicit ``verify`` wins; otherwise fall back to the
    ``PICSURE_SSL_VERIFY`` env var; otherwise verify (the secure default).
    A string that is not a boolean keyword is treated as a CA-bundle path.
    """
    if verify is not None:
        return verify
    raw = os.environ.get(_SSL_VERIFY_ENV)
    if raw is None or raw == "":
        return True
    lowered = raw.strip().lower()
    if lowered in ("false", "0", "no", "off"):
        return False
    if lowered in ("true", "1", "yes", "on"):
        return True
    return raw  # a CA-bundle path

# Transport failures where the request provably never reached the server --
# or never finished being sent -- so re-sending cannot double-execute even a
# non-idempotent POST:
#   - ConnectError / ConnectTimeout: no connection was ever established.
#   - PoolTimeout: the request never left the local connection pool.
#   - WriteError: sending the request failed part-way (e.g. EPIPE on a stale
#     pooled connection the server killed with RST); the server cannot
#     process a request it never fully received.
_PRE_SEND_FAILURES = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.WriteError,
)

# Deterministic configuration or client-side errors where a retry cannot
# change the outcome: a proxy refusing the connection, a base URL whose
# scheme httpx does not support, a request httpx itself considers malformed.
_NO_RETRY_FAILURES = (
    httpx.ProxyError,
    httpx.UnsupportedProtocol,
    httpx.LocalProtocolError,
)


def _server_disconnected_before_response(exc: httpx.RemoteProtocolError) -> bool:
    """True for the stale pooled keep-alive symptom.

    httpcore uses this exact wording only when the server closed the
    connection before sending any part of a response -- meaning the request
    was never processed.  Every other ``RemoteProtocolError`` (truncated
    body, malformed response) arrives *after* the server received -- and may
    have executed -- the request, so it must not be blindly re-sent for
    non-GETs.  If a future httpcore rewords the message this degrades
    safely: non-GETs simply stop retrying this case.
    """
    return str(exc).startswith("Server disconnected")


def _should_retry(method: str, exc: httpx.TransportError) -> bool:
    """Whether a failed request is safe to send again.

    Safe for every method when the request provably never reached the
    server; otherwise only for idempotent GETs (the server may already
    have processed the request).
    """
    if isinstance(exc, _NO_RETRY_FAILURES):
        return False
    if isinstance(exc, _PRE_SEND_FAILURES):
        return True
    if isinstance(
        exc, httpx.RemoteProtocolError
    ) and _server_disconnected_before_response(exc):
        return True
    # ReadError, ReadTimeout, WriteTimeout, CloseError, truncated-body
    # RemoteProtocolError, ...: the request was fully sent and the failure
    # happened while receiving the response.
    return method == "GET"


def _connection_failure_message(exc: httpx.TransportError) -> str:
    """Build the ``TransportConnectionError`` message for a failure."""
    if isinstance(
        exc, httpx.RemoteProtocolError
    ) and _server_disconnected_before_response(exc):
        return (
            "Server closed the connection before responding "
            f"(stale pooled connection): {exc}"
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"Request timed out: {exc}"
    if isinstance(exc, (httpx.ReadError, httpx.WriteError, httpx.CloseError)):
        return (
            "Network error on an established connection (possibly a stale "
            f"pooled connection closed by the server): {exc}"
        )
    return str(exc) or type(exc).__name__


def _package_version() -> str:
    """Return the installed ``picsure`` version, or ``"unknown"``."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("picsure")
    except PackageNotFoundError:  # pragma: no cover - only when not installed
        return "unknown"


def _user_agent(client_type: str) -> str:
    """Build a User-Agent identifying the calling adapter and its version.

    ``"PYTHON_ADAPTER"`` -> ``"picsure-python-adapter/<version>"``;
    ``"R_ADAPTER"`` -> ``"picsure-r-adapter/<version>"``.
    """
    product = client_type.lower().replace("_", "-")
    return f"picsure-{product}/{_package_version()}"


def _mark_emitted(exc: BaseException) -> BaseException:
    # Tag exceptions whose failure has already been recorded as a dev-mode
    # error event so @timed wrappers higher up the stack don't double-emit.
    exc._picsure_dev_emitted = True  # type: ignore[attr-defined]
    return exc


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
        session_id: str = "",
        client_type: str = "PYTHON_ADAPTER",
        verify: bool | str | None = None,
    ) -> None:
        # BDC's API gateway routes auth based on a "request-source" header:
        # "Authorized" when a bearer token is present, "Open" otherwise.
        # Without it, authorized endpoints (e.g. /hpds/auth/v3/query/sync) can
        # reject tokens that are otherwise valid on PSAMA or the data-dictionary.
        token = token.strip()
        headers = {
            "Content-Type": "application/json",
            "request-source": "Authorized" if token else "Open",
            # Correlation headers consumed by the backend's AuditLoggingFilter:
            # X-Client-Type identifies the calling adapter; User-Agent carries
            # the same information in the standard slot. X-Session-Id ties every
            # request in this session together (the server otherwise falls back
            # to a hash of IP + User-Agent, which is not per-user).
            "X-Client-Type": client_type,
            "User-Agent": _user_agent(client_type),
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if session_id:
            headers["X-Session-Id"] = session_id
        self._http = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
            verify=_resolve_verify(verify),
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

    def put_json(self, path: str, body: dict | None = None) -> dict:  # type: ignore[type-arg]
        """Send PUT request with JSON body and return parsed JSON."""
        response = self._request("PUT", path, json=body)
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
        success-path body is left as a live stream.  A transport failure
        while the caller drains the stream is translated to
        :class:`TransportConnectionError` as well, so no raw httpx
        exception escapes this context manager.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            stream_cm = self._http.stream("POST", path, json=body)
            try:
                response = stream_cm.__enter__()
            except httpx.TransportError as exc:
                last_exc = exc
                # This stream is always a POST, so retry only the failures
                # where the request provably never reached the server (see
                # _should_retry).
                if _should_retry("POST", exc) and attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(
                    _connection_failure_message(exc)
                ) from exc

            status = response.status_code

            if status >= 400:
                # Read the (presumably small) error body so the mapper
                # below can include a preview, then close the stream.  The
                # status alone drives the mapping, so degrade to a
                # placeholder if the connection drops mid-read.
                try:
                    response.read()
                    body_text = response.text
                except httpx.TransportError as exc:
                    body_text = f"<error body unavailable: {exc}>"
                finally:
                    stream_cm.__exit__(None, None, None)
                if 400 <= status < 500:
                    _raise_for_status(status, body_text, response)
                # POST /stream is non-idempotent; do not retry on 5xx.
                raise TransportServerError(status, body_text)

            # Happy path: hand the live response to the caller.  A transport
            # failure while the caller drains the stream is thrown back into
            # this generator at the yield; translate it so callers see the
            # Transport* contract, never a raw httpx error.  No retry is
            # possible here -- part of the body has already been consumed.
            try:
                yield response
            except httpx.TransportError as exc:
                raise TransportConnectionError(
                    f"Connection failed while streaming the response: {exc}"
                ) from exc
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
            except httpx.TransportError as exc:
                last_exc = exc
                self._emit_error(method, path, attempt, start, type(exc).__name__)
                # Retry only when re-sending cannot double-execute: failures
                # where the request never reached the server retry for every
                # method; failures after the request was fully sent (the
                # server may have processed it) retry for GETs only.  See
                # _should_retry for the per-exception classification.
                if _should_retry(method, exc) and attempt < _MAX_RETRIES:
                    continue
                raise _mark_emitted(
                    TransportConnectionError(_connection_failure_message(exc))
                ) from exc

            self._emit_http(method, path, body, response, attempt, start)

            status = response.status_code

            if 400 <= status < 500:
                try:
                    _raise_for_status(status, response.text, response)
                except TransportError as exc:
                    self._emit_error(method, path, attempt, start, type(exc).__name__)
                    _mark_emitted(exc)
                    raise

            if status >= 500:
                # POST is non-idempotent: a 5xx after the request reached
                # the server may have partially executed.  Only retry GETs.
                if method == "GET" and attempt < _MAX_RETRIES:
                    continue
                self._emit_error(method, path, attempt, start, "TransportServerError")
                raise _mark_emitted(TransportServerError(status, response.text))

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

        if body_is_sensitive(path, method, body):
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
    except (TypeError, ValueError):
        return None
