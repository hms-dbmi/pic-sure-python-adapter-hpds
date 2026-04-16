import os
from pathlib import Path

import pytest

from picsure._transport.platforms import Platform

PICSURE_INTEGRATION = os.environ.get("PICSURE_INTEGRATION", "0") == "1"
PICSURE_TEST_TOKEN = os.environ.get("PICSURE_TEST_TOKEN", "")
PICSURE_TEST_PLATFORM = os.environ.get("PICSURE_TEST_PLATFORM", "DEMO")

_PLATFORM_BY_NAME = {p.name: p for p in Platform}


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
    if not PICSURE_TEST_TOKEN:
        pytest.skip("PICSURE_TEST_TOKEN not set")
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
