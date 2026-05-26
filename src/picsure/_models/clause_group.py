from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from picsure._models.clause import Clause


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
    ``PhenotypicSubquery`` (``operator`` / ``phenotypicClauses``) per
    the ``/picsure/v3/query/sync`` contract. The previous wire format
    is not supported.
    """

    clauses: list[Clause | ClauseGroup]
    operator: GroupOperator

    def to_query_json(self) -> dict[str, object]:
        """Serialize this group as a v3 ``PhenotypicSubquery``."""
        return {
            "operator": self.operator.value,
            "phenotypicClauses": [child.to_query_json() for child in self.clauses],
            "not": False,
        }
