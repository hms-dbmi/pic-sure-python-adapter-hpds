from __future__ import annotations

import base64
import json
import logging
import sys
from datetime import datetime, timezone
from uuid import uuid4

from picsure._dev.config import DevConfig
from picsure._dev.events import Event
from picsure._models.session import Session
from picsure._services.consents import fetch_consents
from picsure._transport.client import PicSureClient
from picsure._transport.platforms import Platform, resolve_platform
from picsure.errors import (
    PicSureValidationError,
)

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
    supports_genomic: bool | None = None,
    dev_mode: bool | None = None,
    client_type: str = "PYTHON_ADAPTER",
) -> Session:
    """Connect to a PIC-SURE instance and return a Session.

    Args:
        platform: A :class:`Platform` enum member (e.g.
            ``Platform.BDC_AUTHORIZED``) or a full URL
            (e.g. ``"https://my-picsure.example.com"``).  Pass the bare
            origin: the ``/picsure`` ingress prefix is part of the routes
            this adapter builds, and a URL that already ends in
            ``/picsure`` is normalized so it is never doubled.
        token: Your PIC-SURE API token.  Leave empty for open-access
            platforms (e.g. ``Platform.BDC_OPEN``) that don't require
            authentication.
        resource_uuid: Deprecated and no longer used for routing. The
            gateway now selects the HPDS backend by URL path
            (``/picsure/hpds/auth`` vs ``/picsure/hpds/open``), derived from the
            platform, so a resource UUID no longer chooses a backend.
            Accepted for backwards compatibility and stored on the
            session, but it does not affect which data is queried.
        include_consents: Override the platform's consent policy.  For
            known Platform members this defaults to the member's own
            flag; for custom URLs it defaults to ``False``.  Pass
            ``True`` to fetch the consent list from PSAMA on connect.
        requires_auth: Override the platform's auth requirement.  Known
            Platform members default to their own flag; custom URLs
            default to ``True``.  Pass ``False`` on an open-access
            deployment to connect anonymously without a token.
        supports_genomic: Override whether genomic operations are allowed
            on this session.  Defaults to the platform's own flag (``True``
            for ``Platform.BDC_AUTHORIZED``, ``False`` otherwise).  For
            custom URLs pass ``True`` to allow genomic operations.
        dev_mode: Developer-mode toggle. ``None`` (default) defers to
            the ``PICSURE_DEV_MODE`` env var; ``True`` / ``False``
            overrides it. When on, events for every HTTP call and
            public Session method are captured in an in-memory buffer,
            and a default stderr handler is attached to the ``picsure``
            logger (unless one already exists).
        client_type: Identifies the calling client to the backend's audit
            log, sent as the ``X-Client-Type`` header on every request.
            Defaults to ``"PYTHON_ADAPTER"``; the R adapter passes
            ``"R_ADAPTER"``.

    Returns:
        A Session you can use to search, build queries, and export data.

    Raises:
        PicSureError: If the token is invalid, the server is unreachable,
            or the platform name is not recognized.

    Example:
        >>> import picsure
        >>> session = picsure.connect(
        ...     platform=picsure.Platform.BDC_AUTHORIZED,
        ...     token="your-api-token",
        ... )
        You're successfully connected to BDC Authorized as user you@email.com!
        Your token expires on 2026-06-15T00:00:00Z.

        >>> # Custom deployment: pass a full URL string
        >>> session = picsure.connect(
        ...     platform="https://my-picsure.example.com",
        ...     token="your-api-token",
        ... )

        >>> # Open-access: no token needed
        >>> session = picsure.connect(platform=picsure.Platform.BDC_OPEN)
    """
    info = resolve_platform(
        platform,
        include_consents=include_consents,
        requires_auth=requires_auth,
        supports_genomic=supports_genomic,
    )
    display_name = platform.label if isinstance(platform, Platform) else platform

    # Fail fast on an empty / whitespace-only token when the platform
    # requires auth.  Without this, PicSureClient would silently drop
    # the token, the "request-source: Open" header would be sent, and
    # the backend would later reject with a confusing "token invalid
    # or expired" message.
    if info.requires_auth and not token.strip():
        raise PicSureValidationError(
            f"Platform {display_name} requires a token but none was provided. "
            "Pass token=<your PIC-SURE API token> to picsure.connect(), or "
            "use an open-access platform (e.g. Platform.BDC_OPEN)."
        )

    dev_config = DevConfig.from_env(override=dev_mode)
    if dev_config.enabled:
        _install_default_handler()

    # One stable id for the lifetime of this session, forwarded on every
    # request so the backend audit log can correlate the session's calls.
    session_id = str(uuid4())

    client = PicSureClient(
        base_url=info.url,
        token=token,
        dev_config=dev_config,
        session_id=session_id,
        client_type=client_type,
    )

    if info.requires_auth:
        # The token is the PSAMA-issued PIC-SURE JWT (built from
        # UserClaims), so both the display email and the expiry come
        # straight from its claims — no round trip to /psama/user/me.
        email = _email_from_jwt(token)
        expiration = _token_expiration_from_jwt(token)
    else:
        email = _ANONYMOUS_EMAIL
        expiration = _ANONYMOUS_EXPIRATION

    # The resource registry (/info/resources) is gone: the gateway routes
    # by URL path, not by a resource UUID discovered from a registry, so
    # there is no discovery round-trip on connect.
    consents = fetch_consents(client) if info.include_consents else []

    if info.requires_auth:
        print(f"You're successfully connected to {display_name} as user {email}!")
        print(f"Your token expires on {expiration}.")
    else:
        print(f"You're successfully connected to {display_name} (open access).")

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
                    "consents": len(consents),
                    "requires_auth": info.requires_auth,
                },
            )
        )

    # HPDS backend is chosen by URL path, not a resource UUID: open-access
    # deployments (no auth, no consents) route to /picsure/hpds/open and use the v1
    # query lifecycle; authorized and consent-gated deployments route to
    # /picsure/hpds/auth and use v3.  This preserves the split where BDC's gateway
    # serves open-access traffic only on v1 and authorized traffic on v3.
    backend = "open" if not info.requires_auth and not info.include_consents else "auth"

    return Session(
        client=client,
        user_email=email,
        token_expiration=expiration,
        resource_uuid=resource_uuid,
        consents=consents,
        dev_config=dev_config,
        backend=backend,
        supports_genomic=info.supports_genomic,
        session_id=session_id,
    )


def _decode_jwt_payload(token: str) -> dict[str, object] | None:
    """Decode a JWT's payload segment without verifying the signature.

    The signature is intentionally not verified — the server enforces
    token validity; we only read display fields (email, expiry) from
    the payload.  Returns the payload dict, or ``None`` if the token is
    not a parseable JWT with a JSON-object payload.
    """
    try:
        payload_b64 = token.strip().split(".")[1]
    except IndexError:
        return None

    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except (ValueError, TypeError):
        return None

    return payload if isinstance(payload, dict) else None


def _token_expiration_from_jwt(token: str) -> str:
    """Extract the ``exp`` claim from a JWT and format it as UTC ISO.

    Returns ``"unknown"`` if the token is not a parseable JWT or has no
    numeric ``exp`` claim.
    """
    payload = _decode_jwt_payload(token)
    if payload is None:
        return "unknown"

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or isinstance(exp, bool):
        return "unknown"

    return datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Preference order for the display email in the connect banner.  PSAMA
# builds the PIC-SURE token from UserClaims, which carries ``email``
# (plus ``preferred_username`` and ``sub``).  ``email`` is not immutable
# per RAS guidance, but we only display it, so degrade gracefully to
# progressively less specific claims rather than fail the connect.
_EMAIL_CLAIMS = ("email", "preferred_username", "sub")


def _email_from_jwt(token: str) -> str:
    """Read a display email from the JWT the user supplied.

    Falls back through :data:`_EMAIL_CLAIMS` and finally to ``"unknown"``
    if none is present, so the connect banner never breaks on a token
    whose claims vary by IdP / Okta mapping.
    """
    payload = _decode_jwt_payload(token)
    if payload is None:
        return "unknown"

    for claim in _EMAIL_CLAIMS:
        value = payload.get(claim)
        if isinstance(value, str) and value.strip():
            return value
    return "unknown"


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
