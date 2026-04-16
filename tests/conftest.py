import json
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def profile_response() -> dict:
    """Sample PSAMA /user/me response."""
    return json.loads((_FIXTURES_DIR / "profile.json").read_text())


@pytest.fixture()
def resources_response() -> dict[str, str]:
    """Sample /info/resources response ({uuid: name, ...})."""
    return json.loads((_FIXTURES_DIR / "resources.json").read_text())


@pytest.fixture()
def search_response() -> dict:
    """Sample /picsure/search/{resourceId} response."""
    return json.loads((_FIXTURES_DIR / "dictionary_search.json").read_text())
