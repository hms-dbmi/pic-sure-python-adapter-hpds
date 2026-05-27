from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest
import respx

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.resource import Resource
from picsure._models.session import Session
from picsure._transport.client import PicSureClient


def _make_session(
    resources: list[Resource] | None = None,
    email: str = "user@example.com",
    expiration: str = "2026-06-15T00:00:00Z",
) -> Session:
    client = MagicMock()
    if resources is None:
        resources = [
            Resource(uuid="uuid-1", name="Resource A", description="Desc A"),
            Resource(uuid="uuid-2", name="Resource B", description="Desc B"),
        ]
    return Session(
        client=client,
        user_email=email,
        token_expiration=expiration,
        resources=resources,
    )


class TestSession:
    def test_get_resource_id_returns_dataframe(self):
        session = _make_session()
        df = session.getResourceID()
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["uuid", "name", "description"]
        assert len(df) == 2

    def test_get_resource_id_empty(self):
        session = _make_session(resources=[])
        df = session.getResourceID()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == ["uuid", "name", "description"]

    def test_resource_uuid_defaults_to_none(self):
        session = _make_session()
        assert session._resource_uuid is None

    def test_consents_default_to_empty(self):
        session = _make_session()
        assert session.consents == []

    def test_consents_property_returns_copy(self):
        client = MagicMock()
        session = Session(
            client=client,
            user_email="u@e.com",
            token_expiration="",
            resources=[],
            consents=["phs000007.c1"],
        )
        session.consents.append("phs999999.c9")
        assert session.consents == ["phs000007.c1"]

    def test_set_resource_id(self):
        session = _make_session()
        session.setResourceID("uuid-1")
        assert session._resource_uuid == "uuid-1"

    def test_set_resource_id_invalid_raises(self):
        import pytest

        from picsure.errors import PicSureValidationError

        session = _make_session()
        with pytest.raises(PicSureValidationError, match="not a valid resource UUID"):
            session.setResourceID("nonexistent-uuid")

    def test_set_resource_id_by_name(self):
        session = _make_session()
        session.setResourceIDByName("Resource B")
        assert session._resource_uuid == "uuid-2"

    def test_set_resource_id_by_name_invalid_raises(self):
        import pytest

        from picsure.errors import PicSureValidationError

        session = _make_session()
        with pytest.raises(PicSureValidationError, match="does not match"):
            session.setResourceIDByName("nonexistent")


class TestSessionDefaultResourceUuid:
    def test_returns_explicit_resource_uuid_when_set(self):
        client = MagicMock()
        resources = [
            Resource(uuid="uuid-1", name="A", description=""),
            Resource(uuid="uuid-2", name="B", description=""),
        ]
        session = Session(
            client=client,
            user_email="u@e.com",
            token_expiration="",
            resources=resources,
            resource_uuid="uuid-2",
        )
        assert session._default_resource_uuid() == "uuid-2"

    def test_returns_single_resource_when_not_set(self):
        session = _make_session(
            resources=[Resource(uuid="only-uuid", name="Solo", description="")]
        )
        assert session._default_resource_uuid() == "only-uuid"

    def test_raises_when_multiple_resources_unselected(self):
        import pytest

        from picsure.errors import PicSureValidationError

        session = _make_session()
        with pytest.raises(PicSureValidationError) as exc_info:
            session._default_resource_uuid()
        msg = str(exc_info.value)
        assert "setResourceID" in msg
        assert "Available resources:" in msg
        assert "uuid-1" in msg
        assert "Resource A" in msg
        assert "uuid-2" in msg
        assert "Resource B" in msg

    def test_raises_when_no_resources(self):
        session = _make_session(resources=[])
        with __import__("pytest").raises(
            __import__("picsure.errors", fromlist=["PicSureError"]).PicSureError,
            match="No resources",
        ):
            session._default_resource_uuid()


BASE_URL = "https://test.example.com"
TOKEN = "test-token"


def _make_live_session(
    resource_uuid: str = "resource-uuid-aaaa-1111",
) -> Session:
    from picsure._transport.client import PicSureClient

    client = PicSureClient(base_url=BASE_URL, token=TOKEN)
    resources = [Resource(uuid=resource_uuid, name="Test", description="")]
    return Session(
        client=client,
        user_email="test@test.com",
        token_expiration="2026-12-31T00:00:00Z",
        resources=resources,
    )


def _client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _session_with_resources(
    client: PicSureClient,
    *,
    resources: list[Resource],
    resource_uuid: str | None = None,
    use_legacy_query_path: bool = False,
) -> Session:
    return Session(
        client=client,
        user_email="x@y.com",
        token_expiration="2030-01-01",
        resources=resources,
        resource_uuid=resource_uuid,
        use_legacy_query_path=use_legacy_query_path,
    )


def _metadata_envelope(
    *,
    select: list[str],
    phenotypic: dict | None,
) -> dict:  # type: ignore[type-arg]
    return {
        "status": "COMPLETED",
        "resourceID": "resource-uuid-aaaa",
        "picsureResultId": "abc-123",
        "resourceResultId": "result-1",
        "startTime": 1715000000000,
        "resultMetadata": {
            "queryJson": {
                "@type": "GeneralQueryRequest",
                "resourceUUID": "resource-uuid-aaaa",
                "resourceCredentials": {},
                "query": {
                    "select": select,
                    "phenotypicClause": phenotypic,
                    "genomicFilters": [],
                    "expectedResultType": "COUNT",
                    "picsureId": None,
                    "id": None,
                },
            },
            "queryResultMetadata": "",
        },
    }


_CONCEPTS_URL = (
    f"{BASE_URL}/picsure/proxy/dictionary-api/concepts?page_number=0&page_size=100"
)
_FACETS_URL = f"{BASE_URL}/picsure/proxy/dictionary-api/facets"


class TestSessionSearch:
    @respx.mock
    def test_search_returns_dataframe(self, search_response):
        respx.post(_CONCEPTS_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )

        session = _make_live_session()
        df = session.searchDictionary("sex")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    @respx.mock
    def test_search_empty_term(self, search_response):
        respx.post(_CONCEPTS_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )

        session = _make_live_session()
        df = session.searchDictionary()

        assert isinstance(df, pd.DataFrame)

    @respx.mock
    def test_search_forwards_consents(self, search_response):
        route = respx.post(_CONCEPTS_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        from picsure._transport.client import PicSureClient

        client = PicSureClient(base_url=BASE_URL, token=TOKEN)
        session = Session(
            client=client,
            user_email="u@e.com",
            token_expiration="",
            resources=[Resource(uuid="r", name="t", description="")],
            consents=["phs000007.c1"],
        )
        session.searchDictionary("age")
        body = __import__("json").loads(route.calls[0].request.content)
        assert body["consents"] == ["phs000007.c1"]


class TestSessionFacets:
    @respx.mock
    def test_facets_returns_facet_set(self, facets_response):
        respx.post(_FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )

        session = _make_live_session()
        fs = session.facets()

        from picsure._models.facet import FacetSet

        assert isinstance(fs, FacetSet)
        view = fs.view()
        assert "dataset_id" in view
        assert "data_type" in view

    @respx.mock
    def test_facets_can_add_and_use_in_search(self, facets_response, search_response):
        respx.post(_FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        concepts_route = respx.post(_CONCEPTS_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )

        session = _make_live_session()
        fs = session.facets()
        fs.add("dataset_id", "phs000007")
        session.searchDictionary("sex", facets=fs)

        import json

        last_body = json.loads(concepts_route.calls[-1].request.content)
        assert len(last_body["facets"]) == 1
        sent = last_body["facets"][0]
        assert sent["category"] == "dataset_id"
        assert sent["name"] == "phs000007"
        assert sent["categoryRef"]["name"] == "dataset_id"

    @respx.mock
    def test_facets_forwards_term(self, facets_response):
        route = respx.post(_FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )

        session = _make_live_session()
        session.facets(term="blood")

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["search"] == "blood"

    @respx.mock
    def test_facets_forwards_term_and_facets(self, facets_response):
        # Two calls: first loads the FacetCategory list, second re-queries
        # with the current term + selection.
        route = respx.post(_FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )

        session = _make_live_session()
        fs = session.facets()
        fs.add("dataset_id", "phs000007")
        session.facets(term="blood", facets=fs)

        import json

        body = json.loads(route.calls[-1].request.content)
        assert body["search"] == "blood"
        assert len(body["facets"]) == 1
        assert body["facets"][0]["name"] == "phs000007"


class TestSessionShowAllFacets:
    @respx.mock
    def test_show_all_facets_returns_dataframe(self, facets_response):
        respx.post(_FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )

        session = _make_live_session()
        df = session.showAllFacets()

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == [
            "category",
            "Category Display",
            "display",
            "description",
            "value",
            "count",
        ]
        assert len(df) == 7

    @respx.mock
    def test_show_all_facets_forwards_term_and_facets(self, facets_response):
        route = respx.post(_FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )

        session = _make_live_session()
        fs = session.facets()
        fs.add("dataset_id", "phs000007")
        session.showAllFacets(term="blood", facets=fs)

        import json

        body = json.loads(route.calls[-1].request.content)
        assert body["search"] == "blood"
        assert len(body["facets"]) == 1
        assert body["facets"][0]["name"] == "phs000007"


class TestSessionRunQuery:
    @respx.mock
    def test_run_query_count(self):
        respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
            return_value=httpx.Response(200, content=b"42")
        )
        from picsure._models.clause import Clause, PhenotypicFilterType
        from picsure._models.count_result import CountResult

        session = _make_live_session()
        clause = Clause(
            keys=["\\sex\\"], type=PhenotypicFilterType.FILTER, categories=["Male"]
        )
        result = session.runQuery(clause, type="count")

        assert isinstance(result, CountResult)
        assert result.value == 42
        assert result.obfuscated is False

    @respx.mock
    def test_run_query_participant(self, participant_response):
        respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
            return_value=httpx.Response(200, content=participant_response)
        )
        from picsure._models.clause import Clause, PhenotypicFilterType

        session = _make_live_session()
        clause = Clause(
            keys=["\\sex\\"], type=PhenotypicFilterType.FILTER, categories=["Male"]
        )
        df = session.runQuery(clause, type="participant")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5


class TestSessionExport:
    @respx.mock
    def test_export_pfb(self, tmp_path):
        # Session.exportAsPFB drives the async flow:
        # submit -> poll status -> stream result.
        query_id = "session-pfb-1"
        respx.post(f"{BASE_URL}/picsure/v3/query").mock(
            return_value=httpx.Response(200, json={"picsureResultId": query_id})
        )
        respx.post(f"{BASE_URL}/picsure/v3/query/{query_id}/status").mock(
            return_value=httpx.Response(200, json={"status": "AVAILABLE"})
        )
        respx.post(f"{BASE_URL}/picsure/v3/query/{query_id}/result").mock(
            return_value=httpx.Response(200, content=b"pfb_data")
        )
        from unittest.mock import patch

        from picsure._models.clause import Clause, PhenotypicFilterType

        session = _make_live_session()
        clause = Clause(
            keys=["\\sex\\"], type=PhenotypicFilterType.FILTER, categories=["Male"]
        )
        output = tmp_path / "test.pfb"
        with patch("picsure._services.export.time.sleep"):
            session.exportAsPFB(clause, output)

        assert output.exists()
        assert output.read_bytes() == b"pfb_data"

    def test_export_pfb_rejects_open_session(self, tmp_path):
        # Open-access deployments don't expose the authorized v3 async
        # flow that PFB export depends on. Surface that as a clear
        # validation error instead of letting the request 401 deep in
        # the async polling loop.
        from picsure._models.clause import Clause, PhenotypicFilterType
        from picsure.errors import PicSureValidationError

        client = MagicMock()
        session = Session(
            client=client,
            user_email="anonymous",
            token_expiration="N/A",
            resources=[Resource(uuid="uuid-1", name="open-hpds", description="")],
            resource_uuid="uuid-1",
            use_legacy_query_path=True,
        )
        clause = Clause(
            keys=["\\sex\\"], type=PhenotypicFilterType.FILTER, categories=["Male"]
        )
        output = tmp_path / "test.pfb"

        with pytest.raises(PicSureValidationError, match="open-access"):
            session.exportAsPFB(clause, output)

        # The submit endpoint must not have been hit — the guard fires
        # before any HTTP traffic.
        assert client.post_json.call_count == 0
        assert client.post_raw_stream.call_count == 0
        assert not output.exists()

    def test_save_query_by_name_forwards_to_service(self, monkeypatch):
        # Verify Session.saveQueryByName forwards to the service layer with
        # the session-bound client, resource UUID, and legacy-flag.
        from picsure._models import session as session_module

        session = _make_session(
            resources=[Resource(uuid="uuid-1", name="hpds", description="x")],
        )
        session._resource_uuid = "uuid-1"
        clause = Clause(
            keys=["\\sex\\"], type=PhenotypicFilterType.FILTER, categories=["Male"]
        )

        captured: dict[str, object] = {}

        def fake_save(
            client,
            resource_uuid,
            query,
            name,
            *,
            use_legacy_query_path,
            overwrite,
        ):
            captured["client"] = client
            captured["resource_uuid"] = resource_uuid
            captured["query"] = query
            captured["name"] = name
            captured["use_legacy_query_path"] = use_legacy_query_path
            captured["overwrite"] = overwrite
            return "qid-fake-001"

        # The session lazy-imports save_query_by_name, so patch the module
        # the service lives in.
        from picsure._services import query_save

        monkeypatch.setattr(query_save, "save_query_by_name", fake_save)

        qid = session.saveQueryByName(clause, "Cohort A", overwrite=True)

        assert qid == "qid-fake-001"
        assert captured["client"] is session._client
        assert captured["resource_uuid"] == "uuid-1"
        assert captured["query"] is clause
        assert captured["name"] == "Cohort A"
        assert captured["use_legacy_query_path"] is False
        assert captured["overwrite"] is True
        # Silence unused-import warning from ruff for the imported alias.
        assert session_module.Session is Session

    def test_export_csv(self, tmp_path):
        session = _make_session()
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        output = tmp_path / "test.csv"
        session.exportCSV(df, output)

        assert output.exists()
        assert "id,name" in output.read_text()

    def test_export_tsv(self, tmp_path):
        session = _make_session()
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        output = tmp_path / "test.tsv"
        session.exportTSV(df, output)

        assert output.exists()
        assert "id\tname" in output.read_text()


class TestSessionClose:
    def test_close_calls_client_close(self):
        session = _make_session()
        session.close()
        session._client.close.assert_called_once()

    def test_close_is_idempotent(self):
        session = _make_session()
        session.close()
        # A second close() must not raise.
        session.close()

    def test_context_manager_returns_session(self):
        session = _make_session()
        with session as s:
            assert s is session

    def test_context_manager_closes_on_exit(self):
        session = _make_session()
        with session:
            pass
        session._client.close.assert_called_once()

    def test_context_manager_closes_on_exception(self):
        session = _make_session()
        with pytest.raises(RuntimeError), session:  # noqa: PT012
            raise RuntimeError("boom")
        session._client.close.assert_called_once()


class TestSessionLoadQueryByID:
    @respx.mock
    def test_always_hits_legacy_metadata_endpoint(self):
        # The v3 metadata endpoint is broken on BDC; loadQueryByID pins
        # reads to the legacy path regardless of how the session was
        # connected (authorized v3 sessions still hit legacy here).
        client = _client()
        session = _session_with_resources(
            client,
            resources=[Resource(uuid="r-1", name="hpds", description="x")],
            resource_uuid="r-1",
        )
        body = _metadata_envelope(
            select=[],
            phenotypic={
                "phenotypicFilterType": "FILTER",
                "conceptPath": "\\phs1\\sex\\",
                "values": ["Male"],
                "not": False,
            },
        )
        legacy = respx.get(f"{BASE_URL}/picsure/query/abc-123/metadata").mock(
            return_value=httpx.Response(200, json=body)
        )
        v3 = respx.get(f"{BASE_URL}/picsure/v3/query/abc-123/metadata").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = session.loadQueryByID("abc-123")
        assert legacy.called
        assert not v3.called
        assert isinstance(result, Clause)
        assert result.type == PhenotypicFilterType.FILTER

    @respx.mock
    def test_works_without_resource_uuid_set(self):
        # The metadata endpoint is not scoped to a resource; loadQueryByID
        # must not require setResourceID first.
        client = _client()
        session = _session_with_resources(client, resources=[])
        body = _metadata_envelope(
            select=[],
            phenotypic={
                "phenotypicFilterType": "FILTER",
                "conceptPath": "\\phs1\\sex\\",
                "values": ["Male"],
                "not": False,
            },
        )
        respx.get(f"{BASE_URL}/picsure/query/abc-123/metadata").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = session.loadQueryByID("abc-123")
        assert isinstance(result, Clause)


class TestSessionRunQueryByID:
    @respx.mock
    def test_run_query_by_id_count(self):
        # runQueryByID should load the saved query from /metadata, then
        # execute it against /v3/query/sync and return a CountResult.
        from picsure._models.count_result import CountResult

        client = _client()
        session = _session_with_resources(
            client,
            resources=[Resource(uuid="r-1", name="hpds", description="x")],
            resource_uuid="r-1",
        )
        body = _metadata_envelope(
            select=[],
            phenotypic={
                "phenotypicFilterType": "FILTER",
                "conceptPath": "\\phs1\\sex\\",
                "values": ["Male"],
                "not": False,
            },
        )
        metadata = respx.get(f"{BASE_URL}/picsure/query/abc-123/metadata").mock(
            return_value=httpx.Response(200, json=body)
        )
        sync = respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
            return_value=httpx.Response(200, content=b"42")
        )

        result = session.runQueryByID("abc-123", type="count")

        assert metadata.called
        assert sync.called
        assert isinstance(result, CountResult)
        assert result.value == 42

    @respx.mock
    def test_run_query_by_id_participant(self, participant_response):
        client = _client()
        session = _session_with_resources(
            client,
            resources=[Resource(uuid="r-1", name="hpds", description="x")],
            resource_uuid="r-1",
        )
        body = _metadata_envelope(
            select=["\\phs1\\age\\"],
            phenotypic={
                "phenotypicFilterType": "FILTER",
                "conceptPath": "\\phs1\\sex\\",
                "values": ["Male"],
                "not": False,
            },
        )
        respx.get(f"{BASE_URL}/picsure/query/abc-123/metadata").mock(
            return_value=httpx.Response(200, json=body)
        )
        respx.post(f"{BASE_URL}/picsure/v3/query/sync").mock(
            return_value=httpx.Response(200, content=participant_response)
        )

        df = session.runQueryByID("abc-123", type="participant")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5

    def test_run_query_by_id_rejects_blank_id(self):
        from picsure.errors import PicSureValidationError

        session = _make_live_session()
        with pytest.raises(PicSureValidationError, match="non-empty query ID"):
            session.runQueryByID("   ", type="count")
