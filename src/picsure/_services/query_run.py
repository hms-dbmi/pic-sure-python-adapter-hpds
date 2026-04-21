from __future__ import annotations

import io
import json
import re

import pandas as pd

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup
from picsure._models.count_result import CountResult
from picsure._models.query import Query
from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportValidationError,
)
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

_COUNT_EXACT = re.compile(r"^(\d+)$")
_COUNT_NOISY = re.compile(r"^(\d+)\s*\u00b1\s*(\d+)$")
_COUNT_SUPPRESSED = re.compile(r"^<\s*(\d+)$")


def run_query(
    client: PicSureClient,
    resource_uuid: str,
    query: Query,
    query_type: str,
) -> CountResult | dict[str, CountResult] | pd.DataFrame:
    """Execute a query against PIC-SURE and return the result.

    Args:
        client: Authenticated HTTP client.
        resource_uuid: The resource to query.
        query: A Clause or ClauseGroup built with createClause/buildClauseGroup.
        query_type: One of "count", "participant", "timestamp", or "cross_count".

    Returns:
        - ``count``        → :class:`CountResult`
        - ``cross_count``  → ``dict[str, CountResult]`` keyed by concept path
        - ``participant``  → :class:`pandas.DataFrame`
        - ``timestamp``    → :class:`pandas.DataFrame`

    Note:
        For ``participant`` and ``timestamp`` queries, a patient with multiple
        observations on the same concept appears as a single cell containing
        all values joined by ``\\t`` (tab). Use ``df[col].str.split("\\t")``
        to get a list-valued column when you need the individual observations.

    Raises:
        PicSureValidationError: If the query type is invalid.
        PicSureConnectionError: If the server is unreachable.
        PicSureQueryError: If the server response cannot be parsed.
    """
    resolved_type = _resolve_query_type(query_type)
    body = build_query_body(query, resource_uuid, resolved_type)

    try:
        raw = client.post_raw(_PICSURE_QUERY_SYNC_PATH, body=body)
    except TransportValidationError as exc:
        raise PicSureValidationError(
            f"Server rejected the query (HTTP {exc.status_code}): {exc.body[:200]}"
        ) from exc
    except TransportNotFoundError as exc:
        raise PicSureQueryError(
            f"Query endpoint not found (HTTP {exc.status_code}): {exc.body[:200]}"
        ) from exc
    except TransportRateLimitError as exc:
        if exc.retry_after is not None:
            msg = f"Rate limited; server said retry after {exc.retry_after} seconds."
        else:
            msg = "Rate limited. Please wait and try again."
        raise PicSureConnectionError(msg) from exc
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not execute query. The server may be temporarily unavailable."
        ) from exc

    if resolved_type == "COUNT":
        return _parse_count(raw)
    if resolved_type == "CROSS_COUNT":
        return _parse_cross_count(raw)
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
    if not isinstance(query, (Clause, ClauseGroup)):
        raise PicSureValidationError(
            "Query must be a Clause or ClauseGroup. "
            "Use createClause() or buildClauseGroup() to construct one."
        )
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


def _parse_count(raw: bytes) -> CountResult:
    """Decode and parse a bytes count response."""
    return _parse_count_string(raw.decode("utf-8"))


def _parse_cross_count(raw: bytes) -> dict[str, CountResult]:
    """Parse a CROSS_COUNT response into a mapping of concept path → count.

    The server returns a JSON object. Each value may be an exact integer
    (direct HPDS response, ``Map<String, Integer>``) or a count string
    (aggregate-obfuscated response, e.g. ``"42"``, ``"11309 \u00b13"``,
    or ``"< 10"``). Both are parsed into :class:`CountResult`.

    Malformed JSON, non-object top-level values, and malformed count
    values all raise :class:`PicSureQueryError`.
    """
    try:
        data = json.loads(raw.decode("utf-8"))
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
            result[key] = CountResult(value=v, margin=None, cap=None, raw=str(v))
        else:
            result[key] = _parse_count_string(str(v))
    return result


def _parse_dataframe(raw: bytes) -> pd.DataFrame:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        byte_preview = raw[:200]
        raise PicSureQueryError(
            f"Server returned a malformed CSV response: {byte_preview!r}"
        ) from exc
    if not text.strip():
        return pd.DataFrame()
    try:
        return pd.read_csv(io.StringIO(text))
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        text_preview = text[:200]
        raise PicSureQueryError(
            f"Server returned a malformed CSV response: {text_preview!r}"
        ) from exc
