import httpx
import pytest
import respx

from picsure._models.facet import FacetCategory, FacetSet
from picsure._services.search import fetch_facets, search, show_all_facets
from picsure._transport.client import PicSureClient
from picsure.errors import PicSureConnectionError

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
RESOURCE_UUID = "resource-uuid-aaaa-1111"
SEARCH_URL = f"{BASE_URL}/picsure/search/{RESOURCE_UUID}"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


class TestSearch:
    @respx.mock
    def test_returns_dataframe(self, search_response):
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        df = search(client, RESOURCE_UUID, term="sex")
        assert len(df) == 3
        assert "conceptPath" in df.columns
        assert "name" in df.columns

    @respx.mock
    def test_dataframe_has_correct_columns(self, search_response):
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        df = search(client, RESOURCE_UUID, term="sex")
        expected_cols = [
            "conceptPath",
            "name",
            "display",
            "description",
            "dataType",
            "studyId",
            "values",
        ]
        assert list(df.columns) == expected_cols

    @respx.mock
    def test_include_values_false_omits_values_column(self, search_response):
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        df = search(client, RESOURCE_UUID, term="sex", include_values=False)
        assert "values" not in df.columns
        assert "conceptPath" in df.columns

    @respx.mock
    def test_sends_search_term_in_body(self, search_response):
        route = respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        search(client, RESOURCE_UUID, term="blood pressure")
        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["query"]["searchTerm"] == "blood pressure"

    @respx.mock
    def test_sends_facets_in_body(self, search_response):
        route = respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        categories = [
            FacetCategory(name="study_ids", display="Study", options=[]),
        ]
        facets = FacetSet(categories)
        facets.add("study_ids", "phs000007")

        client = _make_client()
        search(client, RESOURCE_UUID, term="sex", facets=facets)
        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        included = body["query"]["includedFacets"]
        assert len(included) == 1
        assert included[0]["name"] == "study_ids"
        assert included[0]["values"] == ["phs000007"]

    @respx.mock
    def test_deduplicates_by_concept_path(self):
        duplicate_response = {
            "results": [
                {
                    "conceptPath": "\\same\\path\\",
                    "name": "var1",
                    "display": "First",
                },
                {
                    "conceptPath": "\\same\\path\\",
                    "name": "var1",
                    "display": "Duplicate",
                },
                {
                    "conceptPath": "\\other\\path\\",
                    "name": "var2",
                    "display": "Different",
                },
            ],
            "facets": [],
            "totalCount": 3,
        }
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=duplicate_response)
        )
        client = _make_client()
        df = search(client, RESOURCE_UUID)
        assert len(df) == 2
        assert df.iloc[0]["display"] == "First"

    @respx.mock
    def test_zero_results_returns_empty_dataframe(self):
        empty_response = {"results": [], "facets": [], "totalCount": 0}
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=empty_response)
        )
        client = _make_client()
        df = search(client, RESOURCE_UUID, term="nonexistent")
        assert len(df) == 0
        assert "conceptPath" in df.columns

    @respx.mock
    def test_zero_results_prints_note(self, capsys):
        empty_response = {"results": [], "facets": [], "totalCount": 0}
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=empty_response)
        )
        client = _make_client()
        search(client, RESOURCE_UUID, term="nonexistent")
        captured = capsys.readouterr()
        assert "0 results" in captured.err

    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        client = _make_client()
        with pytest.raises(PicSureConnectionError, match="search"):
            search(client, RESOURCE_UUID, term="test")

    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.post(SEARCH_URL).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        client = _make_client()
        with pytest.raises(PicSureConnectionError):
            search(client, RESOURCE_UUID, term="test")


class TestFetchFacets:
    @respx.mock
    def test_returns_facet_categories(self, search_response):
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        cats = fetch_facets(client, RESOURCE_UUID)
        assert len(cats) == 2
        assert cats[0].name == "study_ids"
        assert cats[1].name == "data_type"

    @respx.mock
    def test_facet_options_populated(self, search_response):
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        cats = fetch_facets(client, RESOURCE_UUID)
        assert len(cats[0].options) == 2
        assert cats[0].options[0].value == "phs000007"
        assert cats[0].options[0].count == 42

    @respx.mock
    def test_sends_empty_search_term(self, search_response):
        route = respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        fetch_facets(client, RESOURCE_UUID)
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["query"]["searchTerm"] == ""


class TestShowAllFacets:
    @respx.mock
    def test_returns_dataframe(self, search_response):
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        df = show_all_facets(client, RESOURCE_UUID)
        assert list(df.columns) == ["category", "display", "value", "count"]

    @respx.mock
    def test_has_all_facet_values(self, search_response):
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        client = _make_client()
        df = show_all_facets(client, RESOURCE_UUID)
        assert len(df) == 4  # 2 study + 2 data_type
        assert set(df["category"]) == {"study_ids", "data_type"}

    @respx.mock
    def test_empty_facets_returns_empty_dataframe(self):
        empty = {"results": [], "facets": [], "totalCount": 0}
        respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=empty)
        )
        client = _make_client()
        df = show_all_facets(client, RESOURCE_UUID)
        assert len(df) == 0
        assert list(df.columns) == ["category", "display", "value", "count"]
