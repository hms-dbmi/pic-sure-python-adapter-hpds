from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from picsure._models.resource import Resource

if TYPE_CHECKING:
    from picsure._models.facet import FacetSet
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
            f"'{name}' does not match any resource. Available resources: {valid}."
        )

    def search(
        self,
        term: str = "",
        *,
        facets: FacetSet | None = None,
        include_values: bool = True,
    ) -> pd.DataFrame:
        """Search the PIC-SURE data dictionary.

        Args:
            term: Search term. Empty string returns all variables.
            facets: Optional FacetSet to narrow results by category.
            include_values: If False, omit variable values from results.

        Returns:
            DataFrame of matching data dictionary entries.
        """
        from picsure._services.search import search as _search

        return _search(
            self._client,
            self._default_resource_uuid(),
            term,
            facets,
            include_values,
        )

    def facets(self) -> FacetSet:
        """Fetch available facet categories and return a FacetSet.

        The FacetSet starts with no selections. Use ``add()`` to select
        values, then pass it to ``search()`` to narrow results.
        """
        from picsure._models.facet import FacetSet as _FacetSet
        from picsure._services.search import fetch_facets

        available = fetch_facets(self._client, self._default_resource_uuid())
        return _FacetSet(available)

    def showAllFacets(self) -> pd.DataFrame:
        """Fetch and display all available facet categories as a DataFrame.

        Returns:
            DataFrame with columns: category, display, value, count.
        """
        from picsure._services.search import show_all_facets

        return show_all_facets(self._client, self._default_resource_uuid())

    def _default_resource_uuid(self) -> str:
        if self._resource_uuid is not None:
            return self._resource_uuid
        if not self._resources:
            from picsure.errors import PicSureError

            raise PicSureError(
                "No resources are available on this connection. "
                "Check with your administrator."
            )
        return self._resources[0].uuid
