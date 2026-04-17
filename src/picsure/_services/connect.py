from __future__ import annotations

from picsure._models.resource import Resource
from picsure._models.session import Session
from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportError,
    TransportServerError,
)
from picsure._transport.platforms import Platform, resolve_platform
from picsure.errors import PicSureAuthError, PicSureConnectionError

_PSAMA_PROFILE_PATH = "/psama/user/me"
_PICSURE_RESOURCES_PATH = "/picsure/info/resources"


def connect(
    platform: Platform | str,
    token: str,
    resource_uuid: str | None = None,
) -> Session:
    """Connect to a PIC-SURE instance and return an authenticated Session.

    Args:
        platform: A :class:`Platform` enum member (e.g.
            ``Platform.BDC_AUTHORIZED``) or a full URL
            (e.g. ``"https://my-picsure.example.com"``).
        token: Your PIC-SURE API token.
        resource_uuid: Optional resource UUID to use. Overrides the
            default UUID from the Platform enum. Required for custom
            URLs — if omitted, call ``session.setResourceID(uuid)``
            after reviewing ``session.getResourceID()``.

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
    """
    info = resolve_platform(platform)
    display_name = platform.label if isinstance(platform, Platform) else platform
    client = PicSureClient(base_url=info.url, token=token)

    profile = _fetch_profile(client, display_name, info.url)
    resources = _fetch_resources(client, display_name)

    email = str(profile.get("email", "unknown"))
    expiration = str(profile.get("expirationDate", "unknown"))

    # Explicit resource_uuid wins, then Platform default, then None.
    effective_uuid = resource_uuid if resource_uuid is not None else info.resource_uuid

    print(f"You're successfully connected to {display_name} as user {email}!")
    print(f"Your token expires on {expiration}.")

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
    except (TransportConnectionError, TransportServerError) as exc:
        raise PicSureConnectionError(
            f"Could not reach {display_name} ({base_url}). Check your internet "
            "connection, or try a different platform."
        ) from exc


def _fetch_resources(client: PicSureClient, display_name: str) -> list[Resource]:
    try:
        data = client.get_json(_PICSURE_RESOURCES_PATH)
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
