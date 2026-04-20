from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from picsure._dev.config import DevConfig
from picsure._dev.events import Event
from picsure._models.resource import Resource
from picsure._models.session import Session
from picsure._services.consents import fetch_consents
from picsure._services.search import fetch_total_concepts
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
    dev_mode: bool | None = None,
) -> Session:
    """Connect to a PIC-SURE instance and return a Session.

    See module docstring for full parameter docs. `dev_mode`:

    - ``None`` (default): defer to ``PICSURE_DEV_MODE`` env var.
    - ``True`` / ``False``: explicit override.

    When dev mode is on, events for every HTTP call and public Session
    method are captured in an in-memory buffer, and a default stderr
    handler is attached to the ``picsure`` logger (unless one already
    exists).
    """
    info = resolve_platform(
        platform,
        include_consents=include_consents,
        requires_auth=requires_auth,
    )
    display_name = platform.label if isinstance(platform, Platform) else platform

    dev_config = DevConfig.from_env(override=dev_mode)
    if dev_config.enabled:
        _install_default_handler()

    client = PicSureClient(base_url=info.url, token=token, dev_config=dev_config)

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
                    "resources": len(resources),
                    "consents": len(consents),
                    "total_concepts": total_concepts,
                    "requires_auth": info.requires_auth,
                },
            )
        )

    return Session(
        client=client,
        user_email=email,
        token_expiration=expiration,
        resources=resources,
        resource_uuid=effective_uuid,
        consents=consents,
        total_concepts=total_concepts,
        dev_config=dev_config,
    )


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
