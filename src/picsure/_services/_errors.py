from __future__ import annotations

from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConsentDeniedError,
    TransportConsentLookupError,
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportValidationError,
)
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureConsentDeniedError,
    PicSureConsentLookupError,
    PicSureError,
    PicSureQueryError,
    PicSureValidationError,
)


def rate_limit_message(
    exc: TransportRateLimitError,
    *,
    suffix: str = "",
) -> str:
    """Render a consistent rate-limit message across services.

    ``suffix`` is appended after "Rate limited" so callers can add
    operation-specific context (e.g. " by BDC Authorized",
    " on PFB result").
    """
    base = f"Rate limited{suffix}"
    if exc.retry_after is not None:
        return f"{base}; server said retry after {exc.retry_after} seconds."
    return f"{base}. Please wait and try again."


def translate_stage_error(
    exc: TransportError,
    *,
    service: str,
    stage: str,
) -> PicSureError:
    """Translate a transport exception to the public hierarchy.

    Shared shape for multi-stage flows (PFB export, saveQueryByName)
    where each stage gets the same template message keyed by
    ``"{service} {stage}"`` (e.g. ``"PFB submit"``).
    """
    label = f"{service} {stage}"
    if isinstance(exc, TransportConsentDeniedError):
        return PicSureConsentDeniedError(
            exc.status_code,
            exc.body,
            exc.error_type,
            exc.server_message,
            f"Consent was denied for {label} (HTTP {exc.status_code}), but your "
            f"session is still valid: {exc.server_message}",
        )
    if isinstance(exc, TransportConsentLookupError):
        return PicSureConsentLookupError(
            exc.status_code,
            exc.body,
            exc.error_type,
            exc.server_message,
            f"The server could not resolve consent permissions for {label} "
            f"(HTTP {exc.status_code}). This is a server-side "
            f"permission-resolution problem: {exc.server_message}",
        )
    if isinstance(exc, TransportValidationError):
        return PicSureValidationError(
            f"Server rejected the {label} request "
            f"(HTTP {exc.status_code}): {exc.body[:200]}"
        )
    if isinstance(exc, TransportNotFoundError):
        return PicSureQueryError(f"{label} endpoint returned 404: {exc.body[:200]}")
    if isinstance(exc, TransportAuthenticationError):
        return PicSureAuthError(
            f"Authentication failed on {label} "
            f"(HTTP {exc.status_code}): {exc.body[:200]}"
        )
    if isinstance(exc, TransportRateLimitError):
        return PicSureConnectionError(rate_limit_message(exc, suffix=f" on {label}"))
    return PicSureConnectionError(
        f"Could not {stage} {service}. The server may be temporarily unavailable."
    )
