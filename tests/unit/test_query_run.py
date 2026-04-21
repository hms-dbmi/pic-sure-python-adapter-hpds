import httpx
import pytest
import respx

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.count_result import CountResult
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
QUERY_URL = f"{BASE_URL}/picsure/v3/query/sync"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _simple_clause() -> Clause:
    return Clause(keys=["\\phs1\\sex\\"], type=ClauseType.FILTER, categories=["Male"])


class TestRunQueryCount:
    @respx.mock
    def test_returns_count_result(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"1234"))
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "count")
        assert isinstance(result, CountResult)
        assert result.value == 1234
        assert result.margin is None
        assert result.cap is None
        assert result.obfuscated is False
        assert result.raw == "1234"

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
        query = body["query"]
        assert query["expectedResultType"] == "COUNT"
        assert query["select"] == []
        assert query["genomicFilters"] == []
        assert query["picsureId"] is None
        assert query["id"] is None
        pheno = query["phenotypicClause"]
        assert pheno["phenotypicFilterType"] == "FILTER"
        assert pheno["conceptPath"] == "\\phs1\\sex\\"
        assert pheno["values"] == ["Male"]
        assert pheno["not"] is False

    @respx.mock
    def test_does_not_send_authorization_filters(self):
        # PSAMA populates authorizationFilters server-side from the user's
        # token. A client-asserted list is treated as tampering and can be
        # rejected with a 401, so we must never send the key.
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"7")
        )
        client = _make_client()
        run_query(client, RESOURCE_UUID, _simple_clause(), "count")

        import json

        body = json.loads(route.calls[0].request.content)
        assert "authorizationFilters" not in body["query"]

    @respx.mock
    def test_invalid_count_raises_query_error(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"not a number")
        )
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "count")

    @respx.mock
    def test_count_strips_surrounding_whitespace(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"  567  \n")
        )
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "count")
        assert result.value == 567
        assert result.obfuscated is False

    @respx.mock
    def test_noisy_count_preserves_margin(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content="11309 \u00b13".encode())
        )
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "count")
        assert result.value == 11309
        assert result.margin == 3
        assert result.cap is None
        assert result.obfuscated is True

    @respx.mock
    def test_noisy_count_without_spaces(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content="42\u00b13".encode())
        )
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "count")
        assert result.value == 42
        assert result.margin == 3

    @respx.mock
    def test_suppressed_count_has_cap_and_null_value(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"< 10"))
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "count")
        assert result.value is None
        assert result.margin is None
        assert result.cap == 10
        assert result.obfuscated is True

    @respx.mock
    def test_suppressed_count_no_space(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"<10"))
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "count")
        assert result.value is None
        assert result.cap == 10

    @respx.mock
    def test_malformed_margin_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content="10 \u00b1".encode())
        )
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "count")

    @respx.mock
    def test_empty_response_raises(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "count")


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
        assert body["query"]["expectedResultType"] == "DATAFRAME"

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
        assert body["query"]["expectedResultType"] == "DATAFRAME_TIMESERIES"

    @respx.mock
    def test_returns_dataframe(self):
        csv = b"patient_id,variable,date,value\nP001,bp,2024-01-15,120\n"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=csv))
        client = _make_client()
        df = run_query(client, RESOURCE_UUID, _simple_clause(), "timestamp")
        assert len(df) == 1
        assert "date" in df.columns


class TestRunQueryCrossCount:
    @respx.mock
    def test_sends_cross_count_result_type(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"\\\\phs000001\\\\": "42"}')
        )
        client = _make_client()
        run_query(client, RESOURCE_UUID, _simple_clause(), "cross_count")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["expectedResultType"] == "CROSS_COUNT"

    @respx.mock
    def test_returns_dict_of_count_results(self):
        # Mirrors the real server shape: concept_path -> count string.
        # Includes one of each count shape (exact, noisy, suppressed).
        payload = (
            '{"\\\\phs000001\\\\consent_a\\\\": "42",'
            ' "\\\\phs000001\\\\consent_b\\\\": "11309 \u00b13",'
            ' "\\\\phs000002\\\\": "< 10"}'
        ).encode()
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=payload))
        client = _make_client()
        result = run_query(client, RESOURCE_UUID, _simple_clause(), "cross_count")

        assert isinstance(result, dict)
        assert set(result.keys()) == {
            "\\phs000001\\consent_a\\",
            "\\phs000001\\consent_b\\",
            "\\phs000002\\",
        }
        exact = result["\\phs000001\\consent_a\\"]
        assert isinstance(exact, CountResult)
        assert exact.value == 42
        assert exact.obfuscated is False

        noisy = result["\\phs000001\\consent_b\\"]
        assert noisy.value == 11309
        assert noisy.margin == 3

        suppressed = result["\\phs000002\\"]
        assert suppressed.value is None
        assert suppressed.cap == 10

    @respx.mock
    def test_malformed_json_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"not json")
        )
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="cross-count"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "cross_count")

    @respx.mock
    def test_non_object_json_raises(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"[1,2,3]"))
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="cross-count"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "cross_count")

    @respx.mock
    def test_invalid_count_value_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"\\\\p\\\\": "banana"}')
        )
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(client, RESOURCE_UUID, _simple_clause(), "cross_count")


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
        pheno = body["query"]["phenotypicClause"]
        assert pheno["operator"] == "AND"
        assert pheno["not"] is False
        assert len(pheno["phenotypicClauses"]) == 2

    @respx.mock
    def test_mixed_group_with_select_raises(self):
        # Mixing SELECT clauses inside a phenotypic group is not supported.
        # SELECTs should be kept outside the ClauseGroup (top-level of the
        # query) so they can be lifted to the ``select`` array cleanly.
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"100"))
        out = Clause(keys=["\\out_a\\", "\\out_b\\"], type=ClauseType.SELECT)
        group = ClauseGroup(
            clauses=[_simple_clause(), out],
            operator=GroupOperator.AND,
        )
        client = _make_client()
        with pytest.raises(PicSureValidationError, match="SELECT"):
            run_query(client, RESOURCE_UUID, group, "count")

    @respx.mock
    def test_group_with_only_selects_yields_null_phenotypic(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"100")
        )
        select_a = Clause(keys=["\\a\\"], type=ClauseType.SELECT)
        select_b = Clause(keys=["\\b\\"], type=ClauseType.SELECT)
        group = ClauseGroup(
            clauses=[select_a, select_b],
            operator=GroupOperator.AND,
        )
        client = _make_client()
        run_query(client, RESOURCE_UUID, group, "count")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["phenotypicClause"] is None
        assert body["query"]["select"] == ["\\a\\", "\\b\\"]

    @respx.mock
    def test_single_select_clause_yields_null_phenotypic(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"100")
        )
        select = Clause(keys=["\\a\\"], type=ClauseType.SELECT)
        client = _make_client()
        run_query(client, RESOURCE_UUID, select, "count")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["phenotypicClause"] is None
        assert body["query"]["select"] == ["\\a\\"]


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
