from __future__ import annotations

from typing import TYPE_CHECKING

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure.errors import PicSureQueryError, PicSureValidationError

if TYPE_CHECKING:
    from picsure._models.query import Query


_FILTER_TYPE_TO_CLAUSE: dict[str, ClauseType] = {
    "FILTER": ClauseType.FILTER,
    "REQUIRED": ClauseType.REQUIRE,
    "ANY_RECORD_OF": ClauseType.ANYRECORD,
}


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
        raise PicSureQueryError(
            "Subquery node missing 'phenotypicClauses'."
        )
    raise PicSureQueryError(
        f"Unrecognized phenotypic clause shape: keys={sorted(node.keys())!r}"
    )


def _parse_leaf(node: dict[str, object]) -> Clause:
    raw_type = node.get("phenotypicFilterType")
    if not isinstance(raw_type, str) or raw_type not in _FILTER_TYPE_TO_CLAUSE:
        raise PicSureQueryError(
            f"Unknown phenotypicFilterType: {raw_type!r}. "
            f"Expected one of: {sorted(_FILTER_TYPE_TO_CLAUSE.keys())}."
        )
    concept_path = node.get("conceptPath")
    if not isinstance(concept_path, str):
        raise PicSureQueryError(
            "Leaf phenotypic clause missing 'conceptPath' string."
        )
    clause_type = _FILTER_TYPE_TO_CLAUSE[raw_type]
    categories: list[str] | None = None
    cmin: float | None = None
    cmax: float | None = None
    if clause_type == ClauseType.FILTER:
        values = node.get("values")
        if isinstance(values, list) and values:
            categories = [str(v) for v in values]
        raw_min = node.get("min")
        raw_max = node.get("max")
        if isinstance(raw_min, (int, float)) and not isinstance(raw_min, bool):
            cmin = float(raw_min)
        if isinstance(raw_max, (int, float)) and not isinstance(raw_max, bool):
            cmax = float(raw_max)
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
    children: list[Clause | ClauseGroup] = [
        _parse_phenotypic(c) for c in raw_children
    ]
    return ClauseGroup(
        clauses=children,
        operator=GroupOperator(raw_op),
    )


def _to_query(
    select_paths: list[str],
    phenotypic_node: object | None,
) -> Clause | ClauseGroup:
    """Combine the saved SELECT paths and phenotypic tree into a single Query."""
    selects: list[Clause | ClauseGroup] = [
        Clause(keys=[p], type=ClauseType.SELECT) for p in select_paths
    ]
    phenotypic: Clause | ClauseGroup | None = (
        _parse_phenotypic(phenotypic_node)
        if phenotypic_node is not None
        else None
    )

    if phenotypic is None and not selects:
        raise PicSureQueryError(
            "Server returned an empty saved query: no select paths and no "
            "phenotypic clause."
        )
    if phenotypic is None:
        if len(selects) == 1:
            return selects[0]
        return ClauseGroup(clauses=selects, operator=GroupOperator.AND)
    if not selects:
        return phenotypic
    return ClauseGroup(
        clauses=[*selects, phenotypic], operator=GroupOperator.AND
    )
