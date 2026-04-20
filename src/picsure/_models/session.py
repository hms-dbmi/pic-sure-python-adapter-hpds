from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from picsure._dev.config import DevConfig
from picsure._dev.reporting import events_to_df, stats_to_df
from picsure._dev.timing import timed
from picsure._models.resource import Resource

if TYPE_CHECKING:
    from pathlib import Path

    from picsure._models.facet import FacetSet
    from picsure._models.query import Query
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
        consents: list[str] | None = None,
        total_concepts: int = 0,
        dev_config: DevConfig | None = None,
    ) -> None:
        self._client = client
        self._user_email = user_email
        self._token_expiration = token_expiration
        self._resources = resources
        self._resource_uuid = resource_uuid
        self._consents: list[str] = list(consents) if consents else []
        self._total_concepts = total_concepts
        self._dev_config = dev_config if dev_config is not None else DevConfig(
            enabled=False, max_events=1
        )

    @property
    def consents(self) -> list[str]:
        """Study-consent identifiers the user is authorized for.

        Empty list on open-access deployments.  Dictionary-api calls
        on authorized deployments must include this list in the request
        body so the backend scopes results to accessible studies.
        """
        return list(self._consents)

    @property
    def total_concepts(self) -> int:
        """Total number of concepts in the data dictionary.

        Captured at connect time and used as the page size for search
        requests so every result comes back in one page.
        """
        return self._total_concepts

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

    @timed("session.search")
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

        Example:
            >>> df = session.search("blood pressure")
            >>> df_filtered = session.search("sex", facets=my_facets)
        """
        from picsure._services.search import search as _search

        return _search(
            self._client,
            term=term,
            facets=facets,
            include_values=include_values,
            consents=self._consents,
            page_size=self._total_concepts,
        )

    @timed("session.facets")
    def facets(self) -> FacetSet:
        """Fetch available facet categories and return a FacetSet.

        The FacetSet starts with no selections. Use ``add()`` to select
        values, then pass it to ``search()`` to narrow results.

        Example:
            >>> fs = session.facets()
            >>> fs.add("study_ids", "phs000007")
            >>> df = session.search("sex", facets=fs)
        """
        from picsure._models.facet import FacetSet as _FacetSet
        from picsure._services.search import fetch_facets

        available = fetch_facets(self._client, consents=self._consents)
        return _FacetSet(available)

    @timed("session.showAllFacets")
    def showAllFacets(self) -> pd.DataFrame:
        """Fetch and display all available facet categories as a DataFrame.

        Returns:
            DataFrame with columns: category, display, value, count.
        """
        from picsure._services.search import show_all_facets

        return show_all_facets(self._client, consents=self._consents)

    @timed("session.runQuery")
    def runQuery(  # noqa: N802
        self,
        query: Query,
        type: str = "count",  # noqa: A002
    ) -> int | pd.DataFrame:
        """Execute a query and return the result.

        Args:
            query: A Clause or ClauseGroup built with createClause/buildClauseGroup.
            type: Result type — "count" (returns int), "participant"
                (returns DataFrame), or "timestamp" (returns DataFrame).

        Returns:
            An integer for count queries, or a DataFrame for data queries.

        Example:
            >>> count = session.runQuery(my_query, type="count")
            >>> df = session.runQuery(my_query, type="participant")
        """
        from picsure._services.query_run import run_query

        return run_query(
            self._client,
            self._default_resource_uuid(),
            query,
            type,
        )

    @timed("session.exportPFB")
    def exportPFB(  # noqa: N802
        self,
        query: Query,
        path: str | Path,
    ) -> None:
        """Execute a query and write the result as a PFB file.

        Args:
            query: A Clause or ClauseGroup.
            path: File path to write the PFB data to.
        """
        from picsure._services.export import export_pfb

        export_pfb(
            self._client,
            self._default_resource_uuid(),
            query,
            path,
        )

    @timed("session.exportCSV")
    def exportCSV(  # noqa: N802
        self,
        data: pd.DataFrame,
        path: str | Path,
    ) -> None:
        """Write a DataFrame to a CSV file.

        Args:
            data: DataFrame to export (e.g. from runQuery).
            path: File path for the CSV output.
        """
        from picsure._services.export import export_csv

        export_csv(data, path)

    @timed("session.exportTSV")
    def exportTSV(  # noqa: N802
        self,
        data: pd.DataFrame,
        path: str | Path,
    ) -> None:
        """Write a DataFrame to a TSV file.

        Args:
            data: DataFrame to export (e.g. from runQuery).
            path: File path for the TSV output.
        """
        from picsure._services.export import export_tsv

        export_tsv(data, path)

    # --- dev-mode surface ---------------------------------------------------

    @property
    def dev_mode(self) -> bool:
        """True if developer mode is enabled for this session."""
        return self._dev_config.enabled

    def dev_events(self) -> pd.DataFrame:
        """Return the raw event log as a DataFrame (one row per event)."""
        return events_to_df(self._dev_config.buffer.snapshot())

    def dev_stats(self) -> pd.DataFrame:
        """Return aggregated per-(kind, name) stats as a DataFrame."""
        return stats_to_df(self._dev_config.buffer.snapshot())

    def dev_clear(self) -> None:
        """Empty the event buffer. No-op when dev mode is disabled."""
        self._dev_config.buffer.clear()

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
