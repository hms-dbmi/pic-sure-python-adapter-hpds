"""Genomic (variant) filter model and value enums."""

from __future__ import annotations

import re
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


# Variant-spec (SNP) keys are recognized server-side by
# VariantUtils.pathIsVariantSpec: an rsID, or a comma-delimited
# chromosome,offset,ref,alt[,gene,consequence] spec.  Variant-spec (SNP)
# filtering is not supported by this adapter yet, so buildGenomicFilter and the
# saved-query loader reject keys matching these shapes.  The patterns mirror
# the server's regex so rejection matches what the backend treats as a variant.
_VARIANT_SPEC_PATTERNS = (
    re.compile(r"rs[0-9]+.*"),
    re.compile(r".*,[0-9.]+,[CATGcatg]*,[CATGcatg]*"),
    re.compile(r".*,[0-9.]+,[CATGcatg]*,[CATGcatg]*,\w*,\w*"),
)


def is_variant_spec(key: str) -> bool:
    """Return True if ``key`` is a variant spec (rsID or ``chr,pos,ref,alt``...).

    Mirrors the server's ``VariantUtils.pathIsVariantSpec`` so the adapter's
    rejection of variant-spec (SNP) keys matches what the backend would treat
    as a specific variant. Annotation keys like ``"Gene_with_variant"`` (no
    comma) never match.
    """
    return any(pattern.fullmatch(key) for pattern in _VARIANT_SPEC_PATTERNS)


@dataclass(frozen=True)
class GenomicFilter:
    """A single categorical genomic (variant-annotation) filter in a query.

    Created by ``picsure.buildGenomicFilter()``. Genomic filters form a flat,
    conjunctive list on the query — there is no AND/OR nesting, unlike the
    phenotypic ``Clause`` / ``ClauseGroup`` tree.

    A filter matches when the annotation named by ``key`` is one of ``values``.

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
