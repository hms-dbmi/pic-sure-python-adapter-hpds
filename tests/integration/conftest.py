import os

import pytest

PICSURE_INTEGRATION = os.environ.get("PICSURE_INTEGRATION", "0") == "1"
PICSURE_TEST_TOKEN = os.environ.get("PICSURE_TEST_TOKEN", "")
PICSURE_TEST_PLATFORM = os.environ.get("PICSURE_TEST_PLATFORM", "Demo")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not PICSURE_INTEGRATION:
        skip = pytest.mark.skip(
            reason="Integration tests disabled. Set PICSURE_INTEGRATION=1 to run."
        )
        for item in items:
            item.add_marker(skip)


@pytest.fixture()
def test_token() -> str:
    if not PICSURE_TEST_TOKEN:
        pytest.skip("PICSURE_TEST_TOKEN not set")
    return PICSURE_TEST_TOKEN


@pytest.fixture()
def test_platform() -> str:
    return PICSURE_TEST_PLATFORM
