from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from picsure._models.clause import Clause
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

    Created by ``picsure.buildClauseGroup()``. Can contain both
    ``Clause`` and nested ``ClauseGroup`` objects for arbitrarily
    deep nesting.

    **Wire format.** :meth:`to_query_json` emits a v3
    ``PhenotypicSubquery`` (``operator`` / ``phenotypicClauses``) per the
    ``/picsure/hpds/{auth,open}/v3/query`` contract. The previous wire
    format is not supported.

    **Immutability.** Frozen with a tuple of children, so a group is
    hashable and usable as a dict key or set member. ``clauses`` accepts
    any sequence of :class:`Clause` / :class:`ClauseGroup` and always
    stores a tuple. A bare :class:`Clause` or :class:`ClauseGroup` passed
    where the sequence belongs raises :class:`PicSureValidationError`,
    and so does a string, which is a sequence of characters and would
    otherwise become one child per character.

    **The container.** Anything else that cannot be iterated raises the
    same class, naming the type that arrived. The check is the attempt
    itself rather than a list of types, so a
    :class:`~picsure._models.query.Query`, the case a caller reaches by
    accident, is covered without this module importing ``query``, which
    imports it back.

    **Children.** Every element is checked as well, because only a
    :class:`Clause` and a :class:`ClauseGroup` carry the
    ``to_query_json`` the group calls. An unchecked child survives
    construction and fails later with an ``AttributeError`` raised inside
    :meth:`to_query_json`, outside the public error hierarchy and
    pointing at this class rather than at the argument the caller passed.
    """

    clauses: Sequence[Clause | ClauseGroup]
    operator: GroupOperator

    def __post_init__(self) -> None:
        if isinstance(self.clauses, str):
            raise PicSureValidationError(
                "ClauseGroup expects a sequence of Clause or ClauseGroup objects, "
                "not a string. Pass a list of clauses built with "
                "picsure.buildClause() or picsure.buildClauseGroup()."
            )
        if isinstance(self.clauses, (Clause, ClauseGroup)):
            raise PicSureValidationError(
                "ClauseGroup expects a sequence of Clause or ClauseGroup objects, "
                f"not a bare {type(self.clauses).__name__}. Wrap it in a list "
                "or tuple."
            )
        if not isinstance(self.clauses, tuple):
            try:
                object.__setattr__(self, "clauses", tuple(self.clauses))
            except TypeError as exc:
                raise PicSureValidationError(
                    f"ClauseGroup expects a sequence of Clause or ClauseGroup "
                    f"objects, not a {type(self.clauses).__name__}, which "
                    f"cannot be iterated. {_replacement_advice(self.clauses)}"
                ) from exc
        for position, child in enumerate(self.clauses):
            if not isinstance(child, (Clause, ClauseGroup)):
                raise PicSureValidationError(
                    f"ClauseGroup child at index {position} is a "
                    f"{type(child).__name__}, not a Clause or ClauseGroup. "
                    f"{_replacement_advice(child)}"
                )

    def concept_paths(self) -> list[str]:
        """All concept paths referenced anywhere in this group, depth-first.

        Recurses uniformly through nested groups because each child —
        ``Clause`` or ``ClauseGroup`` — implements ``concept_paths()``.
        """
        return [path for child in self.clauses for path in child.concept_paths()]

    def to_query_json(self) -> dict[str, object]:
        """Serialize this group as a v3 ``PhenotypicSubquery``."""
        return {
            "operator": self.operator.value,
            "phenotypicClauses": [child.to_query_json() for child in self.clauses],
            "not": False,
        }


def _replacement_advice(child: object) -> str:
    """Say what to pass in place of an object that cannot be a group child.

    A :class:`~picsure._models.query.Query` is the case a caller reaches
    by accident, because ``Session.loadQueryByID`` returns one for a
    saved query that carries output concepts, and composing that result
    into a group is the natural next step. Its ``phenotypicFilter`` is
    the composable part, so the advice names it. The import is deferred
    because ``query`` imports this module.

    Args:
        child: The offending element.

    Returns:
        One sentence naming what to pass instead.
    """
    from picsure._models.query import Query

    if isinstance(child, Query):
        return (
            "A Query is a whole query rather than a clause; pass its "
            "phenotypicFilter instead, as in "
            "buildClauseGroup([saved.phenotypicFilter, other_clause])."
        )
    return "Build each child with picsure.buildClause() or picsure.buildClauseGroup()."
