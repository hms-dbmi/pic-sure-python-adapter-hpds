import threading
from datetime import datetime, timezone

from picsure._dev.buffer import EventBuffer
from picsure._dev.events import Event


def _make_event(name: str = "x") -> Event:
    return Event(
        timestamp=datetime.now(timezone.utc),
        kind="http",
        name=name,
        duration_ms=1.0,
        bytes_in=0,
        bytes_out=0,
        status=200,
        retry=0,
        error=None,
        metadata={},
    )


def test_append_and_list():
    buf = EventBuffer(max_events=10)
    buf.append(_make_event("a"))
    buf.append(_make_event("b"))
    names = [e.name for e in buf.snapshot()]
    assert names == ["a", "b"]


def test_append_over_cap_drops_oldest():
    buf = EventBuffer(max_events=3)
    for n in ["a", "b", "c", "d", "e"]:
        buf.append(_make_event(n))
    names = [e.name for e in buf.snapshot()]
    assert names == ["c", "d", "e"]


def test_clear_empties_buffer():
    buf = EventBuffer(max_events=10)
    buf.append(_make_event("a"))
    buf.clear()
    assert buf.snapshot() == []


def test_concurrent_appends_do_not_lose_or_corrupt():
    buf = EventBuffer(max_events=10000)
    threads = []
    per_thread = 200
    thread_count = 10

    def worker(tag: str) -> None:
        for i in range(per_thread):
            buf.append(_make_event(f"{tag}-{i}"))

    for t in range(thread_count):
        thr = threading.Thread(target=worker, args=(f"t{t}",))
        threads.append(thr)
        thr.start()
    for thr in threads:
        thr.join()

    events = buf.snapshot()
    assert len(events) == per_thread * thread_count
    for e in events:
        assert isinstance(e, Event)
