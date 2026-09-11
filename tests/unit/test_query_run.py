import httpx
import pytest
import respx

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.count_result import CountResult
from picsure._models.genomic_filter import GenomicFilter
from picsure._models.query import Query
from picsure._models.query_type import QueryType
from picsure._models.session import Session
from picsure._services._hpds_paths import query_prefix
from picsure._services.query_run import _resolve_query_type, run_query
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureConsentDeniedError,
    PicSureConsentLookupError,
    PicSureQueryError,
    PicSureValidationError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
QUERY_URL = f"{BASE_URL}{query_prefix('auth', v3=True)}/query/sync"
OPEN_QUERY_URL = f"{BASE_URL}{query_prefix('open', v3=True)}/query/sync"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _simple_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\sex\\"], type=PhenotypicFilterType.FILTER, categories=["Male"]
    )


class TestRunQueryCount:
    @respx.mock
    def test_returns_count_result(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"1234"))
        client = _make_client()
        result = run_query(client, _simple_clause(), "count", backend="auth")
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
        run_query(client, _simple_clause(), "count", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        # The gateway selects the HPDS backend by URL path, so the body
        # must not carry a top-level resourceUUID sibling anymore.
        assert "resourceUUID" not in body
        query = body["query"]
        assert query["expectedResultType"] == "COUNT"
        # The clause's own concept path is folded into ``select`` so a
        # query's filter variables are returned without being repeated in
        # includeConcepts.
        assert query["select"] == ["\\phs1\\sex\\"]
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
        run_query(client, _simple_clause(), "count", backend="auth")

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
            run_query(client, _simple_clause(), "count", backend="auth")

    @respx.mock
    def test_count_strips_surrounding_whitespace(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"  567  \n")
        )
        client = _make_client()
        result = run_query(client, _simple_clause(), "count", backend="auth")
        assert result.value == 567
        assert result.obfuscated is False

    @respx.mock
    def test_noisy_count_preserves_margin(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content="11309 \u00b13".encode())
        )
        client = _make_client()
        result = run_query(client, _simple_clause(), "count", backend="auth")
        assert result.value == 11309
        assert result.margin == 3
        assert result.cap is None
        assert result.obfuscated is True

    @respx.mock
    def test_suppressed_count_has_cap_and_null_value(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"< 10"))
        client = _make_client()
        result = run_query(client, _simple_clause(), "count", backend="auth")
        assert result.value is None
        assert result.margin is None
        assert result.cap == 10
        assert result.obfuscated is True

    @respx.mock
    def test_malformed_margin_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content="10 \u00b1".encode())
        )
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(client, _simple_clause(), "count", backend="auth")

    @respx.mock
    def test_empty_response_raises(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="empty response"):
            run_query(client, _simple_clause(), "count", backend="auth")


class TestEmptyCountBodyDiagnostic:
    """RL-14: an empty 200 body means the query probably never ran.

    Verified live: a filter whose shape does not match its concept's type
    (numeric min/max on a categorical concept, or categories on a continuous
    one) returns HTTP 200 with a zero-length body, while a merely unknown
    category value or concept path returns "0". So the empty body points at
    a filter/concept type mismatch, and the message should say so.
    """

    @respx.mock
    def test_message_suggests_the_query_was_not_run(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        with pytest.raises(PicSureQueryError) as exc_info:
            run_query(_make_client(), _simple_clause(), "count", backend="auth")

        message = str(exc_info.value)
        assert "was not run" in message
        assert "min/max" in message
        assert "categorical" in message

    @respx.mock
    def test_message_names_the_filtered_concept(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        with pytest.raises(PicSureQueryError) as exc_info:
            run_query(_make_client(), _simple_clause(), "count", backend="auth")

        assert "\\phs1\\sex\\" in str(exc_info.value)

    @respx.mock
    def test_message_names_genomic_filter_keys(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        query = Query(
            phenotypicFilter=None,
            includeConcepts=(),
            genomicFilters=(GenomicFilter(key="Gene_with_variant", values=("BRCA1",)),),
        )
        with pytest.raises(PicSureQueryError) as exc_info:
            run_query(_make_client(), query, "count", backend="auth")

        assert "Gene_with_variant" in str(exc_info.value)

    @respx.mock
    def test_message_does_not_blame_the_server(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        with pytest.raises(PicSureQueryError) as exc_info:
            run_query(_make_client(), _simple_clause(), "count", backend="auth")

        message = str(exc_info.value).lower()
        for blame in ("malformed", "broken", "invalid response", "server error"):
            assert blame not in message

    @respx.mock
    def test_names_concepts_from_a_nested_clause_group(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        group = ClauseGroup(
            clauses=[
                Clause(
                    keys=["\\a\\"],
                    type=PhenotypicFilterType.FILTER,
                    categories=["x"],
                ),
                ClauseGroup(
                    clauses=[
                        Clause(
                            keys=["\\b\\"],
                            type=PhenotypicFilterType.FILTER,
                            min=1.0,
                        )
                    ],
                    operator=GroupOperator.OR,
                ),
            ],
            operator=GroupOperator.AND,
        )
        with pytest.raises(PicSureQueryError) as exc_info:
            run_query(_make_client(), group, "count", backend="auth")

        message = str(exc_info.value)
        assert "\\a\\" in message
        assert "\\b\\" in message

    def test_describe_filters_tolerates_an_unexpected_body(self):
        from picsure._services.query_run import _describe_filters

        assert _describe_filters({}) == ""
        assert _describe_filters({"query": "not-a-dict"}) == ""
        assert _describe_filters({"query": {}}) == "The query carried no filters."


class TestRunQueryParticipant:
    @respx.mock
    def test_returns_dataframe(self, participant_response):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=participant_response)
        )
        client = _make_client()
        df = run_query(client, _simple_clause(), "participant", backend="auth")
        assert len(df) == 5
        assert "patient_id" in df.columns
        assert "sex" in df.columns

    @respx.mock
    def test_sends_participant_result_type(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"id\n1\n")
        )
        client = _make_client()
        run_query(client, _simple_clause(), "participant", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["expectedResultType"] == "DATAFRAME"

    @respx.mock
    def test_empty_csv_returns_empty_dataframe(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        client = _make_client()
        df = run_query(client, _simple_clause(), "participant", backend="auth")
        assert len(df) == 0


class TestRunQueryTimestamp:
    @respx.mock
    def test_sends_timestamp_result_type(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"id,date,val\n1,2024-01-01,120\n")
        )
        client = _make_client()
        run_query(client, _simple_clause(), "timestamp", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["expectedResultType"] == "DATAFRAME_TIMESERIES"

    @respx.mock
    def test_returns_dataframe(self):
        csv = b"patient_id,variable,date,value\nP001,bp,2024-01-15,120\n"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=csv))
        client = _make_client()
        df = run_query(client, _simple_clause(), "timestamp", backend="auth")
        assert len(df) == 1
        assert "date" in df.columns


class TestRunQueryParticipantMalformed:
    @respx.mock
    def test_inconsistent_columns_raises_query_error(self):
        # Rows with mismatched field counts trigger pandas ParserError.
        # We wrap that as PicSureQueryError with a preview so the user
        # sees an actionable message instead of a raw pandas traceback.
        body = b"a,b,c\n1,2,3\n4,5,6,7,8\n"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=body))
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="malformed CSV"):
            run_query(client, _simple_clause(), "participant", backend="auth")

    @respx.mock
    def test_malformed_csv_error_includes_preview(self):
        # The preview in the error message lets the user spot a proxy
        # error page or truncated response without enabling debug logs.
        body = b"a,b,c\n1,2,3\n4,5,6,7,8\nmarker-xyz\n"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=body))
        client = _make_client()
        with pytest.raises(PicSureQueryError) as excinfo:
            run_query(client, _simple_clause(), "participant", backend="auth")
        assert "a,b,c" in str(excinfo.value)

    @respx.mock
    def test_non_utf8_bytes_raises_query_error(self):
        # Bytes that aren't valid UTF-8 should produce a PicSureQueryError
        # rather than leaking a raw UnicodeDecodeError.
        body = b"\xff\xfe\x00\x00invalid utf-8"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=body))
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="malformed CSV"):
            run_query(client, _simple_clause(), "participant", backend="auth")

    @respx.mock
    def test_empty_response_still_returns_empty_dataframe(self):
        # Regression guard: empty body is a legitimate "no rows" signal,
        # not a parse error.
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b""))
        client = _make_client()
        df = run_query(client, _simple_clause(), "participant", backend="auth")
        assert len(df) == 0

    @respx.mock
    def test_whitespace_only_response_returns_empty_dataframe(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"   \n"))
        client = _make_client()
        df = run_query(client, _simple_clause(), "participant", backend="auth")
        assert len(df) == 0


class TestRunQueryCrossCount:
    @respx.mock
    def test_sends_cross_count_result_type(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"\\\\phs000001\\\\": "42"}')
        )
        client = _make_client()
        run_query(client, _simple_clause(), "cross_count", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["expectedResultType"] == "CROSS_COUNT"

    @respx.mock
    def test_cross_count_body_includes_filter_concepts(self):
        # cross_count flows through the same select-folding, so the filter
        # variable lands in the wire select and is therefore cross-counted
        # alongside any includeConcepts.
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"\\\\phs1\\\\sex\\\\": "42"}')
        )
        run_query(_make_client(), _simple_clause(), "cross_count", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["select"] == ["\\phs1\\sex\\"]

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
        result = run_query(client, _simple_clause(), "cross_count", backend="auth")

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
            run_query(client, _simple_clause(), "cross_count", backend="auth")

    @respx.mock
    def test_non_object_json_raises(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"[1,2,3]"))
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="cross-count"):
            run_query(client, _simple_clause(), "cross_count", backend="auth")

    @respx.mock
    def test_invalid_count_value_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"\\\\p\\\\": "banana"}')
        )
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(client, _simple_clause(), "cross_count", backend="auth")

    @respx.mock
    def test_integer_values_direct_hpds_shape(self):
        # When HPDS is queried directly (no aggregate-obfuscation proxy),
        # CountV3Processor.runCrossCounts returns Map<String, Integer>,
        # serialized as integer values: {"\\path\\": 42}.
        payload = b'{"\\\\phs000007\\\\": 42, "\\\\phs000013\\\\": 100}'
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=payload))
        client = _make_client()
        result = run_query(client, _simple_clause(), "cross_count", backend="auth")

        assert isinstance(result, dict)
        assert set(result.keys()) == {"\\phs000007\\", "\\phs000013\\"}

        first = result["\\phs000007\\"]
        assert isinstance(first, CountResult)
        assert first.value == 42
        assert first.margin is None
        assert first.cap is None
        assert first.raw == "42"
        assert first.obfuscated is False

        second = result["\\phs000013\\"]
        assert second.value == 100
        assert second.obfuscated is False

    @respx.mock
    def test_mixed_integers_and_count_strings(self):
        # A response mixing integers (direct HPDS) and count strings
        # (aggregate-obfuscation proxy) should parse both correctly.
        payload = (
            '{"\\\\a\\\\": 42, "\\\\b\\\\": "100 \u00b13", "\\\\c\\\\": "< 10"}'
        ).encode()
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=payload))
        client = _make_client()
        result = run_query(client, _simple_clause(), "cross_count", backend="auth")

        assert result["\\a\\"].value == 42
        assert result["\\a\\"].obfuscated is False

        assert result["\\b\\"].value == 100
        assert result["\\b\\"].margin == 3

        assert result["\\c\\"].value is None
        assert result["\\c\\"].cap == 10

    @respx.mock
    def test_boolean_value_raises(self):
        # True/False are technically `int` subclasses in Python; the guard
        # ``not isinstance(v, bool)`` must route them through the string
        # parser, which then fails as expected.
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"\\\\x\\\\": true}')
        )
        client = _make_client()
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(client, _simple_clause(), "cross_count", backend="auth")


class TestRunQueryWithClauseGroup:
    @respx.mock
    def test_clause_group_serialized(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"100")
        )
        age = Clause(keys=["\\age\\"], type=PhenotypicFilterType.FILTER, min=40.0)
        group = ClauseGroup(
            clauses=[_simple_clause(), age],
            operator=GroupOperator.AND,
        )
        client = _make_client()
        run_query(client, group, "count", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        pheno = body["query"]["phenotypicClause"]
        assert pheno["operator"] == "AND"
        assert pheno["not"] is False
        assert len(pheno["phenotypicClauses"]) == 2

    @respx.mock
    def test_query_with_filter_and_include_concepts(self):
        # A Query carrying both a phenotypic filter and includeConcepts lifts
        # the concepts to the top-level ``select`` array and serializes the
        # filter as ``phenotypicClause``. The filter's own concept path is
        # appended after the explicit includeConcepts.
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"100")
        )
        query = Query(
            phenotypicFilter=_simple_clause(),
            includeConcepts=("\\out_a\\", "\\out_b\\"),
        )
        client = _make_client()
        run_query(client, query, "count", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["select"] == ["\\out_a\\", "\\out_b\\", "\\phs1\\sex\\"]
        pheno = body["query"]["phenotypicClause"]
        assert pheno is not None
        assert pheno["phenotypicFilterType"] == "FILTER"

    @respx.mock
    def test_include_only_query_yields_null_phenotypic(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"100")
        )
        query = Query(includeConcepts=("\\a\\", "\\b\\"))
        client = _make_client()
        run_query(client, query, "count", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["phenotypicClause"] is None
        assert body["query"]["select"] == ["\\a\\", "\\b\\"]

    @respx.mock
    def test_bare_clause_selects_filter_concepts(self):
        # A bare clause with no includeConcepts still returns its filtered
        # variable as an output column — previously this select was empty
        # and only the participant ID came back.
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"100")
        )
        client = _make_client()
        run_query(client, _simple_clause(), "count", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["select"] == ["\\phs1\\sex\\"]
        assert body["query"]["phenotypicClause"] is not None


class TestSelectIncludesFilterConcepts:
    """Filter variables are returned as output columns without includeConcepts."""

    def _select_for(self, query) -> list[str]:
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"1")
        )
        run_query(_make_client(), query, "participant", backend="auth")

        import json

        return json.loads(route.calls[0].request.content)["query"]["select"]

    @respx.mock
    def test_bare_clause_group_selects_all_filter_concepts(self):
        age = Clause(keys=["\\age\\"], type=PhenotypicFilterType.FILTER, min=40.0)
        group = ClauseGroup(clauses=[_simple_clause(), age], operator=GroupOperator.AND)
        assert self._select_for(group) == ["\\phs1\\sex\\", "\\age\\"]

    @respx.mock
    def test_nested_group_collects_every_path_in_order(self):
        age = Clause(keys=["\\age\\"], type=PhenotypicFilterType.FILTER, min=40.0)
        bmi = Clause(keys=["\\bmi\\"], type=PhenotypicFilterType.FILTER, min=18.0)
        inner = ClauseGroup(clauses=[age, bmi], operator=GroupOperator.OR)
        outer = ClauseGroup(
            clauses=[_simple_clause(), inner], operator=GroupOperator.AND
        )
        assert self._select_for(outer) == ["\\phs1\\sex\\", "\\age\\", "\\bmi\\"]

    @respx.mock
    def test_multi_key_clause_contributes_all_keys(self):
        multi = Clause(keys=["\\a\\", "\\b\\"], type=PhenotypicFilterType.ANYRECORD)
        assert self._select_for(multi) == ["\\a\\", "\\b\\"]

    @respx.mock
    def test_include_concepts_come_first_then_filter_vars(self):
        query = Query(
            phenotypicFilter=_simple_clause(),
            includeConcepts=("\\out_a\\",),
        )
        assert self._select_for(query) == ["\\out_a\\", "\\phs1\\sex\\"]

    @respx.mock
    def test_overlap_is_deduped_and_filter_only_var_appended(self):
        # The group filters on sex AND age; age is also explicitly included.
        # age must appear once in its includeConcepts slot (dedup), while the
        # filter-only sex var is appended after — so both the append and the
        # dedup are load-bearing (the assertion fails if either is dropped).
        age = Clause(keys=["\\age\\"], type=PhenotypicFilterType.FILTER, min=40.0)
        group = ClauseGroup(clauses=[_simple_clause(), age], operator=GroupOperator.AND)
        query = Query(phenotypicFilter=group, includeConcepts=("\\age\\", "\\out_b\\"))
        assert self._select_for(query) == ["\\age\\", "\\out_b\\", "\\phs1\\sex\\"]

    @respx.mock
    def test_duplicate_path_across_clauses_is_deduped(self):
        # Two clauses filter the SAME concept path (age > 40 AND age < 80).
        # The path must appear only once in select — this is the case the
        # dict.fromkeys dedup in _split() exists to collapse.
        low = Clause(keys=["\\age\\"], type=PhenotypicFilterType.FILTER, min=40.0)
        high = Clause(keys=["\\age\\"], type=PhenotypicFilterType.FILTER, max=80.0)
        group = ClauseGroup(clauses=[low, high], operator=GroupOperator.AND)
        assert self._select_for(group) == ["\\age\\"]

    @respx.mock
    def test_include_only_query_unaffected(self):
        query = Query(includeConcepts=("\\a\\", "\\b\\"))
        assert self._select_for(query) == ["\\a\\", "\\b\\"]


class TestRunQueryValidation:
    def test_invalid_query_type_raises(self):
        client = _make_client()
        with pytest.raises(PicSureValidationError, match="not a valid query type"):
            run_query(client, _simple_clause(), "invalid", backend="auth")

    def test_plain_dict_query_raises_validation_error(self):
        # A plain dict is not a Clause or ClauseGroup. We want an
        # actionable PicSureValidationError, not an AttributeError from
        # some internal accessor that assumes the API shape.
        client = _make_client()
        with pytest.raises(
            PicSureValidationError,
            match="Clause, ClauseGroup, or Query",
        ):
            run_query(
                client,
                {"keys": ["\\phs1\\sex\\"]},  # type: ignore[arg-type]
                "count",
                backend="auth",
            )


class TestRunQueryErrors:
    @respx.mock
    def test_consent_denied_raises_typed_error(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(
                403,
                json={
                    "errorType": "consent_denied",
                    "message": "You no longer have consent for this saved result",
                },
            )
        )

        with pytest.raises(PicSureConsentDeniedError) as exc_info:
            run_query(_make_client(), _simple_clause(), "count", backend="auth")

        exc = exc_info.value
        assert exc.status_code == 403
        assert exc.error_type == "consent_denied"
        assert exc.server_message == "You no longer have consent for this saved result"

    @respx.mock
    def test_variant_consent_lookup_failure_is_not_unsupported(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(
                502,
                json={
                    "errorType": "consent_lookup_failed",
                    "message": "Unable to resolve caller consents",
                },
            )
        )

        with pytest.raises(PicSureConsentLookupError) as exc_info:
            run_query(_make_client(), _simple_clause(), "variant_count", backend="auth")

        exc = exc_info.value
        assert exc.status_code == 502
        assert exc.error_type == "consent_lookup_failed"
        assert exc.server_message == "Unable to resolve caller consents"
        assert route.call_count == 1

    @respx.mock
    def test_401_raises_auth_error(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        with pytest.raises(PicSureAuthError):
            run_query(_make_client(), _simple_clause(), "count", backend="auth")

    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        client = _make_client()
        with pytest.raises(PicSureConnectionError, match="query"):
            run_query(client, _simple_clause(), "count", backend="auth")

    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.post(QUERY_URL).mock(side_effect=httpx.ConnectError("Connection refused"))
        client = _make_client()
        with pytest.raises(PicSureConnectionError):
            run_query(client, _simple_clause(), "count", backend="auth")


class TestQueryTypeMemberInput:
    def test_count_member_resolves_to_wire_format(self):
        assert _resolve_query_type(QueryType.COUNT) == "COUNT"

    def test_participant_member_resolves_to_wire_format(self):
        assert _resolve_query_type(QueryType.PARTICIPANT) == "DATAFRAME"

    def test_timestamp_member_resolves_to_wire_format(self):
        assert _resolve_query_type(QueryType.TIMESTAMP) == "DATAFRAME_TIMESERIES"

    def test_cross_count_member_resolves_to_wire_format(self):
        assert _resolve_query_type(QueryType.CROSS_COUNT) == "CROSS_COUNT"

    def test_string_input_still_works(self):
        # Backwards compat — string path is untouched.
        assert _resolve_query_type("count") == "COUNT"

    def test_string_input_case_insensitive(self):
        assert _resolve_query_type("COUNT") == "COUNT"

    def test_string_input_strips_whitespace(self):
        assert _resolve_query_type("  count  ") == "COUNT"

    def test_non_member_non_string_raises(self):
        with pytest.raises(
            PicSureValidationError,
            match=r"not a valid query type.*count",
        ):
            _resolve_query_type(42)  # type: ignore[arg-type]


class TestRunQueryWithQueryTypeMember:
    @respx.mock
    def test_count_query_with_member_sets_wire_format(self):
        # Mirrors the existing TestRunQueryCount style — proves a QueryType
        # member flows end-to-end through run_query and produces the same
        # wire body as the equivalent string.
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"42"),
        )

        client = _make_client()
        result = run_query(
            client,
            _simple_clause(),
            QueryType.COUNT,
            backend="auth",
        )

        assert isinstance(result, CountResult)
        assert result.value == 42

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["expectedResultType"] == "COUNT"


class TestSessionRunQueryWithMember:
    @respx.mock
    def test_session_run_query_accepts_query_type_member(self):
        # Confirms the member form flows through Session.runQuery, not
        # just the lower-level run_query function.
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"7"),
        )

        client = _make_client()
        session = Session(
            client=client,
            user_email="test@example.com",
            token_expiration="N/A",
        )

        result = session.runQuery(_simple_clause(), type=QueryType.COUNT)

        assert isinstance(result, CountResult)
        assert result.value == 7


class TestRunQueryBackendRouting:
    @respx.mock
    def test_auth_backend_uses_auth_v3_path(self):
        auth = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"1"),
        )
        open_route = respx.post(OPEN_QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"99"),
        )
        client = _make_client()

        result = run_query(client, _simple_clause(), "count", backend="auth")

        assert isinstance(result, CountResult)
        assert result.value == 1
        assert auth.call_count == 1
        assert open_route.call_count == 0

    @respx.mock
    def test_open_backend_routes_to_open_path(self):
        # BDC's API gateway 401s open-access requests on the auth v3 sync
        # endpoint.  Open-only deployments must use the open path.
        auth = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(401, text="Unauthorized"),
        )
        open_route = respx.post(OPEN_QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"42"),
        )
        client = _make_client()

        result = run_query(client, _simple_clause(), "count", backend="open")

        assert isinstance(result, CountResult)
        assert result.value == 42
        assert auth.call_count == 0
        assert open_route.call_count == 1
        assert open_route.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"

    @respx.mock
    def test_open_path_preserves_body_shape(self):
        # The open endpoint accepts the same body shape as auth; we should
        # not start emitting a different shape just because we're routing
        # to /picsure/hpds/open/v3/query/sync.
        route = respx.post(OPEN_QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"7"),
        )
        client = _make_client()
        run_query(client, _simple_clause(), "count", backend="open")

        import json

        body = json.loads(route.calls[0].request.content)
        assert "resourceUUID" not in body
        query = body["query"]
        assert query["expectedResultType"] == "COUNT"
        assert "authorizationFilters" not in query
        assert query["picsureId"] is None
        assert query["id"] is None

    @respx.mock
    def test_session_with_open_backend_routes_to_open(self):
        open_route = respx.post(OPEN_QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"3"),
        )
        auth = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(401, text="Unauthorized"),
        )
        client = _make_client()
        session = Session(
            client=client,
            user_email="anonymous",
            token_expiration="N/A",
            backend="open",
        )

        result = session.runQuery(_simple_clause(), type=QueryType.COUNT)

        assert isinstance(result, CountResult)
        assert result.value == 3
        assert open_route.call_count == 1
        assert auth.call_count == 0

    @respx.mock
    def test_session_default_backend_routes_to_auth(self):
        auth = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"5"),
        )
        open_route = respx.post(OPEN_QUERY_URL).mock(
            return_value=httpx.Response(401, text="Unauthorized"),
        )
        client = _make_client()
        session = Session(
            client=client,
            user_email="test@example.com",
            token_expiration="N/A",
        )

        result = session.runQuery(_simple_clause(), type=QueryType.COUNT)

        assert isinstance(result, CountResult)
        assert result.value == 5
        assert auth.call_count == 1
        assert open_route.call_count == 0


class TestBuildQueryBodyGenomic:
    def test_includes_genomic_filters(self):
        from picsure._services.query_build import buildGenomicFilter, buildQuery
        from picsure._services.query_run import build_query_body

        gf = buildGenomicFilter("Gene_with_variant", values=["BRCA1"])
        q = buildQuery(genomicFilters=gf, includeConcepts=["\\bmi\\"])
        body = build_query_body(q, "COUNT")
        assert body["query"]["genomicFilters"] == [
            {"key": "Gene_with_variant", "values": ["BRCA1"]}
        ]

    def test_no_genomic_filters_is_empty(self):
        from picsure._services.query_build import buildClause
        from picsure._services.query_run import build_query_body

        c = buildClause("\\path\\", type=PhenotypicFilterType.FILTER, categories="X")
        body = build_query_body(c, "COUNT")
        assert body["query"]["genomicFilters"] == []

    def test_genomic_filters_do_not_affect_select(self):
        from picsure._services.query_build import buildGenomicFilter, buildQuery
        from picsure._services.query_run import build_query_body

        gf = buildGenomicFilter("Gene_with_variant", values=["BRCA1"])
        q = buildQuery(genomicFilters=gf, includeConcepts=["\\bmi\\"])
        body = build_query_body(q, "DATAFRAME")
        assert body["query"]["select"] == ["\\bmi\\"]


class TestVariantResultParsing:
    def test_resolve_new_query_types(self):
        from picsure._services.query_run import _resolve_query_type

        assert _resolve_query_type("variant_count") == "VARIANT_COUNT_FOR_QUERY"
        assert _resolve_query_type("variant_list") == "VARIANT_LIST_FOR_QUERY"
        assert _resolve_query_type(QueryType.VCF_EXCERPT) == "VCF_EXCERPT"
        assert (
            _resolve_query_type(QueryType.AGGREGATE_VCF_EXCERPT)
            == "AGGREGATE_VCF_EXCERPT"
        )

    def test_parse_variant_count_exact(self):
        from picsure._services.query_run import _parse_variant_count

        result = _parse_variant_count(b"123")
        assert isinstance(result, CountResult)
        assert result.value == 123
        assert result.margin is None
        assert result.cap is None

    def test_parse_variant_count_noisy(self):
        # If the server obfuscates the count, it is represented faithfully
        # rather than raising on int().
        from picsure._services.query_run import _parse_variant_count

        result = _parse_variant_count("11309 ±3".encode())
        assert result.value == 11309
        assert result.margin == 3

    def test_parse_variant_count_suppressed(self):
        from picsure._services.query_run import _parse_variant_count

        result = _parse_variant_count(b"< 10")
        assert result.value is None
        assert result.cap == 10

    def test_parse_variant_count_not_allowed(self):
        from picsure._services.query_run import _parse_variant_count

        with pytest.raises(PicSureQueryError):
            _parse_variant_count(b"VARIANT_COUNT_FOR_QUERY query type not allowed")

    def test_parse_variant_count_garbage_raises(self):
        from picsure._services.query_run import _parse_variant_count

        with pytest.raises(PicSureQueryError):
            _parse_variant_count(b"not a count")

    def test_parse_variant_list(self):
        from picsure._services.query_run import _parse_variant_list

        # Real variant specs are 6 comma-separated fields
        # (chromosome,offset,ref,alt,gene,consequence) joined with ", ".
        # The internal commas must NOT split the spec apart.
        raw = b"[7,100000,A,T,CHD8,missense_variant, 8,200000,G,C,GENE2,stop_gained]"
        assert _parse_variant_list(raw) == [
            "7,100000,A,T,CHD8,missense_variant",
            "8,200000,G,C,GENE2,stop_gained",
        ]

    def test_parse_variant_list_single_spec(self):
        from picsure._services.query_run import _parse_variant_list

        # A single spec has no ", " separator; it must come back intact.
        raw = b"[7,100000,A,T,CHD8,missense_variant]"
        assert _parse_variant_list(raw) == ["7,100000,A,T,CHD8,missense_variant"]

    def test_parse_variant_list_empty(self):
        from picsure._services.query_run import _parse_variant_list

        assert _parse_variant_list(b"[]") == []

    def test_parse_vcf_excerpt(self):
        from picsure._services.query_run import _parse_vcf_excerpt

        raw = b"CHROM\tPOSITION\tREF\tALT\n1\t100\tA\tT\n"
        df = _parse_vcf_excerpt(raw)
        assert list(df.columns) == ["CHROM", "POSITION", "REF", "ALT"]
        assert len(df) == 1

    def test_parse_vcf_excerpt_no_variants(self):
        from picsure._services.query_run import _parse_vcf_excerpt

        df = _parse_vcf_excerpt(b"No Variants Found\n")
        assert df.empty

    def test_parse_vcf_excerpt_not_allowed(self):
        from picsure._services.query_run import _parse_vcf_excerpt

        with pytest.raises(PicSureQueryError):
            _parse_vcf_excerpt(b"VCF_EXCERPT query type not allowed")

    def test_empty_body_reports_unsupported_deployment(self):
        # BDC returns HTTP 200 with an empty body for variant result types it
        # does not serve. Surface that as a clear "not available on this
        # deployment" error rather than a confusing parse failure (or, for
        # VCF, a silently-empty DataFrame).
        from picsure._services.query_run import (
            _parse_variant_count,
            _parse_variant_list,
            _parse_vcf_excerpt,
        )

        for parser in (_parse_variant_count, _parse_variant_list, _parse_vcf_excerpt):
            with pytest.raises(PicSureQueryError, match="not available on this"):
                parser(b"")

    @respx.mock
    def test_variant_500_reports_unsupported_deployment(self):
        # BDC's backend returns HTTP 500 for variant result types it does not
        # serve yet. Surface that as the same clear "not available" error as the
        # empty-200 case, not the generic "temporarily unavailable".
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(500, text="ri_error 500")
        )
        with pytest.raises(PicSureQueryError, match="not available on this"):
            run_query(_make_client(), _simple_clause(), "variant_count", backend="auth")

    @respx.mock
    def test_nonvariant_500_stays_temporarily_unavailable(self):
        # A 5xx on a normal (non-variant) query is still a transient-style
        # outage, not an unsupported feature.
        respx.post(QUERY_URL).mock(return_value=httpx.Response(500, text="boom"))
        with pytest.raises(PicSureConnectionError, match="temporarily unavailable"):
            run_query(_make_client(), _simple_clause(), "count", backend="auth")


# Response bodies below were captured from a live PIC-SURE stack on
# 2026-09-10 (local all-in-one, genomic data loaded).  VARIANT_COUNT is the
# only variant type this deployment serves; VARIANT_LIST, VCF_EXCERPT and
# AGGREGATE_VCF_EXCERPT are disabled there and answer with the
# "<TYPE> query type not allowed" body reproduced here, so their success
# shapes are exercised as unit tests only.
VARIANT_COUNT_LIVE = b'{"count":1,"message":"Query ran successfully"}'
VARIANT_COUNT_NO_FILTERS_LIVE = (
    b'{"count":"0","message":"No variant filters were supplied, so no query was run."}'
)
VARIANT_LIST_NOT_ALLOWED_LIVE = b"VARIANT_LIST query type not allowed"
VCF_EXCERPT_NOT_ALLOWED_LIVE = b"VCF_EXCERPT query type not allowed"
AGGREGATE_VCF_NOT_ALLOWED_LIVE = b"AGGREGATE_VCF_EXCERPT query type not allowed"


def _genomic_query() -> Query:
    return Query(
        phenotypicFilter=None,
        includeConcepts=(),
        genomicFilters=(
            GenomicFilter(key="Gene_with_variant", values=("CONSENTQA902_1",)),
        ),
    )


class TestRunQueryVariantCountEndToEnd:
    """PYR-9 / PL-03: drive VARIANT_COUNT through ``run_query``.

    The server answers with a JSON object, which the old parser rejected
    because it expected a bare count string. Reproduced live before the fix.
    """

    @respx.mock
    def test_parses_the_live_json_body(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(
                200,
                content=VARIANT_COUNT_LIVE,
                headers={"content-type": "application/json"},
            )
        )
        result = run_query(
            _make_client(), _genomic_query(), "variant_count", backend="auth"
        )
        assert isinstance(result, CountResult)
        assert result.value == 1
        assert result.margin is None
        assert result.cap is None
        assert result.obfuscated is False

    @respx.mock
    def test_raw_preserves_the_whole_body_including_message(self):
        # The server's `message` has no field of its own on CountResult; it
        # survives because `raw` keeps the entire response body.
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=VARIANT_COUNT_LIVE)
        )
        result = run_query(
            _make_client(), _genomic_query(), "variant_count", backend="auth"
        )
        assert result.raw == VARIANT_COUNT_LIVE.decode()
        assert "Query ran successfully" in result.raw

    @respx.mock
    def test_sends_the_expected_request_body(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=VARIANT_COUNT_LIVE)
        )
        run_query(_make_client(), _genomic_query(), "variant_count", backend="auth")

        import json

        body = json.loads(route.calls[0].request.content)
        query = body["query"]
        assert query["expectedResultType"] == "VARIANT_COUNT_FOR_QUERY"
        assert query["genomicFilters"] == [
            {"key": "Gene_with_variant", "values": ["CONSENTQA902_1"]}
        ]
        assert query["phenotypicClause"] is None
        assert query["select"] == []
        assert "resourceUUID" not in body

    @respx.mock
    def test_accepts_a_string_count(self):
        # `count` is a JSON string in some responses, not always a number.
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"count":"7"}')
        )
        result = run_query(
            _make_client(), _genomic_query(), "variant_count", backend="auth"
        )
        assert result.value == 7

    @respx.mock
    def test_string_count_keeps_obfuscation_metadata(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content='{"count":"11309 ±3"}'.encode())
        )
        result = run_query(
            _make_client(), _genomic_query(), "variant_count", backend="auth"
        )
        assert result.value == 11309
        assert result.margin == 3
        assert result.obfuscated is True

    @respx.mock
    def test_suppressed_string_count(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"count":"< 10"}')
        )
        result = run_query(
            _make_client(), _genomic_query(), "variant_count", backend="auth"
        )
        assert result.value is None
        assert result.cap == 10
        assert result.obfuscated is True

    @respx.mock
    def test_bare_numeric_body_still_accepted(self):
        # Kept for any deployment that answers with a bare count string.
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"42"))
        result = run_query(
            _make_client(), _genomic_query(), "variant_count", backend="auth"
        )
        assert result.value == 42
        assert result.raw == "42"

    @respx.mock
    def test_no_variant_filters_message_raises_instead_of_reporting_zero(self):
        # Live shape for a variant count with no genomic filter. Returning
        # CountResult(value=0) here would read as "no matching variants" when
        # the server never ran a query at all.
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=VARIANT_COUNT_NO_FILTERS_LIVE)
        )
        with pytest.raises(PicSureQueryError) as exc_info:
            run_query(_make_client(), _simple_clause(), "variant_count", backend="auth")

        message = str(exc_info.value)
        assert "at least one genomic filter" in message
        assert "buildGenomicFilter" in message

    @respx.mock
    def test_json_object_without_a_count_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"message":"hi"}')
        )
        with pytest.raises(PicSureQueryError, match="'count' field"):
            run_query(_make_client(), _genomic_query(), "variant_count", backend="auth")

    @respx.mock
    def test_json_object_with_a_boolean_count_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"count":true}')
        )
        with pytest.raises(PicSureQueryError, match="'count' field"):
            run_query(_make_client(), _genomic_query(), "variant_count", backend="auth")

    @respx.mock
    def test_json_object_with_a_non_scalar_count_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b'{"count":[1,2]}')
        )
        with pytest.raises(PicSureQueryError, match="number or a count string"):
            run_query(_make_client(), _genomic_query(), "variant_count", backend="auth")

    @respx.mock
    def test_garbage_body_still_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"not a count")
        )
        with pytest.raises(PicSureQueryError, match="Expected a count"):
            run_query(_make_client(), _genomic_query(), "variant_count", backend="auth")

    @respx.mock
    def test_disabled_result_type_body_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(
                200, content=b"VARIANT_COUNT_FOR_QUERY query type not allowed"
            )
        )
        with pytest.raises(PicSureQueryError, match="may be disabled"):
            run_query(_make_client(), _genomic_query(), "variant_count", backend="auth")


class TestRunQueryVariantListEndToEnd:
    """PYR-9: drive VARIANT_LIST through ``run_query``.

    Disabled on the verified deployment, so the "not allowed" body is the
    live shape and the success shape is unit-tested only.
    """

    @respx.mock
    def test_sends_the_expected_request_body(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"[]")
        )
        run_query(_make_client(), _genomic_query(), "variant_list", backend="auth")

        import json

        query = json.loads(route.calls[0].request.content)["query"]
        assert query["expectedResultType"] == "VARIANT_LIST_FOR_QUERY"
        assert query["genomicFilters"] == [
            {"key": "Gene_with_variant", "values": ["CONSENTQA902_1"]}
        ]

    @respx.mock
    def test_parses_a_multi_spec_list(self):
        body = b"[7,100000,A,T,CHD8,missense_variant, 7,100001,C,G,CHD8,stop_gained]"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=body))
        result = run_query(
            _make_client(), _genomic_query(), "variant_list", backend="auth"
        )
        assert result == [
            "7,100000,A,T,CHD8,missense_variant",
            "7,100001,C,G,CHD8,stop_gained",
        ]

    @respx.mock
    def test_parses_an_empty_list(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"[]"))
        result = run_query(
            _make_client(), _genomic_query(), "variant_list", backend="auth"
        )
        assert result == []

    @respx.mock
    def test_live_disabled_body_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=VARIANT_LIST_NOT_ALLOWED_LIVE)
        )
        with pytest.raises(PicSureQueryError, match="may be disabled"):
            run_query(_make_client(), _genomic_query(), "variant_list", backend="auth")

    @respx.mock
    def test_unbracketed_body_raises(self):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"7,100000,A,T")
        )
        with pytest.raises(PicSureQueryError, match="bracketed variant list"):
            run_query(_make_client(), _genomic_query(), "variant_list", backend="auth")


class TestRunQueryVcfExcerptEndToEnd:
    """PYR-9: drive both VCF excerpt types through ``run_query``.

    Both are disabled on the verified deployment, so their success shapes
    are unit-tested only; the "not allowed" bodies are the live ones.
    """

    @pytest.mark.parametrize(
        ("query_type", "expected_result_type"),
        [
            ("vcf_excerpt", "VCF_EXCERPT"),
            ("aggregate_vcf_excerpt", "AGGREGATE_VCF_EXCERPT"),
        ],
    )
    @respx.mock
    def test_sends_the_expected_request_body(self, query_type, expected_result_type):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"CHROM\tPOS\n7\t100000\n")
        )
        run_query(_make_client(), _genomic_query(), query_type, backend="auth")

        import json

        query = json.loads(route.calls[0].request.content)["query"]
        assert query["expectedResultType"] == expected_result_type
        assert query["genomicFilters"] == [
            {"key": "Gene_with_variant", "values": ["CONSENTQA902_1"]}
        ]

    @pytest.mark.parametrize("query_type", ["vcf_excerpt", "aggregate_vcf_excerpt"])
    @respx.mock
    def test_parses_the_tab_separated_body(self, query_type):
        body = b"CHROM\tPOS\tREF\tALT\n7\t100000\tA\tT\n7\t100001\tC\tG\n"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=body))
        df = run_query(_make_client(), _genomic_query(), query_type, backend="auth")
        assert list(df.columns) == ["CHROM", "POS", "REF", "ALT"]
        assert len(df) == 2
        assert df["POS"].tolist() == [100000, 100001]

    @pytest.mark.parametrize("query_type", ["vcf_excerpt", "aggregate_vcf_excerpt"])
    @respx.mock
    def test_no_variants_sentinel_is_an_empty_frame(self, query_type):
        respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"No Variants Found\n")
        )
        df = run_query(_make_client(), _genomic_query(), query_type, backend="auth")
        assert df.empty

    @pytest.mark.parametrize(
        ("query_type", "body"),
        [
            ("vcf_excerpt", VCF_EXCERPT_NOT_ALLOWED_LIVE),
            ("aggregate_vcf_excerpt", AGGREGATE_VCF_NOT_ALLOWED_LIVE),
        ],
    )
    @respx.mock
    def test_live_disabled_body_raises(self, query_type, body):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=body))
        with pytest.raises(PicSureQueryError, match="may be disabled"):
            run_query(_make_client(), _genomic_query(), query_type, backend="auth")


class TestVariantParserDefensiveBranches:
    """Branches reachable only from a malformed body."""

    def test_clause_concept_paths_ignores_a_non_list_subquery(self):
        from picsure._services.query_run import _clause_concept_paths

        assert _clause_concept_paths({"phenotypicClauses": "not-a-list"}) == []
        assert _clause_concept_paths({"operator": "AND"}) == []
        assert _clause_concept_paths("not-a-dict") == []

    def test_empty_count_message_without_context(self):
        from picsure._services.query_run import _empty_count_message

        message = _empty_count_message("")
        assert "empty response" in message
        assert "  " not in message

    def test_no_variant_filters_message_without_context(self):
        from picsure._services.query_run import _parse_variant_count

        with pytest.raises(PicSureQueryError, match="at least one genomic filter"):
            _parse_variant_count(VARIANT_COUNT_NO_FILTERS_LIVE)

    def test_vcf_excerpt_undecodable_body_raises(self):
        from picsure._services.query_run import _parse_vcf_excerpt

        with pytest.raises(PicSureQueryError, match="malformed VCF excerpt"):
            _parse_vcf_excerpt(b"\xff\xfe\x00bad")

    def test_vcf_excerpt_unparsable_table_raises(self):
        from picsure._services.query_run import _parse_vcf_excerpt

        # Ragged rows the tab reader cannot square into a table.
        body = b'CHROM\tPOS\n7\t100000\n"unclosed\tquote\t\t\t\n'
        with pytest.raises(PicSureQueryError, match="malformed VCF excerpt"):
            _parse_vcf_excerpt(body)
