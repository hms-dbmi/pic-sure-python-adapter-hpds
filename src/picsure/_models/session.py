from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from picsure._models.resource import Resource

if TYPE_CHECKING:
    from pathlib import Path

    from picsure._models.count_result import CountResult
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
    ) -> None:
        self._client = client
        self._user_email = user_email
        self._token_expiration = token_expiration
        self._resources = resources
        self._resource_uuid = resource_uuid
        self._consents: list[str] = list(consents) if consents else []
        self._total_concepts = total_concepts

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

    def facets(
        self,
        term: str = "",
        *,
        facets: FacetSet | None = None,
    ) -> FacetSet:
        """Fetch available facet categories and return a FacetSet.

        The returned FacetSet starts with no selections. Use ``add()`` to
        select values, then pass it to ``search()`` to narrow results.

        Args:
            term: Optional search term. When supplied, each returned
                category's option counts reflect only concepts matching
                the term.  When omitted (the default), counts are global.
            facets: Optional current-selection :class:`FacetSet`. When
                supplied, the returned counts reflect how many additional
                concepts each option would match given the current
                selections — matching the UI sidebar's behavior.

        Returns:
            A fresh :class:`FacetSet` whose available categories carry
            contextual counts when ``term``/``facets`` are provided and
            global counts otherwise.

        Example:
            >>> fs = session.facets()
            >>> fs.add("dataset_id", "phs000007")
            >>> df = session.search("sex", facets=fs)
            >>> # Recompute with contextual counts:
            >>> refreshed = session.facets(term="sex", facets=fs)
        """
        from picsure._models.facet import FacetSet as _FacetSet
        from picsure._services.search import fetch_facets

        available = fetch_facets(
            self._client,
            consents=self._consents,
            term=term,
            facets=facets,
        )
        return _FacetSet(available)

    def showAllFacets(  # noqa: N802
        self,
        term: str = "",
        *,
        facets: FacetSet | None = None,
    ) -> pd.DataFrame:
        """Fetch and display all available facet categories as a DataFrame.

        Returns every facet option including those with count 0. The UI
        hides count=0 options; this method exposes them so notebook
        callers can see which options matched nothing.

        Args:
            term: Optional search term; when provided, the returned
                counts are contextual to concepts matching the term.
            facets: Optional current-selection :class:`FacetSet`; when
                provided, counts reflect what would remain if each option
                were added to the current selection.

        Returns:
            DataFrame with columns: ``category``, ``Category Display``,
            ``display``, ``description``, ``value``, ``count``. Counts
            are contextual when ``term``/``facets`` are supplied; global
            otherwise.
        """
        from picsure._services.search import show_all_facets

        return show_all_facets(
            self._client,
            consents=self._consents,
            term=term,
            facets=facets,
        )

    def runQuery(  # noqa: N802
        self,
        query: Query,
        type: str = "count",  # noqa: A002
    ) -> CountResult | dict[str, CountResult] | pd.DataFrame:
        """Execute a query and return the result.

        Args:
            query: A Clause or ClauseGroup built with createClause/buildClauseGroup.
            type: Result type — one of:

                - ``"count"`` → :class:`CountResult` with ``value`` /
                  ``margin`` / ``cap`` fields, preserving server-side
                  obfuscation of small counts.
                - ``"cross_count"`` → ``dict[str, CountResult]`` keyed
                  by concept path.
                - ``"participant"`` → :class:`pandas.DataFrame`.
                - ``"timestamp"`` → :class:`pandas.DataFrame`.

        Returns:
            A :class:`CountResult`, a ``dict[str, CountResult]``, or a
            DataFrame depending on ``type``.

        Example:
            >>> count = session.runQuery(my_query, type="count")
            >>> if count.value is not None:
            ...     print(f"{count.value} participants")
            ... else:
            ...     print(f"fewer than {count.cap} participants")
            >>> df = session.runQuery(my_query, type="participant")
        """
        from picsure._services.query_run import run_query

        return run_query(
            self._client,
            self._default_resource_uuid(),
            query,
            type,
        )

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

    def close(self) -> None:
        """Close the underlying HTTP client and release its connection pool.

        Safe to call more than once. Called automatically when ``Session`` is
        used as a context manager.
        """
        self._client.close()

    def __enter__(self) -> Session:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        self.close()

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
