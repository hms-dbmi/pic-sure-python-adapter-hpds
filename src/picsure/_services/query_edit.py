from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace as dataclass_replace
from typing import TypeAlias

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.query import Query
from picsure.errors import PicSureValidationError

# Re-attaches the result of an edit to its original container shape (identity
# for a bare filter, or back into a Query preserving includeConcepts).
_Rewrap: TypeAlias = Callable[[Clause | ClauseGroup], "Query | Clause | ClauseGroup"]


def removeSubQuery(  # noqa: N802
    query: Query | Clause | ClauseGroup,
    target: Clause | ClauseGroup,
) -> Query | Clause | ClauseGroup:
    """Return a copy of ``query`` with every match of ``target`` removed.

    Matching is structural (frozen-dataclass equality): any nested
    ``Clause`` or ``ClauseGroup`` that ``==`` the target is dropped,
    along with all of its children. If a parent ``ClauseGroup`` is
    emptied by removals, the parent is dropped too.

    When ``query`` is a :class:`Query`, the edit applies to its
    ``phenotypicFilter`` tree and the ``includeConcepts`` are preserved.

    Raises:
        PicSureValidationError: if the whole filter would be removed
            (nothing left), if ``target`` is not a Clause/ClauseGroup, or
            if ``query`` is an include-only Query (no filter to edit).
    """
    filter_tree, rewrap = _unwrap(query)
    _check_is_filter(target, "target")

    if filter_tree == target:
        raise PicSureValidationError(
            "removeSubQuery would remove the entire query; no clauses would remain."
        )

    pruned = _prune(filter_tree, target)
    if pruned is None:
        raise PicSureValidationError(
            "removeSubQuery would remove the entire query; no clauses would remain."
        )
    return rewrap(pruned)


def replaceClause(  # noqa: N802
    query: Query | Clause | ClauseGroup,
    target: Clause | ClauseGroup,
    replacement: Clause | ClauseGroup,
) -> Query | Clause | ClauseGroup:
    """Return a copy of ``query`` with every match of ``target`` swapped.

    Each structurally-equal occurrence of ``target`` is replaced by
    ``replacement``. Matching is structural (frozen-dataclass equality).

    When ``query`` is a :class:`Query`, the edit applies to its
    ``phenotypicFilter`` tree and the ``includeConcepts`` are preserved.

    Raises:
        PicSureValidationError: if ``target`` / ``replacement`` are not
            Clause/ClauseGroup, or if ``query`` is an include-only Query
            (no filter to edit).
    """
    filter_tree, rewrap = _unwrap(query)
    _check_is_filter(target, "target")
    _check_is_filter(replacement, "replacement")

    return rewrap(_replace(filter_tree, target, replacement))


def _unwrap(
    query: Query | Clause | ClauseGroup,
) -> tuple[Clause | ClauseGroup, _Rewrap]:
    """Return the editable filter tree and a function to re-wrap the result.

    For a bare ``Clause`` / ``ClauseGroup`` the re-wrap is the identity. For a
    ``Query`` it re-attaches the original ``includeConcepts``. An include-only
    ``Query`` (``phenotypicFilter is None``) has no editable tree and raises.
    """
    if isinstance(query, Query):
        if query.phenotypicFilter is None:
            raise PicSureValidationError(
                "This query has no phenotypic filter to edit (it only selects "
                "output concepts). Edit includeConcepts via buildQuery() instead."
            )
        original = query

        def rewrap(tree: Clause | ClauseGroup) -> Query:
            return dataclass_replace(original, phenotypicFilter=tree)

        return query.phenotypicFilter, rewrap
    if isinstance(query, (Clause, ClauseGroup)):
        return query, lambda tree: tree
    raise PicSureValidationError(
        f"`query` must be a Clause, ClauseGroup, or Query; got {type(query).__name__}."
    )


def _check_is_filter(value: object, name: str) -> None:
    if not isinstance(value, (Clause, ClauseGroup)):
        raise PicSureValidationError(
            f"`{name}` must be a Clause or ClauseGroup; got {type(value).__name__}."
        )


def _prune(
    node: Clause | ClauseGroup, target: Clause | ClauseGroup
) -> Clause | ClauseGroup | None:
    """Return ``node`` with all matches of ``target`` removed, or ``None``
    if removal empties the node entirely."""
    if node == target:
        return None
    if isinstance(node, Clause):
        return node
    kept: list[Clause | ClauseGroup] = []
    for child in node.clauses:
        pruned = _prune(child, target)
        if pruned is not None:
            kept.append(pruned)
    if not kept:
        return None
    return ClauseGroup(clauses=kept, operator=node.operator)


def _replace(
    node: Clause | ClauseGroup,
    target: Clause | ClauseGroup,
    replacement: Clause | ClauseGroup,
) -> Clause | ClauseGroup:
    if node == target:
        return replacement
    if isinstance(node, Clause):
        return node
    new_children: list[Clause | ClauseGroup] = [
        _replace(c, target, replacement) for c in node.clauses
    ]
    return ClauseGroup(clauses=new_children, operator=node.operator)
