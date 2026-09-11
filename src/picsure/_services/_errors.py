"""Translation from internal transport errors to the public hierarchy.

Every service routes its transport failures through
:func:`translate_transport_error` so one status maps to one public type
and one message everywhere.  ``operation`` is a noun phrase naming what
the caller was doing, e.g. ``"the dictionary search"``; the templates
below read it as an object, so it must not be a bare verb.
"""

from __future__ import annotations

from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConsentDeniedError,
    TransportConsentLookupError,
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportServerError,
    TransportTLSError,
    TransportValidationError,
)
from picsure.errors import (
    PicSureAuthenticationError,
    PicSureAuthError,
    PicSureAuthorizationError,
    PicSureConnectionError,
    PicSureConsentDeniedError,
    PicSureConsentLookupError,
    PicSureError,
    PicSureQueryError,
    PicSureServerError,
    PicSureTLSError,
    PicSureValidationError,
)

_NEW_TOKEN_ADVICE = (
    "Copy a fresh token from the PIC-SURE user interface and pass it as "
    "picsure.connect(token=...)."
)


def _server_said(body: str) -> str:
    """Quote the server's own explanation, or nothing when it sent none.

    Some PIC-SURE refusals carry an empty body; appending a bare "The
    server said:" to those reads as a truncated message.
    """
    quoted = body.strip()[:200]
    return f" The server said: {quoted}" if quoted else ""


def rate_limit_message(
    exc: TransportRateLimitError,
    *,
    suffix: str = "",
) -> str:
    """Render a consistent rate-limit message across services.

    ``suffix`` is appended after "Rate limited" so callers can add
    operation-specific context (e.g. " on the PFB export download").
    """
    base = f"Rate limited{suffix}"
    if exc.retry_after is not None:
        return f"{base}; server said retry after {exc.retry_after} seconds."
    return f"{base}. Please wait and try again."


def translate_transport_error(
    exc: TransportError,
    *,
    operation: str,
) -> PicSureError:
    """Translate a transport exception to the public hierarchy.

    Args:
        exc: The internal transport exception the client raised.
        operation: Noun phrase naming what was being attempted, read as
            the object of the message templates (e.g. ``"the dictionary
            search"``, ``"the PFB export download"``).

    Returns:
        The public exception to raise.  A 401 becomes
        :class:`PicSureAuthenticationError`, a 403
        :class:`PicSureAuthorizationError` (or
        :class:`PicSureConsentDeniedError`), an unreachable server
        :class:`PicSureConnectionError`, and a 5xx
        :class:`PicSureServerError`.
    """
    if isinstance(exc, TransportConsentDeniedError):
        return PicSureConsentDeniedError(
            exc.status_code,
            exc.body,
            exc.error_type,
            exc.server_message,
            f"Consent denied for {operation} (HTTP {exc.status_code}). This is a "
            f"consent decision, not an outage: your approved consents do not cover "
            f"the data this request touches. The server said: "
            f"{exc.server_message}",
        )
    if isinstance(exc, TransportConsentLookupError):
        return PicSureConsentLookupError(
            exc.status_code,
            exc.body,
            exc.error_type,
            exc.server_message,
            f"The server could not resolve your consent permissions for "
            f"{operation} (HTTP {exc.status_code}). This is a failure inside "
            f"PIC-SURE, not a problem with your token or your approvals; try "
            f"again shortly. The server said: {exc.server_message}",
        )
    if isinstance(exc, TransportAuthenticationError):
        return _refusal_error(exc, operation)
    if isinstance(exc, TransportValidationError):
        return PicSureValidationError(
            f"The server rejected {operation} (HTTP {exc.status_code})."
            f"{_server_said(exc.body)}"
        )
    if isinstance(exc, TransportNotFoundError):
        return PicSureQueryError(
            f"The endpoint for {operation} returned HTTP 404.{_server_said(exc.body)}"
        )
    if isinstance(exc, TransportRateLimitError):
        return PicSureConnectionError(
            rate_limit_message(exc, suffix=f" on {operation}")
        )
    return _unreachable_error(exc, operation=operation)


def _unreachable_error(
    exc: TransportError,
    *,
    operation: str,
) -> PicSureConnectionError:
    """Translate a transport failure that produced no usable response.

    Split out so a service with its own fallback branch still reports a
    rejected certificate and a 5xx as the distinct types callers can
    handle, rather than flattening both into "temporarily unavailable".
    """
    if isinstance(exc, TransportTLSError):
        return PicSureTLSError(str(exc))
    if isinstance(exc, TransportServerError):
        return PicSureServerError(
            f"The server failed to complete {operation} (HTTP {exc.status_code}) "
            f"and may be temporarily unavailable. Try again shortly."
            f"{_server_said(exc.body)}"
        )
    return PicSureConnectionError(
        f"Could not reach the PIC-SURE server for {operation}. The server may be "
        f"temporarily unavailable, or the network path to it is down. Details: "
        f"{exc}"
    )


def _refusal_error(
    exc: TransportAuthenticationError,
    operation: str,
) -> PicSureAuthError:
    """Split a 401/403 refusal into a token problem and a permission problem.

    The 403 wording stops short of asserting the token is good: PSAMA
    answers 403 rather than 401 for a stale token on some routes, so a
    message that promised "your token is valid" would be wrong there.
    """
    if exc.status_code == 401:
        return PicSureAuthenticationError(
            f"Your PIC-SURE token was rejected on {operation} (HTTP 401). The "
            f"token is missing, malformed, or expired — this is not a permissions "
            f"problem and not a server outage. {_NEW_TOKEN_ADVICE}"
            f"{_server_said(exc.body)}"
        )
    return PicSureAuthorizationError(
        f"PIC-SURE refused {operation} (HTTP 403): this account is not authorized "
        f"for it. This is a permissions decision, not a server outage. Check that "
        f"the account holds the privilege or study approval the request needs; if "
        f"it should, the token may be stale or issued for a different environment, "
        f"so try a fresh one.{_server_said(exc.body)}"
    )
