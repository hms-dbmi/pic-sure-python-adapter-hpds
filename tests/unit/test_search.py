import json

import httpx
import pytest
import respx

from picsure._models.facet import FacetCategory, FacetSet
from picsure._services import search as search_module
from picsure._services.search import (
    _CONCEPTS_PATH,
    _DEFAULT_PAGE_SIZE,
    _FACETS_PATH,
    _MAX_UNPAGED_ROWS,
    _SERVER_MAX_PAGE_SIZE,
    fetch_facets,
    searchDictionary,
    show_all_facets,
)
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureAuthenticationError,
    PicSureAuthorizationError,
    PicSureConnectionError,
    PicSureConsentDeniedError,
    PicSureValidationError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
CONCEPTS_BASE = f"{BASE_URL}{_CONCEPTS_PATH}"
FACETS_URL = f"{BASE_URL}{_FACETS_PATH}"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _concepts_url(page_size: int, page: int = 0) -> str:
    return f"{CONCEPTS_BASE}?page_number={page}&page_size={page_size}"


def _page(
    rows: list[dict],
    *,
    total: int,
    last: bool,
    number: int = 0,
    size: int | None = None,
) -> dict:
    """Build a Spring Data ``Page`` envelope matching the live dictionary-api."""
    return {
        "content": rows,
        "totalElements": total,
        "totalPages": 1 if size is None else -(-total // size),
        "numberOfElements": len(rows),
        "size": size if size is not None else _DEFAULT_PAGE_SIZE,
        "number": number,
        "first": number == 0,
        "last": last,
        "empty": not rows,
    }


def _rows(start: int, count: int) -> list[dict]:
    return [
        {"conceptPath": f"\\c{i}\\", "name": f"c{i}", "display": f"Concept {i}"}
        for i in range(start, start + count)
    ]


class TestSearch:
    @respx.mock
    def test_consent_denied_raises_typed_error(self):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(
                403,
                json={
                    "errorType": "consent_denied",
                    "message": "You no longer have consent for this saved result",
                },
            )
        )

        with pytest.raises(PicSureConsentDeniedError) as exc_info:
            searchDictionary(_make_client(), term="test")

        exc = exc_info.value
        assert exc.status_code == 403
        assert exc.error_type == "consent_denied"
        assert exc.server_message == "You no longer have consent for this saved result"

    @respx.mock
    def test_returns_dataframe(self, search_response):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = searchDictionary(_make_client(), term="sex")
        assert len(df) == 3
        assert "conceptPath" in df.columns
        assert "name" in df.columns

    @respx.mock
    def test_dataframe_has_correct_columns(self, search_response):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = searchDictionary(_make_client(), term="sex")
        assert list(df.columns) == [
            "conceptPath",
            "name",
            "display",
            "description",
            "dataType",
            "studyId",
            "values",
            "min",
            "max",
            "allowFiltering",
            "meta",
            "studyAcronym",
        ]

    @respx.mock
    def test_continuous_fields_populated(self, search_response):
        import pandas as pd

        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = searchDictionary(_make_client(), term="age")
        age_row = df[df["name"] == "age"].iloc[0]
        assert age_row["min"] == 0.0
        assert age_row["max"] == 100.0
        assert bool(age_row["allowFiltering"]) is True
        assert age_row["meta"] == {"units": "years"}
        assert age_row["studyAcronym"] == "FHS"
        # Categorical rows in same response carry NaN min/max.
        assert pd.isna(df[df["name"] == "sex"].iloc[0]["min"])

    @respx.mock
    def test_include_values_false_still_has_extra_columns(self, search_response):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = searchDictionary(_make_client(), term="sex", include_values=False)
        for col in ("min", "max", "allowFiltering", "meta", "studyAcronym"):
            assert col in df.columns

    @respx.mock
    def test_maps_dataset_and_type_fields(self, search_response):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        df = searchDictionary(_make_client(), term="sex")
        assert df.iloc[0]["studyId"] == "phs000007"
        assert df.iloc[0]["dataType"] == "categorical"
        assert df.iloc[2]["dataType"] == "continuous"

    @respx.mock
    def test_body_shape(self, search_response):
        route = respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        searchDictionary(_make_client(), term="blood pressure")
        body = json.loads(route.calls[0].request.content)
        assert body == {"search": "blood pressure", "facets": []}

    @respx.mock
    def test_sends_facets_in_body(self, search_response):
        route = respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        from picsure._models.facet import Facet

        categories = [
            FacetCategory(
                name="dataset_id",
                display="Dataset",
                description="First node of concept path",
                options=[
                    Facet(
                        value="phs000007",
                        count=54984,
                        display="FHS (phs000007)",
                        description="Framingham Cohort",
                    )
                ],
            )
        ]
        facets = FacetSet(categories)
        facets.add("dataset_id", "phs000007")

        searchDictionary(_make_client(), term="sex", facets=facets)
        body = json.loads(route.calls[0].request.content)
        assert body["facets"] == [
            {
                "name": "phs000007",
                "display": "FHS (phs000007)",
                "description": "Framingham Cohort",
                "fullName": None,
                "count": 54984,
                "children": [],
                "category": "dataset_id",
                "meta": None,
                "categoryRef": {
                    "name": "dataset_id",
                    "display": "Dataset",
                    "description": "First node of concept path",
                },
            }
        ]

    @respx.mock
    def test_consents_included_when_provided(self, search_response):
        route = respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        searchDictionary(
            _make_client(),
            term="age",
            consents=["phs000007.c1", "phs001013.c1"],
        )
        body = json.loads(route.calls[0].request.content)
        assert body["consents"] == ["phs000007.c1", "phs001013.c1"]

    @respx.mock
    def test_consents_omitted_when_empty(self, search_response):
        route = respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        searchDictionary(_make_client(), term="age", consents=[])
        body = json.loads(route.calls[0].request.content)
        assert "consents" not in body

    @respx.mock
    def test_consents_omitted_when_none(self, search_response):
        route = respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        searchDictionary(_make_client(), term="age")
        body = json.loads(route.calls[0].request.content)
        assert "consents" not in body

    @respx.mock
    def test_default_page_size_is_bounded(self, search_response):
        assert _DEFAULT_PAGE_SIZE == 500
        route = respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        searchDictionary(_make_client(), term="age")
        assert route.called
        assert route.calls[0].request.url.params["page_size"] == "500"
        assert route.calls[0].request.url.params["page_number"] == "0"

    @respx.mock
    def test_page_size_used_in_url(self, search_response):
        route = respx.post(_concepts_url(487375)).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        searchDictionary(_make_client(), term="age", page_size=487375)
        assert route.called
        assert route.calls[0].request.url.params["page_size"] == "487375"

    @respx.mock
    def test_deduplicates_by_concept_path(self):
        duplicate_response = {
            "content": [
                {"conceptPath": "\\same\\", "name": "v1", "display": "First"},
                {"conceptPath": "\\same\\", "name": "v1", "display": "Duplicate"},
                {"conceptPath": "\\other\\", "name": "v2", "display": "Different"},
            ],
            "totalElements": 3,
            "last": True,
        }
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=duplicate_response)
        )
        df = searchDictionary(_make_client())
        assert len(df) == 2
        assert df.iloc[0]["display"] == "First"

    @respx.mock
    def test_zero_results_returns_empty_dataframe(self):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(
                200, json={"content": [], "totalElements": 0, "last": True}
            )
        )
        df = searchDictionary(_make_client(), term="nonexistent")
        assert len(df) == 0
        assert "conceptPath" in df.columns

    @respx.mock
    def test_zero_results_prints_note(self, capsys):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(
                200, json={"content": [], "totalElements": 0, "last": True}
            )
        )
        searchDictionary(_make_client(), term="nonexistent")
        assert "0 results" in capsys.readouterr().err

    @respx.mock
    def test_partial_page_is_followed_not_rejected(self):
        # A page carrying last=False used to raise "truncated". It is an
        # ordinary pagination boundary, so it must be followed instead.
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=0)).mock(
            return_value=httpx.Response(
                200, json=_page(_rows(0, 1), total=2, last=False)
            )
        )
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=1)).mock(
            return_value=httpx.Response(
                200, json=_page(_rows(1, 1), total=2, last=True, number=1)
            )
        )
        df = searchDictionary(_make_client(), term="x")
        assert len(df) == 2
        assert df.attrs["has_more"] is False
        assert df.attrs["total_elements"] == 2

    @respx.mock
    def test_last_missing_but_counts_match_ok(self):
        # last absent and totalElements equal to what came back: no
        # evidence of another page, so stop after one request.
        response = {
            "content": [{"conceptPath": "\\x\\", "name": "x"}],
            "totalElements": 1,
        }
        route = respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=response)
        )
        df = searchDictionary(_make_client(), term="x")
        assert len(df) == 1
        assert len(route.calls) == 1

    @respx.mock
    def test_total_elements_mismatch_does_not_raise(self):
        # last: True is authoritative even when totalElements disagrees;
        # the old code raised "truncated" on this shape.
        response = {
            "content": [{"conceptPath": "\\x\\", "name": "x"}],
            "totalElements": 3,
            "last": True,
        }
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(200, json=response)
        )
        df = searchDictionary(_make_client(), term="x")
        assert len(df) == 1
        assert df.attrs["has_more"] is False

    @respx.mock
    def test_no_truncation_error_message_survives(self):
        # Guard against the PYR-12 wording coming back: the message told
        # users to act on something they do not control.
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=0)).mock(
            return_value=httpx.Response(
                200, json=_page(_rows(0, 500), total=600, last=False, size=500)
            )
        )
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=1)).mock(
            return_value=httpx.Response(
                200,
                json=_page(_rows(500, 100), total=600, last=True, number=1, size=500),
            )
        )
        df = searchDictionary(_make_client(), term="x")
        assert len(df) == 600


class TestSearchPagination:
    @respx.mock
    def test_unpaged_walks_every_page_in_order(self):
        routes = []
        for n, (start, count, last) in enumerate(
            [(0, 500, False), (500, 500, False), (1000, 277, True)]
        ):
            routes.append(
                respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=n)).mock(
                    return_value=httpx.Response(
                        200,
                        json=_page(
                            _rows(start, count),
                            total=1277,
                            last=last,
                            number=n,
                            size=500,
                        ),
                    )
                )
            )
        df = searchDictionary(_make_client())
        assert len(df) == 1277
        assert [r.calls[0].request.url.params["page_number"] for r in routes] == [
            "0",
            "1",
            "2",
        ]
        assert df.attrs["pages_fetched"] == 3
        assert df.attrs["page"] is None
        assert df.attrs["has_more"] is False
        assert df.attrs["total_elements"] == 1277

    @respx.mock
    def test_explicit_page_issues_one_request_for_that_page(self):
        route = respx.post(_concepts_url(50, page=3)).mock(
            return_value=httpx.Response(
                200,
                json=_page(_rows(150, 50), total=1777, last=False, number=3, size=50),
            )
        )
        df = searchDictionary(_make_client(), page=3, page_size=50)
        assert len(route.calls) == 1
        assert route.calls[0].request.url.params["page_number"] == "3"
        assert route.calls[0].request.url.params["page_size"] == "50"
        assert len(df) == 50
        assert df.attrs["page"] == 3
        assert df.attrs["page_size"] == 50
        assert df.attrs["has_more"] is True
        assert df.attrs["total_elements"] == 1777

    @respx.mock
    def test_explicit_last_page_reports_no_more(self):
        respx.post(_concepts_url(500, page=3)).mock(
            return_value=httpx.Response(
                200, json=_page(_rows(1500, 277), total=1777, last=True, number=3)
            )
        )
        df = searchDictionary(_make_client(), page=3)
        assert df.attrs["has_more"] is False
        assert len(df) == 277

    @respx.mock
    def test_explicit_page_zero_is_not_treated_as_unpaged(self):
        route = respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=0)).mock(
            return_value=httpx.Response(
                200, json=_page(_rows(0, 500), total=1777, last=False, size=500)
            )
        )
        df = searchDictionary(_make_client(), page=0)
        assert len(route.calls) == 1
        assert len(df) == 500
        assert df.attrs["page"] == 0
        assert df.attrs["has_more"] is True

    @respx.mock
    def test_pages_are_disjoint_and_sum_to_total(self):
        # Mirrors the live check against the 1777-concept dictionary.
        for n, (start, count, last) in enumerate(
            [(0, 500, False), (500, 500, False), (1000, 500, False), (1500, 277, True)]
        ):
            respx.post(_concepts_url(500, page=n)).mock(
                return_value=httpx.Response(
                    200,
                    json=_page(
                        _rows(start, count), total=1777, last=last, number=n, size=500
                    ),
                )
            )
        collected: list[str] = []
        for n in range(4):
            page_df = searchDictionary(_make_client(), page=n, page_size=500)
            collected.extend(page_df["conceptPath"].tolist())
        assert len(collected) == 1777
        assert len(set(collected)) == 1777

    @respx.mock
    def test_has_more_derived_from_total_when_last_absent(self):
        respx.post(_concepts_url(10, page=1)).mock(
            return_value=httpx.Response(
                200, json={"content": _rows(10, 10), "totalElements": 25}
            )
        )
        df = searchDictionary(_make_client(), page=1, page_size=10)
        assert df.attrs["has_more"] is True

    @respx.mock
    def test_has_more_false_when_total_consumed_and_last_absent(self):
        respx.post(_concepts_url(10, page=2)).mock(
            return_value=httpx.Response(
                200, json={"content": _rows(20, 5), "totalElements": 25}
            )
        )
        df = searchDictionary(_make_client(), page=2, page_size=10)
        assert df.attrs["has_more"] is False

    @respx.mock
    def test_full_page_without_metadata_assumes_more(self):
        respx.post(_concepts_url(3, page=0)).mock(
            return_value=httpx.Response(200, json={"content": _rows(0, 3)})
        )
        df = searchDictionary(_make_client(), page=0, page_size=3)
        assert df.attrs["has_more"] is True
        assert df.attrs["total_elements"] is None

    @respx.mock
    def test_unpaged_stops_on_empty_page(self):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=0)).mock(
            return_value=httpx.Response(200, json={"content": _rows(0, 500)})
        )
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=1)).mock(
            return_value=httpx.Response(200, json={"content": []})
        )
        df = searchDictionary(_make_client())
        assert len(df) == 500
        assert df.attrs["pages_fetched"] == 2

    @respx.mock
    def test_unpaged_refuses_a_dictionary_above_the_ceiling(self):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=0)).mock(
            return_value=httpx.Response(
                200,
                json=_page(
                    _rows(0, 500), total=_MAX_UNPAGED_ROWS + 1, last=False, size=500
                ),
            )
        )
        with pytest.raises(PicSureValidationError, match="page=0"):
            searchDictionary(_make_client())

    @respx.mock
    def test_ceiling_error_names_the_match_count(self):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=0)).mock(
            return_value=httpx.Response(
                200, json=_page(_rows(0, 500), total=250_000, last=False, size=500)
            )
        )
        with pytest.raises(PicSureValidationError, match="250000"):
            searchDictionary(_make_client())

    @respx.mock
    def test_explicit_page_is_exempt_from_the_ceiling(self):
        respx.post(_concepts_url(500, page=0)).mock(
            return_value=httpx.Response(
                200, json=_page(_rows(0, 500), total=5_000_000, last=False, size=500)
            )
        )
        df = searchDictionary(_make_client(), page=0, page_size=500)
        assert len(df) == 500
        assert df.attrs["total_elements"] == 5_000_000
        assert df.attrs["has_more"] is True

    @respx.mock
    def test_ceiling_enforced_on_accumulated_rows_when_total_absent(self, monkeypatch):
        # Without totalElements the up-front check cannot fire, so the walk
        # has to stop itself once it has collected too much.
        monkeypatch.setattr(search_module, "_MAX_UNPAGED_ROWS", 5)
        for n in range(3):
            respx.post(_concepts_url(3, page=n)).mock(
                return_value=httpx.Response(200, json={"content": _rows(n * 3, 3)})
            )
        with pytest.raises(PicSureValidationError, match="too many"):
            searchDictionary(_make_client(), page_size=3)

    @pytest.mark.parametrize("bad", [0, -1, -500])
    def test_non_positive_page_size_rejected(self, bad):
        with pytest.raises(PicSureValidationError, match="page_size"):
            searchDictionary(_make_client(), page_size=bad)

    def test_page_size_above_server_max_rejected(self):
        with pytest.raises(PicSureValidationError, match="HTTP 400"):
            searchDictionary(_make_client(), page_size=_SERVER_MAX_PAGE_SIZE + 1)

    def test_server_max_page_size_is_java_int_max(self):
        assert _SERVER_MAX_PAGE_SIZE == 2_147_483_647

    def test_negative_page_rejected(self):
        with pytest.raises(PicSureValidationError, match="zero-based"):
            searchDictionary(_make_client(), page=-1)

    @pytest.mark.parametrize("bad", [True, 1.5, "2"])
    def test_non_integer_page_rejected(self, bad):
        with pytest.raises(PicSureValidationError, match="`page` must be an integer"):
            searchDictionary(_make_client(), page=bad)

    @pytest.mark.parametrize("bad", [True, 1.5, "2"])
    def test_non_integer_page_size_rejected(self, bad):
        with pytest.raises(
            PicSureValidationError, match="`page_size` must be an integer"
        ):
            searchDictionary(_make_client(), page_size=bad)

    def test_pagination_validated_before_any_request(self):
        # No respx mock is installed, so any outgoing call would error.
        with pytest.raises(PicSureValidationError):
            searchDictionary(_make_client(), page=-3)

    @respx.mock
    def test_empty_result_still_carries_attrs(self):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=0)).mock(
            return_value=httpx.Response(200, json=_page([], total=0, last=True))
        )
        df = searchDictionary(_make_client(), term="nhanes", consents=["phs999901.c1"])
        assert len(df) == 0
        assert df.attrs["total_elements"] == 0
        assert df.attrs["has_more"] is False

    @respx.mock
    def test_consents_forwarded_on_every_page(self):
        bodies = []
        for n, last in enumerate([False, True]):
            respx.post(_concepts_url(_DEFAULT_PAGE_SIZE, page=n)).mock(
                return_value=httpx.Response(
                    200,
                    json=_page(
                        _rows(n * 500, 500 if not last else 3),
                        total=503,
                        last=last,
                        number=n,
                        size=500,
                    ),
                )
            )
        df = searchDictionary(_make_client(), consents=["phs999901.c1"])
        for call in respx.calls:
            bodies.append(json.loads(call.request.content))
        assert len(bodies) == 2
        assert all(b["consents"] == ["phs999901.c1"] for b in bodies)
        assert len(df) == 503


class TestSearchTransportErrors:
    @respx.mock
    def test_server_error_raises_connection_error(self):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(PicSureConnectionError, match="search"):
            searchDictionary(_make_client(), term="test")

    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.post(_concepts_url(_DEFAULT_PAGE_SIZE)).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(PicSureConnectionError):
            searchDictionary(_make_client(), term="test")


class TestFetchFacets:
    @respx.mock
    def test_consent_denied_raises_typed_error(self):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(
                403,
                json={
                    "errorType": "consent_denied",
                    "message": "You no longer have consent for this saved result",
                },
            )
        )

        with pytest.raises(PicSureConsentDeniedError) as exc_info:
            fetch_facets(_make_client())

        exc = exc_info.value
        assert exc.status_code == 403
        assert exc.error_type == "consent_denied"
        assert exc.server_message == "You no longer have consent for this saved result"

    @respx.mock
    def test_returns_facet_categories(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        cats = fetch_facets(_make_client())
        assert len(cats) == 3
        assert cats[0].name == "dataset_id"
        assert cats[1].name == "data_type"
        assert cats[2].name == "Consortium_Curated_Facets"

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
    def test_nested_children_preserved(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        cats = fetch_facets(_make_client())
        curated = cats[2]
        parent = curated.options[0]
        assert len(parent.children) == 2
        assert {c.value for c in parent.children} == {"Infected", "Non-infected"}

    @respx.mock
    def test_body_shape_defaults_to_global_counts(self, facets_response):
        route = respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        fetch_facets(_make_client())
        body = json.loads(route.calls[0].request.content)
        assert body == {"search": "", "facets": []}

    @respx.mock
    def test_term_forwarded_in_body(self, facets_response):
        route = respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        fetch_facets(_make_client(), term="blood")
        body = json.loads(route.calls[0].request.content)
        assert body["search"] == "blood"
        assert body["facets"] == []

    @respx.mock
    def test_facets_forwarded_in_body(self, facets_response):
        route = respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        from picsure._models.facet import Facet

        categories = [
            FacetCategory(
                name="dataset_id",
                display="Dataset",
                description="First node of concept path",
                options=[
                    Facet(
                        value="phs000007",
                        count=54984,
                        display="FHS (phs000007)",
                        description="Framingham Cohort",
                    )
                ],
            )
        ]
        fs = FacetSet(categories)
        fs.add("dataset_id", "phs000007")

        fetch_facets(_make_client(), term="blood", facets=fs)
        body = json.loads(route.calls[0].request.content)
        assert body["search"] == "blood"
        assert len(body["facets"]) == 1
        assert body["facets"][0]["name"] == "phs000007"
        assert body["facets"][0]["category"] == "dataset_id"

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


_EXPECTED_COLUMNS = [
    "category",
    "Category Display",
    "display",
    "description",
    "value",
    "count",
]


class TestShowAllFacets:
    @respx.mock
    def test_returns_dataframe(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        df = show_all_facets(_make_client())
        assert list(df.columns) == _EXPECTED_COLUMNS

    @respx.mock
    def test_option_display_and_description_populated(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        df = show_all_facets(_make_client())
        fhs = df[df["value"] == "phs000007"].iloc[0]
        assert fhs["display"] == "FHS (phs000007)"
        assert fhs["description"] == "Framingham Cohort"
        assert fhs["Category Display"] == "Dataset"
        assert fhs["category"] == "dataset_id"

    @respx.mock
    def test_has_all_facet_values(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        df = show_all_facets(_make_client())
        # 2 dataset_id + 2 data_type + 1 parent + 2 nested children = 7
        assert len(df) == 7
        assert set(df["category"]) == {
            "dataset_id",
            "data_type",
            "Consortium_Curated_Facets",
        }

    @respx.mock
    def test_flattens_nested_children(self, facets_response):
        respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        df = show_all_facets(_make_client())
        curated_values = set(df[df["category"] == "Consortium_Curated_Facets"]["value"])
        assert curated_values == {
            "RECOVER Adult Curated",
            "Infected",
            "Non-infected",
        }

    @respx.mock
    def test_empty_facets_returns_empty_dataframe(self):
        respx.post(FACETS_URL).mock(return_value=httpx.Response(200, json=[]))
        df = show_all_facets(_make_client())
        assert len(df) == 0
        assert list(df.columns) == _EXPECTED_COLUMNS

    @respx.mock
    def test_forwards_term_and_facets(self, facets_response):
        route = respx.post(FACETS_URL).mock(
            return_value=httpx.Response(200, json=facets_response)
        )
        from picsure._models.facet import Facet

        categories = [
            FacetCategory(
                name="dataset_id",
                display="Dataset",
                description="First node of concept path",
                options=[
                    Facet(value="phs000007", count=54984, display="FHS"),
                ],
            )
        ]
        fs = FacetSet(categories)
        fs.add("dataset_id", "phs000007")
        show_all_facets(_make_client(), term="blood", facets=fs)
        body = json.loads(route.calls[0].request.content)
        assert body["search"] == "blood"
        assert len(body["facets"]) == 1
        assert body["facets"][0]["name"] == "phs000007"


class TestDictionaryRefusalIsNotAvailability:
    """401/403 on search, facets and showAllFacets name the real cause."""

    @respx.mock
    def test_search_401_names_the_token(self):
        respx.post(url__startswith=CONCEPTS_BASE).mock(
            return_value=httpx.Response(401, text="Token is invalid or expired")
        )
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            searchDictionary(_make_client(), "sex")
        message = str(exc_info.value)
        assert "token was rejected" in message
        assert "unavailable" not in message

    @respx.mock
    def test_search_403_names_the_permission(self):
        respx.post(url__startswith=CONCEPTS_BASE).mock(
            return_value=httpx.Response(403, text="Forbidden")
        )
        with pytest.raises(PicSureAuthorizationError) as exc_info:
            searchDictionary(_make_client(), "sex")
        message = str(exc_info.value)
        assert "not authorized for it" in message
        assert "unavailable" not in message

    @respx.mock
    def test_facets_401_names_the_token(self):
        respx.post(FACETS_URL).mock(return_value=httpx.Response(401, text="nope"))
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            fetch_facets(_make_client())
        assert "unavailable" not in str(exc_info.value)

    @respx.mock
    def test_facets_403_names_the_permission(self):
        respx.post(FACETS_URL).mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(PicSureAuthorizationError):
            fetch_facets(_make_client())

    @respx.mock
    def test_show_all_facets_401_names_the_token(self):
        respx.post(FACETS_URL).mock(return_value=httpx.Response(401, text="nope"))
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            show_all_facets(_make_client())
        assert "unavailable" not in str(exc_info.value)

    @respx.mock
    def test_show_all_facets_403_names_the_permission(self):
        respx.post(FACETS_URL).mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(PicSureAuthorizationError):
            show_all_facets(_make_client())
