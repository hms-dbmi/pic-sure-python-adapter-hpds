import httpx
import pytest
import respx

from picsure._dev.config import DevConfig
from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportConnectionError,
    TransportServerError,
)
from picsure.errors import PicSureServerError

BASE_URL = "https://test.example.com"
TOKEN = "test-token-abc"


@respx.mock
def test_get_json_emits_http_event_when_enabled():
    respx.get(f"{BASE_URL}/picsure/info/resources").mock(
        return_value=httpx.Response(200, json={"uuid-1": "hpds"})
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.get_json("/picsure/info/resources")

    events = cfg.buffer.snapshot()
    assert len(events) == 1
    e = events[0]
    assert e.kind == "http"
    assert e.name == "/picsure/info/resources"
    assert e.status == 200
    assert e.retry == 0
    assert e.error is None
    assert e.bytes_received is not None and e.bytes_received > 0


@respx.mock
def test_post_json_emits_http_event_with_bytes_sent():
    respx.post(f"{BASE_URL}/picsure/search/abc").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.post_json("/picsure/search/abc", body={"query": "x"})

    events = cfg.buffer.snapshot()
    assert len(events) == 1
    assert events[0].bytes_sent is not None and events[0].bytes_sent > 0


@respx.mock
def test_byte_counters_are_not_swapped():
    """A small request against a large response pins the direction.

    The two counters used to be called ``bytes_in`` / ``bytes_out`` with the
    request size under ``bytes_in``, so an assertion that only checked
    "both are positive" passed either way round. Sizing the two bodies
    differently is what makes a swap fail.
    """
    small_request = {"q": "x"}
    large_response = {"results": ["y" * 500]}
    respx.post(f"{BASE_URL}/picsure/search/abc").mock(
        return_value=httpx.Response(200, json=large_response)
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.post_json("/picsure/search/abc", body=small_request)

    event = cfg.buffer.snapshot()[0]
    assert event.bytes_sent is not None
    assert event.bytes_received is not None
    assert event.bytes_sent < 100
    assert event.bytes_received > 500
    assert event.bytes_sent < event.bytes_received


@respx.mock
def test_retry_emits_two_events():
    respx.get(f"{BASE_URL}/flaky").mock(
        side_effect=[
            httpx.Response(500, text="err"),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.get_json("/flaky")

    events = cfg.buffer.snapshot()
    assert [e.retry for e in events] == [0, 1]
    assert [e.status for e in events] == [500, 200]


@respx.mock
def test_stale_connection_retry_emits_error_event_then_success():
    # Exact wording httpx/httpcore use for a stale pooled connection; the
    # retry policy discriminates RemoteProtocolError variants on it, so the
    # simulated failure must stay faithful to real traffic.
    respx.post(f"{BASE_URL}/query/sync").mock(
        side_effect=[
            httpx.RemoteProtocolError(
                "Server disconnected without sending a response."
            ),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.post_json("/query/sync", body={"q": "x"})

    events = cfg.buffer.snapshot()
    # The stale first attempt is recorded as an error event; the retry that
    # succeeds on a fresh connection is recorded as an http event.
    assert any(
        e.kind == "error" and e.error == "RemoteProtocolError" and e.retry == 0
        for e in events
    )
    assert any(e.kind == "http" and e.status == 200 and e.retry == 1 for e in events)


@respx.mock
def test_connection_error_emits_error_event_then_raises():
    respx.get(f"{BASE_URL}/down").mock(side_effect=httpx.ConnectError("refused"))
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    with pytest.raises(TransportConnectionError):
        client.get_json("/down")

    events = cfg.buffer.snapshot()
    assert any(e.kind == "error" and e.error == "ConnectError" for e in events)


@respx.mock
def test_server_error_after_retries_emits_events_for_each_attempt():
    respx.get(f"{BASE_URL}/bad").mock(return_value=httpx.Response(500, text="boom"))
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    with pytest.raises(TransportServerError):
        client.get_json("/bad")

    events = cfg.buffer.snapshot()
    http_events = [e for e in events if e.kind == "http"]
    assert [e.retry for e in http_events] == [0, 1]
    assert all(e.status == 500 for e in http_events)
    assert any(e.kind == "error" and e.error == "TransportServerError" for e in events)


@respx.mock
def test_auth_error_emits_error_event_before_raising():
    from picsure._transport.errors import TransportAuthenticationError

    respx.get(f"{BASE_URL}/denied").mock(return_value=httpx.Response(401, text="nope"))
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    with pytest.raises(TransportAuthenticationError):
        client.get_json("/denied")

    events = cfg.buffer.snapshot()
    assert any(
        e.kind == "error" and e.error == "TransportAuthenticationError" for e in events
    )


@respx.mock
def test_no_events_when_disabled():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))
    cfg = DevConfig(enabled=False, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.get_json("/x")
    assert cfg.buffer.snapshot() == []


@respx.mock
def test_no_events_when_dev_config_is_none():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))
    client = PicSureClient(base_url=BASE_URL, token=TOKEN)  # default: no dev_config
    client.get_json("/x")  # Must not raise.


@respx.mock
def test_participant_query_body_not_logged():
    respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
        return_value=httpx.Response(200, content=b"patient_id,sex\nP1,M\n")
    )
    cfg = DevConfig(enabled=True, max_events=10)
    client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)

    client.post_raw(
        "/picsure/v3/query/sync",
        body={"query": {"expectedResultType": "DATAFRAME", "fields": []}},
    )

    events = cfg.buffer.snapshot()
    http_events = [e for e in events if e.kind == "http"]
    assert http_events[-1].metadata.get("redacted") == "participant"
    assert (
        http_events[-1].bytes_received is not None
        and http_events[-1].bytes_received > 0
    )


class TestStreamedDownloadEvents:
    """A download that goes to disk must still be accounted for.

    Participant and timestamp queries stream to a temporary file rather
    than buffering the body, and the streaming helper does not go through
    ``_request``.  Without its own event, switching those queries to the
    streaming path silently removed them from the dev-mode buffer.
    """

    @staticmethod
    def _run(query_type: str, content: bytes, cfg: DevConfig):
        from picsure._models.clause import Clause, PhenotypicFilterType
        from picsure._services._hpds_paths import query_prefix
        from picsure._services.query_run import run_query

        url = f"{BASE_URL}{query_prefix('auth', v3=True)}/query/sync"
        respx.post(url).mock(return_value=httpx.Response(200, content=content))
        client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)
        clause = Clause(
            keys=["\\a\\b\\"], type=PhenotypicFilterType.FILTER, categories=["X"]
        )
        return run_query(client, clause, query_type, backend="auth")

    @respx.mock
    @pytest.mark.parametrize("query_type", ["participant", "timestamp"])
    def test_a_streamed_query_emits_one_http_event(self, query_type):
        cfg = DevConfig(enabled=True, max_events=10)

        self._run(query_type, b"patient_id,age\nP1,42\n", cfg)

        http_events = [e for e in cfg.buffer.snapshot() if e.kind == "http"]
        assert len(http_events) == 1
        assert http_events[0].status == 200

    @respx.mock
    def test_the_event_reports_the_bytes_written_to_disk(self):
        cfg = DevConfig(enabled=True, max_events=10)
        content = b"patient_id,age\nP1,42\nP2,51\n"

        self._run("participant", content, cfg)

        http_events = [e for e in cfg.buffer.snapshot() if e.kind == "http"]
        assert http_events[0].bytes_received == len(content)

    @respx.mock
    def test_a_streamed_participant_body_is_still_marked_redacted(self):
        # The buffered path marked these; losing the mark would make a
        # participant-bearing body look safe to log.
        cfg = DevConfig(enabled=True, max_events=10)

        self._run("participant", b"patient_id,age\nP1,42\n", cfg)

        http_events = [e for e in cfg.buffer.snapshot() if e.kind == "http"]
        assert http_events[0].metadata.get("redacted") == "participant"

    @respx.mock
    def test_a_failed_download_emits_an_error_event(self):
        from picsure._models.clause import Clause, PhenotypicFilterType
        from picsure._services._hpds_paths import query_prefix
        from picsure._services.query_run import run_query

        url = f"{BASE_URL}{query_prefix('auth', v3=True)}/query/sync"
        respx.post(url).mock(return_value=httpx.Response(500, text="boom"))
        cfg = DevConfig(enabled=True, max_events=10)
        client = PicSureClient(base_url=BASE_URL, token=TOKEN, dev_config=cfg)
        clause = Clause(
            keys=["\\a\\b\\"], type=PhenotypicFilterType.FILTER, categories=["X"]
        )

        with pytest.raises(PicSureServerError):
            run_query(client, clause, "participant", backend="auth")

        errors = [e for e in cfg.buffer.snapshot() if e.kind == "error"]
        assert errors and errors[0].error == "TransportServerError"

    @respx.mock
    def test_nothing_is_emitted_when_dev_mode_is_off(self):
        cfg = DevConfig(enabled=False, max_events=10)

        self._run("participant", b"patient_id,age\nP1,42\n", cfg)

        assert cfg.buffer.snapshot() == []
