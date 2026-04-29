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
    """

    COUNT = "count"
    PARTICIPANT = "participant"
    TIMESTAMP = "timestamp"
    CROSS_COUNT = "cross_count"
