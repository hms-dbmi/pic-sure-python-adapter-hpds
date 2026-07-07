"""Genomic (variant) filter model and value enums."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from importlib import resources


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


class GenomicFilterKey(str, Enum):
    """Recognized genomic annotation keys for ``buildGenomicFilter(key=...)``.

    Pass a member directly, or the equivalent string (validated against these
    members). ``VARIANT_SEVERITY`` is a *virtual* key: the backend has no
    ``Variant_severity`` filter, so the builder expands it to the matching
    ``Variant_consequence_calculated`` values (see :class:`VariantSeverity`).
    """

    GENE_WITH_VARIANT = "Gene_with_variant"
    VARIANT_CONSEQUENCE_CALCULATED = "Variant_consequence_calculated"
    VARIANT_FREQUENCY_AS_TEXT = "Variant_frequency_as_text"
    VARIANT_CLASS = "Variant_class"
    VARIANT_SEVERITY = "Variant_severity"


class VariantSeverity(str, Enum):
    """Severity buckets for the virtual ``Variant_severity`` key.

    Each member maps to a set of ``Variant_consequence_calculated`` values;
    ``buildGenomicFilter`` expands it so filtering by severity behaves as if
    the backend supported a ``Variant_severity`` key.
    """

    HIGH = "High Severity"
    MEDIUM = "Medium Severity"
    LOW = "Low Severity"


@lru_cache(maxsize=1)
def _severity_map() -> dict[str, tuple[str, ...]]:
    """Load ``variant_consequences.json`` as ``{severity_label: consequences}``.

    Pure JSON (no pandas), cached once. Same bundled file
    ``genomicConsequences()`` reads, keyed by severity label
    (``"High Severity"`` ...).
    """
    raw = (
        resources.files("picsure._data")
        .joinpath("variant_consequences.json")
        .read_text(encoding="utf-8")
    )
    groups = json.loads(raw)
    return {group["key"]: tuple(group["children"]) for group in groups}


def known_severities() -> tuple[str, ...]:
    """Return the valid severity labels, in file order (for error messages)."""
    return tuple(_severity_map().keys())


def severity_consequences(severity: str) -> tuple[str, ...]:
    """Return the consequences for one severity label.

    Raises:
        KeyError: If ``severity`` is not a known severity label.
    """
    return _severity_map()[severity]


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
    (``{"key", "values"?}``) per the ``/hpds/{auth,open}[/v3]/query`` contract.
    """

    key: str
    values: tuple[str, ...] | None = None

    def to_query_json(self) -> dict[str, object]:
        """Serialize this filter as a v3 ``GenomicFilter`` record."""
        out: dict[str, object] = {"key": self.key}
        if self.values is not None:
            out["values"] = list(self.values)
        return out
