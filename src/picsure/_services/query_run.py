from __future__ import annotations

import io

import pandas as pd

from picsure._models.query import Query
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import (
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

_PICSURE_QUERY_SYNC_PATH = "/picsure/query/sync"

_VALID_QUERY_TYPES: dict[str, str] = {
    "count": "COUNT",
    "participant": "DATAFRAME",
    "timestamp": "DATAFRAME_TIMESERIES",
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
        query_type: One of "count", "participant", or "timestamp".

    Returns:
        An integer for count queries, or a DataFrame for data queries.

    Raises:
        PicSureValidationError: If the query type is invalid.
        PicSureConnectionError: If the server is unreachable.
        PicSureQueryError: If the server response cannot be parsed.
    """
    resolved_type = _resolve_query_type(query_type)

    body: dict[str, object] = {
        "resourceUUID": resource_uuid,
        "query": query.to_query_json(),
        "expectedResultType": resolved_type,
    }

    try:
        raw = client.post_raw(_PICSURE_QUERY_SYNC_PATH, body=body)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not execute query. The server may be temporarily unavailable."
        ) from exc

    if resolved_type == "COUNT":
        return _parse_count(raw)
    return _parse_dataframe(raw)


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
