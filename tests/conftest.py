import json
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Golden contract fixtures, copied verbatim from the server monorepo's
# pic-sure-contracts module
# (libs/pic-sure-commons/pic-sure-contracts/src/test/resources/fixtures).
# They are the CROSS-LANGUAGE inputs: the Java contract tests and this
# adapter's shape tests read the same bytes, so a wire change that lands
# server-side breaks here too.  Do not hand-edit -- re-copy them.
_CONTRACT_FIXTURES_DIR = _FIXTURES_DIR / "contracts"


def load_contract_fixture(name: str) -> dict:
    """Load a golden contract fixture by file name (without ``.json``)."""
    return json.loads((_CONTRACT_FIXTURES_DIR / f"{name}.json").read_text())


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
    """Sample /picsure/dictionary/concepts response."""
    return json.loads((_FIXTURES_DIR / "dictionary_search.json").read_text())


@pytest.fixture()
def facets_response() -> list:
    """Sample /picsure/dictionary/facets response (top-level array)."""
    return json.loads((_FIXTURES_DIR / "facets_response.json").read_text())


@pytest.fixture()
def participant_response() -> bytes:
    """Sample participant-level CSV query response."""
    return (_FIXTURES_DIR / "query_participant.csv").read_bytes()
