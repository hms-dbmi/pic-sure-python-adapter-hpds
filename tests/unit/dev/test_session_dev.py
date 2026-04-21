from __future__ import annotations

import httpx
import respx

from picsure._dev.config import DevConfig
from picsure._models.resource import Resource
from picsure._models.session import Session
from picsure._transport.client import PicSureClient

BASE_URL = "https://test.example.com"
RESOURCE_UUID = "uuid-1"


def _make_session(dev_enabled: bool) -> Session:
    cfg = DevConfig(enabled=dev_enabled, max_events=100)
    client = PicSureClient(base_url=BASE_URL, token="t", dev_config=cfg)
    return Session(
        client=client,
        user_email="u@e",
        token_expiration="N/A",
        resources=[Resource(uuid=RESOURCE_UUID, name="hpds", description="")],
        resource_uuid=RESOURCE_UUID,
        consents=[],
        total_concepts=100,
        dev_config=cfg,
    )


def test_dev_mode_property_reflects_config():
    on = _make_session(dev_enabled=True)
    off = _make_session(dev_enabled=False)
    assert on.dev_mode is True
    assert off.dev_mode is False


def test_dev_events_empty_when_off_has_columns():
    off = _make_session(dev_enabled=False)
    df = off.dev_events()
    assert len(df) == 0
    assert "timestamp" in df.columns and "kind" in df.columns


def test_dev_stats_empty_when_off_has_columns():
    off = _make_session(dev_enabled=False)
    df = off.dev_stats()
    assert len(df) == 0
    assert "calls" in df.columns


def test_dev_clear_is_noop_when_off():
    off = _make_session(dev_enabled=False)
    off.dev_clear()  # Must not raise.


@respx.mock
def test_runquery_count_emits_http_and_function_events():
    respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
        return_value=httpx.Response(200, content=b"42")
    )
    session = _make_session(dev_enabled=True)

    from picsure._models.clause import Clause, ClauseType

    clause = Clause(keys=["\\phs1\\sex\\"], type=ClauseType.FILTER, categories=["Male"])
    session.runQuery(clause, type="count")

    events = session.dev_events()
    kinds = list(events["kind"])
    assert "http" in kinds and "function" in kinds
    fn_rows = events[events["kind"] == "function"]
    assert any(fn_rows["name"] == "session.runQuery")


@respx.mock
def test_dev_stats_aggregates_from_live_calls():
    respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
        return_value=httpx.Response(200, content=b"42")
    )
    session = _make_session(dev_enabled=True)

    from picsure._models.clause import Clause, ClauseType

    clause = Clause(keys=["\\phs1\\sex\\"], type=ClauseType.FILTER, categories=["Male"])
    session.runQuery(clause, type="count")
    session.runQuery(clause, type="count")

    stats = session.dev_stats()
    fn = stats[(stats["kind"] == "function") & (stats["name"] == "session.runQuery")]
    assert len(fn) == 1
    assert fn.iloc[0]["calls"] == 2


@respx.mock
def test_dev_clear_empties_buffer():
    respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
        return_value=httpx.Response(200, content=b"1")
    )
    session = _make_session(dev_enabled=True)

    from picsure._models.clause import Clause, ClauseType

    clause = Clause(keys=["\\phs1\\sex\\"], type=ClauseType.FILTER, categories=["Male"])
    session.runQuery(clause, type="count")
    assert len(session.dev_events()) > 0

    session.dev_clear()
    assert len(session.dev_events()) == 0
