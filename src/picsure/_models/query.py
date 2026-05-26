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
    "filter, no extra output columns."

    A ``genomicFilter`` field is anticipated here in the future, alongside
    ``phenotypicFilter``.
    """

    phenotypicFilter: Clause | ClauseGroup | None = None  # noqa: N815
    includeConcepts: tuple[str, ...] = field(default_factory=tuple)  # noqa: N815
