import httpx
import pytest
import respx

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._services.query_run import run_query
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
RESOURCE_UUID = "resource-uuid-aaaa-1111"
QUERY_URL = f"{BASE_URL}/picsure/query/sync"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _simple_clause() -> Clause:
    return Clause(keys=["\\phs1\\sex\\"], type=ClauseType.FILTER, categories=["Male"])


class TestRunQueryCount:
    @respx.mock
    def test_returns_int(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"1234"))
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "count")
        assert result == 1234
        assert isinstance(result, int)

    @respx.mock
    def test_sends_correct_body(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"42")
        )
        client = _make_client()
        run_query(client, RESOURCE_UUID, _simple_clause(), "count")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["resourceUUID"] == RESOURCE_UUID
        assert body["query"]["type"] == "clause"
        assert body["expectedResultType"] == "COUNT"

    @respx.mock
    def test_invalid_count_raises_query_error(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"not a number")
        )
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "count")

    @respx.mock
    def test_count_strips_whitespace(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"  567  \n")
        )
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "count")
        assert result == 567


class TestRunQueryParticipant:
    @respx.mock
    def test_returns_dataframe(self, participant_response):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=participant_response)
        )
        client = _make_client()
        df = run_query(client, RESOURCE_UUID, _simple_clause(), "participant")
        assert len(df) == 5
        assert "patient_id" in df.columns
        assert "sex" in df.columns

    @respx.mock
    def test_sends_participant_result_type(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"id\n1\n")
        )
        client = _make_client()
        run_query(client, RESOURCE_UUID, _simple_clause(), "participant")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["expectedResultType"] == "DATAFRAME"

    @respx.mock
    def test_empty_csv_returns_empty_dataframe(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        client = _make_client()
        df = run_query(client, RESOURCE_UUID, _simple_clause(), "participant")
        assert len(df) == 0


class TestRunQueryTimestamp:
    @respx.mock
    def test_sends_timestamp_result_type(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"id,date,val\n1,2024-01-01,120\n")
        )
        client = _make_client()
        run_query(client, RESOURCE_UUID, _simple_clause(), "timestamp")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["expectedResultType"] == "DATAFRAME_TIMESERIES"

    @respx.mock
    def test_returns_dataframe(self):
        csv = b"patient_id,variable,date,value\nP001,bp,2024-01-15,120\n"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=csv))
        client = _make_client()
        df = run_query(client, RESOURCE_UUID, _simple_clause(), "timestamp")
        assert len(df) == 1
        assert "date" in df.columns


class TestRunQueryWithClauseGroup:
    @respx.mock
    def test_clause_group_serialized(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"100")
        )
        age = Clause(keys=["\\age\\"], type=ClauseType.FILTER, min=40.0)
        group = ClauseGroup(
            clauses=[_simple_clause(), age],
            operator=GroupOperator.AND,
        )
        client = _make_client()
        run_query(client, RESOURCE_UUID, group, "count")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["type"] == "and"
        assert len(body["query"]["children"]) == 2


class TestRunQueryValidation:
    def test_invalid_query_type_raises(self):
        client = _make_client()
        with pytest.raises(PicSureValidationError, match="not a valid query type"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "invalid")

    def test_invalid_query_type_lists_valid(self):
        client = _make_client()
        with pytest.raises(PicSureValidationError, match="count"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "typo")


class TestRunQueryErrors:
    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        client = _make_client()
        with pytest.raises(PicSureConnectionError, match="query"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "count")

    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.post(QUERY_URL).mock(side_effect=httpx.ConnectError("Connection refused"))
        client = _make_client()
        with pytest.raises(PicSureConnectionError):
            run_query(client, RESOURCE_UUID, _simple_clause(), "count")
