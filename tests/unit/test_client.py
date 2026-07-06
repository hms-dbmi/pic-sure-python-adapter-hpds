import httpx
import pytest
import respx

from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportServerError,
    TransportValidationError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token-abc123"

# The message httpx raises when a pooled keep-alive connection was closed by
# the server before it responded -- the stale-connection symptom under test.
STALE_CONN_MSG = "Server disconnected without sending a response."

# The message httpx raises when the connection dies part-way through the
# response body.  Same exception class as STALE_CONN_MSG, but here the server
# received -- and may have executed -- the request, so a blind POST retry
# would double-execute it.
TRUNCATED_BODY_MSG = (
    "peer closed connection without sending complete message body "
    "(received 5 bytes, expected 100)"
)


class _FailsMidStream(httpx.SyncByteStream):
    """Response stream that yields one chunk, then dies like a reset."""

    def __iter__(self):
        yield b"first-chunk"
        raise httpx.ReadError("Connection reset by peer")


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
    def test_post_raw_csv_content(self):
        csv = b"patient_id,sex,age\nP001,Male,45\nP002,Female,52\n"
        respx.post(f"{BASE_URL}/query/sync").mock(
            return_value=httpx.Response(200, content=csv)
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        result = client.post_raw("/query/sync")

        assert b"patient_id" in result
        assert result.count(b"\n") == 3

    @respx.mock
    def test_whitespace_only_token_omits_auth_header(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(base_url=BASE_URL, token="   ")
        client.get_json("/some/path")

        request = route.calls[0].request
        assert "authorization" not in request.headers
        assert request.headers["request-source"] == "Open"

    @respx.mock
    def test_token_is_stripped_before_auth_header(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(base_url=BASE_URL, token="  tok-abc  ")
        client.get_json("/some/path")

        request = route.calls[0].request
        assert request.headers["authorization"] == "Bearer tok-abc"
        assert request.headers["request-source"] == "Authorized"


class TestPicSureClient4xxMapping:
    @respx.mock
    def test_400_raises_validation_error(self):
        respx.get(f"{BASE_URL}/bad").mock(
            return_value=httpx.Response(400, text="Bad Request")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportValidationError) as exc_info:
            client.get_json("/bad")
        assert exc_info.value.status_code == 400

    @respx.mock
    def test_422_raises_validation_error(self):
        respx.post(f"{BASE_URL}/bad").mock(
            return_value=httpx.Response(422, text="Unprocessable")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportValidationError) as exc_info:
            client.post_json("/bad", body={"x": 1})
        assert exc_info.value.status_code == 422

    @respx.mock
    def test_404_raises_not_found_error(self):
        respx.get(f"{BASE_URL}/nope").mock(
            return_value=httpx.Response(404, text="Not Found")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportNotFoundError) as exc_info:
            client.get_json("/nope")
        assert exc_info.value.status_code == 404

    @respx.mock
    def test_429_with_retry_after_raises_rate_limit_error(self):
        respx.post(f"{BASE_URL}/busy").mock(
            return_value=httpx.Response(
                429,
                text="Too many requests",
                headers={"Retry-After": "30"},
            )
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportRateLimitError) as exc_info:
            client.post_json("/busy", body={})
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 30

    @respx.mock
    def test_429_without_retry_after(self):
        respx.get(f"{BASE_URL}/busy").mock(
            return_value=httpx.Response(429, text="Too many")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportRateLimitError) as exc_info:
            client.get_json("/busy")
        assert exc_info.value.retry_after is None

    @respx.mock
    def test_429_with_non_integer_retry_after(self):
        respx.get(f"{BASE_URL}/busy").mock(
            return_value=httpx.Response(
                429,
                text="Too many",
                headers={"Retry-After": "Mon, 01 Jan 2100 00:00:00 GMT"},
            )
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportRateLimitError) as exc_info:
            client.get_json("/busy")
        assert exc_info.value.retry_after is None


class TestPicSureClientRetryScoping:
    @respx.mock
    def test_post_502_does_not_retry(self):
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            return_value=httpx.Response(502, text="bad gateway")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportServerError):
            client.post_json("/query/sync", body={"q": "x"})
        assert route.call_count == 1

    @respx.mock
    def test_get_502_does_retry(self):
        route = respx.get(f"{BASE_URL}/flaky").mock(
            return_value=httpx.Response(502, text="bad gateway")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportServerError):
            client.get_json("/flaky")
        assert route.call_count == 2

    @respx.mock
    def test_post_connect_error_does_retry(self):
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=httpx.ConnectError("refused")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportConnectionError):
            client.post_json("/query/sync", body={"q": "x"})
        assert route.call_count == 2

    @respx.mock
    def test_post_timeout_does_not_retry(self):
        # Read-timeouts on POST may mean the server already processed the
        # request; retrying would risk duplicating a non-idempotent mutation.
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportConnectionError):
            client.post_json("/query/sync", body={"q": "x"})
        assert route.call_count == 1

    @respx.mock
    def test_post_raw_502_does_not_retry(self):
        route = respx.post(f"{BASE_URL}/fail").mock(
            return_value=httpx.Response(502, content=b"bad gateway")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(TransportServerError):
            client.post_raw("/fail", body={"q": "x"})
        assert route.call_count == 1

    @respx.mock
    def test_close_is_idempotent(self):
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        client.close()
        # A second close should not raise.
        client.close()
        assert client._http.is_closed


class TestPicSureClientStaleConnection:
    """A pooled keep-alive connection the server has silently closed surfaces
    as httpx.RemoteProtocolError ("Server disconnected without sending a
    response"). Because the server never produced a response, it never
    processed the request, so retrying once on a fresh connection is safe for
    every method -- including non-idempotent POST.
    """

    @respx.mock
    def test_post_remote_protocol_error_retries_then_succeeds(self):
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=[
                httpx.RemoteProtocolError(STALE_CONN_MSG),
                httpx.Response(200, json={"recovered": True}),
            ]
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        result = client.post_json("/query/sync", body={"q": "x"})

        assert result == {"recovered": True}
        assert route.call_count == 2  # stale connection + retry on a fresh one

    @respx.mock
    def test_post_remote_protocol_error_exhausts_raises_connection_error(self):
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=httpx.RemoteProtocolError(STALE_CONN_MSG)
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        with pytest.raises(TransportConnectionError, match="stale"):
            client.post_json("/query/sync", body={"q": "x"})
        assert route.call_count == 2  # initial + 1 retry

    @respx.mock
    def test_get_remote_protocol_error_retries_then_succeeds(self):
        route = respx.get(f"{BASE_URL}/flaky").mock(
            side_effect=[
                httpx.RemoteProtocolError(STALE_CONN_MSG),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        result = client.get_json("/flaky")

        assert result == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_post_raw_stream_remote_protocol_error_retries_then_succeeds(self):
        route = respx.post(f"{BASE_URL}/export").mock(
            side_effect=[
                httpx.RemoteProtocolError(STALE_CONN_MSG),
                httpx.Response(200, content=b"streamed-bytes"),
            ]
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        with client.post_raw_stream("/export", body={"q": "x"}) as response:
            data = b"".join(response.iter_bytes())

        assert data == b"streamed-bytes"
        assert route.call_count == 2

    @respx.mock
    def test_post_raw_stream_remote_protocol_error_exhausts_raises(self):
        route = respx.post(f"{BASE_URL}/export").mock(
            side_effect=httpx.RemoteProtocolError(STALE_CONN_MSG)
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        # Both attempts fail while opening the stream, so the failure
        # surfaces from __enter__ -- a with-block body would be dead code.
        stream = client.post_raw_stream("/export", body={"q": "x"})
        with pytest.raises(TransportConnectionError, match="stale"):
            stream.__enter__()
        assert route.call_count == 2


class TestPicSureClientRetrySafety:
    """Retry/mapping policy across the httpx failure modes.

    Two invariants:  (1) a request is re-sent only when it provably never
    reached the server (or, for GETs, when re-sending is idempotent-safe);
    (2) every httpx.TransportError surfaces as a Transport* exception --
    never as a raw httpx error.
    """

    @respx.mock
    def test_post_truncated_body_does_not_retry(self):
        # Same exception class as the stale-connection case, but the server
        # already received (and may have executed) the POST -- re-sending
        # would double-execute it.
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=httpx.RemoteProtocolError(TRUNCATED_BODY_MSG)
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        with pytest.raises(TransportConnectionError):
            client.post_json("/query/sync", body={"q": "x"})
        assert route.call_count == 1

    @respx.mock
    def test_get_truncated_body_retries(self):
        route = respx.get(f"{BASE_URL}/flaky").mock(
            side_effect=[
                httpx.RemoteProtocolError(TRUNCATED_BODY_MSG),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        assert client.get_json("/flaky") == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_post_write_error_retries_then_succeeds(self):
        # EPIPE while sending: the RST flavor of a stale pooled connection.
        # The server cannot process a request it never fully received.
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=[
                httpx.WriteError("[Errno 32] Broken pipe"),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        assert client.post_json("/query/sync", body={"q": "x"}) == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_post_read_error_maps_without_retry(self):
        # ECONNRESET while reading the response: the POST may have been
        # processed, so no retry -- but it must map, not escape raw.
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=httpx.ReadError("[Errno 54] Connection reset by peer")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        with pytest.raises(TransportConnectionError):
            client.post_json("/query/sync", body={"q": "x"})
        assert route.call_count == 1

    @respx.mock
    def test_get_read_error_retries_then_succeeds(self):
        route = respx.get(f"{BASE_URL}/flaky").mock(
            side_effect=[
                httpx.ReadError("[Errno 54] Connection reset by peer"),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        assert client.get_json("/flaky") == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_proxy_error_maps_without_retry(self):
        route = respx.get(f"{BASE_URL}/x").mock(
            side_effect=httpx.ProxyError("407 Proxy Authentication Required")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        with pytest.raises(TransportConnectionError):
            client.get_json("/x")
        assert route.call_count == 1

    @respx.mock
    def test_unsupported_protocol_maps_without_retry(self):
        route = respx.post(f"{BASE_URL}/x").mock(
            side_effect=httpx.UnsupportedProtocol("Request URL is missing scheme")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        with pytest.raises(TransportConnectionError):
            client.post_json("/x", body={})
        assert route.call_count == 1

    @respx.mock
    def test_post_connect_timeout_retries_then_succeeds(self):
        # The TCP/TLS handshake never completed, so the request was never
        # sent -- exactly as retry-safe as ConnectError.
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=[
                httpx.ConnectTimeout("timed out"),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        assert client.post_json("/query/sync", body={"q": "x"}) == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_post_pool_timeout_retries_then_succeeds(self):
        # The request never left the local connection pool.
        route = respx.post(f"{BASE_URL}/query/sync").mock(
            side_effect=[
                httpx.PoolTimeout("pool timeout"),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        assert client.post_json("/query/sync", body={"q": "x"}) == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_stream_mid_body_failure_maps(self):
        # The server drops the connection while the caller drains the
        # stream: no retry is possible (bytes are already consumed), but the
        # error must surface as TransportConnectionError, not raw httpx.
        respx.post(f"{BASE_URL}/export").mock(
            return_value=httpx.Response(200, stream=_FailsMidStream())
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        with (
            pytest.raises(TransportConnectionError, match="streaming"),
            client.post_raw_stream("/export", body={"q": "x"}) as response,
        ):
            for _ in response.iter_bytes():
                pass

    @respx.mock
    def test_stream_error_body_read_failure_still_maps_by_status(self):
        # 500 whose error body can't be read (connection drops mid-read):
        # the status alone must still drive the mapping.
        respx.post(f"{BASE_URL}/fail").mock(
            return_value=httpx.Response(500, stream=_FailsMidStream())
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        stream = client.post_raw_stream("/fail", body={"q": "x"})
        with pytest.raises(TransportServerError) as exc_info:
            stream.__enter__()
        assert exc_info.value.status_code == 500

    @respx.mock
    def test_stream_read_timeout_does_not_retry(self):
        # A timeout waiting for response headers on this POST may mean the
        # server is still executing it; re-sending could double-submit.
        route = respx.post(f"{BASE_URL}/export").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        stream = client.post_raw_stream("/export", body={"q": "x"})
        with pytest.raises(TransportConnectionError, match="timed out"):
            stream.__enter__()
        assert route.call_count == 1


class TestPicSureClientCorrelationHeaders:
    @respx.mock
    def test_sends_session_id_and_client_type_headers(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(
            base_url=BASE_URL,
            token=TOKEN,
            session_id="sess-abc-123",
            client_type="PYTHON_ADAPTER",
        )
        client.get_json("/some/path")

        headers = route.calls[0].request.headers
        assert headers["x-session-id"] == "sess-abc-123"
        assert headers["x-client-type"] == "PYTHON_ADAPTER"
        assert headers["user-agent"].startswith("picsure-python-adapter/")

    @respx.mock
    def test_r_adapter_client_type_shapes_user_agent(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(
            base_url=BASE_URL,
            token=TOKEN,
            session_id="sess-r",
            client_type="R_ADAPTER",
        )
        client.get_json("/some/path")

        headers = route.calls[0].request.headers
        assert headers["x-client-type"] == "R_ADAPTER"
        assert headers["user-agent"].startswith("picsure-r-adapter/")

    @respx.mock
    def test_defaults_to_python_adapter_and_omits_empty_session_id(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        client.get_json("/some/path")

        headers = route.calls[0].request.headers
        assert headers["x-client-type"] == "PYTHON_ADAPTER"
        assert headers["user-agent"].startswith("picsure-python-adapter/")
        assert "x-session-id" not in headers
