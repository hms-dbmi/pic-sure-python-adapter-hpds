from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.parse import quote
from uuid import UUID

from picsure._models.clause import (
    PHENOTYPIC_FILTER_TYPE_BY_WIRE_NAME,
    Clause,
    PhenotypicFilterType,
)
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.dictionary import coerce_float
from picsure._models.genomic_filter import GenomicFilter, is_variant_spec
from picsure._models.query import Query
from picsure._services._errors import translate_transport_error
from picsure._transport.errors import TransportError, TransportNotFoundError
from picsure.errors import PicSureQueryError, PicSureValidationError

_LOAD_OPERATION = "the saved-query load"

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
    categories: tuple[str, ...] | None = None
    cmin: float | None = None
    cmax: float | None = None
    if clause_type == PhenotypicFilterType.FILTER:
        values = node.get("values")
        if isinstance(values, list) and values:
            categories = tuple(str(v) for v in values)
        cmin = coerce_float(node.get("min"))
        cmax = coerce_float(node.get("max"))
    return Clause(
        keys=(concept_path,),
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
    children = tuple(_parse_phenotypic(c) for c in raw_children)
    return ClauseGroup(
        clauses=children,
        operator=GroupOperator(raw_op),
    )


def _parse_genomic_filters(raw: object) -> tuple[GenomicFilter, ...]:
    """Rebuild the saved ``genomicFilters`` array into GenomicFilter objects."""
    if not isinstance(raw, list):
        return ()
    filters: list[GenomicFilter] = []
    for item in raw:
        if not isinstance(item, dict):
            raise PicSureQueryError(
                f"Expected a genomic filter object, got {type(item).__name__}."
            )
        key = item.get("key")
        if not isinstance(key, str):
            raise PicSureQueryError("Genomic filter is missing a 'key' string.")
        if is_variant_spec(key):
            raise PicSureValidationError(
                f"The saved query uses a variant-spec (SNP) genomic filter "
                f"({key!r}), which this adapter does not support yet."
            )
        if item.get("min") is not None or item.get("max") is not None:
            raise PicSureValidationError(
                f"Genomic filter '{key}' uses a numeric range (min/max), which "
                "this adapter does not support — only categorical 'values' "
                "filters. The saved query was likely built outside the adapter."
            )
        raw_values = item.get("values")
        values: tuple[str, ...] | None = None
        if isinstance(raw_values, list) and raw_values:
            values = tuple(str(v) for v in raw_values)
        filters.append(GenomicFilter(key=key, values=values))
    return tuple(filters)


def _to_query(
    select_paths: list[str],
    phenotypic_node: object | None,
    genomic_filters: tuple[GenomicFilter, ...] = (),
) -> Query | Clause | ClauseGroup:
    """Combine the saved include paths, phenotypic tree, and genomic filters.

    Returns a bare ``Clause`` / ``ClauseGroup`` when the saved query has no
    ``select`` paths and no genomic filters, or a :class:`Query` wrapping the
    filter tree (possibly ``None``) plus the include concepts / genomic
    filters otherwise.
    """
    phenotypic: Clause | ClauseGroup | None = (
        _parse_phenotypic(phenotypic_node) if phenotypic_node is not None else None
    )

    if phenotypic is None and not select_paths and not genomic_filters:
        raise PicSureQueryError(
            "Server returned an empty saved query: no select paths, no "
            "phenotypic clause, and no genomic filters."
        )
    if not select_paths and not genomic_filters:
        return phenotypic  # type: ignore[return-value]  # guarded non-None above
    return Query(
        phenotypicFilter=phenotypic,
        includeConcepts=tuple(select_paths),
        genomicFilters=genomic_filters,
    )


# Query metadata is served under the versioned (/v3) query routes -- the
# non-versioned route 404s on the current gateway. The {backend} segment is
# required for routing but the read does not depend on which backend is named.
_HPDS_QUERY_METADATA_PATH = "/picsure/hpds/{backend}/v3/query/{query_id}/metadata"


def _validate_query_id(query_id: str) -> str:
    """Normalize a saved-query identifier to canonical UUID form.

    The controller binds this path segment as ``@PathVariable UUID``, so
    anything that is not a UUID cannot succeed server-side and is worth
    rejecting before the request goes out.

    Args:
        query_id: Caller-supplied identifier.

    Returns:
        The canonical lower-case hyphenated UUID string.

    Raises:
        PicSureValidationError: If ``query_id`` is not a UUID.
    """
    try:
        return str(UUID(query_id.strip()))
    except (ValueError, AttributeError, TypeError) as exc:
        raise PicSureValidationError(
            f"{query_id!r} is not a valid query ID. A PIC-SURE query ID is a "
            "UUID, for example '3fa85f64-5717-4562-b3fc-2c963f66afa6'."
        ) from exc


def load_query(
    client: PicSureClient,
    query_id: str,
    *,
    backend: str,
) -> Query | Clause | ClauseGroup:
    """Load a previously-saved query by ID and rebuild it as a Query.

    Reads ``/picsure/hpds/{backend}/v3/query/{id}/metadata``.  The read
    itself does not depend on HPDS -- the query-service returns the stored
    query row -- but only the versioned route is mapped on the current
    gateway, so ``/v3`` is used for every session.

    Args:
        client: Authenticated HTTP client.
        query_id: The UUID string of a previous query.  Validated and
            normalized to canonical form before the request is sent.
        backend: ``"auth"`` or ``"open"`` — the HPDS backend segment for
            the metadata route (does not affect the metadata read itself).

    Returns:
        A :class:`Query` when the saved row carries output concepts or
        genomic filters, otherwise the bare :class:`Clause` or
        :class:`ClauseGroup` it reduces to.  Any of the three can be
        passed directly to :meth:`Session.runQuery`,
        :meth:`Session.exportAsPFB`, or composed with :func:`buildQuery`.

    Raises:
        PicSureValidationError: If the ID is blank or not a UUID, the
            query was not found, or the saved query uses features this
            adapter cannot yet represent (NOT clauses).
        PicSureAuthenticationError: On 401.
        PicSureAuthorizationError: On 403.
        PicSureConnectionError: On network failures or 5xx.
        PicSureQueryError: If the response shape is malformed.
    """
    if not query_id or not query_id.strip():
        raise PicSureValidationError(
            "A non-empty query ID is required to load a saved query."
        )
    normalized_id = _validate_query_id(query_id)
    path = _HPDS_QUERY_METADATA_PATH.format(
        backend=backend, query_id=quote(normalized_id, safe="")
    )

    try:
        response = client.get_json(path)
    except TransportNotFoundError as exc:
        raise PicSureValidationError(
            f"No saved query found with ID '{normalized_id}' (HTTP {exc.status_code})."
        ) from exc
    except TransportError as exc:
        raise translate_transport_error(exc, operation=_LOAD_OPERATION) from exc

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
    genomic_filters = _parse_genomic_filters(inner.get("genomicFilters"))
    raw_select = inner.get("select")
    select_paths: list[str] = (
        [str(p) for p in raw_select] if isinstance(raw_select, list) else []
    )
    phenotypic_node = inner.get("phenotypicClause")
    return _to_query(select_paths, phenotypic_node, genomic_filters)
