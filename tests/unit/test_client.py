import httpx
import pytest
import respx

from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportServerError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token-abc123"


class TestPicSureClient:
    @respx.mock
    def test_get_json_sends_auth_header(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        result = client.get_json("/some/path")

        assert result == {"ok": True}
        assert route.called
        request = route.calls[0].request
        assert request.headers["authorization"] == f"Bearer {TOKEN}"

    @respx.mock
    def test_empty_token_omits_auth_header(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(base_url=BASE_URL, token="")
        client.get_json("/some/path")

        assert "authorization" not in route.calls[0].request.headers

    @respx.mock
    def test_default_token_omits_auth_header(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(base_url=BASE_URL)
        client.get_json("/some/path")

        assert "authorization" not in route.calls[0].request.headers

    @respx.mock
    def test_post_json_sends_body_and_auth_header(self):
        route = respx.post(f"{BASE_URL}/query").mock(
            return_value=httpx.Response(200, json={"count": 42})
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        result = client.post_json("/query", body={"filter": "age > 40"})

        assert result == {"count": 42}
        request = route.calls[0].request
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert request.headers["content-type"] == "application/json"

    @respx.mock
    def test_401_raises_authentication_error(self):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportAuthenticationError) as exc_info:
            client.get_json("/psama/user/me")
        assert exc_info.value.status_code == 401

    @respx.mock
    def test_403_raises_authentication_error(self):
        respx.get(f"{BASE_URL}/resource").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportAuthenticationError) as exc_info:
            client.get_json("/resource")
        assert exc_info.value.status_code == 403

    @respx.mock
    def test_500_retries_then_raises_server_error(self):
        route = respx.get(f"{BASE_URL}/flaky").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportServerError) as exc_info:
            client.get_json("/flaky")
        assert exc_info.value.status_code == 500
        assert route.call_count == 2  # initial + 1 retry

    @respx.mock
    def test_500_then_200_succeeds_on_retry(self):
        respx.get(f"{BASE_URL}/flaky").mock(
            side_effect=[
                httpx.Response(500, text="error"),
                httpx.Response(200, json={"recovered": True}),
            ]
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        result = client.get_json("/flaky")
        assert result == {"recovered": True}

    @respx.mock
    def test_connection_error_raises_transport_connection_error(self):
        respx.get(f"{BASE_URL}/down").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportConnectionError, match="Connection refused"):
            client.get_json("/down")

    @respx.mock
    def test_timeout_raises_transport_connection_error(self):
        respx.get(f"{BASE_URL}/slow").mock(side_effect=httpx.ReadTimeout("timed out"))

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportConnectionError, match="timed out"):
            client.get_json("/slow")

    @respx.mock
    def test_close_closes_underlying_client(self):
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        client.close()
        assert client._http.is_closed

    @respx.mock
    def test_post_raw_returns_bytes(self):
        respx.post(f"{BASE_URL}/query/sync").mock(
            return_value=httpx.Response(200, content=b"1234")
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        result = client.post_raw("/query/sync", body={"query": "test"})

        assert result == b"1234"
        assert isinstance(result, bytes)

    @respx.mock
    def test_post_raw_sends_auth_header(self):
        route = respx.post(f"{BASE_URL}/data").mock(
            return_value=httpx.Response(200, content=b"csv,data")
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        client.post_raw("/data", body={"q": "x"})

        request = route.calls[0].request
        assert request.headers["authorization"] == f"Bearer {TOKEN}"

    @respx.mock
    def test_post_raw_500_retries_then_raises(self):
        route = respx.post(f"{BASE_URL}/fail").mock(
            return_value=httpx.Response(500, content=b"error")
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportServerError):
            client.post_raw("/fail")
        assert route.call_count == 2

    @respx.mock
    def test_post_raw_csv_content(self):
        csv = b"patient_id,sex,age\nP001,Male,45\nP002,Female,52\n"
        respx.post(f"{BASE_URL}/query/sync").mock(
            return_value=httpx.Response(200, content=csv)
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        result = client.post_raw("/query/sync")

        assert b"patient_id" in result
        assert result.count(b"\n") == 3
