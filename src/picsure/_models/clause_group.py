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
    """

    clauses: list[Clause | ClauseGroup]
    operator: GroupOperator

    def to_query_json(self) -> dict[str, object]:
        """Serialize this group to the v3 query JSON format."""
        return {
            "type": self.operator.value.lower(),
            "children": [c.to_query_json() for c in self.clauses],
        }
