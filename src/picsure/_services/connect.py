from __future__ import annotations

from picsure._models.resource import Resource
from picsure._models.session import Session
from picsure._services.consents import fetch_consents
from picsure._services.search import fetch_total_concepts
from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportServerError,
    TransportValidationError,
)
from picsure._transport.platforms import Platform, resolve_platform
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

_PSAMA_PROFILE_PATH = "/psama/user/me"
_PICSURE_RESOURCES_PATH = "/picsure/info/resources"

_ANONYMOUS_EMAIL = "anonymous"
_ANONYMOUS_EXPIRATION = "N/A"


def connect(
    platform: Platform | str,
    token: str = "",
    resource_uuid: str | None = None,
    *,
    include_consents: bool | None = None,
    requires_auth: bool | None = None,
) -> Session:
    """Connect to a PIC-SURE instance and return a Session.

    Args:
        platform: A :class:`Platform` enum member (e.g.
            ``Platform.BDC_AUTHORIZED``) or a full URL
            (e.g. ``"https://my-picsure.example.com"``).
        token: Your PIC-SURE API token.  Leave empty for open-access
            platforms (e.g. ``Platform.BDC_OPEN``) that don't require
            authentication.
        resource_uuid: Optional resource UUID to use. Overrides the
            default UUID from the Platform enum. Required for custom
            URLs — if omitted, call ``session.setResourceID(uuid)``
            after reviewing ``session.getResourceID()``.
        include_consents: Override the platform's consent policy.  For
            known Platform members this defaults to the member's own
            flag; for custom URLs it defaults to ``False``.  Pass
            ``True`` to fetch the consent list from PSAMA on connect.
        requires_auth: Override the platform's auth requirement.  Known
            Platform members default to their own flag; custom URLs
            default to ``True``.  Pass ``False`` to skip the PSAMA
            profile call on an open-access deployment.

    Returns:
        A Session you can use to search, build queries, and export data.

    Raises:
        PicSureError: If the token is invalid, the server is unreachable,
            or the platform name is not recognized.

    Example:
        >>> import picsure
        >>> session = picsure.connect(
        ...     platform="BDC Authorized",
        ...     token="your-api-token",
        ... )
        You're successfully connected to BDC Authorized as user you@email.com!
        Your token expires on 2026-06-15T00:00:00Z.

        >>> # Open-access: no token needed
        >>> session = picsure.connect(platform=picsure.Platform.BDC_OPEN)
    """
    info = resolve_platform(
        platform,
        include_consents=include_consents,
        requires_auth=requires_auth,
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

    client = PicSureClient(base_url=info.url, token=token)

    if info.requires_auth:
        profile = _fetch_profile(client, display_name, info.url)
        email = str(profile.get("email", "unknown"))
        expiration = str(profile.get("expirationDate", "unknown"))
    else:
        email = _ANONYMOUS_EMAIL
        expiration = _ANONYMOUS_EXPIRATION

    resources = _fetch_resources(client, display_name, info.requires_auth)
    consents = fetch_consents(client) if info.include_consents else []
    total_concepts = fetch_total_concepts(client, consents=consents)

    # Explicit resource_uuid wins, then Platform default, then None.
    effective_uuid = resource_uuid if resource_uuid is not None else info.resource_uuid

    if info.requires_auth:
        print(f"You're successfully connected to {display_name} as user {email}!")
        print(f"Your token expires on {expiration}.")
    else:
        print(f"You're successfully connected to {display_name} (open access).")

    if effective_uuid is None and resources:
        print("\nAvailable resources:")
        for r in resources:
            print(f"  {r.uuid}  {r.name}")
        print(
            "\nNo resource selected. Use session.setResourceID(uuid) "
            "to choose a resource before searching or querying."
        )

    return Session(
        client=client,
        user_email=email,
        token_expiration=expiration,
        resources=resources,
        resource_uuid=effective_uuid,
        consents=consents,
        total_concepts=total_concepts,
    )


def _fetch_profile(
    client: PicSureClient, display_name: str, base_url: str
) -> dict[str, object]:
    try:
        return client.get_json(_PSAMA_PROFILE_PATH)
    except TransportAuthenticationError as exc:
        raise PicSureAuthError(
            "Your token is invalid or expired. Generate a new one at "
            f"{base_url} and pass it to picsure.connect()."
        ) from exc
    except TransportNotFoundError as exc:
        raise PicSureQueryError(
            f"Profile endpoint not found at {base_url}. The server may not "
            "support this adapter version."
        ) from exc
    except TransportValidationError as exc:
        raise PicSureValidationError(
            f"Server rejected the profile request (HTTP {exc.status_code}): "
            f"{exc.body[:200]}"
        ) from exc
    except TransportRateLimitError as exc:
        raise PicSureConnectionError(_rate_limit_message(display_name, exc)) from exc
    except (TransportConnectionError, TransportServerError) as exc:
        raise PicSureConnectionError(
            f"Could not reach {display_name} ({base_url}). Check your internet "
            "connection, or try a different platform."
        ) from exc


def _rate_limit_message(display_name: str, exc: TransportRateLimitError) -> str:
    if exc.retry_after is not None:
        return (
            f"Rate limited by {display_name}; server said retry after "
            f"{exc.retry_after} seconds."
        )
    return f"Rate limited by {display_name}. Please wait and try again."


def _fetch_resources(
    client: PicSureClient, display_name: str, requires_auth: bool
) -> list[Resource]:
    try:
        data = client.get_json(_PICSURE_RESOURCES_PATH)
    except TransportAuthenticationError:
        # Open-access deployments may gate /info/resources behind auth
        # even though the dictionary-api is public.  Silently degrade
        # to no resources so search/facets still work.
        if not requires_auth:
            return []
        raise
    except TransportError as exc:
        raise PicSureConnectionError(
            f"Connected to {display_name} but could not fetch resources. "
            "The server may be temporarily unavailable."
        ) from exc

    if isinstance(data, dict):
        return [
            Resource(uuid=uuid, name=str(name), description="")
            for uuid, name in data.items()
        ]

    return [Resource.from_dict(r) for r in data]
