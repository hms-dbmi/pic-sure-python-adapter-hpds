from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from picsure._dev.events import Event

_EVENT_COLS = [
    "timestamp",
    "kind",
    "name",
    "duration_ms",
    "bytes_in",
    "bytes_out",
    "status",
    "retry",
    "error",
    "metadata",
]

_STATS_COLS = [
    "kind",
    "name",
    "calls",
    "total_ms",
    "avg_ms",
    "min_ms",
    "max_ms",
    "bytes_in_total",
    "bytes_out_total",
    "retries",
    "errors",
]


def events_to_df(events: list[Event]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=_EVENT_COLS)
    return pd.DataFrame([asdict(e) for e in events], columns=_EVENT_COLS)


def stats_to_df(events: list[Event]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=_STATS_COLS)

    groups: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in events:
        groups[(event.kind, event.name)].append(event)

    rows = []
    for (kind, name), batch in groups.items():
        durations = [e.duration_ms for e in batch]
        rows.append(
            {
                "kind": kind,
                "name": name,
                "calls": len(batch),
                "total_ms": sum(durations),
                "avg_ms": sum(durations) / len(batch),
                "min_ms": min(durations),
                "max_ms": max(durations),
                "bytes_in_total": sum((e.bytes_in or 0) for e in batch),
                "bytes_out_total": sum((e.bytes_out or 0) for e in batch),
                "retries": sum(1 for e in batch if e.retry > 0),
                "errors": sum(1 for e in batch if e.error is not None),
            }
        )
    return pd.DataFrame(rows, columns=_STATS_COLS)
