from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from picsure._models.clause import Clause, ClauseType
from picsure.errors import PicSureValidationError


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

    Created by ``picsure.buildQuery()``. Can contain both
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
        """Serialize this group as a v3 ``PhenotypicSubquery``.

        Raises:
            PicSureValidationError: If any nested child is a SELECT
                clause. SELECT clauses do not participate in filtering
                and must be kept outside of ``ClauseGroup`` so they can
                be lifted into the top-level ``select`` array. Extract
                SELECT paths via :meth:`select_paths` before calling
                :meth:`to_query_json`.
        """
        pheno_children: list[dict[str, object]] = []
        for child in self.clauses:
            if isinstance(child, Clause) and child.type == ClauseType.SELECT:
                raise PicSureValidationError(
                    "ClauseGroup cannot contain a SELECT clause; use "
                    "Clause.select_paths() to extract SELECT concept paths."
                )
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

    def phenotypic_only(self) -> ClauseGroup | None:
        """Return a copy of this group with all SELECT clauses stripped.

        SELECT clauses don't participate in filtering and are lifted to the
        top-level ``select`` array by ``runQuery``.  This helper is used by
        the query-run plumbing to produce a SELECT-free ``ClauseGroup``
        before serializing the phenotypic tree.

        Returns:
            A new ``ClauseGroup`` with SELECTs removed recursively, or
            ``None`` if nothing phenotypic remains.
        """
        kept: list[Clause | ClauseGroup] = []
        for child in self.clauses:
            if isinstance(child, Clause):
                if child.type != ClauseType.SELECT:
                    kept.append(child)
            else:
                stripped = child.phenotypic_only()
                if stripped is not None:
                    kept.append(stripped)
        if not kept:
            return None
        return ClauseGroup(clauses=kept, operator=self.operator)
