from __future__ import annotations

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.query import Query
from picsure.errors import PicSureValidationError


def removeSubQuery(target: Query, query: Query) -> Query:  # noqa: N802
    """Return a copy of ``query`` with every match of ``target`` removed.

    Matching is structural (frozen-dataclass equality): any nested
    ``Clause`` or ``ClauseGroup`` that ``==`` the target is dropped,
    along with all of its children. If a parent ``ClauseGroup`` is
    emptied by removals, the parent is dropped too.

    Raises:
        PicSureValidationError: if the whole query would be removed
            (nothing left), or if either argument is not a Query.
    """
    _check_is_query(target, "target")
    _check_is_query(query, "query")

    if query == target:
        raise PicSureValidationError(
            "removeSubQuery would remove the entire query; no clauses would remain."
        )

    pruned = _prune(query, target)
    if pruned is None:
        raise PicSureValidationError(
            "removeSubQuery would remove the entire query; no clauses would remain."
        )
    return pruned


def replaceClause(  # noqa: N802
    target: Query,
    query: Query,
    replacement: Query,
) -> Query:
    """Return a copy of ``query`` with every match of ``target`` swapped.

    Each structurally-equal occurrence of ``target`` is replaced by
    ``replacement``. Matching is structural (frozen-dataclass equality).

    Raises:
        PicSureValidationError: if any argument is not a Query.
    """
    _check_is_query(target, "target")
    _check_is_query(query, "query")
    _check_is_query(replacement, "replacement")

    return _replace(query, target, replacement)


def _check_is_query(value: object, name: str) -> None:
    if not isinstance(value, (Clause, ClauseGroup)):
        raise PicSureValidationError(
            f"`{name}` must be a Clause or ClauseGroup; got {type(value).__name__}."
        )


def _prune(node: Query, target: Query) -> Query | None:
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


def _replace(node: Query, target: Query, replacement: Query) -> Query:
    if node == target:
        return replacement
    if isinstance(node, Clause):
        return node
    new_children: list[Clause | ClauseGroup] = [
        _replace(c, target, replacement) for c in node.clauses
    ]
    return ClauseGroup(clauses=new_children, operator=node.operator)
