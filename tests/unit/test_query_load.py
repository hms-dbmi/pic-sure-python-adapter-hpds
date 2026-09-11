# ruff: noqa: E402
import pytest

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.query import Query
from picsure._services.query_load import _parse_phenotypic
from picsure.errors import PicSureQueryError, PicSureValidationError


class TestParsePhenotypicLeaf:
    def test_filter_leaf_with_categories(self):
        node = {
            "phenotypicFilterType": "FILTER",
            "conceptPath": "\\phs1\\sex\\",
            "values": ["Male"],
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.keys == ("\\phs1\\sex\\",)
        assert result.type == PhenotypicFilterType.FILTER
        assert result.categories == ("Male",)
        assert result.min is None
        assert result.max is None

    def test_filter_leaf_with_min_and_max(self):
        node = {
            "phenotypicFilterType": "FILTER",
            "conceptPath": "\\phs1\\age\\",
            "min": 40.0,
            "max": 65.5,
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.type == PhenotypicFilterType.FILTER
        assert result.min == 40.0
        assert result.max == 65.5
        assert result.categories is None

    def test_required_leaf(self):
        node = {
            "phenotypicFilterType": "REQUIRED",
            "conceptPath": "\\phs1\\bmi\\",
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.type == PhenotypicFilterType.REQUIRE
        assert result.keys == ("\\phs1\\bmi\\",)

    def test_any_record_of_leaf(self):
        node = {
            "phenotypicFilterType": "ANY_RECORD_OF",
            "conceptPath": "\\phs1\\meds\\",
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.type == PhenotypicFilterType.ANYRECORD

    def test_unknown_filter_type_raises(self):
        node = {
            "phenotypicFilterType": "MYSTERY",
            "conceptPath": "\\phs1\\x\\",
            "not": False,
        }
        with pytest.raises(PicSureQueryError, match="MYSTERY"):
            _parse_phenotypic(node)

    def test_leaf_with_not_true_raises(self):
        node = {
            "phenotypicFilterType": "FILTER",
            "conceptPath": "\\phs1\\sex\\",
            "values": ["Male"],
            "not": True,
        }
        with pytest.raises(PicSureValidationError, match="NOT"):
            _parse_phenotypic(node)

    def test_leaf_missing_concept_path_raises(self):
        node = {"phenotypicFilterType": "REQUIRED", "not": False}
        with pytest.raises(PicSureQueryError, match="conceptPath"):
            _parse_phenotypic(node)


class TestParsePhenotypicSubquery:
    def _filter(self, path: str, val: str) -> dict:  # type: ignore[type-arg]
        return {
            "phenotypicFilterType": "FILTER",
            "conceptPath": path,
            "values": [val],
            "not": False,
        }

    def test_and_subquery(self):
        node = {
            "operator": "AND",
            "phenotypicClauses": [
                self._filter("\\phs1\\sex\\", "Male"),
                self._filter("\\phs1\\copd\\", "Yes"),
            ],
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, ClauseGroup)
        assert result.operator == GroupOperator.AND
        assert len(result.clauses) == 2
        assert all(isinstance(c, Clause) for c in result.clauses)

    def test_or_subquery(self):
        node = {
            "operator": "OR",
            "phenotypicClauses": [
                self._filter("\\phs1\\copd\\", "Yes"),
                self._filter("\\phs1\\asthma\\", "Yes"),
            ],
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, ClauseGroup)
        assert result.operator == GroupOperator.OR

    def test_nested_subquery(self):
        inner = {
            "operator": "OR",
            "phenotypicClauses": [
                self._filter("\\phs1\\copd\\", "Yes"),
                self._filter("\\phs1\\asthma\\", "Yes"),
            ],
            "not": False,
        }
        outer = {
            "operator": "AND",
            "phenotypicClauses": [self._filter("\\phs1\\sex\\", "Male"), inner],
            "not": False,
        }
        result = _parse_phenotypic(outer)
        assert isinstance(result, ClauseGroup)
        assert result.operator == GroupOperator.AND
        nested = result.clauses[1]
        assert isinstance(nested, ClauseGroup)
        assert nested.operator == GroupOperator.OR

    def test_subquery_with_not_true_raises(self):
        node = {
            "operator": "AND",
            "phenotypicClauses": [self._filter("\\phs1\\sex\\", "Male")],
            "not": True,
        }
        with pytest.raises(PicSureValidationError, match="NOT"):
            _parse_phenotypic(node)

    def test_unknown_operator_raises(self):
        node = {
            "operator": "XOR",
            "phenotypicClauses": [self._filter("\\phs1\\sex\\", "Male")],
            "not": False,
        }
        with pytest.raises(PicSureQueryError, match="XOR"):
            _parse_phenotypic(node)

    def test_subquery_missing_clauses_raises(self):
        node = {"operator": "AND", "not": False}
        with pytest.raises(PicSureQueryError, match="phenotypicClauses"):
            _parse_phenotypic(node)

    def test_unknown_node_shape_raises(self):
        node = {"foo": "bar"}
        with pytest.raises(PicSureQueryError):
            _parse_phenotypic(node)


from picsure._services.query_load import _to_query


class TestToQuery:
    def _filter(self, path: str, val: str) -> dict:  # type: ignore[type-arg]
        return {
            "phenotypicFilterType": "FILTER",
            "conceptPath": path,
            "values": [val],
            "not": False,
        }

    def test_phenotypic_only(self):
        result = _to_query([], self._filter("\\phs1\\sex\\", "Male"))
        assert isinstance(result, Clause)
        assert result.type == PhenotypicFilterType.FILTER

    def test_single_select_only(self):
        result = _to_query(["\\phs1\\out\\"], None)
        assert isinstance(result, Query)
        assert result.phenotypicFilter is None
        assert result.includeConcepts == ("\\phs1\\out\\",)

    def test_multiple_selects_only(self):
        result = _to_query(["\\phs1\\out_a\\", "\\phs1\\out_b\\"], None)
        assert isinstance(result, Query)
        assert result.phenotypicFilter is None
        assert result.includeConcepts == ("\\phs1\\out_a\\", "\\phs1\\out_b\\")

    def test_selects_plus_phenotypic_returns_query(self):
        result = _to_query(["\\phs1\\out\\"], self._filter("\\phs1\\sex\\", "Male"))
        assert isinstance(result, Query)
        assert result.includeConcepts == ("\\phs1\\out\\",)
        assert isinstance(result.phenotypicFilter, Clause)
        assert result.phenotypicFilter.type == PhenotypicFilterType.FILTER

    def test_selects_plus_phenotypic_round_trips_through_to_query_json(self):
        # The reconstructed Query must be passable to runQuery — i.e. its
        # filter tree must serialize without error.
        result = _to_query(
            ["\\phs1\\out\\"],
            {
                "operator": "AND",
                "phenotypicClauses": [
                    self._filter("\\phs1\\sex\\", "Male"),
                    self._filter("\\phs1\\copd\\", "Yes"),
                ],
                "not": False,
            },
        )
        assert isinstance(result, Query)
        assert result.includeConcepts == ("\\phs1\\out\\",)
        assert isinstance(result.phenotypicFilter, ClauseGroup)
        json_body = result.phenotypicFilter.to_query_json()
        assert json_body["operator"] == "AND"

    def test_empty_query_raises(self):
        with pytest.raises(PicSureQueryError, match="empty"):
            _to_query([], None)


import httpx
import respx

from picsure._services.query_load import _HPDS_QUERY_METADATA_PATH, load_query
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureConsentDeniedError,
    PicSureConsentLookupError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
QUERY_ID = "11111111-2222-3333-4444-555555555555"
META_URL = f"{BASE_URL}" + _HPDS_QUERY_METADATA_PATH.format(
    backend="auth", query_id=QUERY_ID
)
# The retired non-versioned route, used only as a negative in routing tests.
LEGACY_META_URL = f"{BASE_URL}/picsure/hpds/auth/query/{QUERY_ID}/metadata"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _envelope(
    query_body: dict,
    *,
    include_at_type: bool = True,
    inner_query_as_string: bool = False,
) -> dict:  # type: ignore[type-arg]
    import json as _json

    inner = {
        "resourceUUID": "resource-uuid-aaaa",
        "resourceCredentials": {"BEARER_TOKEN": "tok"},
        "query": _json.dumps(query_body) if inner_query_as_string else query_body,
    }
    if include_at_type:
        inner["@type"] = "GeneralQueryRequest"
    return {
        "status": "COMPLETED",
        "resourceID": "resource-uuid-aaaa",
        "picsureResultId": QUERY_ID,
        "resourceResultId": "result-1",
        "startTime": 1715000000000,
        "resultMetadata": {
            "queryJson": inner,
            "queryResultMetadata": "",
        },
    }


def _filter_leaf(path: str, val: str) -> dict:  # type: ignore[type-arg]
    return {
        "phenotypicFilterType": "FILTER",
        "conceptPath": path,
        "values": [val],
        "not": False,
    }


class TestLoadQueryHappyPath:
    @respx.mock
    def test_phenotypic_only_returns_clause(self):
        body = _envelope(
            {
                "select": [],
                "phenotypicClause": _filter_leaf("\\phs1\\sex\\", "Male"),
                "genomicFilters": [],
                "expectedResultType": "COUNT",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        result = load_query(_make_client(), QUERY_ID, backend="auth")
        assert isinstance(result, Clause)
        assert result.type == PhenotypicFilterType.FILTER

    @respx.mock
    def test_select_plus_phenotypic_returns_group(self):
        body = _envelope(
            {
                "select": ["\\phs1\\out\\"],
                "phenotypicClause": _filter_leaf("\\phs1\\sex\\", "Male"),
                "genomicFilters": [],
                "expectedResultType": "DATAFRAME",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        result = load_query(_make_client(), QUERY_ID, backend="auth")
        assert isinstance(result, Query)
        assert result.includeConcepts == ("\\phs1\\out\\",)

    @respx.mock
    def test_inner_query_arrives_as_json_string(self):
        # The backend stores the entire QueryRequest as a JSON string and
        # only parses the outer envelope; the inner ``query`` field comes
        # back as a string that we must decode ourselves.  Real BDC saved
        # queries hit this path.
        body = _envelope(
            {
                "select": ["\\phs1\\out\\"],
                "phenotypicClause": _filter_leaf("\\phs1\\sex\\", "Male"),
                "genomicFilters": [],
                "authorizationFilters": [
                    {"conceptPath": "\\_consents\\", "values": ["c1"]}
                ],
                "expectedResultType": "DATAFRAME",
                "picsureId": None,
                "id": None,
            },
            inner_query_as_string=True,
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        result = load_query(_make_client(), QUERY_ID, backend="auth")
        assert isinstance(result, Query)
        assert result.includeConcepts == ("\\phs1\\out\\",)

    @respx.mock
    def test_always_uses_versioned_path(self):
        # Query metadata is served under the versioned (/v3) query routes;
        # loadQueryByID pins reads to the versioned metadata route for every
        # deployment, regardless of how the session was connected.
        body = _envelope(
            {
                "select": [],
                "phenotypicClause": _filter_leaf("\\phs1\\sex\\", "Male"),
                "genomicFilters": [],
                "expectedResultType": "COUNT",
                "picsureId": None,
                "id": None,
            }
        )
        versioned = respx.get(META_URL).mock(
            return_value=httpx.Response(200, json=body)
        )
        legacy = respx.get(LEGACY_META_URL).mock(
            return_value=httpx.Response(200, json=body)
        )
        load_query(_make_client(), QUERY_ID, backend="auth")
        assert versioned.called
        assert not legacy.called


class TestLoadQueryStrictness:
    @respx.mock
    def test_not_true_in_phenotypic_raises_validation(self):
        body = _envelope(
            {
                "select": [],
                "phenotypicClause": {
                    "phenotypicFilterType": "FILTER",
                    "conceptPath": "\\phs1\\sex\\",
                    "values": ["Male"],
                    "not": True,
                },
                "genomicFilters": [],
                "expectedResultType": "COUNT",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(PicSureValidationError, match="NOT"):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_malformed_genomic_filter_missing_key_raises(self):
        body = _envelope(
            {
                "select": [],
                "phenotypicClause": _filter_leaf("\\phs1\\sex\\", "Male"),
                "genomicFilters": [{"variantSpec": "rs123"}],
                "expectedResultType": "COUNT",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(PicSureQueryError, match="key"):
            load_query(_make_client(), QUERY_ID, backend="auth")


class TestLoadQueryGenomic:
    @respx.mock
    def test_round_trips_categorical_genomic_filter(self):
        from picsure._models.genomic_filter import GenomicFilter

        body = _envelope(
            {
                "select": [],
                "phenotypicClause": None,
                "genomicFilters": [{"key": "Gene_with_variant", "values": ["BRCA1"]}],
                "expectedResultType": "COUNT",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        result = load_query(_make_client(), QUERY_ID, backend="auth")
        assert isinstance(result, Query)
        assert result.phenotypicFilter is None
        assert result.genomicFilters == (
            GenomicFilter(key="Gene_with_variant", values=("BRCA1",)),
        )

    @respx.mock
    def test_rejects_numeric_range_genomic_filter(self):
        # Numeric range (min/max) genomic filtering was removed; a saved query
        # carrying one cannot be represented and must be rejected loudly rather
        # than silently dropping the constraint.
        body = _envelope(
            {
                "select": ["\\bmi\\"],
                "phenotypicClause": _filter_leaf("\\phs1\\sex\\", "Male"),
                "genomicFilters": [
                    {"key": "Variant_frequency_in_gnomAD", "min": 0.0, "max": 0.01}
                ],
                "expectedResultType": "DATAFRAME",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(PicSureValidationError, match="numeric range"):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_filter_with_any_min_max_rejected(self):
        # Any min/max on a genomic filter is rejected outright, even alongside
        # categorical values.
        body = _envelope(
            {
                "select": [],
                "phenotypicClause": None,
                "genomicFilters": [
                    {"key": "Gene_with_variant", "values": ["BRCA1"], "min": 0.0}
                ],
                "expectedResultType": "COUNT",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(PicSureValidationError, match="numeric range"):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_rejects_variant_spec_genomic_filter(self):
        # Variant-spec (SNP) filtering is not supported yet; a saved query
        # carrying one cannot be represented and must be rejected.
        body = _envelope(
            {
                "select": [],
                "phenotypicClause": None,
                "genomicFilters": [
                    {"key": "chr5,148481541,T,A", "values": ["0/1", "1/1"]}
                ],
                "expectedResultType": "COUNT",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(PicSureValidationError, match="SNP"):
            load_query(_make_client(), QUERY_ID, backend="auth")


class TestLoadQueryIdValidation:
    @pytest.mark.parametrize(
        "bad_id",
        [
            "abc-123",
            "not-a-uuid",
            "11111111-2222-3333-4444",
            "../../psama/user/me",
            "11111111-2222-3333-4444-555555555555/../../admin",
            "1' OR '1'='1",
            "id with spaces",
        ],
    )
    def test_non_uuid_rejected_before_http(self, bad_id):
        # No respx mock installed: reaching the network would raise
        # something other than PicSureValidationError.
        with pytest.raises(PicSureValidationError, match="not a valid query ID"):
            load_query(_make_client(), bad_id, backend="auth")

    def test_error_shows_a_uuid_example(self):
        with pytest.raises(PicSureValidationError) as excinfo:
            load_query(_make_client(), "abc-123", backend="auth")
        assert "3fa85f64-5717-4562-b3fc-2c963f66afa6" in str(excinfo.value)

    @respx.mock
    def test_uppercase_uuid_normalized_to_canonical_form(self):
        route = respx.get(META_URL).mock(
            return_value=httpx.Response(
                200,
                json=_envelope(
                    {
                        "select": ["\\phs1\\sex\\"],
                        "phenotypicClause": None,
                    }
                ),
            )
        )
        load_query(_make_client(), QUERY_ID.upper(), backend="auth")
        assert route.called
        assert QUERY_ID in str(route.calls[0].request.url)

    @respx.mock
    def test_braced_uuid_normalized(self):
        route = respx.get(META_URL).mock(
            return_value=httpx.Response(
                200,
                json=_envelope({"select": ["\\phs1\\sex\\"], "phenotypicClause": None}),
            )
        )
        load_query(_make_client(), f"{{{QUERY_ID}}}", backend="auth")
        assert QUERY_ID in str(route.calls[0].request.url)

    @respx.mock
    def test_surrounding_whitespace_stripped(self):
        route = respx.get(META_URL).mock(
            return_value=httpx.Response(
                200,
                json=_envelope({"select": ["\\phs1\\sex\\"], "phenotypicClause": None}),
            )
        )
        load_query(_make_client(), f"  {QUERY_ID}  ", backend="auth")
        assert route.called

    def test_path_traversal_cannot_reach_another_route(self):
        # The id is escaped as a single path segment, but validation
        # rejects it first -- so no request is ever built.
        with pytest.raises(PicSureValidationError):
            load_query(
                _make_client(), "../../../operations/dataset/named", backend="auth"
            )


class TestLoadQueryErrors:
    def test_blank_id_raises_before_http(self):
        with pytest.raises(PicSureValidationError, match="query ID"):
            load_query(_make_client(), "   ", backend="auth")

    @respx.mock
    def test_404_raises_validation_with_friendly_message(self):
        respx.get(META_URL).mock(return_value=httpx.Response(404, text="not found"))
        with pytest.raises(PicSureValidationError, match="No saved query found"):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_401_raises_auth_error(self):
        respx.get(META_URL).mock(return_value=httpx.Response(401, text="unauthorized"))
        with pytest.raises(PicSureAuthError):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_consent_denied_raises_typed_error(self):
        respx.get(META_URL).mock(
            return_value=httpx.Response(
                403,
                json={
                    "errorType": "consent_denied",
                    "message": "You no longer have consent for this saved result",
                },
            )
        )

        with pytest.raises(PicSureConsentDeniedError) as exc_info:
            load_query(_make_client(), QUERY_ID, backend="auth")

        exc = exc_info.value
        assert exc.status_code == 403
        assert exc.error_type == "consent_denied"
        assert exc.server_message == "You no longer have consent for this saved result"

    @respx.mock
    def test_consent_lookup_failure_raises_typed_error_without_retry(self):
        route = respx.get(META_URL).mock(
            return_value=httpx.Response(
                502,
                json={
                    "errorType": "consent_lookup_failed",
                    "message": "Unable to resolve caller consents",
                },
            )
        )

        with pytest.raises(PicSureConsentLookupError) as exc_info:
            load_query(_make_client(), QUERY_ID, backend="auth")

        exc = exc_info.value
        assert exc.status_code == 502
        assert exc.error_type == "consent_lookup_failed"
        assert exc.server_message == "Unable to resolve caller consents"
        assert route.call_count == 1

    @respx.mock
    def test_5xx_raises_connection_error(self):
        respx.get(META_URL).mock(return_value=httpx.Response(503, text="oops"))
        with pytest.raises(PicSureConnectionError):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_missing_result_metadata_raises_query_error(self):
        respx.get(META_URL).mock(
            return_value=httpx.Response(200, json={"status": "COMPLETED"})
        )
        with pytest.raises(PicSureQueryError, match="resultMetadata"):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_missing_query_json_raises_query_error(self):
        respx.get(META_URL).mock(
            return_value=httpx.Response(200, json={"resultMetadata": {}})
        )
        with pytest.raises(PicSureQueryError, match="queryJson"):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_missing_inner_query_raises_query_error(self):
        body = {
            "resultMetadata": {
                "queryJson": {"@type": "GeneralQueryRequest"},
            }
        }
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(PicSureQueryError, match="query"):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_empty_select_and_null_phenotypic_raises_query_error(self):
        body = _envelope(
            {
                "select": [],
                "phenotypicClause": None,
                "genomicFilters": [],
                "expectedResultType": "COUNT",
                "picsureId": None,
                "id": None,
            }
        )
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(PicSureQueryError, match="empty"):
            load_query(_make_client(), QUERY_ID, backend="auth")

    @respx.mock
    def test_inner_query_string_with_invalid_json_raises_query_error(self):
        body = {
            "resultMetadata": {
                "queryJson": {
                    "@type": "GeneralQueryRequest",
                    "resourceUUID": "r",
                    "resourceCredentials": {},
                    "query": "{not valid json",
                },
            }
        }
        respx.get(META_URL).mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(PicSureQueryError, match="JSON"):
            load_query(_make_client(), QUERY_ID, backend="auth")
