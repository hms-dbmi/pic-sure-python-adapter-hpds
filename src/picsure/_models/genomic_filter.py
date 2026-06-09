"""Genomic (variant) filter model and value enums."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VariantFrequency(str, Enum):
    """Population-frequency buckets for the ``Variant_frequency_as_text`` key.

    Members are plain strings, so they can be passed directly to
    ``picsure.buildGenomicFilter(values=...)``.
    """

    RARE = "Rare"
    COMMON = "Common"
    NOVEL = "Novel"


class Zygosity(str, Enum):
    """Genotype codes for SNP / variant-spec genomic filters.

    Members are plain strings, so they can be passed directly to
    ``picsure.buildGenomicFilter(values=...)``.
    """

    HETEROZYGOUS = "0/1"
    HOMOZYGOUS = "1/1"
    HETEROZYGOUS_OR_HOMOZYGOUS = "1/1,0/1"


@dataclass(frozen=True)
class GenomicFilter:
    """A single genomic (variant-annotation) filter in a PIC-SURE query.

    Created by ``picsure.buildGenomicFilter()``. Genomic filters form a flat,
    conjunctive list on the query — there is no AND/OR nesting, unlike the
    phenotypic ``Clause`` / ``ClauseGroup`` tree.

    A filter is either *categorical* (``values`` set) or a *numeric range*
    (``min`` and/or ``max`` set), never both — enforced by
    ``buildGenomicFilter()``.

    **Wire format.** :meth:`to_query_json` emits a v3 ``GenomicFilter`` record
    (``{"key", "values"?, "min"?, "max"?}``) per the
    ``/picsure/v3/query/sync`` contract.
    """

    key: str
    values: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None

    def to_query_json(self) -> dict[str, object]:
        """Serialize this filter as a v3 ``GenomicFilter`` record."""
        out: dict[str, object] = {"key": self.key}
        if self.values is not None:
            out["values"] = list(self.values)
        if self.min is not None:
            out["min"] = self.min
        if self.max is not None:
            out["max"] = self.max
        return out
