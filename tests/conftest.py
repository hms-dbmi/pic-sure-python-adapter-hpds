import json
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def profile_response() -> dict:
    """Sample PSAMA /user/me response."""
    return json.loads((_FIXTURES_DIR / "profile.json").read_text())


@pytest.fixture()
def resources_response() -> list[dict]:
    """Sample /info/resources response."""
    return json.loads((_FIXTURES_DIR / "resources.json").read_text())
