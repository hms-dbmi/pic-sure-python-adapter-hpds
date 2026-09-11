from __future__ import annotations

import base64
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from picsure._dev.config import DevConfig
from picsure._dev.events import Event
from picsure._models.session import Session
from picsure._services._errors import translate_transport_error
from picsure._services.consents import fetch_consents
from picsure._transport.client import VALIDATION_TIMEOUT_SECONDS, PicSureClient
from picsure._transport.errors import TransportConnectionError, TransportError
from picsure._transport.platforms import Platform, resolve_platform
from picsure._transport.secret import SecretToken, as_secret_token
from picsure.errors import (
    PicSureAuthenticationError,
    PicSureConnectionError,
    PicSureError,
    PicSureValidationError,
)

if TYPE_CHECKING:
    from picsure._transport.platforms import PlatformInfo

_ANONYMOUS_EMAIL = "anonymous"
_ANONYMOUS_EXPIRATION = "N/A"

_LOGGER_NAME = "picsure"

# The one route connect() uses to prove the deployment is reachable and the
# token is good.  It must be /psama/*, which the gateway sends straight to
# PSAMA.  /picsure/user/me is NOT interchangeable: the gateway matches access
# rules against the de-prefixed path, no rule covers "/user/me", and the
# route answers 401 there even for a valid admin token.
_VALIDATION_PATH = "/psama/user/me"
_VALIDATION_OPERATION = "the connect-time credential check"

# Fields PSAMA's own user record carries.  Their absence from a 200 means
# something other than PIC-SURE answered.
_PSAMA_USER_FIELDS = ("uuid", "email", "privileges")

# Tolerance for a token that has only just expired, so a clock a few
# seconds fast on either side does not reject a good token.
_CLOCK_SKEW = timedelta(seconds=60)

# Expiry closer than this earns a warning: long enough to be worth saying
# before a notebook session outlives its token.
_EXPIRY_WARNING_WINDOW = timedelta(days=1)

_NEW_TOKEN_ADVICE = (
    "Copy a fresh token from the PIC-SURE user interface and pass it as "
    "picsure.connect(token=...)."
)


def connect(
    platform: Platform | str,
    token: str | SecretToken = "",
    *,
    include_consents: bool | None = None,
    requires_auth: bool | None = None,
    supports_genomic: bool | None = None,
    dev_mode: bool | None = None,
    client_type: str = "PYTHON_ADAPTER",
    verify: bool | str | None = None,
    timeout: float | None = None,
    validate: bool = True,
) -> Session:
    """Connect to a PIC-SURE instance and return a Session.

    Args:
        platform: A :class:`Platform` enum member (e.g.
            ``Platform.BDC_AUTHORIZED``) or a full URL
            (e.g. ``"https://my-picsure.example.com"``).
        token: Your PIC-SURE API token, as a plain string.  Leave empty
            for open-access platforms (e.g. ``Platform.BDC_OPEN``) that
            don't require authentication.
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
        verify: TLS certificate verification, forwarded to the underlying
            HTTP client. ``None`` (default) verifies, unless the
            ``PICSURE_SSL_VERIFY`` env var overrides it. Pass ``False`` to
            skip verification (self-signed / local-dev deployments only) or
            a path to a CA bundle to trust a private CA. The connect-time
            validation request honours this setting, so it is a real
            check against the same trust decision your queries will use.
        timeout: Per-request deadline in seconds for the data operations
            this session performs — counts, participant downloads, export
            polls. Defaults to ten minutes, because a large dataset can
            legitimately take minutes to assemble server-side. The
            connect-time validation request below is not covered by it:
            that one keeps its own short deadline so a mistyped hostname
            fails in seconds.
        validate: Whether to verify the connection before returning a
            Session. ``True`` (default) checks the token's shape and
            expiry locally, then sends one ``GET /psama/user/me`` to
            confirm the deployment is reachable and, when a token was
            given, that the server accepts it. Pass ``False`` for offline
            or mocked use; nothing is sent and nothing is checked, so the
            returned Session may not work.

    Returns:
        A Session you can use to search, build queries, and export data.

    Raises:
        PicSureValidationError: If the platform is not recognized, the
            flags contradict each other, or a token is missing where one
            is required.
        PicSureAuthenticationError: If the token is not a JWT or has
            already expired (checked locally, before any request).
        PicSureAuthError: If the server refuses the token (HTTP 401/403).
        PicSureTLSError: If the server's certificate cannot be verified.
        PicSureConnectionError: If the server cannot be reached, or
            answers the validation request with something that is not a
            PIC-SURE user record.

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

    Note:
        A traceback renders the arguments and locals of *every* frame it
        passes through, not only the frame that raised, so a token held
        as a plain ``str`` reaches the user's notebook from any
        exception that crosses a function holding it.  ``token`` is
        therefore wrapped in a
        :class:`~picsure._transport.secret.SecretToken`, which renders
        as a placeholder, as the first statement here; the original
        binding is then deleted so the parameter drops out of the
        rendered frame altogether rather than being shown as a
        placeholder, and so nothing later in this function can reach
        for the unwrapped name.
    """
    secret = as_secret_token(token)
    del token

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
    if info.requires_auth and not secret:
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
        token=secret,
        dev_config=dev_config,
        session_id=session_id,
        client_type=client_type,
        verify=verify,
        timeout=timeout,
    )

    if info.requires_auth:
        # The token is the PSAMA-issued PIC-SURE JWT (built from
        # UserClaims), so the expiry comes straight from its claims —
        # /psama/user/me returns the user record without an expiry, so
        # there is nothing to read it from server-side.
        expiry = _token_expiry(secret)
        if validate:
            _reject_unusable_token(secret, expiry)
        else:
            _warn_unchecked_expiry(expiry)
        email = _email_from_jwt(secret)
        expiration = _format_expiry(expiry)
    else:
        email = _ANONYMOUS_EMAIL
        expiration = _ANONYMOUS_EXPIRATION

    if validate:
        # One real request, on every platform: it is the only thing that
        # can tell a working deployment from a hostname that does not
        # resolve.  On an authorized connection it doubles as the token
        # check, which is why the token's local checks run first — no
        # point spending a round trip on a token that cannot work.
        server_email = _validate_connection(client, info)
        if server_email is not None and info.requires_auth:
            # Prefer the server's own answer over the token's claim: it
            # is the account the request will actually run as.  An
            # anonymous connection stays anonymous even if the
            # deployment volunteers a user record.
            email = server_email

    consents = _resolve_consents(
        client,
        info,
        include_consents_requested=include_consents,
        validate=validate,
    )

    # Both the banner and the HPDS route read info.backend, so the words
    # the user sees and the path the queries take cannot disagree.
    if info.backend == "auth":
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
                bytes_sent=None,
                bytes_received=None,
                status=None,
                retry=0,
                error=None,
                metadata={
                    "consents": len(consents),
                    "requires_auth": info.requires_auth,
                },
            )
        )

    return Session(
        client=client,
        user_email=email,
        token_expiration=expiration,
        consents=consents,
        dev_config=dev_config,
        backend=info.backend,
        supports_genomic=info.supports_genomic,
        session_id=session_id,
    )


def _reject_unusable_token(token: str | SecretToken, expiry: datetime | None) -> None:
    """Refuse a token that provably cannot work, before any request.

    Three local checks, cheapest first: the token is a JWT at all, its
    payload decodes, and its ``exp`` has not already passed.  Each is a
    fact about the string the caller handed us, so spending a round trip
    to have the server say the same thing wastes the user's time and
    reports it less clearly.  Nothing here is treated as authorization:
    a token that passes every check may still be refused by the server,
    which is the actual verdict.

    This function raises, so its own frame heads the traceback the user
    sees.  It therefore keeps no token-derived local: the segments are
    counted by :func:`_jwt_segment_count`, whose frame is gone by the
    time anything here can raise, and the wrapped token renders as a
    placeholder.

    Args:
        token: The token as the caller passed it.
        expiry: The token's ``exp`` claim as a datetime, or ``None`` when
            it carries none.

    Raises:
        PicSureAuthenticationError: If the token is not a JWT, its
            payload is unreadable, or it has already expired.
    """
    secret = as_secret_token(token)
    del token

    segment_count, all_segments_present = _jwt_segment_count(secret)
    if segment_count != 3 or not all_segments_present:
        raise PicSureAuthenticationError(
            f"The value passed as token is not a PIC-SURE token: a JWT has "
            f"three non-empty dot-separated segments, this one has "
            f"{segment_count}. No request was sent. {_NEW_TOKEN_ADVICE}"
        )

    if _decode_jwt_payload(secret) is None:
        raise PicSureAuthenticationError(
            "The token's payload segment is not base64url-encoded JSON, so it "
            f"is not a PIC-SURE token. No request was sent. {_NEW_TOKEN_ADVICE}"
        )

    now = datetime.now(timezone.utc)
    if expiry is not None and expiry + _CLOCK_SKEW <= now:
        raise PicSureAuthenticationError(
            f"Your PIC-SURE token expired on {_format_expiry(expiry)}, "
            f"{_describe_age(now - expiry)} ago, so no request was sent. "
            f"{_NEW_TOKEN_ADVICE}"
        )

    if expiry is not None and expiry - now < _EXPIRY_WARNING_WINDOW:
        _warn(
            f"your PIC-SURE token expires on {_format_expiry(expiry)}, in "
            f"{_describe_age(expiry - now)}. Long-running work will start "
            f"failing with an authentication error when it does."
        )


def _warn_unchecked_expiry(expiry: datetime | None) -> None:
    """Flag an already-expired token when validation was opted out of.

    ``validate=False`` is the caller's decision and does not send a
    request, but printing a past date under a success banner is the
    defect that started this, so say it either way.
    """
    if expiry is None:
        return
    now = datetime.now(timezone.utc)
    if expiry + _CLOCK_SKEW <= now:
        _warn(
            f"the token you passed expired on {_format_expiry(expiry)} and "
            f"validate=False skipped the check, so this session will fail on "
            f"its first request. {_NEW_TOKEN_ADVICE}"
        )


def _validate_connection(client: PicSureClient, info: PlatformInfo) -> str | None:
    """Send the one connect-time request and judge the answer.

    Uses a short deadline of its own (see
    :data:`picsure._transport.client.VALIDATION_TIMEOUT_SECONDS`) rather
    than the session's data timeout, so a host that accepts TCP and
    never answers fails in seconds instead of ten minutes.  The request
    goes through the session's own client, so it honours the caller's
    ``verify`` setting — validating against a certificate we would not
    trust for real work would prove nothing.

    What counts as success depends on what there is to verify:

    * With a token, only ``200`` with a PSAMA user record will do.  The
      server accepting the token is the verdict the local checks cannot
      give.
    * Without one, any HTTP response proves the deployment is there,
      which is all an anonymous connection can honestly assert — PSAMA
      answers ``403`` to an unauthenticated ``/user/me``, and that
      ``403`` is itself proof the host exists and is PIC-SURE.

    Returns:
        The email address the server reports for this account, or
        ``None`` when it sent none (or there was no token to verify).

    Raises:
        PicSureError: Translated from the transport failure — a rejected
            token, an unverifiable certificate, an unreachable host.
        PicSureConnectionError: If the server answers ``200`` with
            something that is not a PIC-SURE user record.
    """
    try:
        payload = client.get_json(_VALIDATION_PATH, timeout=VALIDATION_TIMEOUT_SECONDS)
    except TransportConnectionError as exc:
        # No HTTP response at all: unresolved host, refused connection,
        # rejected certificate, timeout.  Fatal on every platform, and
        # the case the old zero-request connect() could not detect.
        raise translate_transport_error(exc, operation=_VALIDATION_OPERATION) from exc
    except TransportError as exc:
        # A status came back, so the deployment is reachable.  That is
        # the whole question for an anonymous connection; for an
        # authorized one the status is a refusal worth reporting.
        if not info.requires_auth:
            return None
        raise translate_transport_error(exc, operation=_VALIDATION_OPERATION) from exc
    except ValueError as exc:
        # 200 with a body that is not JSON at all — a captive portal or
        # a plain web server sitting on this hostname.
        raise PicSureConnectionError(_not_picsure_message(info.url)) from exc

    if not isinstance(payload, dict) or not any(
        field in payload for field in _PSAMA_USER_FIELDS
    ):
        raise PicSureConnectionError(_not_picsure_message(info.url))

    email = payload.get("email")
    return email.strip() if isinstance(email, str) and email.strip() else None


def _not_picsure_message(url: str) -> str:
    """Explain a 200 that is not a PIC-SURE user record."""
    return (
        f"{url} answered {_VALIDATION_PATH} with HTTP 200, but the response is "
        f"not a PIC-SURE user record — this URL may not be a PIC-SURE endpoint. "
        f"Check that it is the deployment root (e.g. "
        f"https://picsure.biodatacatalyst.nhlbi.nih.gov) rather than a path "
        f"inside the API or an unrelated host, or pass a Platform member "
        f"instead of a URL."
    )


def _resolve_consents(
    client: PicSureClient,
    info: PlatformInfo,
    *,
    include_consents_requested: bool | None,
    validate: bool,
) -> list[str]:
    """Fetch the consent list, detecting whether the deployment needs one.

    A custom URL carries no recorded consent policy, so the old default
    of "no consents" silently produced unscoped results: a dictionary
    search against a consent-authorized deployment returned every
    concept in it rather than the handful the user is entitled to.  That
    is a wrong answer rather than an error, and a plausible-looking one.

    Flipping the default the other way would break genuinely open
    deployments, so detect instead: connect() is already authenticated
    against PSAMA at this point, and a PSAMA that serves this account a
    non-empty consent list is by definition consent-scoped.  Detection
    only ever turns scoping **on**, only for a custom URL, and only when
    the caller expressed no preference.

    Where detection cannot answer — the route is absent, the record is
    empty, or validation was skipped — the capability is left off and
    said out loud, naming the argument that turns it on.
    """
    if info.include_consents:
        return fetch_consents(client)

    if include_consents_requested is not None or not info.is_custom_url:
        # An explicit False, or a known Platform whose flag is a recorded
        # fact rather than a guess.  Nothing to detect.
        return []

    if not info.requires_auth:
        # The caller declared this deployment open, so there is no
        # consent policy to detect and nothing to warn about.
        return []

    if not validate:
        _warn_unscoped(info, detected=False)
        return []

    try:
        consents = fetch_consents(client)
    except PicSureError:
        # The consent route is absent or would not answer for this
        # account.  Not fatal: the credential check already passed, so
        # the session works — it just cannot be consent-scoped.
        consents = []

    if consents:
        _note(
            f"consent scoping detected on {info.url} and enabled "
            f"({len(consents)} consents). Pass include_consents=False to "
            f"turn it off."
        )
        return consents

    _warn_unscoped(info, detected=True)
    return []


def _warn_unscoped(info: PlatformInfo, *, detected: bool) -> None:
    """Say which capabilities are off on a URL connection, and how to fix it.

    Named arguments rather than prose: the reader needs the one thing to
    type, not a description of the problem.
    """
    reason = (
        "this deployment reports no consents for your account"
        if detected
        else "consent scoping could not be checked"
    )
    missing = [f"consent scoping is off ({reason}) — include_consents=True"]
    if not info.supports_genomic:
        missing.append("genomic operations are off — supports_genomic=True")
    joined = "; ".join(missing)
    _warn(
        f"connecting to {info.url} by URL, so its capabilities are assumed "
        f"rather than known: {joined}. If this deployment is consent-scoped, "
        f"searches and queries run now will cover every study it holds "
        f"instead of only the ones you are entitled to."
    )


def _warn(message: str) -> None:
    """Print a warning to stderr, matching the note style used elsewhere."""
    print(f"Warning: {message}", file=sys.stderr)


def _note(message: str) -> None:
    """Print an informational note to stderr."""
    print(f"Note: {message}", file=sys.stderr)


def _describe_age(delta: timedelta) -> str:
    """Render a duration as the coarsest unit that still says something."""
    seconds = int(abs(delta).total_seconds())
    if seconds >= 86400:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"
    if seconds >= 3600:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    if seconds >= 60:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{seconds} second{'s' if seconds != 1 else ''}"


def _format_expiry(expiry: datetime | None) -> str:
    """Format a token expiry as UTC ISO, or ``"unknown"`` when absent."""
    if expiry is None:
        return "unknown"
    return expiry.strftime("%Y-%m-%dT%H:%M:%SZ")


def _jwt_segment_count(secret: SecretToken) -> tuple[int, bool]:
    """Count a token's dot-separated segments and whether all are non-empty.

    Split out from :func:`_reject_unusable_token` so the segment list —
    which is the token itself, in three pieces — lives only in this
    frame.  Nothing here can raise, so this frame never reaches a
    rendered traceback, and only the two scalars it returns do.

    Returns:
        The number of segments, and whether every one is non-empty.
    """
    segments = secret.reveal().split(".")
    return len(segments), all(segments)


def _token_expiry(token: str | SecretToken) -> datetime | None:
    """Read the ``exp`` claim from a JWT as an aware UTC datetime.

    Returns ``None`` when the token is not a parseable JWT, carries no
    ``exp``, or carries one that is not a number — the same "we cannot
    tell" answer in every case, which callers must not read as "not
    expired".
    """
    payload = _decode_jwt_payload(token)
    if payload is None:
        return None

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or isinstance(exp, bool):
        return None

    try:
        return datetime.fromtimestamp(exp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        # An exp far outside the representable range: unreadable, not
        # expired.
        return None


def _decode_jwt_payload(token: str | SecretToken) -> dict[str, object] | None:
    """Decode a JWT's payload segment without verifying the signature.

    The signature is intentionally not verified — the server enforces
    token validity; we only read display fields (email, expiry) from
    the payload.  Returns the payload dict, or ``None`` if the token is
    not a parseable JWT with a JSON-object payload.

    The base64 work is delegated rather than inlined so that the encoded
    payload segment — a long contiguous run of the token, and identity
    data in its own right — is never bound in this frame.
    """
    secret = as_secret_token(token)
    del token

    try:
        payload = json.loads(_decoded_payload_segment(secret))
    except (ValueError, TypeError):
        return None

    return payload if isinstance(payload, dict) else None


def _decoded_payload_segment(secret: SecretToken) -> bytes:
    """Base64url-decode the payload segment of a JWT.

    The padded segment is passed straight into
    :func:`base64.urlsafe_b64decode` instead of being bound to a local,
    for the same reason the ``Authorization`` header is built into the
    mapping handed to httpx: a named local is what a traceback renders,
    an argument on its way into a call is not.  ``secret`` is the only
    name live here, and it renders as a placeholder.

    Raises:
        ValueError: If the token has no payload segment, or that segment
            is not valid base64url.
    """
    return base64.urlsafe_b64decode(_padded_payload_segment(secret))


def _padded_payload_segment(secret: SecretToken) -> str:
    """Return a JWT's payload segment with its base64 padding restored.

    Raises:
        ValueError: If the token has no second segment to read.
    """
    segments = secret.reveal().split(".")
    if len(segments) < 2:
        raise ValueError("a JWT has three dot-separated segments")
    return segments[1] + "=" * (-len(segments[1]) % 4)


def _token_expiration_from_jwt(token: str | SecretToken) -> str:
    """Extract the ``exp`` claim from a JWT and format it as UTC ISO.

    Returns ``"unknown"`` if the token is not a parseable JWT or has no
    numeric ``exp`` claim.
    """
    return _format_expiry(_token_expiry(token))


# Preference order for the display email in the connect banner.  PSAMA
# builds the PIC-SURE token from UserClaims, which carries ``email``
# (plus ``preferred_username`` and ``sub``).  ``email`` is not immutable
# per RAS guidance, but we only display it, so degrade gracefully to
# progressively less specific claims rather than fail the connect.
_EMAIL_CLAIMS = ("email", "preferred_username", "sub")


def _email_from_jwt(token: str | SecretToken) -> str:
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
