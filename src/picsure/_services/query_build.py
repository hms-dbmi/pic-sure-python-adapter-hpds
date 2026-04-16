from __future__ import annotations

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure.errors import PicSureValidationError


def createClause(  # noqa: N802
    keys: str | list[str],
    type: ClauseType,  # noqa: A002
    categories: str | list[str] | None = None,
    min: float | None = None,  # noqa: A002
    max: float | None = None,  # noqa: A002
) -> Clause:
    """Create a single filter clause for use in a query.

    Args:
        keys: Concept path(s) this clause applies to.
        type: The kind of filter. Use ``ClauseType.FILTER`` for
            categorical or range filters, ``ClauseType.ANYRECORD``
            to match the presence of any value.
        categories: For FILTER clauses on categorical variables.
        min: For FILTER clauses on numeric variables, minimum value.
        max: For FILTER clauses on numeric variables, maximum value.

    Returns:
        A Clause that can be used in ``buildClauseGroup()`` or
        passed directly to ``Session.runQuery()``.

    Raises:
        PicSureValidationError: If the clause configuration is invalid.
    """
    if isinstance(keys, str):
        keys = [keys]
    if isinstance(categories, str):
        categories = [categories]

    if type == ClauseType.ANYRECORD:
        if categories is not None:
            raise PicSureValidationError(
                "ANYRECORD clauses cannot have categories. ANYRECORD matches "
                "the presence of any value for the variable. Remove the "
                "categories argument."
            )
        if min is not None or max is not None:
            raise PicSureValidationError(
                "ANYRECORD clauses cannot have min or max values. ANYRECORD "
                "matches the presence of any value for the variable. Remove "
                "the min/max arguments."
            )

    if (
        type == ClauseType.FILTER
        and categories is None
        and min is None
        and max is None
    ):
        raise PicSureValidationError(
            "FILTER clauses require at least one of: categories, min, or max. "
            "Use categories for categorical variables or min/max for "
            "continuous variables."
        )

    return Clause(
        keys=keys,
        type=type,
        categories=categories,
        min=min,
        max=max,
    )


def buildClauseGroup(  # noqa: N802
    clauses: list[Clause | ClauseGroup],
    root: GroupOperator = GroupOperator.AND,
) -> ClauseGroup:
    """Create a group of clauses combined with AND or OR.

    Args:
        clauses: List of Clause or ClauseGroup objects to combine.
        root: Logical operator — ``GroupOperator.AND`` (default) or
            ``GroupOperator.OR``.

    Returns:
        A ClauseGroup that can be nested or passed to
        ``Session.runQuery()``.

    Raises:
        PicSureValidationError: If the clause list is empty.
    """
    if not clauses:
        raise PicSureValidationError(
            "A clause group must contain at least one clause."
        )

    return ClauseGroup(clauses=clauses, operator=root)
