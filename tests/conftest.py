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
