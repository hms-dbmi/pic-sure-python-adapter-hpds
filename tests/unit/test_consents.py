import json

import httpx
import pytest
import respx

from picsure._services.consents import fetch_consents
from picsure._transport.client import PicSureClient
from picsure.errors import PicSureConnectionError

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
TEMPLATE_URL = f"{BASE_URL}/psama/user/me/queryTemplate/"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _wrap_template(inner: dict) -> dict:
    return {"queryTemplate": json.dumps(inner)}


class TestFetchConsents:
    @respx.mock
    def test_returns_consents_list(self):
        inner = {
            "categoryFilters": {
                "\\_consents\\": ["phs000007.c1", "phs000179.c1", "phs001013.c1"],
            },
        }
        respx.get(TEMPLATE_URL).mock(
            return_value=httpx.Response(200, json=_wrap_template(inner))
        )
        consents = fetch_consents(_make_client())
        assert consents == ["phs000007.c1", "phs000179.c1", "phs001013.c1"]

    @respx.mock
    def test_ignores_harmonized_and_topmed_keys(self):
        inner = {
            "categoryFilters": {
                "\\_harmonized_consent\\": ["other.c1"],
                "\\_consents\\": ["phs000007.c1"],
                "\\_topmed_consents\\": ["tm.c1"],
            },
        }
        respx.get(TEMPLATE_URL).mock(
            return_value=httpx.Response(200, json=_wrap_template(inner))
        )
        assert fetch_consents(_make_client()) == ["phs000007.c1"]

    @respx.mock
    def test_missing_query_template_returns_empty(self):
        respx.get(TEMPLATE_URL).mock(return_value=httpx.Response(200, json={}))
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_missing_category_filters_returns_empty(self):
        respx.get(TEMPLATE_URL).mock(
            return_value=httpx.Response(200, json=_wrap_template({}))
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_missing_consents_key_returns_empty(self):
        inner = {"categoryFilters": {"\\_harmonized_consent\\": ["other.c1"]}}
        respx.get(TEMPLATE_URL).mock(
            return_value=httpx.Response(200, json=_wrap_template(inner))
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_non_list_consents_returns_empty(self):
        inner = {"categoryFilters": {"\\_consents\\": "not-a-list"}}
        respx.get(TEMPLATE_URL).mock(
            return_value=httpx.Response(200, json=_wrap_template(inner))
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_malformed_template_raises(self):
        respx.get(TEMPLATE_URL).mock(
            return_value=httpx.Response(200, json={"queryTemplate": "{not json"})
        )
        with pytest.raises(PicSureConnectionError, match="malformed"):
            fetch_consents(_make_client())

    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.get(TEMPLATE_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(PicSureConnectionError, match="consent"):
            fetch_consents(_make_client())

    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.get(TEMPLATE_URL).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(PicSureConnectionError):
            fetch_consents(_make_client())
