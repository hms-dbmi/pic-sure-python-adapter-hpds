from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from picsure._models.resource import Resource

if TYPE_CHECKING:
    from picsure._transport.client import PicSureClient


class Session:
    """A live connection to a PIC-SURE instance.

    Returned by ``picsure.connect()``. Holds the authenticated HTTP client
    and resource metadata. Methods for search, query building, and export
    are added in later plans.
    """

    def __init__(
        self,
        client: PicSureClient,
        user_email: str,
        token_expiration: str,
        resources: list[Resource],
        resource_uuid: str | None = None,
    ) -> None:
        self._client = client
        self._user_email = user_email
        self._token_expiration = token_expiration
        self._resources = resources
        self._resource_uuid = resource_uuid

    def getResourceID(self) -> pd.DataFrame:
        """Return resource IDs and metadata as a DataFrame."""
        if not self._resources:
            return pd.DataFrame(columns=["uuid", "name", "description"])
        return pd.DataFrame(
            [
                {
                    "uuid": r.uuid,
                    "name": r.name,
                    "description": r.description,
                }
                for r in self._resources
            ]
        )

    def setResourceID(self, resource_uuid: str) -> None:
        """Set the active resource UUID for searches and queries.

        Args:
            resource_uuid: The UUID of the resource to use. See
                ``getResourceID()`` for available resources.

        Raises:
            PicSureValidationError: If the UUID does not match any
                resource on this connection.
        """
        from picsure.errors import PicSureValidationError

        known_uuids = {r.uuid for r in self._resources}
        if known_uuids and resource_uuid not in known_uuids:
            raise PicSureValidationError(
                f"'{resource_uuid}' is not a valid resource UUID. "
                f"Use session.getResourceID() to see available resources."
            )
        self._resource_uuid = resource_uuid

    def setResourceIDByName(self, name: str) -> None:
        """Set the active resource by looking up its name.

        Args:
            name: The resource name (e.g. ``"hpds"``, ``"auth-hpds"``).

        Raises:
            PicSureValidationError: If no resource matches the given name.
        """
        from picsure.errors import PicSureValidationError

        for r in self._resources:
            if r.name == name:
                self._resource_uuid = r.uuid
                return

        valid = ", ".join(r.name for r in self._resources)
        raise PicSureValidationError(
            f"'{name}' does not match any resource. "
            f"Available resources: {valid}."
        )
