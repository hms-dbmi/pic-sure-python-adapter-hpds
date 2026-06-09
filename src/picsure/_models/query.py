from __future__ import annotations

from dataclasses import dataclass, field

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.genomic_filter import GenomicFilter


@dataclass(frozen=True)
class Query:
    """A phenotypic filter tree, genomic filters, and output concept paths.

    Created by ``picsure.buildQuery()``. The phenotypic filter may be
    ``None`` for an include-only or genomic-only query. Bare ``Clause`` /
    ``ClauseGroup`` objects are still accepted directly by
    ``Session.runQuery()`` and friends — they mean "filter, returning the
    filtered variables as output columns and no others."

    The variables referenced anywhere in ``phenotypicFilter`` are returned
    as output columns automatically; ``includeConcepts`` names *additional*
    columns beyond those. ``genomicFilters`` is a flat, conjunctive list of
    :class:`GenomicFilter` records applied alongside the phenotypic filter.
    """

    phenotypicFilter: Clause | ClauseGroup | None = None  # noqa: N815
    includeConcepts: tuple[str, ...] = field(default_factory=tuple)  # noqa: N815
    genomicFilters: tuple[GenomicFilter, ...] = field(default_factory=tuple)  # noqa: N815
