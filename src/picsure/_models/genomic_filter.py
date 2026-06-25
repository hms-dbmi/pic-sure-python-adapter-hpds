"""Genomic (variant) filter model and value enums."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VariantFrequency(str, Enum):
    """Population-frequency buckets for the ``Variant_frequency_as_text`` key.

    Pass a member directly to ``picsure.buildGenomicFilter(values=...)``; the
    builder uses the member's ``.value`` (e.g. ``VariantFrequency.RARE`` →
    ``"Rare"``). Note that ``str(VariantFrequency.RARE)`` is
    ``"VariantFrequency.RARE"``, not the value — use ``.value`` if you need
    the wire string yourself.
    """

    RARE = "Rare"
    COMMON = "Common"
    NOVEL = "Novel"


class Zygosity(str, Enum):
    """Genotype codes for SNP / variant-spec genomic filters.

    Pass a member directly to ``picsure.buildGenomicFilter(values=...)``; the
    builder uses the member's ``.value`` (e.g. ``Zygosity.HETEROZYGOUS`` →
    ``"0/1"``). Note that ``str(Zygosity.HETEROZYGOUS)`` is
    ``"Zygosity.HETEROZYGOUS"``, not the value — use ``.value`` if you need
    the wire string yourself.
    """

    HETEROZYGOUS = "0/1"
    HOMOZYGOUS = "1/1"
    HETEROZYGOUS_OR_HOMOZYGOUS = "1/1,0/1"


@dataclass(frozen=True)
class GenomicFilter:
    """A single categorical genomic (variant-annotation) filter in a query.

    Created by ``picsure.buildGenomicFilter()``. Genomic filters form a flat,
    conjunctive list on the query — there is no AND/OR nesting, unlike the
    phenotypic ``Clause`` / ``ClauseGroup`` tree.

    A filter matches when the annotation named by ``key`` is one of ``values``.
    (A variant-spec / SNP key may carry no ``values``, in which case the server
    applies its default genotype match.)

    **Wire format.** :meth:`to_query_json` emits a v3 ``GenomicFilter`` record
    (``{"key", "values"?}``) per the ``/picsure/v3/query/sync`` contract.
    """

    key: str
    values: tuple[str, ...] | None = None

    def to_query_json(self) -> dict[str, object]:
        """Serialize this filter as a v3 ``GenomicFilter`` record."""
        out: dict[str, object] = {"key": self.key}
        if self.values is not None:
            out["values"] = list(self.values)
        return out
