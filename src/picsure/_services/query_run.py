from __future__ import annotations

import io

import pandas as pd

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup
from picsure._models.query import Query
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import (
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

_PICSURE_QUERY_SYNC_PATH = "/picsure/v3/query/sync"

_VALID_QUERY_TYPES: dict[str, str] = {
    "count": "COUNT",
    "participant": "DATAFRAME",
    "timestamp": "DATAFRAME_TIMESERIES",
    "cross_count": "CROSS_COUNT",
}


def run_query(
    client: PicSureClient,
    resource_uuid: str,
    query: Query,
    query_type: str,
) -> int | pd.DataFrame:
    """Execute a query against PIC-SURE and return the result.

    Args:
        client: Authenticated HTTP client.
        resource_uuid: The resource to query.
        query: A Clause or ClauseGroup built with createClause/buildClauseGroup.
        query_type: One of "count", "participant", "timestamp", or "cross_count".

    Returns:
        An integer for count queries, or a DataFrame for data queries.

    Raises:
        PicSureValidationError: If the query type is invalid.
        PicSureConnectionError: If the server is unreachable.
        PicSureQueryError: If the server response cannot be parsed.
    """
    resolved_type = _resolve_query_type(query_type)
    body = build_query_body(query, resource_uuid, resolved_type)

    try:
        raw = client.post_raw(_PICSURE_QUERY_SYNC_PATH, body=body)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not execute query. The server may be temporarily unavailable."
        ) from exc

    if resolved_type == "COUNT":
        return _parse_count(raw)
    return _parse_dataframe(raw)


def build_query_body(
    query: Query,
    resource_uuid: str,
    expected_result_type: str,
) -> dict[str, object]:
    """Assemble the v3 ``/picsure/v3/query/sync`` request body.

    Splits any SELECT clauses out of the query tree to the top-level
    ``select`` list; the rest becomes ``phenotypicClause``.

    Notes:
        ``authorizationFilters`` is intentionally omitted from the body.
        PSAMA populates it server-side from the user's token; sending a
        client-asserted list (especially with a long-term token) is
        treated as tampering and can be rejected with a 401.
    """
    select_paths = query.select_paths()
    phenotypic = _phenotypic_clause(query)
    return {
        "query": {
            "select": select_paths,
            "phenotypicClause": phenotypic,
            "genomicFilters": [],
            "expectedResultType": expected_result_type,
            "picsureId": None,
            "id": None,
        },
        "resourceUUID": resource_uuid,
    }


def _phenotypic_clause(query: Query) -> dict[str, object] | None:
    if isinstance(query, Clause):
        if query.type == ClauseType.SELECT:
            return None
        return query.to_query_json()
    if not isinstance(query, ClauseGroup):
        raise PicSureValidationError(
            "Query must be a Clause or ClauseGroup. "
            "Use createClause() or buildClauseGroup() to construct one."
        )
    if not query.has_phenotypic():
        return None
    return query.to_query_json()


def _resolve_query_type(query_type: str) -> str:
    key = query_type.lower().strip()
    if key not in _VALID_QUERY_TYPES:
        valid = ", ".join(_VALID_QUERY_TYPES.keys())
        raise PicSureValidationError(
            f"'{query_type}' is not a valid query type. Valid types: {valid}."
        )
    return _VALID_QUERY_TYPES[key]


def _parse_count(raw: bytes) -> int:
    text = raw.decode("utf-8").strip()
    # Open-access backends may obfuscate small counts:
    #   "11309 ±3"  — central value with a margin; keep the center.
    #   "< 10"      — below-threshold cap; return the cap as a conservative
    #                 upper bound (true value is anywhere in [0, cap)).
    if "\u00b1" in text:
        text = text.split("\u00b1", 1)[0].strip()
    if text.startswith("<"):
        text = text[1:].strip()
    try:
        return int(text)
    except ValueError as exc:
        raise PicSureQueryError(
            f"Expected a count (integer) from the server, but got: '{text[:200]}'"
        ) from exc


def _parse_dataframe(raw: bytes) -> pd.DataFrame:
    text = raw.decode("utf-8")
    if not text.strip():
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(text))
