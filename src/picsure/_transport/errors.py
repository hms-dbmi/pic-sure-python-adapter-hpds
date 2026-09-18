"""Internal transport-layer exception hierarchy.

Every class here that carries a server response body redacts it on the
way in, through :func:`_redact_credentials`. A service re-raises the
public error with ``raise translate_transport_error(...) from exc``, and
Python renders the whole cause chain, so an unredacted transport message
would print a server-echoed token one frame above the redacted public
one. Redacting at construction keeps both the message and the stored
``body`` clean wherever the exception is rendered.
"""

from __future__ import annotations

import re

_CREDENTIAL_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}"),
)
_REDACTED = "<redacted token>"


def _redact_credentials(text: str) -> str:
    """Replace anything shaped like a credential in server-supplied text.

    A PIC-SURE response can echo the request's bearer token back in an
    error body. Keeping that body on an exception, or quoting it into a
    message, would put the token into every traceback and log line that
    renders the exception. Two shapes are replaced: a ``Bearer <value>``
    header fragment and a JWT (three base64url segments).

    The header fragment is replaced first, so ``"Bearer <jwt>"`` leaves
    one placeholder rather than the two a leading JWT pass produces: the
    header pattern would otherwise swallow the leading half of the
    placeholder the JWT pass had just written. The placeholder it leaves
    behind carries no dot, so the JWT pattern cannot match it in turn.

    What the header pattern matches is bounded to base64url and JWT
    characters, at least eight of them, rather than a run of non-space.
    A run of non-space reaches the end of a compact JSON error body,
    whose commas carry no space, and erases the status and the path along
    with the credential; it also matches the ordinary English word
    "bearer" followed by any word.

    Args:
        text: Server-supplied text, typically a response body.

    Returns:
        The same text with every credential-shaped run replaced by
        ``<redacted token>``.
    """
    for pattern in _CREDENTIAL_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


class TransportError(Exception):
    """Base class for internal transport-layer errors."""


class TransportAuthenticationError(TransportError):
    """HTTP 401 or 403 from the server.

    The stored ``body`` is redacted, because a refusal is the response
    most likely to echo the credential that was refused.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = _redact_credentials(body)
        super().__init__(f"HTTP {status_code}: {self.body[:200]}")


class TransportServerError(TransportError):
    """HTTP 5xx from the server after retries.

    The stored ``body`` is redacted.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = _redact_credentials(body)
        super().__init__(f"HTTP {status_code}: {self.body[:200]}")


class _TransportStructuredError(TransportError):
    """Base class for server responses with a documented error payload.

    The stored ``body`` and ``server_message`` are both redacted.
    """

    def __init__(
        self,
        status_code: int,
        body: str,
        error_type: str,
        server_message: str,
    ) -> None:
        self.status_code = status_code
        self.body = _redact_credentials(body)
        self.error_type = error_type
        self.server_message = _redact_credentials(server_message)
        super().__init__(f"HTTP {status_code} {error_type}: {self.server_message}")


class TransportConsentDeniedError(_TransportStructuredError):
    """The request was denied because the caller no longer has consent."""


class TransportConsentLookupError(_TransportStructuredError):
    """The server could not resolve the caller's consent permissions."""


class TransportConnectionError(TransportError):
    """Network-level failure: DNS, timeout, connection refused."""


class TransportTLSError(TransportConnectionError):
    """TLS certificate verification failed before the request was sent.

    Carries the fully-rendered, user-facing explanation: the host, the
    reason OpenSSL gave, and how to trust the certificate.  Retrying is
    pointless, so the client never re-sends after one of these.
    """


class TransportValidationError(TransportError):
    """HTTP 400 / 422 / other 4xx from the server.

    The server rejected the request as malformed or otherwise invalid.
    Callers should surface this as a user-facing validation error. The
    stored ``body`` is redacted.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = _redact_credentials(body)
        super().__init__(f"HTTP {status_code}: {self.body[:200]}")


class TransportNotFoundError(TransportError):
    """HTTP 404 from the server.

    The requested path or resource does not exist on the server. The
    stored ``body`` is redacted.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = _redact_credentials(body)
        super().__init__(f"HTTP {status_code}: {self.body[:200]}")


class TransportRateLimitError(TransportError):
    """HTTP 429 from the server.

    The server throttled the request.  ``retry_after`` captures the
    ``Retry-After`` header value when it is an integer number of
    seconds; HTTP-date values and missing headers leave it ``None``.
    The stored ``body`` is redacted.
    """

    def __init__(
        self, status_code: int, body: str, retry_after: int | None = None
    ) -> None:
        self.status_code = status_code
        self.body = _redact_credentials(body)
        self.retry_after = retry_after
        suffix = f" (retry after {retry_after}s)" if retry_after is not None else ""
        super().__init__(f"HTTP {status_code}{suffix}: {self.body[:200]}")
