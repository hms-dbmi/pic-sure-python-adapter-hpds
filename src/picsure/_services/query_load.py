from __future__ import annotations

import json
from typing import TYPE_CHECKING

from picsure._models.clause import (
    PHENOTYPIC_FILTER_TYPE_BY_WIRE_NAME,
    Clause,
    PhenotypicFilterType,
)
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.dictionary import coerce_float
from picsure._models.query import Query
from picsure._services._errors import rate_limit_message
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportValidationError,
)
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

if TYPE_CHECKING:
    from picsure._transport.client import PicSureClient


def _parse_phenotypic(node: object) -> Clause | ClauseGroup:
    """Rebuild a v3 ``PhenotypicClause`` JSON node into Clause/ClauseGroup.

    Raises:
        PicSureValidationError: If any node has ``not: true``.  This
            adapter does not yet model NOT clauses; rather than silently
            drop the negation, fail loud so the caller knows the loaded
            query cannot be faithfully represented.
        PicSureQueryError: If the node shape is unrecognized or required
            fields are missing.
    """
    if not isinstance(node, dict):
        raise PicSureQueryError(
            f"Expected a phenotypic clause object, got {type(node).__name__}"
        )

    if node.get("not") is True:
        raise PicSureValidationError(
            "This adapter cannot yet represent NOT clauses; the saved "
            "query was likely built with the UI."
        )

    if "phenotypicFilterType" in node:
        return _parse_leaf(node)
    if "operator" in node and "phenotypicClauses" in node:
        return _parse_subquery(node)
    if "operator" in node:
        raise PicSureQueryError("Subquery node missing 'phenotypicClauses'.")
    raise PicSureQueryError(
        f"Unrecognized phenotypic clause shape: keys={sorted(node.keys())!r}"
    )


def _parse_leaf(node: dict[str, object]) -> Clause:
    raw_type = node.get("phenotypicFilterType")
    if (
        not isinstance(raw_type, str)
        or raw_type not in PHENOTYPIC_FILTER_TYPE_BY_WIRE_NAME
    ):
        raise PicSureQueryError(
            f"Unknown phenotypicFilterType: {raw_type!r}. "
            f"Expected one of: {sorted(PHENOTYPIC_FILTER_TYPE_BY_WIRE_NAME.keys())}."
        )
    concept_path = node.get("conceptPath")
    if not isinstance(concept_path, str):
        raise PicSureQueryError("Leaf phenotypic clause missing 'conceptPath' string.")
    clause_type = PHENOTYPIC_FILTER_TYPE_BY_WIRE_NAME[raw_type]
    categories: list[str] | None = None
    cmin: float | None = None
    cmax: float | None = None
    if clause_type == PhenotypicFilterType.FILTER:
        values = node.get("values")
        if isinstance(values, list) and values:
            categories = [str(v) for v in values]
        cmin = coerce_float(node.get("min"))
        cmax = coerce_float(node.get("max"))
    return Clause(
        keys=[concept_path],
        type=clause_type,
        categories=categories,
        min=cmin,
        max=cmax,
    )


def _parse_subquery(node: dict[str, object]) -> ClauseGroup:
    raw_op = node.get("operator")
    if raw_op not in {"AND", "OR"}:
        raise PicSureQueryError(
            f"Unknown subquery operator: {raw_op!r}. Expected 'AND' or 'OR'."
        )
    raw_children = node.get("phenotypicClauses")
    if not isinstance(raw_children, list) or not raw_children:
        raise PicSureQueryError(
            "Subquery 'phenotypicClauses' must be a non-empty list."
        )
    children: list[Clause | ClauseGroup] = [_parse_phenotypic(c) for c in raw_children]
    return ClauseGroup(
        clauses=children,
        operator=GroupOperator(raw_op),
    )


def _to_query(
    select_paths: list[str],
    phenotypic_node: object | None,
) -> Query | Clause | ClauseGroup:
    """Combine the saved include-concept paths and phenotypic tree.

    Returns a bare ``Clause`` / ``ClauseGroup`` when the saved query has no
    ``select`` paths, or a :class:`Query` wrapping the filter tree (possibly
    ``None``) plus the include concepts otherwise.
    """
    phenotypic: Clause | ClauseGroup | None = (
        _parse_phenotypic(phenotypic_node) if phenotypic_node is not None else None
    )

    if phenotypic is None and not select_paths:
        raise PicSureQueryError(
            "Server returned an empty saved query: no select paths and no "
            "phenotypic clause."
        )
    if not select_paths:
        return phenotypic  # type: ignore[return-value]  # guarded non-None above
    return Query(phenotypicFilter=phenotypic, includeConcepts=tuple(select_paths))


# Always use the legacy /picsure/query/{id}/metadata path.  The v3
# /picsure/v3/query/{id}/metadata endpoint has a known issue on BDC, so
# we pin reads to legacy regardless of how the session was connected.
_PICSURE_QUERY_METADATA_PATH = "/picsure/query/{query_id}/metadata"


def load_query(
    client: PicSureClient,
    query_id: str,
) -> Query | Clause | ClauseGroup:
    """Load a previously-saved query by ID and rebuild it as a Query.

    Always uses ``/picsure/query/{id}/metadata`` (legacy) — the v3
    metadata endpoint is currently broken on BDC, so we read via legacy
    for every deployment.

    Args:
        client: Authenticated HTTP client.
        query_id: The UUID string of a previous query.

    Returns:
        A :class:`Clause` or :class:`ClauseGroup` that can be passed
        directly to :meth:`Session.runQuery`, :meth:`Session.exportAsPFB`,
        or composed with :func:`buildQuery`.

    Raises:
        PicSureValidationError: If the ID is blank, the query was not
            found, or the saved query uses features this adapter cannot
            yet represent (NOT clauses, genomic filters).
        PicSureAuthError: On 401 / 403.
        PicSureConnectionError: On network failures or 5xx.
        PicSureQueryError: If the response shape is malformed.
    """
    if not query_id or not query_id.strip():
        raise PicSureValidationError(
            "A non-empty query ID is required to load a saved query."
        )
    path = _PICSURE_QUERY_METADATA_PATH.format(query_id=query_id.strip())

    try:
        response = client.get_json(path)
    except TransportNotFoundError as exc:
        raise PicSureValidationError(
            f"No saved query found with ID '{query_id}' (HTTP {exc.status_code})."
        ) from exc
    except TransportAuthenticationError as exc:
        raise PicSureAuthError(
            f"Authentication failed loading saved query "
            f"(HTTP {exc.status_code}): {exc.body[:200]}"
        ) from exc
    except TransportValidationError as exc:
        raise PicSureValidationError(
            f"Server rejected the load-query request "
            f"(HTTP {exc.status_code}): {exc.body[:200]}"
        ) from exc
    except TransportRateLimitError as exc:
        raise PicSureConnectionError(rate_limit_message(exc)) from exc
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not load the saved query. The server may be temporarily unavailable."
        ) from exc

    return _build_query_from_response(response)


def _build_query_from_response(response: object) -> Query | Clause | ClauseGroup:
    if not isinstance(response, dict):
        raise PicSureQueryError(
            f"Expected a JSON object from the metadata endpoint, got "
            f"{type(response).__name__}."
        )
    metadata = response.get("resultMetadata")
    if not isinstance(metadata, dict):
        raise PicSureQueryError("Metadata response is missing 'resultMetadata' object.")
    query_json = metadata.get("queryJson")
    if not isinstance(query_json, dict):
        raise PicSureQueryError(
            "Metadata response is missing 'resultMetadata.queryJson' object."
        )
    inner = query_json.get("query")
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except json.JSONDecodeError as exc:
            raise PicSureQueryError(
                "Metadata response 'resultMetadata.queryJson.query' was a "
                f"string but could not be decoded as JSON: {inner[:200]!r}"
            ) from exc
    if not isinstance(inner, dict):
        raise PicSureQueryError(
            "Metadata response is missing 'resultMetadata.queryJson.query' object."
        )
    genomic = inner.get("genomicFilters")
    if isinstance(genomic, list) and genomic:
        raise PicSureValidationError(
            "This adapter cannot yet represent genomic filters; the saved "
            "query was likely built with the UI."
        )
    raw_select = inner.get("select")
    select_paths: list[str] = (
        [str(p) for p in raw_select] if isinstance(raw_select, list) else []
    )
    phenotypic_node = inner.get("phenotypicClause")
    return _to_query(select_paths, phenotypic_node)
