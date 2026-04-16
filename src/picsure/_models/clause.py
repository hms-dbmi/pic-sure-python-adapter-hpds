from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ClauseType(Enum):
    """Type of filter clause in a PIC-SURE query.

    Use these constants with ``picsure.createClause()``:

    - ``FILTER`` — filter by categorical values or numeric range
    - ``ANYRECORD`` — match any record that has a value for the variable
    - ``SELECT`` — include the variable in output without filtering
    - ``REQUIRE`` — require the variable to have a non-null value
    """

    FILTER = "filter"
    ANYRECORD = "anyrecord"
    SELECT = "select"
    REQUIRE = "require"


@dataclass(frozen=True)
class Clause:
    """A single filter clause in a PIC-SURE query.

    Created by ``picsure.createClause()``. Can be passed directly to
    ``Session.runQuery()`` or combined with other clauses via
    ``picsure.buildClauseGroup()``.
    """

    keys: list[str]
    type: ClauseType
    categories: list[str] | None = None
    min: float | None = None
    max: float | None = None

    def to_query_json(self) -> dict[str, object]:
        """Serialize this clause to the v3 query JSON format."""
        result: dict[str, object] = {
            "type": "clause",
            "clauseType": self.type.value,
            "keys": self.keys,
        }
        if self.categories is not None:
            result["categories"] = self.categories
        if self.min is not None:
            result["min"] = self.min
        if self.max is not None:
            result["max"] = self.max
        return result
