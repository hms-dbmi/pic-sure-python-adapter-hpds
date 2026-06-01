from __future__ import annotations

from dataclasses import dataclass, field

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup


@dataclass(frozen=True)
class Query:
    """A phenotypic filter tree plus the concept paths to include as output columns.

    Created by ``picsure.buildQuery()``. The phenotypic filter may be
    ``None`` for an include-only query (return the named concepts for all
    matching records). Bare ``Clause`` / ``ClauseGroup`` objects are still
    accepted directly by ``Session.runQuery()`` and friends — they mean
    "filter, returning the filtered variables as output columns and no
    others."

    The variables referenced anywhere in ``phenotypicFilter`` are returned
    as output columns automatically; ``includeConcepts`` names *additional*
    columns beyond those (ALS-11934).

    A ``genomicFilter`` field is anticipated here in the future, alongside
    ``phenotypicFilter``.
    """

    phenotypicFilter: Clause | ClauseGroup | None = None  # noqa: N815
    includeConcepts: tuple[str, ...] = field(default_factory=tuple)  # noqa: N815
