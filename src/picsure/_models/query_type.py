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
    - ``VARIANT_COUNT`` — returns a :class:`CountResult` for the number of
      distinct matching variants (preserving obfuscation, like ``COUNT``).
    - ``VARIANT_LIST``  — returns ``list[str]`` of variant spec strings.
    - ``VCF_EXCERPT``   — returns a :class:`pandas.DataFrame` (one row per
      variant, with per-patient genotype columns).
    - ``AGGREGATE_VCF_EXCERPT`` — like ``VCF_EXCERPT`` without patient columns.

    Note:
        The four variant result types depend on the deployment serving them.
        Some deployments (e.g. BDC as of 2026-06) do not yet, and return an
        empty response; ``runQuery`` raises a clear ``PicSureQueryError`` in
        that case. Genomic *filters* work as a constraint on ``COUNT`` /
        ``PARTICIPANT`` regardless.
    """

    COUNT = "count"
    PARTICIPANT = "participant"
    TIMESTAMP = "timestamp"
    CROSS_COUNT = "cross_count"
    VARIANT_COUNT = "variant_count"
    VARIANT_LIST = "variant_list"
    VCF_EXCERPT = "vcf_excerpt"
    AGGREGATE_VCF_EXCERPT = "aggregate_vcf_excerpt"
