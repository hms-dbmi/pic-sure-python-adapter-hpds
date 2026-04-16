import httpx
import pytest
import respx

from picsure._models.session import Session
from picsure._services.connect import connect
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureValidationError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token-abc123"


class TestConnectSuccess:
    @respx.mock
    def test_returns_session(self, profile_response, resources_response):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(platform=BASE_URL, token=TOKEN)

        assert isinstance(session, Session)

    @respx.mock
    def test_session_has_correct_email(self, profile_response, resources_response):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(platform=BASE_URL, token=TOKEN)

        assert session._user_email == "researcher@university.edu"

    @respx.mock
    def test_session_has_resources(self, profile_response, resources_response):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(platform=BASE_URL, token=TOKEN)

        assert len(session._resources) == 2
        uuids = {r.uuid for r in session._resources}
        assert "resource-uuid-aaaa-1111" in uuids

    @respx.mock
    def test_custom_url_has_no_resource_uuid(
        self, profile_response, resources_response
    ):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(platform=BASE_URL, token=TOKEN)

        assert session._resource_uuid is None

    @respx.mock
    def test_prints_success_message(self, profile_response, resources_response, capsys):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        connect(platform=BASE_URL, token=TOKEN)

        captured = capsys.readouterr()
        assert "successfully connected" in captured.out.lower()
        assert "researcher@university.edu" in captured.out

    @respx.mock
    def test_prints_token_expiration(
        self, profile_response, resources_response, capsys
    ):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        connect(platform=BASE_URL, token=TOKEN)

        captured = capsys.readouterr()
        assert "token expires" in captured.out.lower()
        assert "2026-06-15" in captured.out


class TestConnectAuthErrors:
    @respx.mock
    def test_401_raises_auth_error(self):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        with pytest.raises(PicSureAuthError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)

        msg = str(exc_info.value)
        assert "invalid or expired" in msg.lower()
        assert "picsure.connect()" in msg

    @respx.mock
    def test_403_raises_auth_error(self):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )

        with pytest.raises(PicSureAuthError):
            connect(platform=BASE_URL, token=TOKEN)


class TestConnectConnectionErrors:
    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(PicSureConnectionError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)

        msg = str(exc_info.value)
        assert BASE_URL in msg

    @respx.mock
    def test_resource_fetch_failure_raises_connection_error(self, profile_response):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(PicSureConnectionError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)

        msg = str(exc_info.value)
        assert "resources" in msg.lower()


class TestConnectResourceUuid:
    @respx.mock
    def test_explicit_uuid_overrides_platform(
        self, profile_response, resources_response
    ):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(
            platform=BASE_URL, token=TOKEN, resource_uuid="my-custom-uuid"
        )

        assert session._resource_uuid == "my-custom-uuid"

    @respx.mock
    def test_custom_url_no_uuid_prints_resources(
        self, profile_response, resources_response, capsys
    ):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        connect(platform=BASE_URL, token=TOKEN)

        captured = capsys.readouterr()
        assert "Available resources" in captured.out
        assert "setResourceID" in captured.out

    @respx.mock
    def test_custom_url_with_uuid_no_prompt(
        self, profile_response, resources_response, capsys
    ):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json=profile_response)
        )
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        connect(platform=BASE_URL, token=TOKEN, resource_uuid="resource-uuid-aaaa-1111")

        captured = capsys.readouterr()
        assert "Available resources" not in captured.out


class TestConnectValidation:
    def test_invalid_platform_raises_validation_error(self):
        with pytest.raises(PicSureValidationError):
            connect(platform="NotARealPlatform", token=TOKEN)
