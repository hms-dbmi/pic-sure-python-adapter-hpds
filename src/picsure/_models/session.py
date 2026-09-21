from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from picsure._dev.config import DevConfig
from picsure._dev.reporting import events_to_df, stats_to_df
from picsure._dev.timing import timed
from picsure._models.query_type import QueryType
from picsure._services._hpds_paths import check_backend
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

    Returned by ``picsure.connect()``. Holds the authenticated HTTP client,
    the user's consent list, and the HPDS backend the gateway routes to.
    Search, query building, and export delegate to the service modules.
    """

    def __init__(
        self,
        client: PicSureClient,
        user_email: str,
        token_expiration: str,
        consents: list[str] | None = None,
        dev_config: DevConfig | None = None,
        backend: str = "auth",
        supports_genomic: bool = False,
        session_id: str = "",
    ) -> None:
        """Build a session around an already-configured client.

        Args:
            client: The HTTP client to issue requests through.
            user_email: Display email for the connect banner.
            token_expiration: Formatted token expiry, or ``"N/A"`` on an
                anonymous connection.
            consents: Study-consent identifiers to scope dictionary
                requests by.
            dev_config: Developer-mode configuration; defaults to off.
            backend: ``"auth"`` or ``"open"``, the HPDS instance every
                query on this session routes to, selected by the
                ``/picsure/hpds/auth`` or ``/picsure/hpds/open`` request
                path. ``connect()`` derives it from
                ``PlatformInfo.backend``, the same value the connect
                banner reads, so the two cannot disagree.
            supports_genomic: Whether genomic operations are allowed.
            session_id: Correlation id sent on every request.

        Raises:
            PicSureValidationError: If ``backend`` is not ``"auth"`` or
                ``"open"``.
        """
        self._client = client
        self._user_email = user_email
        self._token_expiration = token_expiration
        self._session_id = session_id
        self._consents: list[str] = list(consents) if consents else []
        check_backend(backend)
        self._backend = backend
        self._supports_genomic = supports_genomic
        self._dev_config = (
            dev_config
            if dev_config is not None
            else DevConfig(enabled=False, max_events=1)
        )

    @property
    def session_id(self) -> str:
        """Stable per-session identifier sent to the backend on every request.

        Generated once at ``connect()`` and forwarded as the ``X-Session-Id``
        header so the server-side audit log can correlate every request in
        this session. Empty string if the session was constructed without one.
        """
        return self._session_id

    @property
    def user_email(self) -> str:
        """Email address of the account this session runs as.

        On an authorized connection with ``validate=True`` (the default)
        this is the address PSAMA returned for the token from
        ``GET /psama/user/me``, so it names the account the server will
        actually run requests as rather than whatever the token claims.
        Falls back to the token's own ``email`` claim when validation was
        skipped, and is ``"anonymous"`` on an open-access connection.

        The token itself is never exposed: only this address and
        :attr:`token_expiration` are readable from a session.
        """
        return self._user_email

    @property
    def token_expiration(self) -> str:
        """When this session's token expires, as UTC ISO 8601.

        Read from the token's ``exp`` claim at connect time and formatted
        as ``"YYYY-MM-DDTHH:MM:SSZ"``. ``"unknown"`` when the token
        carried no readable ``exp``, and ``"N/A"`` on an open-access
        connection, which has no token to expire.

        A rendered timestamp rather than the token: nothing here can be
        replayed as a credential.
        """
        return self._token_expiration

    @property
    def consents(self) -> list[str]:
        """Study-consent identifiers the user is authorized for.

        Empty list on open-access deployments.  Dictionary-api calls
        on authorized deployments must include this list in the request
        body so the backend scopes results to accessible studies.
        """
        return list(self._consents)

    @timed("session.searchDictionary")
    def searchDictionary(  # noqa: N802
        self,
        term: str = "",
        *,
        facets: FacetSet | None = None,
        include_values: bool = True,
        page: int | None = None,
        page_size: int | None = None,
    ) -> pd.DataFrame:
        """Search the PIC-SURE data dictionary.

        Omitting ``page`` collects every matching concept by walking the
        server's pages in ``page_size`` chunks. Passing ``page`` returns
        that one zero-based page and nothing else. Either way the
        returned DataFrame's ``attrs`` carries ``total_elements``,
        ``has_more``, ``page``, ``page_size`` and ``pages_fetched``.

        Args:
            term: Search term. Empty string returns all variables.
            facets: Optional FacetSet to narrow results by category.
            include_values: If False, omit variable values from results.
            page: Zero-based page to return. ``None`` (the default)
                collects every page.
            page_size: Rows per HTTP request. Defaults to 500.

        Returns:
            DataFrame of matching data dictionary entries.

        Raises:
            PicSureValidationError: If ``page`` or ``page_size`` is out of
                range, or if an unpaged search matches more concepts than
                one call may collect.

        Example:
            >>> df = session.searchDictionary("blood pressure")
            >>> df_filtered = session.searchDictionary("sex", facets=my_facets)
            >>> first = session.searchDictionary("sex", page=0, page_size=100)
            >>> first.attrs["has_more"]
        """
        from picsure._services.search import searchDictionary as _searchDictionary

        return _searchDictionary(
            self._client,
            term=term,
            facets=facets,
            include_values=include_values,
            consents=self._consents,
            page=page,
            page_size=page_size,
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

    @timed("session.searchGenomicValues")
    def searchGenomicValues(  # noqa: N802
        self,
        genomicConceptPath: str,  # noqa: N803
        *,
        query: str = "",
        page: int = 1,
        size: int = 50,
    ) -> pd.DataFrame:
        """Look up valid values for a genomic annotation key (paginated).

        Authorized platforms only. Returns one page of matching values as a
        single-column (``value``) DataFrame; pagination metadata (``total``,
        ``page``, ``size``) is preserved on ``df.attrs``. Raise ``size`` to
        pull more results per call, or step ``page`` to walk the full set.

        Paging here is **one-based**: the first page is ``page=1``. This
        is not the convention :meth:`searchDictionary` uses, where
        ``page`` is zero-based and the page size argument is called
        ``page_size``. The two routes are served by different backends
        and each keeps the convention its own API documents.

        Args:
            genomicConceptPath: The genomic key, e.g. ``"Gene_with_variant"``
                or ``"Variant_consequence_calculated"``.
            query: Optional case-insensitive search term to narrow results
                (e.g. ``"BRCA"``). Empty returns the first page of all values.
            page: One-based page number, so the first page is ``page=1``.
            size: Page size (number of values per call).

        Returns:
            A :class:`pandas.DataFrame` with a single ``value`` column.

        Raises:
            PicSureValidationError: If the session is not on a genomic-capable
                platform, if the key is empty, or if ``page`` or ``size`` is
                not an integer of 1 or greater. All are checked before any
                request is sent.

        Example:
            >>> df = session.searchGenomicValues("Gene_with_variant", query="BRCA")
            >>> df["value"].tolist()
            ['BRCA1', 'BRCA2']
        """
        self._require_genomic()

        from picsure._services.genomic_search import search_genomic_values

        return search_genomic_values(
            self._client,
            genomicConceptPath,
            backend=self._backend,
            query=query,
            page=page,
            size=size,
        )

    @timed("session.runQuery")
    def runQuery(  # noqa: N802
        self,
        query: Query | Clause | ClauseGroup,
        type: QueryType | str = "count",  # noqa: A002
    ) -> CountResult | dict[str, CountResult] | pd.DataFrame | list[str]:
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
                - ``"variant_count"`` → :class:`CountResult` (preserving
                  obfuscation, like ``"count"``).
                - ``"variant_list"`` → ``list[str]``.
                - ``"vcf_excerpt"`` / ``"aggregate_vcf_excerpt"`` →
                  :class:`pandas.DataFrame`.

        Returns:
            A :class:`CountResult`, a ``dict[str, CountResult]``, a
            DataFrame, or a ``list[str]`` depending on ``type``.

        A ``"participant"`` or ``"timestamp"`` result is built by a job on
        the server, so the call submits the query, waits until the server
        reports the result ready and then downloads it, with the submit
        and the wait together bounded by the ``timeout`` given to
        :func:`picsure.connect`; passing that budget raises
        :class:`~picsure.errors.PicSureConnectionError`.

        Example:
            >>> count = session.runQuery(my_query, type="count")
            >>> if count.value is not None:
            ...     print(f"{count.value} participants")
            ... else:
            ...     print(f"fewer than {count.cap} participants")
            >>> df = session.runQuery(my_query, type="participant")
        """
        from picsure._models.query import Query

        if (
            isinstance(query, Query)
            and query.genomicFilters
            and not self._supports_genomic
        ):
            self._require_genomic()

        from picsure._services.query_run import run_query

        return run_query(
            self._client,
            query,
            type,
            backend=self._backend,
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

        The submit and the polling loop together are bounded by the
        request timeout ``picsure.connect(timeout=...)`` sets, ten
        minutes by default. The clock starts just before the submit and
        is read after each poll answers, so one poll that runs to the
        per-request deadline completes before the budget is enforced.
        The download that follows carries the same value as its own
        per-request deadline, so the call as a whole can run longer
        than the timeout.

        Args:
            query: A Query, Clause, or ClauseGroup.
            path: File path to write the PFB data to.

        Raises:
            PicSureValidationError: If the session was connected to an
                open-access platform, or the server rejects the submit,
                poll or download with a 4xx other than 401, 403, 404 and
                429.
            PicSureAuthenticationError: If the token is rejected (HTTP
                401).
            PicSureAuthorizationError: If the account may not run the
                export (HTTP 403), including a consent denial.
            PicSureQueryError: If any of the three routes answers 404, if
                the server finishes the query with ``status=ERROR``, or if
                it answers the submit with no query id or one that is not
                a UUID, or a poll with no status field.
            PicSureConnectionError: If the submit and polling pass the
                request timeout with the result still unavailable, if
                the server cannot be reached or
                rate limits the request, if it answers 5xx (as
                :class:`~picsure.errors.PicSureServerError`), or if the
                output file cannot be written.
        """
        if self._backend == "open":
            raise PicSureValidationError(
                "PFB export is not supported on open-access platforms. "
                "Connect with an authorized platform (e.g. "
                "Platform.BDC_AUTHORIZED) and a valid token to export PFB."
            )

        from picsure._services.export import export_pfb

        export_pfb(
            self._client,
            query,
            path,
            backend=self._backend,
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
            query,
            name,
            backend=self._backend,
            overwrite=overwrite,
        )

    @timed("session.exportCSV")
    def exportCSV(  # noqa: N802
        self,
        data: pd.DataFrame | pd.Series,
        path: str | Path,
    ) -> None:
        """Write a DataFrame or Series to a CSV file.

        Args:
            data: DataFrame to export (e.g. from runQuery), or a single
                column of one.
            path: File path for the CSV output.

        Raises:
            PicSureValidationError: If ``data`` is neither a DataFrame nor
                a Series, for example the ``CountResult`` of a count query.
            PicSureConnectionError: If ``path`` could not be written.
        """
        from picsure._services.export import export_csv

        export_csv(data, path)

    @timed("session.exportTSV")
    def exportTSV(  # noqa: N802
        self,
        data: pd.DataFrame | pd.Series,
        path: str | Path,
    ) -> None:
        """Write a DataFrame or Series to a TSV file.

        Args:
            data: DataFrame to export (e.g. from runQuery), or a single
                column of one.
            path: File path for the TSV output.

        Raises:
            PicSureValidationError: If ``data`` is neither a DataFrame nor
                a Series, for example the ``CountResult`` of a count query.
            PicSureConnectionError: If ``path`` could not be written.
        """
        from picsure._services.export import export_tsv

        export_tsv(data, path)

    @timed("session.runQueryByID")
    def runQueryByID(  # noqa: N802
        self,
        query_id: str,
        type: QueryType | str = "count",  # noqa: A002
    ) -> CountResult | dict[str, CountResult] | pd.DataFrame | list[str]:
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
            :class:`pandas.DataFrame`, or ``list[str]`` depending
            on ``type``.

        Raises:
            PicSureValidationError: If the ID is blank, the saved query
                cannot be loaded, or the query type is invalid.
            PicSureAuthenticationError: If the token is rejected (HTTP 401).
            PicSureAuthorizationError: If the account may not load or run
                the query (HTTP 403), including a consent denial.
            PicSureConnectionError: If the server cannot be reached, or
                :class:`PicSureServerError` if it answered with a 5xx.
            PicSureQueryError: If a response cannot be parsed.

        Example:
            >>> count = session.runQueryByID(
            ...     "11111111-2222-3333-4444-555555555555", type="count"
            ... )
            >>> df = session.runQueryByID(
            ...     "22222222-3333-4444-5555-666666666666", type="participant"
            ... )
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
            PicSureAuthenticationError: If the token is rejected (HTTP 401).
            PicSureAuthorizationError: If the account may not load the
                query (HTTP 403), including a consent denial.
            PicSureConnectionError: If the server cannot be reached, or
                :class:`PicSureServerError` if it answered with a 5xx.
            PicSureQueryError: If the response cannot be parsed.

        Example:
            >>> previous = session.loadQueryByID("11111111-2222-3333-4444-555555555555")
            >>> count = session.runQuery(previous, type="count")
        """
        from picsure._services.query_load import load_query

        return load_query(self._client, query_id, backend=self._backend)

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

    def _require_genomic(self) -> None:
        """Raise unless this session is on a genomic-capable platform."""
        if not self._supports_genomic:
            raise PicSureValidationError(
                "Genomic operations require an authorized platform "
                "(e.g. Platform.BDC_AUTHORIZED); this session is connected "
                "to an open or non-genomic resource."
            )
