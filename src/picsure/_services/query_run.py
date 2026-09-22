from __future__ import annotations

import json
import re
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path
from typing import NoReturn

import pandas as pd

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.count_result import CountResult
from picsure._models.genomic_filter import GenomicFilter
from picsure._models.query import Query
from picsure._models.query_type import QueryType
from picsure._services._errors import (
    bodiless_response_succeeded,
    translate_transport_error,
)
from picsure._services._hpds_paths import (
    query_id_from_submit_response,
    query_prefix,
    query_result_path,
    query_status_path,
    query_submit_path,
)
from picsure._transport.client import PicSureClient, json_object
from picsure._transport.errors import (
    TransportConnectionError,
    TransportConsentLookupError,
    TransportError,
    TransportRateLimitError,
    TransportServerError,
    TransportTLSError,
)
from picsure.errors import (
    EmptyBodyError,
    PicSureConnectionError,
    PicSureError,
    PicSureQueryError,
    PicSureValidationError,
)

_QUERY_OPERATION = "the query"

_VALID_QUERY_TYPES: dict[str, str] = {
    "count": "COUNT",
    "participant": "DATAFRAME",
    "timestamp": "DATAFRAME_TIMESERIES",
    "cross_count": "CROSS_COUNT",
    "variant_count": "VARIANT_COUNT_FOR_QUERY",
    "variant_list": "VARIANT_LIST_FOR_QUERY",
    "vcf_excerpt": "VCF_EXCERPT",
    "aggregate_vcf_excerpt": "AGGREGATE_VCF_EXCERPT",
}

# Result types that ask the backend for variant-level output rather than a
# patient cohort.  BDC does not serve these yet; a 5xx (or an empty response)
# for one of them means "unsupported on this deployment", not a transient
# outage, so it is surfaced as a clear PicSureQueryError.
_VARIANT_RESULT_TYPES = frozenset(
    {
        "VARIANT_COUNT_FOR_QUERY",
        "VARIANT_LIST_FOR_QUERY",
        "VCF_EXCERPT",
        "AGGREGATE_VCF_EXCERPT",
    }
)

_DATAFRAME_RESULT_TYPES = frozenset({"DATAFRAME", "DATAFRAME_TIMESERIES"})

_STATUS_AVAILABLE = "AVAILABLE"
_STATUS_ERROR = "ERROR"

_INITIAL_POLL_INTERVAL_SECONDS = 1.0
_MAX_POLL_INTERVAL_SECONDS = 10.0

_PREVIEW_BYTES = 200

_COUNT_EXACT = re.compile(r"^(\d+)$")
_COUNT_NOISY = re.compile(r"^(\d+)\s*\u00b1\s*(\d+)$")
_COUNT_SUPPRESSED = re.compile(r"^<\s*(\d+)$")


def run_query(
    client: PicSureClient,
    query: Query | Clause | ClauseGroup,
    query_type: QueryType | str,
    *,
    backend: str,
) -> CountResult | dict[str, CountResult] | pd.DataFrame | list[str]:
    """Execute a query against PIC-SURE and return the result.

    Args:
        client: Authenticated HTTP client.
        query: A Query, Clause, or ClauseGroup built with
            buildQuery/buildClause/buildClauseGroup.
        query_type: A :class:`QueryType` member (e.g. ``QueryType.COUNT``)
            or one of the strings ``"count"``, ``"participant"``,
            ``"timestamp"``, ``"cross_count"``.
        backend: ``"auth"`` or ``"open"`` selects the HPDS backend by
            URL path. Both backends use their versioned v3 query route.

    Returns:
        - ``count``        → :class:`CountResult`
        - ``cross_count``  → ``dict[str, CountResult]`` keyed by concept path
        - ``participant``  → :class:`pandas.DataFrame`
        - ``timestamp``    → :class:`pandas.DataFrame`
        - ``variant_count`` → :class:`CountResult` (handles obfuscation)
        - ``variant_list``  → ``list[str]``
        - ``vcf_excerpt`` / ``aggregate_vcf_excerpt`` → :class:`pandas.DataFrame`

    Note:
        For ``participant`` and ``timestamp`` queries, a patient with multiple
        observations on the same concept appears as a single cell containing
        all values joined by ``\\t`` (tab). Use ``df[col].str.split("\\t")``
        to get a list-valued column when you need the individual observations.

    Raises:
        PicSureValidationError: If the query type is invalid.
        PicSureConnectionError: If the server is unreachable, or a
            ``participant`` or ``timestamp`` query is still unfinished
            when the client's request timeout passes (see
            :func:`run_async_query_to_file`).
        PicSureQueryError: If the server response cannot be parsed, or a
            ``participant`` or ``timestamp`` query is answered with a
            404, a query id that is not a UUID, a poll without a status
            field, or a terminal ``ERROR`` status.
    """
    resolved_type = _resolve_query_type(query_type)
    body = build_query_body(query, resolved_type)

    if resolved_type in _DATAFRAME_RESULT_TYPES:
        return _run_dataframe_query(client, backend, body)

    path = query_prefix(backend, v3=True) + "/query/sync"
    try:
        raw = client.post_raw(path, body=body)
    except TransportError as exc:
        _raise_query_error(exc, resolved_type)

    request = _summarize_request(body)
    if resolved_type == "COUNT":
        return _parse_count(raw, request=request)
    if resolved_type == "CROSS_COUNT":
        return _parse_cross_count(raw)
    if resolved_type == "VARIANT_COUNT_FOR_QUERY":
        return _parse_variant_count(raw, request=request)
    if resolved_type == "VARIANT_LIST_FOR_QUERY":
        return _parse_variant_list(raw)
    return _parse_vcf_excerpt(raw)


def _raise_query_error(exc: TransportError, resolved_type: str) -> NoReturn:
    """Re-raise a transport failure from a query as the public error.

    A 5xx on a variant result type is the backend signalling it does not
    serve that output yet (not a transient outage); surface it clearly.
    """
    if isinstance(exc, TransportServerError) and resolved_type in (
        _VARIANT_RESULT_TYPES
    ):
        raise PicSureQueryError(
            f"{_VARIANT_RESULT_UNSUPPORTED} (The server returned "
            f"HTTP {exc.status_code}.)"
        ) from exc
    raise translate_transport_error(exc, operation=_QUERY_OPERATION) from exc


def _run_dataframe_query(
    client: PicSureClient,
    backend: str,
    body: dict[str, object],
) -> pd.DataFrame:
    """Run a participant or timestamp query and parse its CSV from disk.

    Only the CSV cohort result types (``DATAFRAME`` and
    ``DATAFRAME_TIMESERIES``) come through here. The server serves them
    from a job rather than from ``/query/sync``, which refuses them, so
    the query goes through :func:`run_async_query_to_file`: submit,
    poll until the server reports the result available, then stream
    it to a temporary file. A participant download for a big cohort can
    run to hundreds of megabytes, while every other result type, VCF
    excerpts included, is a short body parsed in place. Holding the
    whole CSV in memory and then building a DataFrame from it put peak
    usage at the raw bytes plus the frame, enough to exhaust a notebook
    kernel, which presents as a dead kernel with no error rather than
    as a failure. Streaming to a temporary file drops the peak to the
    frame alone.

    Staging the result on disk introduces local failures a buffered
    path never had: no temporary directory, a full disk, an unreadable
    file. Those are translated to :class:`PicSureConnectionError`, as
    the export helpers do, so a caller catching ``PicSureError`` still
    sees them.
    """
    try:
        with _download_target() as target:
            run_async_query_to_file(
                client, backend, body, target, operation=_QUERY_OPERATION
            )
            return _parse_dataframe(target)
    except OSError as exc:
        raise PicSureConnectionError(
            f"Could not stage the query result on local disk: {exc}"
        ) from exc


def run_async_query_to_file(
    client: PicSureClient,
    backend: str,
    body: dict[str, object],
    target: Path,
    *,
    operation: str,
) -> None:
    """Run a query through the server's job flow and download its result.

    The server serves the file-sized result types (the CSV cohort types
    and the PFB export) from a job rather than from one request: the
    query is submitted, polled until the server reports it finished,
    and then collected. Every route is built by
    :mod:`picsure._services._hpds_paths` from ``backend`` and the id the
    server chose, which is checked to be a UUID and escaped into one
    path segment before it is interpolated.

    1. ``POST {prefix}/query`` submits ``body`` and answers with the
       query id.
    2. ``POST {prefix}/query/{id}/status`` is polled, first straight
       after the submit and then after sleeps of 1s, 2s, 4s, 8s and
       10s from there on, until the server reports ``AVAILABLE``. Any
       status other than ``AVAILABLE`` and ``ERROR`` means the job is
       still running. A poll that is throttled, answered with a 5xx or
       lost to a network failure (a timeout, a refused connection, a
       DNS miss) is sent again after the same sleep, a throttled one
       after the ``Retry-After`` the server gave when that is longer;
       a 401, 403, 404, a validation error, a rejected certificate or
       an answer carrying no body raises at once.
    3. ``POST {prefix}/query/{id}/result`` streams the bytes into
       ``target`` through :meth:`PicSureClient.post_raw_to_file`, which
       stages them at ``<target>.part`` and promotes the file only once
       the body is complete.

    The submit and the polls together, failed polls included, are
    bounded by :attr:`PicSureClient.timeout`, measured from just before
    the submit and read after each poll answers. The last sleep is
    clamped to what is left of it, so the final poll is sent at the
    budget rather than after it. That poll and the download that
    follows each carry the same value as their own per-request
    deadline, so the call as a whole can still run past it.

    Args:
        client: Authenticated HTTP client.
        backend: ``"auth"`` or ``"open"``.
        body: The request body, resent unchanged on every step. It
            carries the ``expectedResultType`` the server keys the job
            on.
        target: Where the result bytes are written. Its parent must
            exist.
        operation: Noun phrase naming what is being run, read as the
            object of every error message, e.g. ``"the query"`` or
            ``"the PFB export"``.

    Raises:
        PicSureQueryError: If any of the three routes answers 404, the
            submit carries no query id or one that is not a UUID, a
            poll carries no body or no status field, or the server
            finishes the job with status ``ERROR``.
        PicSureConnectionError: If the budget passes with the job still
            unfinished; when the last poll failed rather than answered,
            that failure decides the message and the class, so the
            narrower :class:`~picsure.errors.PicSureServerError` or
            :class:`~picsure.errors.PicSureConsentLookupError` is
            raised, and it is chained as the cause. Also if the submit
            or the download cannot reach the server, is rate limited or
            answers 5xx, the last arriving as
            :class:`~picsure.errors.PicSureServerError`. A rejected
            certificate on any step arrives as
            :class:`~picsure.errors.PicSureTLSError`.
        PicSureValidationError: If the server rejects a step with a 4xx
            other than 401, 403, 404 and 429.
        PicSureAuthError: If the server answers 401 or 403.
        OSError: If ``target`` cannot be written or promoted. The
            partial file is removed first.
    """
    started = time.monotonic()
    query_id = _submit_query(client, backend, body, operation=operation)
    _wait_until_available(
        client, backend, query_id, body, started=started, operation=operation
    )
    _download_result(client, backend, query_id, body, target, operation=operation)


def _submit_query(
    client: PicSureClient,
    backend: str,
    body: dict[str, object],
    *,
    operation: str,
) -> str:
    """Submit ``body`` and return the query id the server chose."""
    submit_path = query_submit_path(backend)
    try:
        payload = client.post_json(submit_path, body=body)
    except TransportError as exc:
        raise translate_transport_error(exc, operation=f"{operation} submit") from exc
    return query_id_from_submit_response(
        json_object(payload, path=submit_path), operation=operation
    )


def _wait_until_available(
    client: PicSureClient,
    backend: str,
    query_id: str,
    body: dict[str, object],
    *,
    started: float,
    operation: str,
) -> None:
    """Poll the status route until the job finishes or the budget passes.

    Args:
        client: Authenticated HTTP client.
        backend: ``"auth"`` or ``"open"``.
        query_id: The canonical query id.
        body: The request body, resent on every poll.
        started: The ``time.monotonic()`` reading the budget counts from.
        operation: Noun phrase for the error messages.

    Raises:
        PicSureQueryError: If a poll carries no body or no status field,
            or the server reports ``ERROR``.
        PicSureConnectionError: If :attr:`PicSureClient.timeout` seconds
            pass after ``started`` with the job still unfinished. When
            the last poll failed rather than answered, the subclass
            matching that failure is raised instead.
    """
    status_path = query_status_path(backend, query_id)
    budget = client.timeout
    interval = _INITIAL_POLL_INTERVAL_SECONDS
    failure: TransportError | None = None
    while True:
        try:
            status = _poll_status(client, status_path, body, operation=operation)
        except EmptyBodyError as exc:
            raise _bodiless_poll_error(exc, operation=operation) from exc
        except TransportError as exc:
            if not _is_transient(exc):
                raise translate_transport_error(
                    exc, operation=f"{operation} status check"
                ) from exc
            failure = exc
        else:
            failure = None
            if status == _STATUS_AVAILABLE:
                return
            if status == _STATUS_ERROR:
                raise PicSureQueryError(
                    f"The server reported that {operation} failed (query "
                    f"{query_id} status=ERROR) and gave no further detail."
                )
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0:
            raise _budget_exceeded(operation, query_id, budget, failure)
        time.sleep(min(_pause_after(failure, interval), remaining))
        interval = min(interval * 2, _MAX_POLL_INTERVAL_SECONDS)


def _is_transient(exc: TransportError) -> bool:
    """Whether a failed status poll is worth sending again.

    A throttled poll, a 5xx and a network failure (a timeout, a refused
    connection, a DNS miss) can all clear on their own. The structured
    consent-lookup 502 is included on purpose: it is a sibling class of
    the bare 5xx rather than a subclass, the job keeps running
    server-side while the gateway cannot resolve the caller's consents,
    and the failure is inside PIC-SURE rather than in the caller's
    token. A rejected certificate cannot clear on its own, and neither
    can a refusal by status, a 404 or a validation error, so those are
    not retried.
    """
    if isinstance(exc, TransportTLSError):
        return False
    return isinstance(
        exc,
        (
            TransportRateLimitError,
            TransportServerError,
            TransportConsentLookupError,
            TransportConnectionError,
        ),
    )


def _pause_after(failure: TransportError | None, interval: float) -> float:
    """How long to sleep before the next poll.

    A throttled poll waits what the server asked for, floored at the
    current interval so a ``Retry-After`` of zero cannot spin the loop
    and a negative one cannot reach ``time.sleep``; every other case, a
    failed poll included, waits the current interval.
    """
    if isinstance(failure, TransportRateLimitError) and failure.retry_after is not None:
        return max(float(failure.retry_after), interval)
    return interval


def _budget_exceeded(
    operation: str,
    query_id: str,
    budget: float,
    failure: TransportError | None,
) -> PicSureError:
    """Build the error for a job still unfinished when the budget passes.

    When the last poll failed rather than answered, that failure decides
    both the message and the class, so a caller catching
    :class:`~picsure.errors.PicSureServerError` or
    :class:`~picsure.errors.PicSureConsentLookupError` still catches
    what the same failure on a single request would have raised. Every
    class a retried poll failure can produce is a
    :class:`~picsure.errors.PicSureConnectionError` subclass, so a
    caller catching the wider class is unaffected either way. The
    operation, the query id and the budget are folded into the phrase
    the message templates read as their object, and the transport
    failure is chained as the cause.
    """
    waited = f"{operation} (query {query_id}) within its budget of {budget:g} seconds"
    if failure is None:
        return PicSureConnectionError(
            f"The server had not finished {waited}, and never reported the "
            f"result available. That budget is the session's request timeout, "
            f"set by picsure.connect(timeout=...)."
        )
    error = translate_transport_error(failure, operation=waited)
    error.__cause__ = failure
    return error


def _bodiless_poll_error(exc: EmptyBodyError, *, operation: str) -> PicSureQueryError:
    """Explain a status poll that answered with no body at all.

    A poll is only usable when it carries a ``QueryStatus``, so a
    bodiless answer ends the wait rather than counting as one more
    in-progress poll: a 2xx with no body is an answered but unreadable
    poll, the same protocol break as a body carrying no status field,
    and :func:`_extract_status` already raises for that. Any other
    status below 400 reaches here too, a ``302`` to an SSO login on an
    expired gateway session being the one a long wait invites, and it
    is named as the session problem it is rather than as a decoding
    failure. Either way the job may still be running server-side.

    Args:
        exc: The empty-body failure the transport raised.
        operation: Noun phrase naming what was being run.

    Returns:
        The public error to raise.
    """
    lead = (
        f"The server answered a status poll for {operation} with HTTP "
        f"{exc.status_code} and an empty body"
    )
    tail = "The query may still be running on the server."
    if bodiless_response_succeeded(exc):
        return PicSureQueryError(
            f"{lead}, where a query status was expected, so the wait could "
            f"not go on. {tail}"
        )
    return PicSureQueryError(
        f"{lead}, which usually means a redirect to a login page after the "
        f"gateway session expired. Reconnect and run this again. {tail}"
    )


def _poll_status(
    client: PicSureClient,
    status_path: str,
    body: dict[str, object],
    *,
    operation: str,
) -> str:
    """Send one status poll and return the status it reports.

    Raises:
        TransportError: Untranslated, so the caller can decide whether
            the failure is worth polling through.
        EmptyBodyError: If the answer carries no body, which the caller
            turns into a message that fits the status it arrived with.
        PicSureQueryError: If the answer carries no status field.
    """
    payload = client.post_json(status_path, body=body)
    return _extract_status(json_object(payload, path=status_path), operation=operation)


def _extract_status(response: dict[str, object], *, operation: str) -> str:
    """Pull the status string out of a ``QueryStatus`` response.

    PIC-SURE's ``QueryStatus`` has both a top-level ``status`` (the
    canonical ``PicSureStatus`` enum) and ``resourceStatus`` (the raw
    string from HPDS). They should agree in v3; prefer ``status``.

    Raises:
        PicSureQueryError: If neither field carries a non-empty string.
    """
    for field in ("status", "resourceStatus"):
        value = response.get(field)
        if isinstance(value, str) and value:
            return value.upper()
    raise PicSureQueryError(
        f"Server did not return a status field in the poll response for {operation}."
    )


def _download_result(
    client: PicSureClient,
    backend: str,
    query_id: str,
    body: dict[str, object],
    target: Path,
    *,
    operation: str,
) -> None:
    """Stream the finished result into ``target``.

    A transport failure is translated by status; an ``OSError`` from the
    staging file or the rename is left to the caller, which knows what
    the file is for.
    """
    result_path = query_result_path(backend, query_id)
    try:
        client.post_raw_to_file(result_path, target, body=body)
    except TransportError as exc:
        raise translate_transport_error(exc, operation=f"{operation} download") from exc


@contextmanager
def _download_target() -> Iterator[Path]:
    """Yield a path to stream a download into, removed on the way out.

    The enclosing directory is what gets cleaned up, so the ``.part``
    staging file :meth:`PicSureClient.post_raw_to_file` writes goes with
    it whether the download succeeded, failed part-way, or the parse
    afterwards raised.
    """
    with tempfile.TemporaryDirectory(prefix="picsure-query-") as directory:
        yield Path(directory) / "result.csv"


def build_query_body(
    query: Query | Clause | ClauseGroup,
    expected_result_type: str,
) -> dict[str, object]:
    """Assemble the ``/picsure/hpds/{auth,open}/v3/query`` request body.

    Normalizes the query into a phenotypic filter tree and a list of
    ``includeConcepts``; the tree becomes ``phenotypicClause`` and the
    concept paths become the top-level ``select`` array.

    Notes:
        No ``resourceUUID`` is sent: the gateway selects the HPDS backend
        by URL path (``/picsure/hpds/auth`` vs ``/picsure/hpds/open``), not
        by a resource-selection UUID in the body.

        ``authorizationFilters`` is intentionally omitted from the body.
        PSAMA populates it server-side from the user's token; sending a
        client-asserted list (especially with a long-term token) is
        treated as tampering and can be rejected with a 401.
    """
    filter_tree, select_paths, genomic = _split(query)
    phenotypic = filter_tree.to_query_json() if filter_tree is not None else None
    return {
        "query": {
            "select": select_paths,
            "phenotypicClause": phenotypic,
            "genomicFilters": [g.to_query_json() for g in genomic],
            "expectedResultType": expected_result_type,
            "picsureId": None,
            "id": None,
        },
    }


def _split(
    query: Query | Clause | ClauseGroup,
) -> tuple[Clause | ClauseGroup | None, list[str], tuple[GenomicFilter, ...]]:
    """Normalize a runnable query into (filter tree, select paths, genomic).

    Every concept path referenced in the filter tree is folded into the
    select paths, so a query's filter variables are returned as output
    columns without being repeated in ``includeConcepts``. Genomic filters
    do not contribute to ``select``.
    Explicit ``includeConcepts`` keep their position; filter-derived paths
    are appended in tree-traversal order; duplicates are dropped.
    """
    if isinstance(query, Query):
        filter_tree: Clause | ClauseGroup | None = query.phenotypicFilter
        select = list(query.includeConcepts)
        genomic: tuple[GenomicFilter, ...] = query.genomicFilters
    elif isinstance(query, (Clause, ClauseGroup)):
        filter_tree = query
        select = []
        genomic = ()
    else:
        raise PicSureValidationError(
            "Query must be a Clause, ClauseGroup, or Query. Use "
            "buildClause()/buildClauseGroup()/buildQuery() to construct one."
        )

    if filter_tree is not None:
        select.extend(filter_tree.concept_paths())
    return filter_tree, list(dict.fromkeys(select)), genomic


def _resolve_query_type(query_type: QueryType | str) -> str:
    valid = ", ".join(_VALID_QUERY_TYPES.keys())
    if isinstance(query_type, QueryType):
        key = query_type.value
    elif isinstance(query_type, str):
        key = query_type.lower().strip()
    else:
        raise PicSureValidationError(
            f"'{query_type}' is not a valid query type. Pass a QueryType "
            f"member or one of: {valid}."
        )
    if key not in _VALID_QUERY_TYPES:
        raise PicSureValidationError(
            f"'{query_type}' is not a valid query type. Pass a QueryType "
            f"member or one of: {valid}."
        )
    return _VALID_QUERY_TYPES[key]


def _parse_count_string(s: str) -> CountResult:
    """Parse a single PIC-SURE count string into a :class:`CountResult`.

    Recognises three shapes the server emits:

    - ``"42"``      — exact value
    - ``"11309 ±3"`` — noisy (additive margin)
    - ``"< 10"``    — suppressed (below threshold)

    Anything else raises :class:`PicSureQueryError` loudly rather than
    silently coercing.
    """
    text = s.strip()
    if m := _COUNT_EXACT.match(text):
        return CountResult(value=int(m.group(1)), margin=None, cap=None, raw=text)
    if m := _COUNT_NOISY.match(text):
        return CountResult(
            value=int(m.group(1)),
            margin=int(m.group(2)),
            cap=None,
            raw=text,
        )
    if m := _COUNT_SUPPRESSED.match(text):
        return CountResult(value=None, margin=None, cap=int(m.group(1)), raw=text)
    raise PicSureQueryError(
        f"Expected a count response (e.g. '42', '11309 \u00b13', '< 10'), "
        f"but got: '{text[:200]}'"
    )


def _decode_body(raw: bytes, description: str) -> str:
    """Decode a response body as UTF-8 inside the public error hierarchy.

    ``bytes.decode`` raises :class:`UnicodeDecodeError`, which is a
    ``ValueError`` and so escapes an ``except PicSureError`` a caller
    wrapped the query in. Every parser decodes through here instead, so an
    undecodable body reads the same whichever result type asked for it.

    Args:
        raw: The response body.
        description: What the body was expected to be, used as the
            subject of the error message, e.g. ``"a malformed VCF
            excerpt"``.

    Returns:
        The decoded text.

    Raises:
        PicSureQueryError: If the body is not valid UTF-8. The message
            quotes the leading bytes.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PicSureQueryError(
            f"Server returned {description}: {raw[:_PREVIEW_BYTES]!r}"
        ) from exc


def _parse_count(raw: bytes, *, request: _RequestSummary | None = None) -> CountResult:
    """Decode and parse a bytes count response.

    Args:
        raw: The response body.
        request: What the request carried, named in the empty-body message.

    Raises:
        PicSureQueryError: If the body is not valid UTF-8, is empty, or is
            not a count.
    """
    text = _decode_body(raw, "a malformed count response")
    if not text.strip():
        raise PicSureQueryError(_empty_count_message(request))
    return _parse_count_string(text)


def _empty_count_message(request: _RequestSummary | None) -> str:
    """Explain an empty body where a count was expected.

    The server answers with no body when it did not run the query. With
    filters set, the usual cause is a filter whose shape does not match
    its concept's type (a numeric ``min``/``max`` on a categorical concept,
    or ``categories`` on a continuous one). Without filters the only input
    left to check is the select paths.

    The parser is handed the response bytes alone, so the status is not
    known here and the message does not name one. It used to claim a 200,
    which any sub-400 answer with no body contradicted.
    """
    lead = (
        "The server returned an empty body where a count was expected, "
        f"which means the query was not run.{_sent(request)}"
    )
    if request is not None and not request.has_filters:
        return (
            f"{lead} With no filters set, check that each select path is a "
            "concept path this deployment serves. searchDictionary() finds "
            "the paths it knows."
        )
    return (
        f"{lead} The usual cause is a filter that could not be applied to the "
        "concept it names. Check that each filter's shape matches its "
        "concept's type: min/max applies to a continuous concept and "
        "categories to a categorical one. searchDictionary() reports a "
        "concept's type."
    )


@dataclass(frozen=True)
class _RequestSummary:
    """What a query request body carried, for use in error messages.

    Attributes:
        concepts: Concept paths named by phenotypic filters, in order.
        genomic_keys: Keys of the genomic filters, in order.
        select_paths: Concept paths requested as output columns.
    """

    concepts: tuple[str, ...] = ()
    genomic_keys: tuple[str, ...] = ()
    select_paths: tuple[str, ...] = ()

    @property
    def has_filters(self) -> bool:
        """Whether the request carried any phenotypic or genomic filter."""
        return bool(self.concepts or self.genomic_keys)

    def describe(self) -> str:
        """Render one sentence saying what the request carried."""
        parts = []
        if self.concepts:
            parts.append("phenotypic filters on " + _quoted(self.concepts))
        if self.genomic_keys:
            parts.append("genomic filter keys " + _quoted(self.genomic_keys))
        if parts:
            return "The request carried " + " and ".join(parts) + "."
        if self.select_paths:
            return (
                "The request carried no filters, only the select paths "
                + _quoted(self.select_paths)
                + "."
            )
        return "The request carried no filters and no select paths."


def _quoted(items: tuple[str, ...]) -> str:
    """Join ``items`` as a comma-separated list of single-quoted strings."""
    return ", ".join(f"'{item}'" for item in items)


def _sent(request: _RequestSummary | None) -> str:
    """Render the request summary as a trailing sentence, or nothing."""
    return f" {request.describe()}" if request is not None else ""


def _clause_concept_paths(clause: object) -> list[str]:
    """Collect ``conceptPath`` values from a serialized phenotypic clause tree."""
    if not isinstance(clause, dict):
        return []
    path = clause.get("conceptPath")
    if isinstance(path, str):
        return [path]
    children = clause.get("phenotypicClauses")
    if not isinstance(children, list):
        return []
    paths: list[str] = []
    for child in children:
        paths.extend(_clause_concept_paths(child))
    return paths


def _summarize_request(body: dict[str, object]) -> _RequestSummary | None:
    """Read the filters and select paths out of a request body.

    Returns ``None`` if the body is not shaped as expected, so a diagnostic
    message never depends on the body's structure.
    """
    query = body.get("query")
    if not isinstance(query, dict):
        return None
    concepts = _clause_concept_paths(query.get("phenotypicClause"))
    raw_genomic = query.get("genomicFilters")
    genomic_keys: list[str] = []
    if isinstance(raw_genomic, list):
        genomic_keys = [
            str(g["key"])
            for g in raw_genomic
            if isinstance(g, dict) and isinstance(g.get("key"), str)
        ]
    raw_select = query.get("select")
    select_paths: list[str] = []
    if isinstance(raw_select, list):
        select_paths = [path for path in raw_select if isinstance(path, str)]
    return _RequestSummary(
        concepts=tuple(dict.fromkeys(concepts)),
        genomic_keys=tuple(dict.fromkeys(genomic_keys)),
        select_paths=tuple(dict.fromkeys(select_paths)),
    )


def _non_negative(count: int, text: str) -> int:
    """Return ``count`` unless it is negative, which no PIC-SURE count is.

    Args:
        count: The integer the server sent.
        text: The response body, quoted in the error.

    Raises:
        PicSureQueryError: If ``count`` is below zero.
    """
    if count < 0:
        raise PicSureQueryError(
            f"Expected a non-negative count, but got {count} in: '{text[:200]}'"
        )
    return count


def _parse_cross_count(raw: bytes) -> dict[str, CountResult]:
    """Parse a CROSS_COUNT response into a mapping of concept path → count.

    The server returns a JSON object. Each value may be an exact integer
    (direct HPDS response, ``Map<String, Integer>``) or a count string
    (aggregate-obfuscated response, e.g. ``"42"``, ``"11309 \u00b13"``,
    or ``"< 10"``). Both are parsed into :class:`CountResult`.

    Malformed JSON, non-object top-level values, malformed count values,
    and negative counts all raise :class:`PicSureQueryError`.
    """
    text = _decode_body(raw, "a malformed cross-count response")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        preview = raw[:200]
        raise PicSureQueryError(
            f"Expected a cross-count JSON object, but got: {preview!r}"
        ) from exc
    if not isinstance(data, dict):
        raise PicSureQueryError(
            f"Expected a cross-count JSON object, got {type(data).__name__}"
        )
    result: dict[str, CountResult] = {}
    for path, v in data.items():
        key = str(path)
        # bool is an int subclass in Python; guard against True/False
        # masquerading as valid counts.
        if isinstance(v, int) and not isinstance(v, bool):
            result[key] = CountResult(
                value=_non_negative(v, text), margin=None, cap=None, raw=str(v)
            )
        else:
            result[key] = _parse_count_string(str(v))
    return result


def _parse_dataframe(source: Path) -> pd.DataFrame:
    """Parse a streamed CSV download into a DataFrame.

    Takes a path rather than the response bytes so pandas reads the file
    incrementally and the raw body is never held alongside the frame.
    An empty or whitespace-only body is a legitimate "no rows" answer,
    which pandas reports as ``EmptyDataError``; it becomes an empty
    DataFrame rather than a parse failure.
    """
    try:
        return pd.read_csv(source, encoding="utf-8")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise PicSureQueryError(
            f"Server returned a malformed CSV response: {_download_preview(source)!r}"
        ) from exc


def _download_preview(source: Path) -> bytes:
    """Return the leading bytes of a download, to quote in an error."""
    with source.open("rb") as handle:
        return handle.read(_PREVIEW_BYTES)


_QUERY_TYPE_NOT_ALLOWED = "query type not allowed"
_NO_VARIANTS_FOUND = "No Variants Found"
_NO_VARIANT_FILTERS = "No variant filters were supplied"
_VARIANT_RESULT_UNSUPPORTED = (
    "The variant result types (variant_count, variant_list, vcf_excerpt, "
    "aggregate_vcf_excerpt) are not available on this PIC-SURE deployment "
    "yet — genomic filters still work as a constraint on count / "
    "participant queries."
)


def _parse_variant_count(
    raw: bytes, *, request: _RequestSummary | None = None
) -> CountResult:
    """Parse a VARIANT_COUNT_FOR_QUERY response into a :class:`CountResult`.

    The server answers with a JSON object such as ``{"count": 1, "message":
    "Query ran successfully"}``, whose ``count`` is either a number or a count
    string. A bare count string is still accepted for deployments that send
    one. Either way the count is parsed with the same logic as patient
    counts, so an obfuscated response (``"11309 ±3"`` noisy or ``"< 10"``
    suppressed) is represented faithfully rather than raising.

    ``CountResult.raw`` keeps the whole response body, so the server's
    ``message`` is preserved without a field of its own.

    Args:
        raw: The response body.
        request: What the request carried, named in the empty-body and
            missing-filter messages.

    Raises:
        PicSureQueryError: If the body is empty, reports the result type as
            disallowed, says no variant filters were supplied, or carries no
            usable count.
    """
    text = _decode_body(raw, "a malformed variant-count response").strip()
    if not text:
        raise PicSureQueryError(_empty_variant_count_message(request))
    if _QUERY_TYPE_NOT_ALLOWED in text:
        raise PicSureQueryError(
            f"The server rejected the variant-count query: '{text[:200]}'. "
            "This result type may be disabled on this deployment."
        )
    payload = _variant_count_payload(text)
    if payload is None:
        return _parse_count_string(text)
    return _variant_count_from_payload(payload, text, request)


def _empty_variant_count_message(request: _RequestSummary | None) -> str:
    """Explain an empty body where a variant count was expected.

    A deployment that does not serve the variant result types answers them
    with an empty body, and so does one that serves them when a filter could
    not be applied, so the message names both causes.

    Like :func:`_empty_count_message`, this sees only the response bytes,
    so it states the empty body without claiming a status for it.
    """
    return (
        "The server returned an empty body where a variant count was "
        f"expected.{_sent(request)} Either the variant result types "
        "(variant_count, variant_list, vcf_excerpt, aggregate_vcf_excerpt) "
        "are not available on this PIC-SURE deployment, or a filter could not "
        "be applied to the concept it names. Check that each filter's shape "
        "matches its concept's type. Genomic filters still work as a "
        "constraint on count and participant queries."
    )


def _variant_count_payload(text: str) -> dict[str, object] | None:
    """Return the response as a JSON object, or ``None`` if it is not one.

    A bare count such as ``"42"`` is valid JSON but not an object, so it
    falls through to the count-string parser.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _variant_count_from_payload(
    payload: dict[str, object],
    text: str,
    request: _RequestSummary | None,
) -> CountResult:
    """Read the count out of a variant-count JSON object.

    ``raw`` is set to the whole body rather than just the count, so the
    server's ``message`` survives on the returned :class:`CountResult`.
    """
    message = payload.get("message")
    if isinstance(message, str) and _NO_VARIANT_FILTERS in message:
        raise PicSureQueryError(
            "A variant count needs at least one genomic filter, and the "
            f"server reports that none were supplied: '{message[:200]}'."
            f"{_sent(request)} Add a filter with buildGenomicFilter() and pass "
            "it to buildQuery(genomicFilters=...). A phenotypic filter alone "
            "cannot select variants."
        )

    count = payload.get("count")
    if isinstance(count, bool) or count is None:
        raise PicSureQueryError(
            "Expected a variant-count response with a 'count' field, but "
            f"got: '{text[:200]}'"
        )
    if isinstance(count, int):
        return CountResult(
            value=_non_negative(count, text), margin=None, cap=None, raw=text
        )
    if isinstance(count, str):
        return replace(_parse_count_string(count), raw=text)
    raise PicSureQueryError(
        "Expected a variant-count 'count' to be a number or a count string, "
        f"but got: '{text[:200]}'"
    )


def _parse_variant_list(raw: bytes) -> list[str]:
    """Parse a VARIANT_LIST_FOR_QUERY response into a list of variant specs.

    The server returns ``"[" + specs.join(", ") + "]"``. Each spec is itself
    six comma-separated fields
    (``chromosome,offset,ref,alt,gene,consequence``), so the specs must be
    split on the joiner's ``", "`` (comma-space) — splitting on a bare ``","``
    would shred each spec into its fields. Within a spec the commas have no
    trailing space, so ``", "`` only occurs between specs.
    """
    text = _decode_body(raw, "a malformed variant-list response").strip()
    if not text:
        raise PicSureQueryError(_VARIANT_RESULT_UNSUPPORTED)
    if _QUERY_TYPE_NOT_ALLOWED in text:
        raise PicSureQueryError(
            f"The server rejected the variant-list query: '{text[:200]}'. "
            "This result type may be disabled on this deployment."
        )
    if not (text.startswith("[") and text.endswith("]")):
        raise PicSureQueryError(
            "Expected a bracketed variant list like "
            "'[7,100000,A,T,CHD8,missense_variant, ...]', "
            f"but got: '{text[:200]}'"
        )
    inner = text[1:-1].strip()
    if not inner:
        return []
    return [tok.strip() for tok in inner.split(", ") if tok.strip()]


def _parse_vcf_excerpt(raw: bytes) -> pd.DataFrame:
    """Parse a (AGGREGATE_)VCF_EXCERPT tab-separated response into a DataFrame.

    Maps the ``"No Variants Found"`` sentinel to an empty DataFrame and
    raises on the ``"... query type not allowed"`` body. The column set is
    server-driven (info columns vary by deployment), so no fixed schema is
    assumed.
    """
    text = _decode_body(raw, "a malformed VCF excerpt")
    stripped = text.strip()
    if not stripped:
        # A served deployment signals "empty" with the "No Variants Found"
        # sentinel below; a truly empty body means the result type is not
        # available here.
        raise PicSureQueryError(_VARIANT_RESULT_UNSUPPORTED)
    if stripped.startswith(_NO_VARIANTS_FOUND):
        return pd.DataFrame()
    if _QUERY_TYPE_NOT_ALLOWED in stripped:
        raise PicSureQueryError(
            f"The server rejected the VCF-excerpt query: '{stripped[:200]}'. "
            "This result type may be disabled on this deployment."
        )
    try:
        return pd.read_csv(StringIO(text), sep="\t")
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise PicSureQueryError(
            f"Server returned a malformed VCF excerpt: {raw[:200]!r}"
        ) from exc
