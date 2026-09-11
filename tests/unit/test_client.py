import ssl
import warnings

import httpx
import pytest
import respx

from picsure._transport.client import (
    DATA_TIMEOUT_SECONDS,
    VALIDATION_TIMEOUT_SECONDS,
    PicSureClient,
    _resolve_verify,
    json_object,
)
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportConsentDeniedError,
    TransportConsentLookupError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportServerError,
    TransportTLSError,
    TransportValidationError,
)
from picsure.errors import PicSureError, PicSureQueryError, PicSureValidationError

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


class TestJsonBodyShapes:
    """The JSON accessors return an object or an array, and nothing else."""

    @respx.mock
    def test_get_json_returns_top_level_array(self):
        respx.get(f"{BASE_URL}/picsure/dictionary/facets").mock(
            return_value=httpx.Response(200, json=[{"name": "study"}])
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        result = client.get_json("/picsure/dictionary/facets")

        assert result == [{"name": "study"}]

    @respx.mock
    @pytest.mark.parametrize("payload", [5, "text", True])
    def test_scalar_top_level_raises_value_error(self, payload):
        respx.get(f"{BASE_URL}/odd").mock(
            return_value=httpx.Response(200, json=payload)
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(ValueError, match="at the top level"):
            client.get_json("/odd")

    @respx.mock
    def test_json_null_top_level_raises_value_error(self):
        # A literal `null` body decodes fine, so it reaches the shape check
        # rather than failing in the decoder like an empty body does.
        respx.get(f"{BASE_URL}/odd").mock(
            return_value=httpx.Response(
                200,
                content=b"null",
                headers={"content-type": "application/json"},
            )
        )

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(ValueError, match="NoneType at the top level"):
            client.get_json("/odd")

    @respx.mock
    def test_post_json_scalar_top_level_raises_value_error(self):
        respx.post(f"{BASE_URL}/odd").mock(return_value=httpx.Response(200, json=7))

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        with pytest.raises(ValueError, match="at the top level"):
            client.post_json("/odd", body={})

    def test_json_object_passes_a_dict_through(self):
        payload = {"email": "user@example.com"}

        assert json_object(payload, path="/psama/user/me") is payload

    def test_json_object_rejects_an_array_with_a_public_error(self):
        with pytest.raises(PicSureQueryError, match="expected an object"):
            json_object([1, 2], path="/psama/user/me")

    def test_json_object_error_is_in_the_public_hierarchy(self):
        with pytest.raises(PicSureError):
            json_object([], path="/psama/user/me")


class TestPublicExceptionExports:
    def test_consent_errors_are_exported_from_package(self):
        from picsure import PicSureConsentDeniedError, PicSureConsentLookupError

        assert PicSureConsentDeniedError.__name__ == "PicSureConsentDeniedError"
        assert PicSureConsentLookupError.__name__ == "PicSureConsentLookupError"


class TestPicSureClient4xxMapping:
    @respx.mock
    def test_buffered_consent_denied_raises_typed_error(self):
        respx.get(f"{BASE_URL}/saved-result").mock(
            return_value=httpx.Response(
                403,
                json={
                    "errorType": "consent_denied",
                    "message": "You no longer have consent for this saved result",
                },
            )
        )

        with pytest.raises(TransportConsentDeniedError) as exc_info:
            PicSureClient(base_url=BASE_URL, token=TOKEN).get_json("/saved-result")

        exc = exc_info.value
        assert exc.status_code == 403
        assert exc.error_type == "consent_denied"
        assert exc.server_message == "You no longer have consent for this saved result"

    @respx.mock
    def test_generic_403_remains_authentication_error(self):
        respx.get(f"{BASE_URL}/saved-result").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )

        with pytest.raises(TransportAuthenticationError) as exc_info:
            PicSureClient(base_url=BASE_URL, token=TOKEN).get_json("/saved-result")

        assert exc_info.value.status_code == 403

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
    def test_get_consent_lookup_failed_raises_typed_error_without_retry(self):
        route = respx.get(f"{BASE_URL}/saved-result").mock(
            return_value=httpx.Response(
                502,
                json={
                    "errorType": "consent_lookup_failed",
                    "message": "Unable to resolve caller consents",
                },
            )
        )

        with pytest.raises(TransportConsentLookupError) as exc_info:
            PicSureClient(base_url=BASE_URL, token=TOKEN).get_json("/saved-result")

        exc = exc_info.value
        assert exc.status_code == 502
        assert exc.error_type == "consent_lookup_failed"
        assert exc.server_message == "Unable to resolve caller consents"
        assert route.call_count == 1

    @respx.mock
    def test_streaming_consent_denied_raises_typed_error(self):
        route = respx.post(f"{BASE_URL}/query/saved/result").mock(
            return_value=httpx.Response(
                403,
                json={
                    "errorType": "consent_denied",
                    "message": "You no longer have consent for this saved result",
                },
            )
        )
        client = PicSureClient(base_url=BASE_URL, token=TOKEN)

        with (
            pytest.raises(TransportConsentDeniedError) as exc_info,
            client.post_raw_stream("/query/saved/result", body={}),
        ):
            pass

        assert exc_info.value.status_code == 403
        assert exc_info.value.error_type == "consent_denied"
        assert (
            exc_info.value.server_message
            == "You no longer have consent for this saved result"
        )
        assert route.call_count == 1

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


class TestRefusalStatusWinsOverBody:
    """Every 401/403 lands in the auth family, structured body or not."""

    @respx.mock
    def test_401_with_a_structured_body_is_still_an_authentication_error(self):
        respx.get(f"{BASE_URL}/saved-result").mock(
            return_value=httpx.Response(
                401,
                json={"errorType": "consent_lookup_failed", "message": "no idea"},
            )
        )
        with pytest.raises(TransportAuthenticationError) as exc_info:
            PicSureClient(base_url=BASE_URL, token=TOKEN).get_json("/saved-result")
        assert exc_info.value.status_code == 401

    @respx.mock
    def test_403_with_an_unrelated_error_type_is_an_authentication_error(self):
        respx.get(f"{BASE_URL}/saved-result").mock(
            return_value=httpx.Response(
                403,
                json={"errorType": "consent_lookup_failed", "message": "no idea"},
            )
        )
        with pytest.raises(TransportAuthenticationError) as exc_info:
            PicSureClient(base_url=BASE_URL, token=TOKEN).get_json("/saved-result")
        assert exc_info.value.status_code == 403

    @respx.mock
    def test_403_consent_denied_still_keeps_the_server_payload(self):
        respx.get(f"{BASE_URL}/saved-result").mock(
            return_value=httpx.Response(
                403,
                json={"errorType": "consent_denied", "message": "no consent"},
            )
        )
        with pytest.raises(TransportConsentDeniedError) as exc_info:
            PicSureClient(base_url=BASE_URL, token=TOKEN).get_json("/saved-result")
        assert exc_info.value.server_message == "no consent"


# A self-signed certificate that exists only to be loaded as a CA bundle.
# Its common name is what proves a path reached httpx as a trust store
# rather than being coerced to a boolean: `verify=True` loads the system
# store, which does not contain this.
_TEST_CA_NAME = "picsure-adapter-test-ca"
_TEST_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIDJzCCAg+gAwIBAgIUEzjJ6dTRDoWD7AU7QRhwu+5cLZwwDQYJKoZIhvcNAQEL
BQAwIjEgMB4GA1UEAwwXcGljc3VyZS1hZGFwdGVyLXRlc3QtY2EwIBcNMjYwOTEw
MTMyMjM2WhgPMjEyNjA4MTcxMzIyMzZaMCIxIDAeBgNVBAMMF3BpY3N1cmUtYWRh
cHRlci10ZXN0LWNhMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApbGD
ri2Uc+NmS+4aTM1UDlVWuImLUnn4I/QkzMjy+Wyfzoz+w4C+EVeYLBotKgSXvtet
tREa/mAWhI1fCebwixC0wiEitkWZ9gBswNMFVa4vMVl0eg/nz00k9PqqzP3LUrMf
EcfstzgRpp0s0ladkFdvwdOKG0ZD9khJLLDe14o0AwRW1zwLDF9GfhLxuXH7SYpQ
r0hclxQ8byoWowic1lK5FEom/634Mexci2WUjFs8cQAFA2LVCNguU8RFfIH1wTfe
Gk2/ci7YE3LYrRW+2CdP9vndNEJOro8ECd7QMdjCw/U6OYiJoieBgeG5qmM2OD1q
oho/FXbIk2VBDzkGTQIDAQABo1MwUTAdBgNVHQ4EFgQUfSeyCHtzlYJzbf6J+il3
02nRhXswHwYDVR0jBBgwFoAUfSeyCHtzlYJzbf6J+il302nRhXswDwYDVR0TAQH/
BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAQ89X054NpCahXHHVqJqBxscQ+0CU
RHqbmxbXezg07Xroh/wzneNMTL96KRHqVXkM83guRhBlRsC4G8nbuhq1COeVa4q3
qmrdl44G7S/QEmCGPwf/BxgZP1vTV4Gwgy83fvvWTxqCFpLRrVnYZaEYlzPXn26k
4TY13VPdUHpd/UdJa6aXo4iTr4GWkm2diBWIdrPZ3kmchyEZxQKL/21Rhjuea6n2
SYAkqAmvIOCgjjVPnttAT4sY6kFHK5EGTvH0LhuLJVbQAP/pVi+H2M2K3X8UTHzG
1znIUhXntt4lK7+A/30cT7Fxptymi4PqoOl8ic8pkLktJfDg0E4HNfqclg==
-----END CERTIFICATE-----
"""


def _ssl_context(client: PicSureClient) -> ssl.SSLContext:
    """The SSL context httpx actually built for this client.

    Asserting on this rather than on anything the adapter recorded for
    itself: the question is what the HTTP client was told to do, and only
    the context it built can answer that.
    """
    return client._http._transport._pool._ssl_context


def _ca_common_names(context: ssl.SSLContext) -> list[str]:
    return [
        value
        for ca in context.get_ca_certs()
        for rdn in ca.get("subject", ())
        for key, value in rdn
        if key == "commonName"
    ]


@pytest.fixture(autouse=True)
def _no_ssl_verify_env(monkeypatch):
    """Keep an ambient PICSURE_SSL_VERIFY out of these assertions."""
    monkeypatch.delenv("PICSURE_SSL_VERIFY", raising=False)


@pytest.fixture
def ca_bundle(tmp_path):
    """A real CA bundle file on disk, for the path-forwarding cases."""
    path = tmp_path / "test-ca.pem"
    path.write_text(_TEST_CA_PEM)
    return path


class TestVerifyDefaults:
    """PYR-3: the one setting where a silent regression is a security bug."""

    def test_defaults_to_verifying(self):
        client = PicSureClient(base_url=BASE_URL, token="t")
        context = _ssl_context(client)
        assert context.verify_mode is ssl.CERT_REQUIRED
        assert context.check_hostname is True

    def test_verify_none_is_the_same_as_omitting_it(self):
        explicit = _ssl_context(PicSureClient(base_url=BASE_URL, verify=None))
        omitted = _ssl_context(PicSureClient(base_url=BASE_URL))
        assert explicit.verify_mode is omitted.verify_mode
        assert explicit.verify_mode is ssl.CERT_REQUIRED

    def test_verify_false_turns_verification_off(self):
        context = _ssl_context(PicSureClient(base_url=BASE_URL, verify=False))
        assert context.verify_mode is ssl.CERT_NONE
        # check_hostname has to go too: a context that still checks the
        # hostname would fail before it ever skipped the chain.
        assert context.check_hostname is False

    def test_verify_true_keeps_verification_on(self):
        context = _ssl_context(PicSureClient(base_url=BASE_URL, verify=True))
        assert context.verify_mode is ssl.CERT_REQUIRED


class TestVerifyEnvironmentFallback:
    """PYR-3: PICSURE_SSL_VERIFY is the documented fallback."""

    @pytest.mark.parametrize("raw", ["false", "0", "no", "off", "FALSE", " False "])
    def test_falsey_env_matches_verify_false(self, monkeypatch, raw):
        monkeypatch.setenv("PICSURE_SSL_VERIFY", raw)
        from_env = _ssl_context(PicSureClient(base_url=BASE_URL))
        monkeypatch.delenv("PICSURE_SSL_VERIFY")
        from_arg = _ssl_context(PicSureClient(base_url=BASE_URL, verify=False))
        assert from_env.verify_mode is from_arg.verify_mode
        assert from_env.verify_mode is ssl.CERT_NONE
        assert from_env.check_hostname == from_arg.check_hostname

    @pytest.mark.parametrize("raw", ["true", "1", "yes", "on", "TRUE"])
    def test_truthy_env_verifies(self, monkeypatch, raw):
        monkeypatch.setenv("PICSURE_SSL_VERIFY", raw)
        assert _ssl_context(PicSureClient(base_url=BASE_URL)).verify_mode is (
            ssl.CERT_REQUIRED
        )

    def test_empty_env_falls_back_to_verifying(self, monkeypatch):
        monkeypatch.setenv("PICSURE_SSL_VERIFY", "")
        assert _ssl_context(PicSureClient(base_url=BASE_URL)).verify_mode is (
            ssl.CERT_REQUIRED
        )

    def test_explicit_false_beats_a_truthy_env(self, monkeypatch):
        monkeypatch.setenv("PICSURE_SSL_VERIFY", "true")
        context = _ssl_context(PicSureClient(base_url=BASE_URL, verify=False))
        assert context.verify_mode is ssl.CERT_NONE

    def test_explicit_true_beats_a_falsey_env(self, monkeypatch):
        monkeypatch.setenv("PICSURE_SSL_VERIFY", "false")
        context = _ssl_context(PicSureClient(base_url=BASE_URL, verify=True))
        assert context.verify_mode is ssl.CERT_REQUIRED

    def test_env_path_is_loaded_as_a_ca_bundle(self, monkeypatch, ca_bundle):
        monkeypatch.setenv("PICSURE_SSL_VERIFY", str(ca_bundle))
        context = _ssl_context(PicSureClient(base_url=BASE_URL))
        assert _ca_common_names(context) == [_TEST_CA_NAME]

    def test_explicit_path_beats_a_falsey_env(self, monkeypatch, ca_bundle):
        monkeypatch.setenv("PICSURE_SSL_VERIFY", "false")
        context = _ssl_context(PicSureClient(base_url=BASE_URL, verify=str(ca_bundle)))
        assert context.verify_mode is ssl.CERT_REQUIRED
        assert _ca_common_names(context) == [_TEST_CA_NAME]


class TestVerifyCaBundlePath:
    """PYR-3: the case most likely to break silently."""

    def test_path_is_forwarded_as_a_trust_store_not_a_boolean(self, ca_bundle):
        client = PicSureClient(base_url=BASE_URL, verify=str(ca_bundle))
        context = _ssl_context(client)

        # Coercing the path to True would load the system trust store,
        # which holds many CAs and not this one; coercing it to False
        # would leave no verification at all.
        assert _ca_common_names(context) == [_TEST_CA_NAME]
        assert context.verify_mode is ssl.CERT_REQUIRED

    def test_a_ca_bundle_is_not_the_system_trust_store(self, ca_bundle):
        pinned = _ssl_context(PicSureClient(base_url=BASE_URL, verify=str(ca_bundle)))
        system = _ssl_context(PicSureClient(base_url=BASE_URL, verify=True))
        assert _ca_common_names(pinned) != _ca_common_names(system)

    def test_a_directory_is_accepted_as_a_ca_path(self, tmp_path):
        # OpenSSL takes a hashed CA directory as well as a file, so the
        # existence check must not insist on a regular file.
        client = PicSureClient(base_url=BASE_URL, verify=str(tmp_path))
        assert _ssl_context(client).verify_mode is ssl.CERT_REQUIRED

    def test_a_ca_path_is_loaded_without_a_deprecation_warning(self, ca_bundle):
        # httpx 0.28 deprecates verify=<str>, so the path must be turned
        # into an SSL context here.  The documented API still takes a
        # path; only the plumbing changed.  Without this the adapter's
        # documented verify="/path/to/ca.pem" breaks on a future httpx.
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            client = PicSureClient(base_url=BASE_URL, verify=str(ca_bundle))

        assert _ca_common_names(_ssl_context(client)) == [_TEST_CA_NAME]

    def test_a_ca_path_from_the_env_is_loaded_without_a_deprecation_warning(
        self, monkeypatch, ca_bundle
    ):
        monkeypatch.setenv("PICSURE_SSL_VERIFY", str(ca_bundle))

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            client = PicSureClient(base_url=BASE_URL)

        assert _ca_common_names(_ssl_context(client)) == [_TEST_CA_NAME]

    def test_the_resolver_hands_httpx_a_context_not_a_path(self, ca_bundle):
        assert isinstance(_resolve_verify(str(ca_bundle)), ssl.SSLContext)


class TestVerifyMissingCaBundle:
    """RL-19: a bad CA path must name itself, not raise a bare OS error."""

    def test_missing_path_raises_the_package_error(self, tmp_path):
        missing = tmp_path / "nope" / "ca.pem"
        with pytest.raises(PicSureValidationError) as exc_info:
            PicSureClient(base_url=BASE_URL, verify=str(missing))
        message = str(exc_info.value)
        assert str(missing) in message
        assert "verify" in message

    def test_missing_path_is_not_a_bare_file_not_found(self, tmp_path):
        missing = tmp_path / "ca.pem"
        with pytest.raises(PicSureValidationError):
            PicSureClient(base_url=BASE_URL, verify=str(missing))

    def test_missing_env_path_names_the_env_var(self, monkeypatch, tmp_path):
        missing = tmp_path / "ca.pem"
        monkeypatch.setenv("PICSURE_SSL_VERIFY", str(missing))
        with pytest.raises(PicSureValidationError) as exc_info:
            PicSureClient(base_url=BASE_URL)
        message = str(exc_info.value)
        assert str(missing) in message
        assert "PICSURE_SSL_VERIFY" in message

    def test_the_message_offers_a_way_forward(self, tmp_path):
        with pytest.raises(PicSureValidationError) as exc_info:
            PicSureClient(base_url=BASE_URL, verify=str(tmp_path / "ca.pem"))
        message = str(exc_info.value)
        assert "verify=True" in message
        assert "verify=False" in message


class TestVerifyRejectedCertificate:
    """PYR-3: verification actually refusing a certificate.

    respx replaces a side-effect exception's ``__cause__`` with its own
    wrapper, which destroys the chain ``_certificate_verification_failure``
    walks. These drive a real httpx transport instead.
    """

    def _client_behind_a_bad_certificate(self) -> PicSureClient:
        client = PicSureClient(base_url=BASE_URL, token="t")
        client._http = httpx.Client(
            base_url=BASE_URL, transport=_CertRejectingTransport()
        )
        return client

    def test_rejected_certificate_maps_to_a_tls_error(self):
        client = self._client_behind_a_bad_certificate()
        with pytest.raises(TransportTLSError) as exc_info:
            client.get_json("/psama/user/me")
        message = str(exc_info.value)
        assert "TLS certificate verification failed" in message
        assert "test.example.com" in message
        assert "verify=False" in message
        assert "PICSURE_SSL_VERIFY" in message

    def test_a_tls_error_is_still_a_connection_error(self):
        client = self._client_behind_a_bad_certificate()
        with pytest.raises(TransportConnectionError):
            client.get_json("/psama/user/me")

    def test_rejected_certificate_is_not_retried(self):
        transport = _CertRejectingTransport()
        client = PicSureClient(base_url=BASE_URL, token="t")
        client._http = httpx.Client(base_url=BASE_URL, transport=transport)
        with pytest.raises(TransportTLSError):
            client.get_json("/psama/user/me")
        assert transport.attempts == 1


class _CertRejectingTransport(httpx.BaseTransport):
    """Fails the way an untrusted certificate really does, cause intact."""

    def __init__(self) -> None:
        self.attempts = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        try:
            raise ssl.SSLCertVerificationError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "self signed certificate"
            )
        except ssl.SSLCertVerificationError as cause:
            raise httpx.ConnectError(
                "certificate verify failed", request=request
            ) from cause


class TestClientTimeouts:
    """PYR-4: ten minutes for data, seconds for the connect-time check."""

    def test_defaults_to_the_data_deadline(self):
        client = PicSureClient(base_url=BASE_URL, token="t")
        assert client._timeout == DATA_TIMEOUT_SECONDS
        assert client._http.timeout.read == DATA_TIMEOUT_SECONDS

    def test_ten_minutes_is_the_data_deadline(self):
        assert DATA_TIMEOUT_SECONDS == 600.0

    def test_the_validation_deadline_is_much_shorter(self):
        assert VALIDATION_TIMEOUT_SECONDS == 15.0
        assert VALIDATION_TIMEOUT_SECONDS < DATA_TIMEOUT_SECONDS

    def test_explicit_timeout_overrides_the_default(self):
        client = PicSureClient(base_url=BASE_URL, token="t", timeout=12.5)
        assert client._timeout == 12.5
        assert client._http.timeout.read == 12.5

    @respx.mock
    def test_per_request_timeout_overrides_the_client_default(self):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json={})
        )
        client = PicSureClient(base_url=BASE_URL, token="t")
        client.get_json("/psama/user/me", timeout=VALIDATION_TIMEOUT_SECONDS)

        timeout = respx.calls[0].request.extensions["timeout"]
        assert timeout["connect"] == VALIDATION_TIMEOUT_SECONDS
        assert timeout["read"] == VALIDATION_TIMEOUT_SECONDS

    @respx.mock
    def test_omitting_the_per_request_timeout_keeps_the_client_default(self):
        respx.get(f"{BASE_URL}/psama/user/me").mock(
            return_value=httpx.Response(200, json={})
        )
        client = PicSureClient(base_url=BASE_URL, token="t")
        client.get_json("/psama/user/me")

        # Not None, which httpx reads as "no deadline at all".
        timeout = respx.calls[0].request.extensions["timeout"]
        assert timeout["read"] == DATA_TIMEOUT_SECONDS
