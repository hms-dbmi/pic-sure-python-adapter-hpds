from __future__ import annotations


class TransportError(Exception):
    """Base class for internal transport-layer errors."""


class TransportAuthenticationError(TransportError):
    """HTTP 401 or 403 from the server."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:200]}")


class TransportServerError(TransportError):
    """HTTP 5xx from the server after retries."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:200]}")


class _TransportStructuredError(TransportError):
    """Base class for server responses with a documented error payload."""

    def __init__(
        self,
        status_code: int,
        body: str,
        error_type: str,
        server_message: str,
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.error_type = error_type
        self.server_message = server_message
        super().__init__(f"HTTP {status_code} {error_type}: {server_message}")


class TransportConsentDeniedError(_TransportStructuredError):
    """The request was denied because the caller no longer has consent."""


class TransportConsentLookupError(_TransportStructuredError):
    """The server could not resolve the caller's consent permissions."""


class TransportConnectionError(TransportError):
    """Network-level failure: DNS, timeout, connection refused."""


class TransportValidationError(TransportError):
    """HTTP 400 / 422 / other 4xx from the server.

    The server rejected the request as malformed or otherwise invalid.
    Callers should surface this as a user-facing validation error.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:200]}")


class TransportNotFoundError(TransportError):
    """HTTP 404 from the server.

    The requested path or resource does not exist on the server.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:200]}")


class TransportRateLimitError(TransportError):
    """HTTP 429 from the server.

    The server throttled the request.  ``retry_after`` captures the
    ``Retry-After`` header value when it is an integer number of
    seconds; HTTP-date values and missing headers leave it ``None``.
    """

    def __init__(
        self, status_code: int, body: str, retry_after: int | None = None
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.retry_after = retry_after
        suffix = f" (retry after {retry_after}s)" if retry_after is not None else ""
        super().__init__(f"HTTP {status_code}{suffix}: {body[:200]}")
