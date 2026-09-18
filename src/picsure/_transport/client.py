"""HTTP transport for the PIC-SURE adapter.

``RequestBody`` is a JSON request body. It is always an object, because
no PIC-SURE route takes a bare array or scalar. ``JsonBody`` is a decoded
response body, an object or an array. Most routes answer with an object,
but ``/picsure/dictionary/facets`` and
``/picsure/operations/dataset/named`` answer with a top-level array, so a
general accessor cannot promise a ``dict``.

Two request deadlines are kept separate. ``DATA_TIMEOUT_SECONDS`` is the
per-request deadline for real work such as a count, a participant
download, or an export poll. Thirty seconds was too tight, since a large
dataset legitimately takes minutes to assemble server-side, so the default
is ten minutes; the ``timeout`` argument of :class:`PicSureClient`
overrides it. ``VALIDATION_TIMEOUT_SECONDS`` is the deadline for a single
connect-time request that proves the deployment is reachable and the
token is good. It stays short so a mistyped hostname that accepts TCP but
never answers fails in seconds rather than waiting out the data deadline.
"""

from __future__ import annotations

import contextlib
import json
import os
import ssl
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypeAlias

import httpx

from picsure._dev.events import Event
from picsure._dev.redaction import body_is_sensitive
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportConsentDeniedError,
    TransportConsentLookupError,
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportServerError,
    TransportTLSError,
    TransportValidationError,
)
from picsure._transport.secret import SecretToken, as_secret_token
from picsure.errors import (
    EmptyBodyError,
    PicSureQueryError,
    PicSureTLSError,
    PicSureValidationError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from picsure._dev.config import DevConfig

RequestBody: TypeAlias = dict[str, Any]

JsonObject: TypeAlias = dict[str, Any]
JsonArray: TypeAlias = list[Any]
JsonBody: TypeAlias = JsonObject | JsonArray

_MAX_RETRIES = 1

DATA_TIMEOUT_SECONDS = 600.0
VALIDATION_TIMEOUT_SECONDS = 15.0

_CHUNK_BYTES = 64 * 1024

# Env var controlling TLS certificate verification, used only when the caller
# does not pass an explicit ``verify`` to connect()/PicSureClient. Accepts a
# CA-bundle path, or a boolean-ish string ("false"/"0"/"no" disables checking).
# Disabling verification is for local/self-signed deployments only.
_SSL_VERIFY_ENV = "PICSURE_SSL_VERIFY"


def _resolve_verify(verify: bool | str | None) -> bool | ssl.SSLContext:
    """Resolve the httpx ``verify`` argument.

    Precedence: an explicit ``verify`` wins; otherwise fall back to the
    ``PICSURE_SSL_VERIFY`` env var; otherwise verify (the secure default).
    A string that is not a boolean keyword is treated as a CA-bundle path
    and must exist, so a typo fails naming the path instead of surfacing
    httpx's bare ``FileNotFoundError``.

    A path is turned into an :class:`ssl.SSLContext` here rather than
    passed through, because httpx 0.28 deprecates ``verify=<str>``.  What
    the caller may pass is unchanged.

    Raises:
        PicSureValidationError: If a CA-bundle path does not exist.
        PicSureTLSError: If it exists but cannot be loaded as a CA bundle.
    """
    if isinstance(verify, str):
        return _ca_bundle_context(verify, source=f"verify={verify!r}")
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
    return _ca_bundle_context(raw, source=f"{_SSL_VERIFY_ENV}={raw!r}")


def _ca_bundle_context(path: str, *, source: str) -> ssl.SSLContext:
    """Build an SSL context trusting the CA bundle at ``path``.

    ``source`` names where the value came from, the ``verify`` argument
    or the env var, so the reader knows which one to fix.  A directory
    is accepted: OpenSSL takes a hashed CA directory as well as a file.

    Raises:
        PicSureValidationError: If the path does not exist.
        PicSureTLSError: If the path exists but OpenSSL cannot load a
            certificate from it, because it is not PEM, is empty, or
            cannot be read.
    """
    if not os.path.exists(path):
        raise PicSureValidationError(
            f"The CA bundle {path!r} does not exist, so TLS verification "
            f"cannot be configured (from {source}). Point it at a PEM file "
            f"(or an OpenSSL CA directory) that this machine can read, pass "
            f"verify=True to use the system trust store, or verify=False to "
            f"skip verification on a self-signed deployment."
        )
    try:
        if os.path.isdir(path):
            return ssl.create_default_context(capath=path)
        return ssl.create_default_context(cafile=path)
    except (ssl.SSLError, OSError) as exc:
        raise PicSureTLSError(
            f"The CA bundle {path!r} could not be loaded, so TLS verification "
            f"cannot be configured (from {source}): {exc}. Point it at a PEM "
            f"file (or an OpenSSL CA directory) that this machine can read, "
            f"pass verify=True to use the system trust store, or verify=False "
            f"to skip verification on a self-signed deployment."
        ) from exc


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


def _certificate_verification_failure(
    exc: BaseException,
) -> ssl.SSLCertVerificationError | None:
    """Return the certificate-verification error underlying ``exc``, if any.

    httpx does not expose TLS failures as a distinct exception type: an
    untrusted certificate arrives as an ``httpx.ConnectError`` wrapping an
    ``ssl.SSLCertVerificationError``.  Walk the ``__cause__`` /
    ``__context__`` chain to find it, guarding against a cycle.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _tls_failure_message(host: str, reason: ssl.SSLCertVerificationError) -> str:
    """Explain a certificate rejection and how to get past it."""
    return (
        f"TLS certificate verification failed for {host}: {reason}. The server's "
        "certificate is not trusted by this machine, so no request was sent. If "
        "this is a local or self-signed deployment, pass verify=False to "
        "picsure.connect() (or set PICSURE_SSL_VERIFY=false). To trust a private "
        'CA, pass verify="/path/to/ca-bundle.pem" (or set PICSURE_SSL_VERIFY to '
        "that path)."
    )


def _should_retry(method: str, exc: httpx.TransportError) -> bool:
    """Whether a failed request is safe to send again.

    Safe for every method when the request provably never reached the
    server; otherwise only for idempotent GETs (the server may already
    have processed the request).  A rejected certificate is deterministic
    and never retried.
    """
    if _certificate_verification_failure(exc) is not None:
        return False
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


def _connection_error(exc: httpx.TransportError, host: str) -> TransportConnectionError:
    """Build the transport error for a request that got no response."""
    certificate_failure = _certificate_verification_failure(exc)
    if certificate_failure is not None:
        return TransportTLSError(_tls_failure_message(host, certificate_failure))
    return TransportConnectionError(_connection_failure_message(exc))


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


def _decode_json(response: httpx.Response, path: str) -> JsonBody:
    """Decode a response body as a JSON object or array.

    ``httpx.Response.json`` is typed ``Any``, so a ``dict`` return
    annotation on the accessors above was unenforced, and wrong, since
    two PIC-SURE routes answer with a top-level array.  Narrowing here
    makes the union the accessors advertise a checked fact rather than a
    claim, and turns a scalar or ``null`` top level into a stated failure
    instead of an ``AttributeError`` in whichever service indexed it.

    Raises:
        EmptyBodyError: If the body is empty or whitespace only.
        PicSureQueryError: If the body is not JSON, or decodes to
            something other than an object or an array.  The decoder's
            own ``ValueError`` is kept as the cause, so the failure stays
            inside the public hierarchy and a caller wrapping the call in
            ``except PicSureError`` still catches it.
    """
    if not response.content.strip():
        raise EmptyBodyError(
            response.status_code,
            f"{path} returned an empty body; expected a JSON object or an array.",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise PicSureQueryError(
            f"{path} returned a body that is not JSON: {exc}"
        ) from exc
    if isinstance(payload, (dict, list)):
        return payload
    raise PicSureQueryError(
        f"{path} returned a JSON {type(payload).__name__} at the top level; "
        f"expected an object or an array."
    )


def json_object(payload: JsonBody, *, path: str) -> JsonObject:
    """Narrow a decoded JSON body to an object, or say what arrived instead.

    For the routes whose contract is a single object.  Raising
    :class:`~picsure.errors.PicSureQueryError` keeps an unexpected array
    inside the public hierarchy, so a caller wrapping the call in
    ``except PicSureError`` still catches it.
    """
    if isinstance(payload, dict):
        return payload
    raise PicSureQueryError(
        f"{path} returned a JSON array at the top level; expected an object."
    )


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
        token: str | SecretToken = "",
        dev_config: DevConfig | None = None,
        session_id: str = "",
        client_type: str = "PYTHON_ADAPTER",
        verify: bool | str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Build the client and its one long-lived httpx.Client.

        ``token`` is wrapped in a :class:`SecretToken`, which renders as
        a placeholder, and the original binding is then deleted so the
        parameter drops out of any rendered frame.  This matters here
        because ``_resolve_verify`` below raises on a CA-bundle path
        that does not exist, putting this frame on a traceback the user
        sees.  For the same reason the ``Authorization`` header is built
        into the mapping handed to httpx rather than added to the
        ``headers`` local first: that local would be rendered by any
        traceback showing this frame, whereas ``httpx.Headers`` redacts
        ``authorization`` in its own repr, so the value is safe once it
        is inside the client.

        Args:
            base_url: Deployment root the paths are resolved against.
            token: PIC-SURE API token, as a ``str`` or an already-wrapped
                :class:`SecretToken`.  Empty for open-access use.
            dev_config: Developer-mode event sink, or ``None``.
            session_id: Correlation id sent as ``X-Session-Id``.
            client_type: Calling adapter, sent as ``X-Client-Type``.
            verify: TLS verification, resolved by :func:`_resolve_verify`.
            timeout: Per-request deadline for data operations.
        """
        secret = as_secret_token(token)
        del token

        # BDC's API gateway routes auth based on a "request-source" header:
        # "Authorized" when a bearer token is present, "Open" otherwise.
        # Without it, authorized endpoints (e.g. /hpds/auth/v3/query/sync) can
        # reject tokens that are otherwise valid on PSAMA or the data-dictionary.
        headers = {
            "Content-Type": "application/json",
            "request-source": "Authorized" if secret else "Open",
            # Correlation headers consumed by the backend's AuditLoggingFilter:
            # X-Client-Type identifies the calling adapter; User-Agent carries
            # the same information in the standard slot. X-Session-Id ties every
            # request in this session together (the server otherwise falls back
            # to a hash of IP + User-Agent, which is not per-user).
            "X-Client-Type": client_type,
            "User-Agent": _user_agent(client_type),
        }
        if session_id:
            headers["X-Session-Id"] = session_id
        self._timeout = DATA_TIMEOUT_SECONDS if timeout is None else timeout
        self._http = httpx.Client(
            base_url=base_url,
            headers=(
                {**headers, "Authorization": f"Bearer {secret.reveal()}"}
                if secret
                else headers
            ),
            timeout=self._timeout,
            verify=_resolve_verify(verify),
        )
        self._host = self._http.base_url.host
        self._dev_config = dev_config

    def get_json(
        self,
        path: str,
        *,
        timeout: float | None = None,
        retry: bool = True,
    ) -> JsonBody:
        """Send GET request and return the parsed JSON object or array.

        Args:
            path: Request path, relative to the client's base URL.
            timeout: Per-request deadline in seconds, overriding the
                session-wide one.  Used by the connect-time validation
                call, which must fail fast on an unreachable host rather
                than wait out the long data deadline.
            retry: Whether a transport failure or 5xx may be sent once
                more.  ``False`` caps the call at a single attempt, so a
                caller's deadline is the whole cost of the call.

        Returns:
            The decoded body.  Callers that require an object should pass
            it through :func:`json_object` rather than assume the shape.

        Raises:
            PicSureQueryError: If the body is not JSON, or decodes to
                something other than an object or an array.
        """
        response = self._request("GET", path, retry=retry, **_timeout_kwargs(timeout))
        return _decode_json(response, path)

    def post_json(self, path: str, body: RequestBody | None = None) -> JsonBody:
        """Send POST request with JSON body and return parsed JSON.

        See :meth:`get_json` for the return contract.
        """
        response = self._request("POST", path, json=body)
        return _decode_json(response, path)

    def put_json(self, path: str, body: RequestBody | None = None) -> JsonBody:
        """Send PUT request with JSON body and return parsed JSON.

        See :meth:`get_json` for the return contract.
        """
        response = self._request("PUT", path, json=body)
        return _decode_json(response, path)

    def post_raw(self, path: str, body: RequestBody | None = None) -> bytes:
        """Send POST request with JSON body and return raw response bytes.

        Use this for endpoints that return non-JSON data (CSV, PFB, etc.).
        """
        response = self._request("POST", path, json=body)
        return response.content

    @contextmanager
    def post_raw_stream(
        self,
        path: str,
        body: RequestBody | None = None,
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
        exception escapes this context manager.  Only a failure where the
        request provably never reached the server is retried, because a
        POST may have executed on the server otherwise.

        Developer-mode accounting also matches :meth:`_request`: every
        failed attempt emits an ``error`` event, a 4xx/5xx emits an
        ``http`` event carrying the status before its ``error`` event,
        and every raised exception is marked as already recorded.  The
        attempt that produced the yielded response is stored in
        ``response.extensions["picsure_retry"]`` so the caller can report
        it on the event it emits for the streamed body.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            start = time.monotonic()
            stream_cm = self._http.stream("POST", path, json=body)
            try:
                response = stream_cm.__enter__()
            except httpx.TransportError as exc:
                last_exc = exc
                self._emit_error("POST", path, attempt, start, type(exc).__name__)
                if _should_retry("POST", exc) and attempt < _MAX_RETRIES:
                    continue
                raise _mark_emitted(_connection_error(exc, self._host)) from exc

            status = response.status_code

            if status >= 400:
                try:
                    response.read()
                    body_text = response.text
                except httpx.TransportError as exc:
                    body_text = f"<error body unavailable: {exc}>"
                finally:
                    stream_cm.__exit__(None, None, None)
                self._emit_http("POST", path, body, response, attempt, start)
                error = _status_error(status, body_text, response)
                self._emit_error("POST", path, attempt, start, type(error).__name__)
                raise _mark_emitted(error)

            response.extensions["picsure_retry"] = attempt
            try:
                yield response
            except httpx.TransportError as exc:
                error = TransportConnectionError(
                    f"Connection failed while streaming the response: {exc}"
                )
                self._emit_error("POST", path, attempt, start, type(error).__name__)
                raise _mark_emitted(error) from exc
            finally:
                stream_cm.__exit__(None, None, None)
            return

        raise TransportConnectionError("Request failed after retries") from last_exc

    def post_raw_to_file(
        self,
        path: str,
        target: Path,
        body: RequestBody | None = None,
    ) -> None:
        """POST a JSON body and stream the response to ``target`` on disk.

        The buffered counterpart, :meth:`post_raw`, holds the whole
        response in memory; with a ten-minute deadline a participant
        download can be large enough that buffering it kills the kernel
        with no error at all.  This method never holds more than one
        chunk: bytes go to ``<target>.part`` as they arrive and
        :func:`os.replace` promotes that to ``target`` only once the body
        is complete, so a failed download never leaves a truncated file
        at the real path.

        Args:
            path: Request path, relative to the client's base URL.
            target: Final path to write.  Its parent must exist.
            body: JSON request body.

        Emits the developer-mode ``http`` event for the download only
        once the file sits at ``target``, sized by the byte count written
        rather than ``len(response.content)``, which a streamed response
        does not have.  A failure anywhere, the rename included, emits an
        ``error`` event instead, unless :meth:`post_raw_stream` already
        recorded it as a transport failure.

        Raises:
            TransportError: Same mapping as :meth:`post_raw_stream`.
            OSError: If the staging file cannot be written or promoted.
        """
        part_path = target.with_suffix(target.suffix + ".part")
        start = time.monotonic()
        try:
            with (
                self.post_raw_stream(path, body=body) as response,
                open(part_path, "wb") as out,
            ):
                written = 0
                for chunk in response.iter_bytes(chunk_size=_CHUNK_BYTES):
                    if chunk:
                        written += out.write(chunk)
            os.replace(part_path, target)
        except BaseException as exc:
            if not getattr(exc, "_picsure_dev_emitted", False):
                self._emit_error("POST", path, 0, start, type(exc).__name__)
            _remove_partial(part_path)
            raise
        self._emit_download(
            path,
            body,
            response,
            written,
            start,
            retry=int(response.extensions.get("picsure_retry", 0)),
        )

    def _request(
        self, method: str, path: str, *, retry: bool = True, **kwargs: object
    ) -> httpx.Response:
        """Send one request, retrying once where a resend is safe.

        Args:
            method: HTTP method.
            path: Request path, relative to the client's base URL.
            retry: ``False`` allows a single attempt regardless of method.
            kwargs: Forwarded to ``httpx.Client.request``.

        Raises:
            TransportError: The failure the last attempt ended in.
        """
        last_exc: Exception | None = None
        raw_body = kwargs.get("json")
        body = raw_body if isinstance(raw_body, dict) else None
        max_retries = _MAX_RETRIES if retry else 0

        for attempt in range(max_retries + 1):
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
                if _should_retry(method, exc) and attempt < max_retries:
                    continue
                raise _mark_emitted(_connection_error(exc, self._host)) from exc

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
                structured_error = _structured_transport_error(status, response.text)
                if structured_error is not None:
                    self._emit_error(
                        method, path, attempt, start, type(structured_error).__name__
                    )
                    raise _mark_emitted(structured_error)
                # POST is non-idempotent: a 5xx after the request reached
                # the server may have partially executed.  Only retry GETs.
                if method == "GET" and attempt < max_retries:
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
        body: RequestBody | None,
        response: httpx.Response,
        attempt: int,
        start: float,
    ) -> None:
        cfg = self._dev_config
        if cfg is None or not cfg.enabled:
            return

        duration_ms = (time.monotonic() - start) * 1000.0
        bytes_sent = (
            len(response.request.content or b"")
            if response.request
            else _estimate_bytes(body)
        )
        try:
            bytes_received: int | None = len(response.content or b"")
        except httpx.ResponseNotRead:
            bytes_received = None
        metadata: dict[str, object] = {}

        if body_is_sensitive(path, method, body):
            metadata["redacted"] = "participant"

        cfg.emit(
            Event(
                timestamp=datetime.now(timezone.utc),
                kind="http",
                name=path,
                duration_ms=duration_ms,
                bytes_sent=bytes_sent,
                bytes_received=bytes_received,
                status=response.status_code,
                retry=attempt,
                error=None,
                metadata=metadata,
            )
        )

    def _emit_download(
        self,
        path: str,
        body: RequestBody | None,
        response: httpx.Response,
        bytes_written: int,
        start: float,
        retry: int,
    ) -> None:
        """Record a completed streamed download as an ``http`` event.

        The buffered path uses :meth:`_emit_http`, which sizes the
        response with ``len(response.content)``.  A streamed response has
        no ``content`` to read, and reading it would defeat the point, so
        the size comes from what was written to disk.  ``retry`` is the
        attempt that produced the response, as :meth:`post_raw_stream`
        recorded it.
        """
        cfg = self._dev_config
        if cfg is None or not cfg.enabled:
            return

        metadata: dict[str, object] = {}
        if body_is_sensitive(path, "POST", body):
            metadata["redacted"] = "participant"

        cfg.emit(
            Event(
                timestamp=datetime.now(timezone.utc),
                kind="http",
                name=path,
                duration_ms=(time.monotonic() - start) * 1000.0,
                bytes_sent=(
                    len(response.request.content or b"")
                    if response.request
                    else _estimate_bytes(body)
                ),
                bytes_received=bytes_written,
                status=response.status_code,
                retry=retry,
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
                bytes_sent=None,
                bytes_received=None,
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

    401 and 403 are decided by status before the response body is
    consulted, so every refusal lands in the authentication /
    authorization family whether or not the server sent a structured
    payload.
    """
    if status in (401, 403):
        raise _refusal_transport_error(status, body)
    structured_error = _structured_transport_error(status, body)
    if structured_error is not None:
        raise structured_error
    if status == 404:
        raise TransportNotFoundError(status, body)
    if status == 429:
        raise TransportRateLimitError(
            status, body, retry_after=_parse_retry_after(response)
        )
    if 400 <= status < 500:
        # 400, 422, and any other 4xx fall into the validation bucket.
        raise TransportValidationError(status, body)


def _status_error(status: int, body: str, response: httpx.Response) -> TransportError:
    """Build the transport exception for a 4xx or 5xx without raising it.

    4xx goes through :func:`_raise_for_status`, so the streaming path
    maps refusals exactly as the buffered one does.  5xx prefers the
    structured consent error encoded in the body and falls back to
    :class:`TransportServerError`.  A POST is never retried on 5xx.
    """
    if 400 <= status < 500:
        try:
            _raise_for_status(status, body, response)
        except TransportError as exc:
            return exc
    structured_error = _structured_transport_error(status, body)
    if structured_error is not None:
        return structured_error
    return TransportServerError(status, body)


def _refusal_transport_error(status: int, body: str) -> TransportError:
    """Build the transport error for a 401 or 403.

    A ``consent_denied`` payload refines the refusal into
    :class:`TransportConsentDeniedError`, which keeps the server's own
    ``errorType`` and message.  Every other 401 / 403 becomes a plain
    :class:`TransportAuthenticationError`, including one carrying
    ``consent_lookup_failed``, which the backend only ever emits as a
    502, so callers can rely on the status alone to place it.
    """
    structured_error = _structured_transport_error(status, body)
    if isinstance(structured_error, TransportConsentDeniedError):
        return structured_error
    return TransportAuthenticationError(status, body)


def _structured_transport_error(
    status: int, body: str
) -> TransportConsentDeniedError | TransportConsentLookupError | None:
    """Return the typed consent error encoded in an HTTP error body, if any."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    error_type = payload.get("errorType")
    server_message = payload.get("message")
    if not isinstance(error_type, str) or not isinstance(server_message, str):
        return None
    if error_type == "consent_denied":
        return TransportConsentDeniedError(status, body, error_type, server_message)
    if error_type == "consent_lookup_failed":
        return TransportConsentLookupError(status, body, error_type, server_message)
    return None


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


def _timeout_kwargs(timeout: float | None) -> dict[str, float]:
    """Render a per-request timeout override as request kwargs.

    Absent an override the key is omitted entirely, so the request keeps
    the client-wide timeout rather than passing ``None``, which httpx
    reads as "no deadline at all".
    """
    return {} if timeout is None else {"timeout": timeout}


def _remove_partial(part_path: Path) -> None:
    """Best-effort removal of a staging file after a failed download.

    If the partial cannot be deleted there is nothing useful to do; the
    original failure is the one worth propagating.
    """
    with contextlib.suppress(OSError):
        part_path.unlink(missing_ok=True)


def _estimate_bytes(body: RequestBody | None) -> int | None:
    if body is None:
        return 0
    import json as _json

    try:
        return len(_json.dumps(body).encode("utf-8"))
    except (TypeError, ValueError):
        return None
