import json
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def profile_response() -> dict:
    """Sample ``GET /psama/user/me`` response."""
    return json.loads((_FIXTURES_DIR / "profile.json").read_text())


@pytest.fixture()
def resources_response() -> dict[str, str]:
    """Sample registry ``/info/resources`` response ({uuid: name, ...}).

    Registry-era. The v3 gateway routes by URL path and this endpoint is
    no longer called by the adapter; the fixture is kept only for tests
    that need an arbitrary object payload.
    """
    return json.loads((_FIXTURES_DIR / "resources.json").read_text())


@pytest.fixture()
def search_response() -> dict:
    """Sample ``POST /picsure/dictionary/concepts`` response.

    Spring Data ``Page`` envelope. Not ``/picsure/proxy/dictionary-api/
    concepts`` -- that path answers 401 and the adapter does not use it.
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
