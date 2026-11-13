"""Translation from internal transport errors to the public hierarchy.

Every service routes its transport failures through
:func:`translate_transport_error` so one status maps to one public type
and one message everywhere.  ``operation`` is a noun phrase naming what
the caller was doing, e.g. ``"the dictionary search"``; the templates
below read it as an object, so it must not be a bare verb.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConsentDeniedError,
    TransportConsentLookupError,
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportResultNotReadyError,
    TransportServerError,
    TransportTLSError,
    TransportValidationError,
    redact_credentials,
)
from picsure.errors import (
    EmptyBodyError,
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


_SERVER_MESSAGE_MAX_CHARS = 1000
_ERROR_TYPE_MAX_CHARS = 100
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True)
class _ServerRefusal:
    """What a 4xx response said about itself, in the user's terms.

    Attributes:
        status_label: The status as the message templates name it,
            ``"HTTP 400"``, or ``"HTTP 400, bad_request"`` when the body
            carried an error type.
        said: The trailing sentence quoting the server, with its leading
            space, or the empty string when there is nothing to quote.
    """

    status_label: str
    said: str


def _server_refusal(status_code: int, body: str) -> _ServerRefusal:
    """Read a 4xx body for the message the server meant the user to see.

    PIC-SURE answers a refusal with a JSON object carrying a string
    ``message`` and usually a string ``errorType``. When the body is
    that, the message is quoted as plain text, whole up to
    ``_SERVER_MESSAGE_MAX_CHARS`` characters, and the error type joins
    the status. The body's other members, the request id among them,
    are left out of the sentence.

    Any other body, one that is not JSON, is nested too deeply to
    decode, is not an object, or has no ``message`` that
    :func:`_printable_server_text` leaves text in, is quoted the way
    :func:`_server_said` quotes it, and the status stands alone.

    The message and the error type go through
    :func:`_printable_server_text`, which redacts them a second time
    after the transport constructor that stored the body. The second
    pass is not redundant here: a credential written with JSON
    ``\\uXXXX`` escapes is invisible to the pass over the raw body and
    appears only once the body is decoded.

    Args:
        status_code: The response status.
        body: The response body as text.

    Returns:
        The status label and the quoting sentence for the templates.
    """
    plain = _ServerRefusal(f"HTTP {status_code}", _server_said(body))
    try:
        payload = json.loads(body)
    except (ValueError, RecursionError):
        return plain
    if not isinstance(payload, dict):
        return plain
    quoted = _printable_server_text(
        payload.get("message"), max_chars=_SERVER_MESSAGE_MAX_CHARS
    )
    if not quoted:
        return plain
    named = _printable_server_text(
        payload.get("errorType"), max_chars=_ERROR_TYPE_MAX_CHARS
    )
    status_label = f"HTTP {status_code}, {named}" if named else plain.status_label
    return _ServerRefusal(status_label, f" The server said: {quoted}")


def _printable_server_text(value: object, *, max_chars: int) -> str:
    """Make a decoded JSON string safe to put inside an error message.

    Decoding turns the escapes of a JSON string into the characters they
    stand for, so a newline, an ESC or a BEL the raw body showed as
    ``\\n`` or ``\\u001b`` would reach a terminal or a notebook as
    itself. Every character below U+0020, and U+007F, becomes a space,
    and each run of whitespace collapses to one space.

    Credentials are redacted before the text is cut to ``max_chars``, so
    a token lying across the cut is replaced whole rather than left half
    shown. The cut can therefore land inside the redaction placeholder,
    which gives nothing away.

    Args:
        value: The member read from the error body.
        max_chars: The longest text to return.

    Returns:
        The cleaned text, or the empty string when ``value`` is not a
        string or holds nothing printable.
    """
    if not isinstance(value, str):
        return ""
    spaced = _CONTROL_CHARACTER.sub(" ", value)
    collapsed = _WHITESPACE_RUN.sub(" ", spaced).strip()
    return redact_credentials(collapsed)[:max_chars]


def _server_said(body: str) -> str:
    """Quote the server's own explanation, or nothing when it sent none.

    Some PIC-SURE refusals carry an empty body; appending a bare "The
    server said:" to those reads as a truncated message.

    The quoted text is redacted twice on purpose. Every transport class
    that stores a body already ran
    :func:`picsure._transport.errors.redact_credentials` over it in its
    constructor, and this repeats the pass on the way into a message a
    user will see. The redundancy costs one regex sweep of at most 200
    characters and covers a constructor that is added later without the
    first pass.
    """
    quoted = redact_credentials(body.strip()[:200])
    return f" The server said: {quoted}" if quoted else ""


def bodiless_response_succeeded(exc: EmptyBodyError) -> bool:
    """Whether a bodiless response's status says the request succeeded.

    The transport translates only 4xx and 5xx and does not follow
    redirects, so every status below 400 arrives as an
    :class:`~picsure.errors.EmptyBodyError`. Some routes answer a
    success with no body on purpose, a ``200`` on a lookup that found
    nothing and a ``201`` or ``204`` on a write, while a ``302`` to an
    SSO login on an expired gateway session is byte-for-byte the same
    failure to decode. The status is the only thing that tells them
    apart, so both consumers of the class ask the question here rather
    than each writing its own comparison.

    Args:
        exc: The empty-body failure the transport raised.

    Returns:
        ``True`` for a 2xx, ``False`` for every other status that can
        reach here.
    """
    return 200 <= exc.status_code < 300


def rate_limit_message(
    exc: TransportRateLimitError,
    *,
    suffix: str = "",
) -> str:
    """Render a consistent rate-limit message across services.

    Split out of :func:`translate_transport_error` for readability
    rather than for reuse: the one caller is twenty lines below, and
    ``suffix`` is the operation phrase it passes (e.g. " on the PFB
    export download").
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
        :class:`PicSureServerError`. A result the server reports as not
        ready becomes :class:`PicSureConnectionError` too, because the
        job flow polls through it and only one that outlived the wait
        gets this far.
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
            f"{redact_credentials(exc.server_message)}",
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
            f"again shortly. The server said: "
            f"{redact_credentials(exc.server_message)}",
        )
    if isinstance(exc, TransportResultNotReadyError):
        return PicSureConnectionError(
            f"The server did not have a result ready for {operation} (HTTP "
            f"{exc.status_code}). It is still being prepared, or is being run "
            f"again after a server restart or a change to your access. Try "
            f"again shortly. The server said: "
            f"{redact_credentials(exc.server_message)}"
        )
    if isinstance(exc, TransportAuthenticationError):
        return _refusal_error(exc, operation)
    if isinstance(exc, TransportValidationError):
        refusal = _server_refusal(exc.status_code, exc.body)
        return PicSureValidationError(
            f"The server rejected {operation} ({refusal.status_label}).{refusal.said}"
        )
    if isinstance(exc, TransportNotFoundError):
        refusal = _server_refusal(404, exc.body)
        return PicSureQueryError(
            f"The endpoint for {operation} returned {refusal.status_label}."
            f"{refusal.said}"
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

    Split out of :func:`translate_transport_error` for readability
    rather than for reuse; its one caller is the fallback branch at the
    end of that function. It keeps a rejected certificate and a 5xx as
    the distinct types callers can handle, rather than flattening both
    into "temporarily unavailable".
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
    refusal = _server_refusal(exc.status_code, exc.body)
    if exc.status_code == 401:
        return PicSureAuthenticationError(
            f"Your PIC-SURE token was rejected on {operation} "
            f"({refusal.status_label}). The "
            f"token is missing, malformed, or expired. This is not a permissions "
            f"problem and not a server outage. {_NEW_TOKEN_ADVICE}"
            f"{refusal.said}"
        )
    return PicSureAuthorizationError(
        f"PIC-SURE refused {operation} ({refusal.status_label}): this account "
        f"is not authorized for it. This is a permissions decision, not a "
        f"server outage. Check that "
        f"the account holds the privilege or study approval the request needs; if "
        f"it should, the token may be stale or issued for a different environment, "
        f"so try a fresh one.{refusal.said}"
    )
