import httpx
import respx

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.query import Query
from picsure._models.session import Session
from picsure._services._hpds_paths import query_prefix
from picsure._services.query_run import run_query
from picsure._transport.client import PicSureClient

BASE_URL = "https://test.example.com"
QUERY_URL = f"{BASE_URL}{query_prefix('auth', v3=True)}/query/sync"


def _client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token="test-token")


def _session() -> Session:
    return Session(
        client=_client(),
        user_email="u@example.com",
        token_expiration="N/A",
    )


def _clause() -> Clause:
    return Clause(
        keys=["\\phs1\\sex\\"],
        type=PhenotypicFilterType.FILTER,
        categories=["Male"],
    )


def _group() -> ClauseGroup:
    return ClauseGroup(
        clauses=[_clause(), Clause(keys=["\\p2\\"], type=PhenotypicFilterType.REQUIRE)],
        operator=GroupOperator.AND,
    )


class TestRunQueryAcceptsAFilterOrAQuery:
    """A bare Clause or ClauseGroup runs everywhere a Query does.

    Query stopped being an alias for ``Clause | ClauseGroup`` at 2.0.0
    and is a frozen dataclass of its own, so a clause is not an instance
    of it. What still holds, and what callers rely on, is that the two
    run-query entry points take all three.
    """

    def test_a_clause_is_not_an_instance_of_query(self):
        assert not isinstance(_clause(), Query)
        assert not isinstance(_group(), Query)

    @respx.mock
    def test_run_query_accepts_a_bare_clause(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"7"))

        result = run_query(_client(), _clause(), "count", backend="auth")

        assert result.value == 7

    @respx.mock
    def test_run_query_accepts_a_bare_clause_group(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"7"))

        result = run_query(_client(), _group(), "count", backend="auth")

        assert result.value == 7

    @respx.mock
    def test_run_query_accepts_a_query(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"7"))

        result = run_query(
            _client(),
            Query(phenotypicFilter=_clause()),
            "count",
            backend="auth",
        )

        assert result.value == 7

    @respx.mock
    def test_session_run_query_accepts_a_bare_clause(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"7"))

        assert _session().runQuery(_clause(), type="count").value == 7

    @respx.mock
    def test_session_run_query_accepts_a_bare_clause_group(self):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"7"))

        assert _session().runQuery(_group(), type="count").value == 7

    @respx.mock
    def test_a_bare_clause_and_the_query_wrapping_it_send_the_same_body(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"7")
        )

        run_query(_client(), _clause(), "count", backend="auth")
        run_query(_client(), Query(phenotypicFilter=_clause()), "count", backend="auth")

        assert route.calls[0].request.content == route.calls[1].request.content


class TestQuerySerialization:
    def test_a_clause_serializes_as_a_phenotypic_filter_leaf(self):
        result = Clause(
            keys=["\\path\\"], type=PhenotypicFilterType.REQUIRE
        ).to_query_json()

        assert result["phenotypicFilterType"] == "REQUIRED"
        assert result["conceptPath"] == "\\path\\"


def test_query_genomic_filters_defaults_empty():
    from picsure import Query

    assert Query().genomicFilters == ()
