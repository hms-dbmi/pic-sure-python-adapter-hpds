from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from picsure.errors import PicSureValidationError


class ClauseType(Enum):
    """Type of filter clause in a PIC-SURE query.

    Use these constants with ``picsure.createClause()``:

    - ``FILTER`` — filter by categorical values or numeric range
    - ``ANYRECORD`` — match records where the concept path *or any
      descendant* has a value (wire: ``ANY_RECORD_OF``)
    - ``SELECT`` — include the concept path(s) in query output; does
      not contribute to filtering
    - ``REQUIRE`` — require the concept path to have a non-null value
      (wire: ``REQUIRED``)
    """

    FILTER = "filter"
    ANYRECORD = "anyrecord"
    SELECT = "select"
    REQUIRE = "require"


_PHENOTYPIC_FILTER_TYPE: dict[ClauseType, str] = {
    ClauseType.FILTER: "FILTER",
    ClauseType.REQUIRE: "REQUIRED",
    ClauseType.ANYRECORD: "ANY_RECORD_OF",
}


@dataclass(frozen=True)
class Clause:
    """A single filter clause in a PIC-SURE query.

    Created by ``picsure.createClause()``. Can be passed directly to
    ``Session.runQuery()`` or combined with other clauses via
    ``picsure.buildClauseGroup()``.

    **Wire format.** :meth:`to_query_json` emits a v3 ``PhenotypicFilter``
    leaf (or an ``OR`` ``PhenotypicSubquery`` of leaves for multi-key
    clauses) per the ``/picsure/v3/query/sync`` contract. The previous
    wire format is not supported.
    """

    keys: list[str]
    type: ClauseType
    categories: list[str] | None = None
    min: float | None = None
    max: float | None = None

    def to_query_json(self) -> dict[str, object]:
        """Serialize this clause as a v3 ``PhenotypicClause``.

        Emits a ``PhenotypicFilter`` leaf for single-key clauses, or
        an OR ``PhenotypicSubquery`` of per-key leaves when the clause
        spans multiple keys.

        Raises:
            PicSureValidationError: If this is a SELECT clause. SELECT
                clauses don't participate in filtering; extract their
                paths via :meth:`select_paths` instead.
        """
        if self.type == ClauseType.SELECT:
            raise PicSureValidationError(
                "SELECT clauses do not serialize as PhenotypicClauses. "
                "Use Clause.select_paths() to retrieve their concept paths."
            )

        leaves = [self._make_leaf(k) for k in self.keys]
        if len(leaves) == 1:
            return leaves[0]
        return {
            "operator": "OR",
            "phenotypicClauses": leaves,
            "not": False,
        }

    def select_paths(self) -> list[str]:
        """Return this clause's concept paths if it's a SELECT, else []."""
        return list(self.keys) if self.type == ClauseType.SELECT else []

    def _make_leaf(self, concept_path: str) -> dict[str, object]:
        leaf: dict[str, object] = {
            "phenotypicFilterType": _PHENOTYPIC_FILTER_TYPE[self.type],
            "conceptPath": concept_path,
            "not": False,
        }
        if self.type == ClauseType.FILTER:
            if self.categories is not None:
                leaf["values"] = list(self.categories)
            if self.min is not None:
                leaf["min"] = self.min
            if self.max is not None:
                leaf["max"] = self.max
        return leaf
