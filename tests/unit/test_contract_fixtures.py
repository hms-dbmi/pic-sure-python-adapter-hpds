"""Shape tests driven by the server's golden contract fixtures.

The JSON under ``tests/fixtures/contracts/`` is copied verbatim from the
server monorepo's ``pic-sure-contracts`` test resources.  The same bytes back
the Java contract tests, so these assertions fail the moment the adapter and
the server disagree about a wire shape.

Every test here either

* feeds a golden RESPONSE fixture through the real parsing helper, or
* asserts that a REQUEST this adapter builds matches the golden request
  fixture / the fields the server's strict deserializer accepts.
"""

from __future__ import annotations

import pandas as pd
import pytest

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._services.export import _extract_query_id, _extract_status
from picsure._services.genomic_search import search_genomic_values
from picsure._services.query_run import build_query_body
from tests.conftest import load_contract_fixture

# Member names the v3 Query record declares (docs/api/*.openapi.json ->
# components.schemas.Query).  The server deserializes STRICTLY: anything
# outside this set is a 400, so the adapter may never emit a key that is not
# here.
_V3_QUERY_FIELDS = frozenset(
    {
        "authorizationFilters",
        "expectedResultType",
        "genomicFilters",
        "id",
        "phenotypicClause",
        "picsureId",
        "select",
    }
)


class _FakeClient:
    """Minimal stand-in that replays a canned JSON body."""

    def __init__(self, response: dict) -> None:
        self._response = response
        self.last_path: str | None = None

    def get_json(self, path: str) -> dict:
        self.last_path = path
        return self._response


def _clause() -> Clause:
    return Clause(
        keys=["\\phs1\\sex\\"],
        type=PhenotypicFilterType.FILTER,
        categories=["Male"],
    )


class TestQueryStatusResponse:
    """query-status-response.json -- the submit / status / metadata reply."""

    @pytest.fixture()
    def status(self) -> dict:
        return load_contract_fixture("query-status-response")

    def test_has_the_contract_fields(self, status):
        assert set(status) == {
            "picsureId",
            "status",
            "resourceStatus",
            "resourceResultId",
            "sizeInBytes",
            "startTime",
            "duration",
            "expiration",
            "resultMetadata",
        }

    def test_retired_fields_are_absent(self, status):
        # picsureResultId was renamed to picsureId; resourceID is gone.
        assert "picsureResultId" not in status
        assert "resourceID" not in status

    def test_query_id_extraction_reads_picsure_id(self, status):
        assert _extract_query_id(status) == status["picsureId"]

    def test_query_id_is_not_the_resource_result_id(self, status):
        # resourceResultId is the BACKING RESOURCE's id and must never be
        # used as the PIC-SURE /query/{id} path parameter.
        assert status["resourceResultId"] != status["picsureId"]
        assert _extract_query_id(status) != status["resourceResultId"]

    def test_status_extraction(self, status):
        assert _extract_status(status) == "AVAILABLE"

    def test_status_is_one_of_the_four_real_values(self, status):
        assert status["status"] in {"QUEUED", "PENDING", "ERROR", "AVAILABLE"}


class TestSignedUrlResponse:
    """signed-url-response.json -- a JSON object, no longer a bare string."""

    def test_is_an_object_with_a_signed_url_member(self):
        payload = load_contract_fixture("signed-url-response")
        assert isinstance(payload, dict)
        assert set(payload) == {"signedUrl"}
        assert payload["signedUrl"].startswith("https://")


class TestSearchRequest:
    """search-request.json -- POST /search takes {"query": "<term>"}."""

    def test_is_a_single_query_member(self):
        payload = load_contract_fixture("search-request")
        assert set(payload) == {"query"}
        assert isinstance(payload["query"], str)


class TestPaginatedResponse:
    """paginated-response.json -- {results, page, total} everywhere."""

    @pytest.fixture()
    def page(self) -> dict:
        return load_contract_fixture("paginated-response")

    def test_has_the_contract_fields(self, page):
        assert set(page) == {"results", "page", "total"}

    def test_spring_page_fields_are_absent(self, page):
        for retired in ("content", "totalElements", "totalPages", "number", "last"):
            assert retired not in page

    def test_genomic_value_search_parses_it(self, page):
        # /picsure/hpds/{backend}/v3/search/values returns this exact envelope.
        client = _FakeClient(
            {
                "results": ["BRCA1", "BRCA2"],
                "page": page["page"],
                "total": page["total"],
            }
        )
        df = search_genomic_values(client, "Gene_with_variant", backend="auth")
        assert isinstance(df, pd.DataFrame)
        assert df["value"].tolist() == ["BRCA1", "BRCA2"]
        assert df.attrs["total"] == page["total"]
        assert df.attrs["page"] == page["page"]

    def test_genomic_value_search_uses_the_v3_route(self, page):
        client = _FakeClient({"results": [], "page": 1, "total": 0})
        search_genomic_values(client, "Gene_with_variant", backend="auth")
        assert client.last_path.startswith("/picsure/hpds/auth/v3/search/values?")


class TestQueryRequestIsBare:
    """The submit body is the bare v3 Query the server binds strictly."""

    def test_no_envelope(self):
        body = build_query_body(_clause(), "COUNT")
        assert "query" not in body
        assert body["expectedResultType"] == "COUNT"

    def test_no_registry_era_fields(self):
        body = build_query_body(_clause(), "COUNT")
        for retired in ("resourceUUID", "resourceCredentials", "@type"):
            assert retired not in body

    def test_only_declared_v3_query_members(self):
        # Strict deserialization: an unknown member is a 400.
        body = build_query_body(_clause(), "DATAFRAME")
        assert set(body) <= _V3_QUERY_FIELDS

    def test_authorization_filters_never_client_asserted(self):
        body = build_query_body(_clause(), "COUNT")
        assert "authorizationFilters" not in body


class TestDispatchResponse:
    """dispatch-response.json -- queryJson is the BARE query, serialized."""

    def test_query_json_has_no_envelope(self):
        import json

        payload = load_contract_fixture("dispatch-response")
        inner = json.loads(payload["queryJson"])
        assert "query" not in inner
        assert "resourceUUID" not in inner
        assert "resourceCredentials" not in inner
        assert inner["expectedResultType"] == "COUNT"
