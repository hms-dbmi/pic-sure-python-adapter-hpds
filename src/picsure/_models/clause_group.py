from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from picsure._models.clause import Clause, ClauseType


class GroupOperator(Enum):
    """Logical operator for combining clauses in a group.

    - ``AND`` — all clauses must match
    - ``OR`` — at least one clause must match
    """

    AND = "AND"
    OR = "OR"


@dataclass(frozen=True)
class ClauseGroup:
    """A group of clauses combined with AND or OR.

    Created by ``picsure.buildClauseGroup()``. Can contain both
    ``Clause`` and nested ``ClauseGroup`` objects for arbitrarily
    deep nesting.

    **Wire format.** :meth:`to_query_json` emits a v3
    ``PhenotypicSubquery`` (``operator`` / ``phenotypicClauses`` /
    ``not``) per the ``/picsure/v3/query/sync`` contract. The previous
    wire format is not supported.
    """

    clauses: list[Clause | ClauseGroup]
    operator: GroupOperator

    def to_query_json(self) -> dict[str, object]:
        """Serialize this group as a v3 ``PhenotypicSubquery``.

        SELECT clauses are stripped out — they are lifted to the
        top-level ``select`` array by the query builder. If every
        child is a SELECT, the resulting ``phenotypicClauses`` list
        is empty; callers should check this via :meth:`has_phenotypic`
        and pass ``None`` for ``phenotypicClause`` on empty groups.
        """
        pheno_children: list[dict[str, object]] = []
        for child in self.clauses:
            if isinstance(child, Clause) and child.type == ClauseType.SELECT:
                continue
            pheno_children.append(child.to_query_json())
        return {
            "operator": self.operator.value,
            "phenotypicClauses": pheno_children,
            "not": False,
        }

    def select_paths(self) -> list[str]:
        """Return all SELECT-clause concept paths, flattened recursively."""
        result: list[str] = []
        for child in self.clauses:
            result.extend(child.select_paths())
        return result

    def has_phenotypic(self) -> bool:
        """True if this group contains any non-SELECT clause, recursively."""
        for child in self.clauses:
            if isinstance(child, Clause):
                if child.type != ClauseType.SELECT:
                    return True
            elif child.has_phenotypic():
                return True
        return False
