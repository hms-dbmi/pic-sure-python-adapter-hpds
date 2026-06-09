from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from picsure._dev.config import DevConfig
from picsure._dev.reporting import events_to_df, stats_to_df
from picsure._dev.timing import timed
from picsure._models.query_type import QueryType
from picsure._models.resource import Resource
from picsure.errors import PicSureValidationError

if TYPE_CHECKING:
    from pathlib import Path

    from picsure._models.clause import Clause
    from picsure._models.clause_group import ClauseGroup
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
        dev_config: DevConfig | None = None,
        use_legacy_query_path: bool = False,
    ) -> None:
        self._client = client
        self._user_email = user_email
        self._token_expiration = token_expiration
        self._resources = resources
        self._resource_uuid = resource_uuid
        self._consents: list[str] = list(consents) if consents else []
        self._total_concepts = total_concepts
        self._use_legacy_query_path = use_legacy_query_path
        self._dev_config = (
            dev_config
            if dev_config is not None
            else DevConfig(enabled=False, max_events=1)
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
        for r in self._resources:
            if r.name == name:
                self._resource_uuid = r.uuid
                return

        valid = ", ".join(r.name for r in self._resources)
        raise PicSureValidationError(
            f"'{name}' does not match any resource. Available resources: {valid}."
        )

    @timed("session.searchDictionary")
    def searchDictionary(  # noqa: N802
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
            >>> df = session.searchDictionary("blood pressure")
            >>> df_filtered = session.searchDictionary("sex", facets=my_facets)
        """
        from picsure._services.search import searchDictionary as _searchDictionary

        return _searchDictionary(
            self._client,
            term=term,
            facets=facets,
            include_values=include_values,
            consents=self._consents,
            page_size=self._total_concepts,
        )

    @timed("session.facets")
    def facets(
        self,
        term: str = "",
        *,
        facets: FacetSet | None = None,
    ) -> FacetSet:
        """Fetch available facet categories and return a FacetSet.

        The returned FacetSet starts with no selections. Use ``add()`` to
        select values, then pass it to ``searchDictionary()`` to narrow results.

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
            >>> df = session.searchDictionary("sex", facets=fs)
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

    @timed("session.showAllFacets")
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

    @timed("session.runQuery")
    def runQuery(  # noqa: N802
        self,
        query: Query | Clause | ClauseGroup,
        type: QueryType | str = "count",  # noqa: A002
    ) -> CountResult | dict[str, CountResult] | pd.DataFrame | int | list[str]:
        """Execute a query and return the result.

        Args:
            query: A Query (from buildQuery), or a bare Clause/ClauseGroup
                (from buildClause/buildClauseGroup). Variables referenced in
                the filter are returned as output columns automatically;
                ``includeConcepts`` adds further non-filtered columns.
            type: Result type. Pass either a :class:`QueryType` member
                (e.g. ``QueryType.COUNT``) or one of the strings:

                - ``"count"`` → :class:`CountResult` with ``value`` /
                  ``margin`` / ``cap`` fields, preserving server-side
                  obfuscation of small counts.
                - ``"cross_count"`` → ``dict[str, CountResult]`` keyed
                  by concept path.
                - ``"participant"`` → :class:`pandas.DataFrame`.
                - ``"timestamp"`` → :class:`pandas.DataFrame`.
                - ``"variant_count"`` → ``int``.
                - ``"variant_list"`` → ``list[str]``.
                - ``"vcf_excerpt"`` / ``"aggregate_vcf_excerpt"`` →
                  :class:`pandas.DataFrame`.

        Returns:
            A :class:`CountResult`, a ``dict[str, CountResult]``, a
            DataFrame, an ``int``, or a ``list[str]`` depending on ``type``.

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
            use_legacy_query_path=self._use_legacy_query_path,
        )

    @timed("session.exportAsPFB")
    def exportAsPFB(  # noqa: N802
        self,
        query: Query | Clause | ClauseGroup,
        path: str | Path,
    ) -> None:
        """Execute a query and write the result as a PFB file.

        Not supported on open-access deployments (platforms with both
        ``requires_auth=False`` and ``include_consents=False``): the PFB
        async flow is exposed only on the authorized v3 endpoints, which
        the BDC API gateway rejects without a token.

        Args:
            query: A Query, Clause, or ClauseGroup.
            path: File path to write the PFB data to.

        Raises:
            PicSureValidationError: If the session was connected to an
                open-access platform.
        """
        if self._use_legacy_query_path:
            raise PicSureValidationError(
                "PFB export is not supported on open-access platforms. "
                "Connect with an authorized platform (e.g. "
                "Platform.BDC_AUTHORIZED) and a valid token to export PFB."
            )

        from picsure._services.export import export_pfb

        export_pfb(
            self._client,
            self._default_resource_uuid(),
            query,
            path,
        )

    @timed("session.saveQueryByName")
    def saveQueryByName(  # noqa: N802
        self,
        query: Query | Clause | ClauseGroup,
        name: str,
        *,
        overwrite: bool = False,
    ) -> str:
        """Save a query to the user's profile and return its PIC-SURE query ID.

        Not supported on open-access deployments. The returned ID can be
        passed to :meth:`loadQueryByID` or :meth:`runQueryByID` later.

        Args:
            query: A Query, Clause, or ClauseGroup.
            name: Display name to associate with the query.
            overwrite: When ``False`` (default), refuse if a named query
                with that name already exists for this user. When ``True``,
                repoint the existing record at the freshly-submitted query.

        Example:
            >>> qid = session.saveQueryByName(my_query, "Cohort 2026-Q2")
            >>> qid = session.saveQueryByName(
            ...     my_query, "Cohort 2026-Q2", overwrite=True
            ... )
            >>> later = session.loadQueryByID(qid)
        """
        from picsure._services.query_save import save_query_by_name

        return save_query_by_name(
            self._client,
            self._default_resource_uuid(),
            query,
            name,
            use_legacy_query_path=self._use_legacy_query_path,
            overwrite=overwrite,
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

    @timed("session.runQueryByID")
    def runQueryByID(  # noqa: N802
        self,
        query_id: str,
        type: QueryType | str = "count",  # noqa: A002
    ) -> CountResult | dict[str, CountResult] | pd.DataFrame | int | list[str]:
        """Load a saved query by ID and execute it in one call.

        Convenience wrapper around :meth:`loadQueryByID` + :meth:`runQuery`.

        Args:
            query_id: The UUID string of a previous PIC-SURE query.
            type: Result type, as accepted by :meth:`runQuery` —
                ``"count"`` (default), ``"cross_count"``, ``"participant"``,
                ``"timestamp"``, ``"variant_count"``, ``"variant_list"``,
                ``"vcf_excerpt"``, or ``"aggregate_vcf_excerpt"`` (or the
                equivalent :class:`QueryType` member).

        Returns:
            A :class:`CountResult`, ``dict[str, CountResult]``,
            :class:`pandas.DataFrame`, ``int``, or ``list[str]`` depending
            on ``type``.

        Raises:
            PicSureValidationError: If the ID is blank, the saved query
                cannot be loaded, or the query type is invalid.
            PicSureAuthError / PicSureConnectionError / PicSureQueryError:
                As raised by the underlying load and execute calls.

        Example:
            >>> count = session.runQueryByID(
            ...     "11111111-2222-3333-4444-555555555555", type="count"
            ... )
            >>> df = session.runQueryByID("XXXXX-ID", type="participant")
        """
        query = self.loadQueryByID(query_id)
        return self.runQuery(query, type)

    @timed("session.loadQueryByID")
    def loadQueryByID(  # noqa: N802
        self, query_id: str
    ) -> Query | Clause | ClauseGroup:
        """Load a previously-saved PIC-SURE query by its query ID.

        Args:
            query_id: The UUID string of a previous query.

        Returns:
            A Query (when the saved query selects output concepts) or a bare
            Clause/ClauseGroup, suitable for runQuery, exportAsPFB, or — for a
            bare filter — composing with buildClauseGroup.

        Raises:
            PicSureValidationError: If the ID is empty, the query was not
                found, or the saved query uses features this adapter cannot
                yet represent (NOT clauses).
            PicSureAuthError: On 401 / 403.
            PicSureConnectionError: If the server is unreachable.
            PicSureQueryError: If the response cannot be parsed.

        Example:
            >>> previous = session.loadQueryByID("11111111-2222-3333-4444-555555555555")
            >>> count = session.runQuery(previous, type="count")
        """
        from picsure._services.query_load import load_query

        return load_query(self._client, query_id)

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
            raise PicSureValidationError(
                "No resources are available on this connection. "
                "Check with your administrator."
            )
        if len(self._resources) == 1:
            return self._resources[0].uuid
        listing = "\n".join(f"  {r.uuid}  {r.name}" for r in self._resources)
        raise PicSureValidationError(
            "This connection has multiple resources and none has been "
            "selected. Call session.setResourceID(uuid) to choose one "
            "before searching or querying.\n\n"
            f"Available resources:\n{listing}"
        )
