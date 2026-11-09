from __future__ import annotations

from dataclasses import dataclass, field

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.genomic_filter import GenomicFilter
from picsure.errors import PicSureValidationError


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

    ``sample`` asks the server for a small sample of the export instead of
    the whole dataset. It applies to the dataframe result types only
    (``"participant"``, ``"timestamp"`` and the PFB export), and the server
    refuses it on every other type. A sample may not represent the whole
    dataset, and its cells can be empty.

    Raises:
        PicSureValidationError: If ``sample`` is not a bool. Only ``True``
            is sent to the server, so any other value would otherwise run
            a full export without saying so.
    """

    phenotypicFilter: Clause | ClauseGroup | None = None  # noqa: N815
    includeConcepts: tuple[str, ...] = field(default_factory=tuple)  # noqa: N815
    genomicFilters: tuple[GenomicFilter, ...] = field(default_factory=tuple)  # noqa: N815
    sample: bool = False

    def __post_init__(self) -> None:
        """Refuse a ``sample`` that is not a bool.

        ``buildQuery`` relies on this check instead of repeating it, so a
        ``Query`` built directly and one built through ``buildQuery`` fail
        the same way.

        Raises:
            PicSureValidationError: If ``sample`` is not a bool.
        """
        if not isinstance(self.sample, bool):
            raise PicSureValidationError(
                f"sample must be True or False, got {type(self.sample).__name__}."
            )
