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
from picsure._transport.platforms import resolve_platform_url
from picsure.errors import PicSureAuthError, PicSureConnectionError

_PSAMA_PROFILE_PATH = "/psama/user/me"
_PICSURE_RESOURCES_PATH = "/picsure/info/resources"


def connect(platform: str, token: str) -> Session:
    """Connect to a PIC-SURE instance and return an authenticated Session.

    Args:
        platform: A named platform (e.g. "BDC Authorized") or a full URL
            (e.g. "https://my-picsure.example.com").
        token: Your PIC-SURE API token.

    Returns:
        A Session you can use to search, build queries, and export data.

    Raises:
        PicSureError: If the token is invalid, the server is unreachable,
            or the platform name is not recognized.
    """
    base_url = resolve_platform_url(platform)
    client = PicSureClient(base_url=base_url, token=token)

    profile = _fetch_profile(client, platform, base_url)
    resources = _fetch_resources(client, platform)

    email = str(profile.get("email", "unknown"))
    expiration = str(profile.get("expirationDate", "unknown"))

    print(f"You're successfully connected to {platform} as user {email}!")
    print(f"Your token expires on {expiration}.")

    return Session(
        client=client,
        user_email=email,
        token_expiration=expiration,
        resources=resources,
    )


def _fetch_profile(
    client: PicSureClient, platform: str, base_url: str
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
            f"Could not reach {platform} ({base_url}). Check your internet "
            "connection, or try a different platform."
        ) from exc


def _fetch_resources(
    client: PicSureClient, platform: str
) -> list[Resource]:
    try:
        data = client.get_json(_PICSURE_RESOURCES_PATH)
    except TransportError as exc:
        raise PicSureConnectionError(
            f"Connected to {platform} but could not fetch resources. "
            "The server may be temporarily unavailable."
        ) from exc

    items: list[dict[str, object]] = data if isinstance(data, list) else [data]

    return [Resource.from_dict(r) for r in items]
