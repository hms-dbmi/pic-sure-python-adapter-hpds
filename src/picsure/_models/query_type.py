"""Public ``QueryType`` enum for ``runQuery``."""

from __future__ import annotations

from enum import Enum


class QueryType(Enum):
    """Type of result to request from :func:`runQuery`.

    Use these constants with ``Session.runQuery()`` (or pass the
    equivalent lowercase string):

    - ``COUNT``        — returns :class:`CountResult` (a single count).
    - ``PARTICIPANT``  — returns a :class:`pandas.DataFrame` with one
      row per matching participant.
    - ``TIMESTAMP``    — returns a :class:`pandas.DataFrame` of
      participant-level timestamps for longitudinal concepts.
    - ``CROSS_COUNT``  — returns ``dict[str, CountResult]`` keyed by
      concept path.
    - ``VARIANT_COUNT`` — returns an ``int`` count of distinct matching
      variants.
    - ``VARIANT_LIST``  — returns ``list[str]`` of variant spec strings.
    - ``VCF_EXCERPT``   — returns a :class:`pandas.DataFrame` (one row per
      variant, with per-patient genotype columns).
    - ``AGGREGATE_VCF_EXCERPT`` — like ``VCF_EXCERPT`` without patient columns.
    """

    COUNT = "count"
    PARTICIPANT = "participant"
    TIMESTAMP = "timestamp"
    CROSS_COUNT = "cross_count"
    VARIANT_COUNT = "variant_count"
    VARIANT_LIST = "variant_list"
    VCF_EXCERPT = "vcf_excerpt"
    AGGREGATE_VCF_EXCERPT = "aggregate_vcf_excerpt"
