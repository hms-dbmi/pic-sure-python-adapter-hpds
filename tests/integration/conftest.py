import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from picsure._transport.platforms import Platform

# Load a .env file at the repo root if present, so developers can keep
# their integration-test token there instead of exporting it. Shell-
# exported vars still win (override=False).
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env", override=False)

PICSURE_INTEGRATION = os.environ.get("PICSURE_INTEGRATION", "0") == "1"
PICSURE_TEST_TOKEN = os.environ.get("PICSURE_TEST_TOKEN", "")
PICSURE_TEST_PLATFORM = os.environ.get("PICSURE_TEST_PLATFORM", "DEMO")
PICSURE_TEST_CONCEPT_PATH = os.environ.get("PICSURE_TEST_CONCEPT_PATH", "")
PICSURE_TEST_SEARCH_TERM = os.environ.get("PICSURE_TEST_SEARCH_TERM", "age")

_PLATFORM_BY_NAME = {p.name: p for p in Platform}


def requires_auth(test_platform: Platform | str) -> bool:
    """Return True if the given platform needs a bearer token."""
    if isinstance(test_platform, Platform):
        return test_platform.requires_auth
    return True


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not PICSURE_INTEGRATION:
        skip = pytest.mark.skip(
            reason="Integration tests disabled. Set PICSURE_INTEGRATION=1 to run."
        )
        integration_dir = str(Path(__file__).parent)
        for item in items:
            if str(item.fspath).startswith(integration_dir):
                item.add_marker(skip)


@pytest.fixture()
def test_token() -> str:
    """Return the configured token, or an empty string for open-access runs."""
    return PICSURE_TEST_TOKEN


@pytest.fixture()
def test_platform() -> Platform | str:
    """Resolve PICSURE_TEST_PLATFORM to a Platform enum or URL string.

    Accepts enum names (e.g. ``DEMO``, ``BDC_AUTHORIZED``) or full URLs.
    """
    key = PICSURE_TEST_PLATFORM.upper()
    if key in _PLATFORM_BY_NAME:
        return _PLATFORM_BY_NAME[key]
    return PICSURE_TEST_PLATFORM


@pytest.fixture()
def test_concept_path() -> str:
    """Concept path used by query/export live tests.

    Platform-specific — set ``PICSURE_TEST_CONCEPT_PATH`` to a path that
    exists on the target deployment. Tests that need it will skip with
    a clear message if unset rather than fail with an opaque server
    error (e.g. a misleading 401 on an invalid path/filter combo).
    """
    if not PICSURE_TEST_CONCEPT_PATH:
        pytest.skip(
            "PICSURE_TEST_CONCEPT_PATH is not set. Add it to your .env "
            "with a concept path valid for PICSURE_TEST_PLATFORM, e.g. "
            r"'\open_access-1000Genomes\SIMULATED AGE\'."
        )
    return PICSURE_TEST_CONCEPT_PATH


@pytest.fixture()
def test_search_term() -> str:
    """Search term used by search live tests. Override via
    ``PICSURE_TEST_SEARCH_TERM``; defaults to ``"age"`` which exists on
    most PIC-SURE deployments."""
    return PICSURE_TEST_SEARCH_TERM
