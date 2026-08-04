import httpx
import pytest
import respx

from picsure._services.consents import (
    CONSENTS_KEY,
    HARMONIZED_CONSENTS_KEY,
    TOPMED_CONSENTS_KEY,
    consent_values,
    fetch_consents,
)
from picsure._transport.client import PicSureClient
from picsure.errors import PicSureConnectionError

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
CONSENTS_URL = f"{BASE_URL}/psama/user/me/consents"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _response(consents: dict) -> dict:
    """The UserConsentsResponse wire shape: two keys, and no more."""
    return {"userId": "6ac1b1df-1c66-4b5c-8f5a-1f5c8c1e0a11", "consents": consents}


class TestConceptPaths:
    def test_are_the_keys_bdc_consents_builder_writes(self):
        # A drift of a single backslash reads as "no consents" and silently
        # drops every authorization filter, so these are pinned byte for byte.
        assert CONSENTS_KEY == "\\_consents\\"
        assert HARMONIZED_CONSENTS_KEY == "\\_harmonized_consent\\"
        assert TOPMED_CONSENTS_KEY == "\\_topmed_consents\\"


class TestConsentValues:
    def test_returns_the_identifiers_verbatim(self):
        consents = {CONSENTS_KEY: ["phs000007.c1", "open_access-1000Genomes"]}
        assert consent_values(consents, CONSENTS_KEY) == [
            "phs000007.c1",
            "open_access-1000Genomes",
        ]

    def test_unknown_concept_path_is_nothing_authorized(self):
        # The server documents its keys as KNOWN, not exhaustive: a path this
        # client does not recognise is an empty answer, never an error.
        assert consent_values({CONSENTS_KEY: ["a"]}, "\\_future_consent\\") == []

    def test_malformed_values_read_as_empty(self):
        assert consent_values({CONSENTS_KEY: "not-a-list"}, CONSENTS_KEY) == []
        assert consent_values({CONSENTS_KEY: None}, CONSENTS_KEY) == []

    def test_non_map_consents_reads_as_empty(self):
        assert consent_values(None, CONSENTS_KEY) == []
        assert consent_values("nope", CONSENTS_KEY) == []


class TestFetchConsents:
    @respx.mock
    def test_returns_consents_list(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                200,
                json=_response(
                    {CONSENTS_KEY: ["phs000007.c1", "phs000179.c1", "phs001013.c1"]}
                ),
            )
        )
        consents = fetch_consents(_make_client())
        assert consents == ["phs000007.c1", "phs000179.c1", "phs001013.c1"]

    @respx.mock
    def test_ignores_harmonized_and_topmed_keys(self):
        # Only the full consent list drives dictionary calls; the harmonized
        # and genomic subsets are already contained in it.
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                200,
                json=_response(
                    {
                        HARMONIZED_CONSENTS_KEY: ["other.c1"],
                        CONSENTS_KEY: ["phs000007.c1"],
                        TOPMED_CONSENTS_KEY: ["tm.c1"],
                    }
                ),
            )
        )
        assert fetch_consents(_make_client()) == ["phs000007.c1"]

    @respx.mock
    def test_user_with_no_stored_consents_returns_empty(self):
        # The server answers an empty map rather than an error for a user with
        # no stored record; that is "nothing authorized", not a failure.
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(200, json=_response({}))
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_missing_consents_key_returns_empty(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                200, json=_response({HARMONIZED_CONSENTS_KEY: ["other.c1"]})
            )
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_non_list_consents_returns_empty(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                200, json=_response({CONSENTS_KEY: "not-a-list"})
            )
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(PicSureConnectionError, match="consent"):
            fetch_consents(_make_client())

    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.get(CONSENTS_URL).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(PicSureConnectionError):
            fetch_consents(_make_client())
