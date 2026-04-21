from datetime import datetime, timezone

from picsure._dev.events import Event
from picsure._dev.reporting import events_to_df, stats_to_df

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


def _event(
    kind="http",
    name="/a",
    duration=10.0,
    retry=0,
    error=None,
    bytes_in=100,
    bytes_out=200,
    status=200,
):
    return Event(
        timestamp=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        kind=kind,
        name=name,
        duration_ms=duration,
        bytes_in=bytes_in,
        bytes_out=bytes_out,
        status=status,
        retry=retry,
        error=error,
        metadata={},
    )


def test_events_to_df_empty_has_columns():
    df = events_to_df([])
    assert list(df.columns) == _EVENT_COLS
    assert len(df) == 0


def test_events_to_df_one_row_per_event():
    df = events_to_df([_event(name="/a"), _event(name="/b")])
    assert len(df) == 2
    assert list(df["name"]) == ["/a", "/b"]


def test_stats_to_df_empty_has_columns():
    df = stats_to_df([])
    assert list(df.columns) == _STATS_COLS
    assert len(df) == 0


def test_stats_to_df_aggregates_by_kind_and_name():
    events = [
        _event(kind="http", name="/a", duration=10.0, bytes_in=100, bytes_out=200),
        _event(kind="http", name="/a", duration=20.0, bytes_in=50, bytes_out=400),
        _event(kind="http", name="/b", duration=5.0, bytes_in=10, bytes_out=20),
    ]
    df = stats_to_df(events)
    a = df[df["name"] == "/a"].iloc[0]
    assert a["calls"] == 2
    assert a["total_ms"] == 30.0
    assert a["avg_ms"] == 15.0
    assert a["min_ms"] == 10.0
    assert a["max_ms"] == 20.0
    assert a["bytes_in_total"] == 150
    assert a["bytes_out_total"] == 600


def test_stats_counts_retries_and_errors():
    events = [
        _event(kind="http", name="/a", retry=0, error=None),
        _event(kind="http", name="/a", retry=1, error=None),
        _event(kind="http", name="/a", retry=0, error="TransportServerError"),
    ]
    df = stats_to_df(events)
    row = df[df["name"] == "/a"].iloc[0]
    assert row["retries"] == 1
    assert row["errors"] == 1


def test_stats_handles_none_bytes():
    events = [
        _event(kind="function", name="session.search", bytes_in=None, bytes_out=None),
    ]
    df = stats_to_df(events)
    assert df.iloc[0]["bytes_in_total"] == 0
    assert df.iloc[0]["bytes_out_total"] == 0
