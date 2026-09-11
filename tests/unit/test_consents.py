import httpx
import pytest
import respx

from picsure._services.consents import fetch_consents
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureAuthenticationError,
    PicSureAuthorizationError,
    PicSureConnectionError,
    PicSureConsentDeniedError,
    PicSureServerError,
    PicSureTLSError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
CONSENTS_URL = f"{BASE_URL}/psama/user/me/consents"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _wrap_consents(consents: object) -> dict:
    """Shape the PSAMA UserConsents entity around a consents map."""
    return {
        "uuid": "8f14e45f-ceea-467a-a3cd-9f1ee0e5f0a1",
        "userId": "3c59dc04-8e88-450b-a0f2-3a1e1f1b1c2d",
        "consents": consents,
    }


class TestFetchConsents:
    @respx.mock
    def test_consent_denied_raises_typed_error(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                403,
                json={
                    "errorType": "consent_denied",
                    "message": "You no longer have consent for this saved result",
                },
            )
        )

        with pytest.raises(PicSureConsentDeniedError) as exc_info:
            fetch_consents(_make_client())

        exc = exc_info.value
        assert exc.status_code == 403
        assert exc.error_type == "consent_denied"
        assert exc.server_message == "You no longer have consent for this saved result"

    @respx.mock
    def test_returns_consents_list(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wrap_consents(
                    {"\\_consents\\": ["phs000007.c1", "phs000179.c1", "phs001013.c1"]}
                ),
            )
        )
        consents = fetch_consents(_make_client())
        assert consents == ["phs000007.c1", "phs000179.c1", "phs001013.c1"]

    @respx.mock
    def test_ignores_harmonized_and_topmed_keys(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                200,
                json=_wrap_consents(
                    {
                        "\\_harmonized_consent\\": ["other.c1"],
                        "\\_consents\\": ["phs000007.c1"],
                        "\\_topmed_consents\\": ["tm.c1"],
                    }
                ),
            )
        )
        assert fetch_consents(_make_client()) == ["phs000007.c1"]

    @respx.mock
    def test_missing_consents_object_returns_empty(self):
        respx.get(CONSENTS_URL).mock(return_value=httpx.Response(200, json={}))
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_null_consents_returns_empty(self):
        """A user with no consent row gets a null consents map, not an error."""
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(200, json=_wrap_consents(None))
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_empty_consents_object_returns_empty(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(200, json=_wrap_consents({}))
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_missing_consents_key_returns_empty(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                200, json=_wrap_consents({"\\_harmonized_consent\\": ["other.c1"]})
            )
        )
        assert fetch_consents(_make_client()) == []

    @respx.mock
    def test_non_list_consents_returns_empty(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(
                200, json=_wrap_consents({"\\_consents\\": "not-a-list"})
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


class TestFetchConsentsRefusalIsNotAvailability:
    @respx.mock
    def test_401_names_the_token(self):
        respx.get(CONSENTS_URL).mock(
            return_value=httpx.Response(401, text="Token is invalid or expired")
        )
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            fetch_consents(_make_client())
        message = str(exc_info.value)
        assert "token was rejected" in message
        assert "unavailable" not in message

    @respx.mock
    def test_403_names_the_permission(self):
        respx.get(CONSENTS_URL).mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(PicSureAuthorizationError) as exc_info:
            fetch_consents(_make_client())
        message = str(exc_info.value)
        assert "not authorized for it" in message
        assert "unavailable" not in message

    @respx.mock
    def test_5xx_is_a_server_error_and_still_a_connection_error(self):
        respx.get(CONSENTS_URL).mock(return_value=httpx.Response(503, text="down"))
        with pytest.raises(PicSureServerError) as exc_info:
            fetch_consents(_make_client())
        assert isinstance(exc_info.value, PicSureConnectionError)
        assert not isinstance(exc_info.value, PicSureTLSError)
