from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PhenotypicFilterType(Enum):
    """Type of filter clause in a PIC-SURE query.

    Use these constants with ``picsure.buildClause()``:

    - ``FILTER`` — filter by categorical values or numeric range
    - ``ANYRECORD`` — match records where the concept path *or any
      descendant* has a value (wire: ``ANY_RECORD_OF``)
    - ``REQUIRE`` — require the concept path to have a non-null value
      (wire: ``REQUIRED``)

    To include concept paths in query output without filtering, pass
    them to ``picsure.buildQuery(includeConcepts=...)`` instead — output
    columns are no longer a clause type.
    """

    FILTER = "filter"
    ANYRECORD = "anyrecord"
    REQUIRE = "require"


_WIRE_NAME_BY_TYPE: dict[PhenotypicFilterType, str] = {
    PhenotypicFilterType.FILTER: "FILTER",
    PhenotypicFilterType.REQUIRE: "REQUIRED",
    PhenotypicFilterType.ANYRECORD: "ANY_RECORD_OF",
}

# Reverse of _WIRE_NAME_BY_TYPE, exposed so query_load can rebuild
# clauses from the wire payload without redefining the mapping.
PHENOTYPIC_FILTER_TYPE_BY_WIRE_NAME: dict[str, PhenotypicFilterType] = {
    v: k for k, v in _WIRE_NAME_BY_TYPE.items()
}


@dataclass(frozen=True)
class Clause:
    """A single filter clause in a PIC-SURE query.

    Created by ``picsure.buildClause()``. Can be passed directly to
    ``Session.runQuery()`` or combined with other clauses via
    ``picsure.buildClauseGroup()``.

    **Wire format.** :meth:`to_query_json` emits a v3 ``PhenotypicFilter``
    leaf (or an ``OR`` ``PhenotypicSubquery`` of leaves for multi-key
    clauses) per the ``/picsure/v3/query/sync`` contract.
    """

    keys: list[str]
    type: PhenotypicFilterType
    categories: list[str] | None = None
    min: float | None = None
    max: float | None = None

    def concept_paths(self) -> list[str]:
        """Concept paths this clause references, in order.

        Used to fold a query's filter variables into the output ``select``
        array so they are returned without being repeated in
        ``includeConcepts``.
        """
        return list(self.keys)

    def to_query_json(self) -> dict[str, object]:
        """Serialize this clause as a v3 ``PhenotypicClause``.

        Emits a ``PhenotypicFilter`` leaf for single-key clauses, or
        an OR ``PhenotypicSubquery`` of per-key leaves when the clause
        spans multiple keys.
        """
        leaves = [self._make_leaf(k) for k in self.keys]
        if len(leaves) == 1:
            return leaves[0]
        return {
            "operator": "OR",
            "phenotypicClauses": leaves,
            "not": False,
        }

    def _make_leaf(self, concept_path: str) -> dict[str, object]:
        leaf: dict[str, object] = {
            "phenotypicFilterType": _WIRE_NAME_BY_TYPE[self.type],
            "conceptPath": concept_path,
            "not": False,
        }
        if self.type == PhenotypicFilterType.FILTER:
            if self.categories is not None:
                leaf["values"] = list(self.categories)
            if self.min is not None:
                leaf["min"] = self.min
            if self.max is not None:
                leaf["max"] = self.max
        return leaf
