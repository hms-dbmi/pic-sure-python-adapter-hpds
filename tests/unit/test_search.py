import json

import httpx
import pytest
import respx

from picsure._models.facet import FacetCategory, FacetSet
from picsure._services.search import (
    fetch_facets,
    fetch_total_concepts,
    search,
    show_all_facets,
)
from picsure._transport.client import PicSureClient
from picsure.errors import PicSureConnectionError

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
CONCEPTS_BASE = f"{BASE_URL}/picsure/proxy/dictionary-api/concepts"
FACETS_URL = f"{BASE_URL}/picsure/proxy/dictionary-api/facets"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _concepts_url(page_size: int) -> str:
    return f"{CONCEPTS_BASE}?page_number=0&page_size={page_size}"


class TestSearch:
    @respx.mock
    def test_returns_dataframe(self, search_response):
        respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = search(_make_client(), term="sex")
        assert len(df) == 3
        assert "conceptPath" in df.columns
        assert "name" in df.columns

    @respx.mock
    def test_dataframe_has_correct_columns(self, search_response):
        respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = search(_make_client(), term="sex")
        assert list(df.columns) == [
            "conceptPath",
            "name",
            "display",
            "description",
            "dataType",
            "studyId",
            "values",
        ]

    @respx.mock
    def test_maps_dataset_and_type_fields(self, search_response):
        respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = search(_make_client(), term="sex")
        assert df.iloc[0]["studyId"] == "phs000007"
        assert df.iloc[0]["dataType"] == "categorical"
        assert df.iloc[2]["dataType"] == "continuous"

    @respx.mock
    def test_include_values_false_omits_values_column(self, search_response):
        respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = search(_make_client(), term="sex", include_values=False)
        assert "values" not in df.columns
        assert "conceptPath" in df.columns

    @respx.mock
    def test_body_shape(self, search_response):
        route = respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        search(_make_client(), term="blood pressure")
        body = json.loads(route.calls[0].request.content)
        assert body == {"search": "blood pressure", "facets": []}

    @respx.mock
    def test_sends_facets_in_body(self, search_response):
        route = respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        categories = [FacetCategory(name="dataset_id", display="Dataset", options=[])]
        facets = FacetSet(categories)
        facets.add("dataset_id", "phs000007")

        search(_make_client(), term="sex", facets=facets)
        body = json.loads(route.calls[0].request.content)
        assert body["facets"] == [{"name": "dataset_id", "values": ["phs000007"]}]

    @respx.mock
    def test_consents_included_when_provided(self, search_response):
        route = respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        search(
            _make_client(),
            term="age",
            consents=["phs000007.c1", "phs001013.c1"],
        )
        body = json.loads(route.calls[0].request.content)
        assert body["consents"] == ["phs000007.c1", "phs001013.c1"]

    @respx.mock
    def test_consents_omitted_when_empty(self, search_response):
        route = respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        search(_make_client(), term="age", consents=[])
        body = json.loads(route.calls[0].request.content)
        assert "consents" not in body

    @respx.mock
    def test_consents_omitted_when_none(self, search_response):
        route = respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        search(_make_client(), term="age")
        body = json.loads(route.calls[0].request.content)
        assert "consents" not in body

    @respx.mock
    def test_page_size_used_in_url(self, search_response):
        route = respx.post(_concepts_url(487375)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        search(_make_client(), term="age", page_size=487375)
        assert route.called

    @respx.mock
    def test_non_positive_page_size_falls_back_to_default(self, search_response):
        route = respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        search(_make_client(), term="age", page_size=0)
        assert route.called

    @respx.mock
    def test_deduplicates_by_concept_path(self):
        duplicate_response = {
            "content": [
                {"conceptPath": "\\same\\", "name": "v1", "display": "First"},
                {"conceptPath": "\\same\\", "name": "v1", "display": "Duplicate"},
                {"conceptPath": "\\other\\", "name": "v2", "display": "Different"},
            ],
            "totalElements": 3,
        }
        respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json=duplicate_response)
        )
        df = search(_make_client())
        assert len(df) == 2
        assert df.iloc[0]["display"] == "First"

    @respx.mock
    def test_zero_results_returns_empty_dataframe(self):
        respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json={"content": [], "totalElements": 0})
        )
        df = search(_make_client(), term="nonexistent")
        assert len(df) == 0
        assert "conceptPath" in df.columns

    @respx.mock
    def test_zero_results_prints_note(self, capsys):
        respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(200, json={"content": [], "totalElements": 0})
        )
        search(_make_client(), term="nonexistent")
        assert "0 results" in capsys.readouterr().err

    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.post(_concepts_url(100)).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(PicSureConnectionError, match="search"):
            search(_make_client(), term="test")

    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.post(_concepts_url(100)).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(PicSureConnectionError):
            search(_make_client(), term="test")


class TestFetchTotalConcepts:
    @respx.mock
    def test_returns_total_elements(self):
        respx.post(_concepts_url(1)).mock(
            return_value=httpx.Response(
                200, json={"content": [], "totalElements": 487375}
            )
        )
        assert fetch_total_concepts(_make_client()) == 487375

    @respx.mock
    def test_body_shape(self):
        route = respx.post(_concepts_url(1)).mock(
            return_value=httpx.Response(200, json={"totalElements": 0})
        )
        fetch_total_concepts(_make_client())
        body = json.loads(route.calls[0].request.content)
        assert body == {"search": "", "facets": []}

    @respx.mock
    def test_consents_forwarded(self):
        route = respx.post(_concepts_url(1)).mock(
            return_value=httpx.Response(200, json={"totalElements": 0})
        )
        fetch_total_concepts(_make_client(), consents=["phs000007.c1"])
        body = json.loads(route.calls[0].request.content)
        assert body["consents"] == ["phs000007.c1"]

    @respx.mock
    def test_missing_total_returns_zero(self):
        respx.post(_concepts_url(1)).mock(
            return_value=httpx.Response(200, json={"content": []})
        )
        assert fetch_total_concepts(_make_client()) == 0

    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.post(_concepts_url(1)).mock(return_value=httpx.Response(500))
        with pytest.raises(PicSureConnectionError, match="dictionary"):
            fetch_total_concepts(_make_client())


class TestFetchFacets:
    @respx.mock
    def test_returns_facet_categories(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        cats = fetch_facets(_make_client())
        assert len(cats) == 2
        assert cats[0].name == "dataset_id"
        assert cats[1].name == "data_type"

    @respx.mock
    def test_facet_options_populated(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        cats = fetch_facets(_make_client())
        assert len(cats[0].options) == 2
        assert cats[0].options[0].value == "phs000007"
        assert cats[0].options[0].count == 54984
        assert cats[0].options[0].display == "FHS (phs000007)"

    @respx.mock
    def test_body_shape(self, facets_response):
        route = respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        fetch_facets(_make_client())
        body = json.loads(route.calls[0].request.content)
        assert body == {"search": "", "facets": []}

    @respx.mock
    def test_consents_forwarded(self, facets_response):
        route = respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        fetch_facets(_make_client(), consents=["phs000007.c1"])
        body = json.loads(route.calls[0].request.content)
        assert body["consents"] == ["phs000007.c1"]

    @respx.mock
    def test_consents_omitted_when_empty(self, facets_response):
        route = respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        fetch_facets(_make_client(), consents=[])
        body = json.loads(route.calls[0].request.content)
        assert "consents" not in body

    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.post(FACETS_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(PicSureConnectionError, match="facets"):
            fetch_facets(_make_client())


class TestShowAllFacets:
    @respx.mock
    def test_returns_dataframe(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        df = show_all_facets(_make_client())
        assert list(df.columns) == ["category", "display", "value", "count"]

    @respx.mock
    def test_has_all_facet_values(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        df = show_all_facets(_make_client())
        assert len(df) == 4
        assert set(df["category"]) == {"dataset_id", "data_type"}

    @respx.mock
    def test_empty_facets_returns_empty_dataframe(self):
        respx.post(FACETS_URL).mock(return_value=httpx.Response(200, json=[]))
        df = show_all_facets(_make_client())
        assert len(df) == 0
        assert list(df.columns) == ["category", "display", "value", "count"]
