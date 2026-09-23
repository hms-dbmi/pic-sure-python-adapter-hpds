import json
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def profile_response() -> dict:
    """Sample ``GET /psama/user/me`` response."""
    return json.loads((_FIXTURES_DIR / "profile.json").read_text())


@pytest.fixture()
def search_response() -> dict:
    """Sample ``POST /picsure/dictionary/concepts`` response.

    Spring Data ``Page`` envelope. The ``/picsure/proxy/dictionary-api/concepts``
    path answers 401 and the adapter does not use it.
    """
    return json.loads((_FIXTURES_DIR / "dictionary_search.json").read_text())


@pytest.fixture()
def facets_response() -> list:
    """Sample ``POST /picsure/dictionary/facets`` response.

    A top-level JSON array, which is why the client's JSON accessors
    return an object-or-array union rather than a ``dict``.
    """
    return json.loads((_FIXTURES_DIR / "facets_response.json").read_text())


@pytest.fixture()
def participant_response() -> bytes:
    """Sample participant-level CSV query response."""
    return (_FIXTURES_DIR / "query_participant.csv").read_bytes()


class FakeClock:
    """A monotonic clock that advances only when the code under test sleeps.

    Attributes:
        now: The current reading, in seconds.
        sleeps: Every duration passed to ``sleep``, in order.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture()
def clock(monkeypatch) -> FakeClock:
    """Replace the query loop's clock and sleep so waits are measured, not slept."""
    import picsure._services.query_run as query_run

    fake = FakeClock()
    monkeypatch.setattr(query_run.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(query_run.time, "sleep", fake.sleep)
    return fake
