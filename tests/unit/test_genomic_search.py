import httpx
import pytest
import respx

from picsure._services._hpds_paths import search_values_path
from picsure._services.genomic_search import search_genomic_values
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import (
    PicSureAuthenticationError,
    PicSureAuthorizationError,
    PicSureConnectionError,
    PicSureConsentDeniedError,
    PicSureError,
    PicSureQueryError,
    PicSureServerError,
    PicSureValidationError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
GENOMIC_VALUES_URL = (
    f"{BASE_URL}{search_values_path('auth')}"
    "?genomicConceptPath=Gene_with_variant&query=&page=1&size=50"
)


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.last_path = None

    def get_json(self, path):
        self.last_path = path
        return self._response


def test_builds_path_with_encoded_params():
    client = _FakeClient({"results": ["BRCA1", "BRCA2"], "page": 1, "total": 2})
    search_genomic_values(
        client, "Gene_with_variant", backend="auth", query="BRCA", page=1, size=50
    )
    assert client.last_path == (
        search_values_path("auth")
        + "?genomicConceptPath=Gene_with_variant&query=BRCA&page=1&size=50"
    )


def test_returns_value_dataframe():
    client = _FakeClient({"results": ["BRCA1", "BRCA2"], "page": 1, "total": 2})
    df = search_genomic_values(client, "Gene_with_variant", backend="auth")
    assert list(df.columns) == ["value"]
    assert df["value"].tolist() == ["BRCA1", "BRCA2"]


def test_preserves_pagination_metadata_in_attrs():
    client = _FakeClient({"results": ["BRCA1"], "page": 2, "total": 41719})
    df = search_genomic_values(
        client, "Gene_with_variant", backend="auth", page=2, size=20
    )
    assert df.attrs["total"] == 41719
    assert df.attrs["page"] == 2
    assert df.attrs["size"] == 20
    assert df.attrs["genomic_concept_path"] == "Gene_with_variant"


def test_malformed_response_raises():
    client = _FakeClient({"unexpected": True})
    with pytest.raises(PicSureQueryError, match="results"):
        search_genomic_values(client, "Gene_with_variant", backend="auth")


def test_blank_key_raises():
    client = _FakeClient({"results": []})
    with pytest.raises(PicSureValidationError, match="non-empty"):
        search_genomic_values(client, "   ", backend="auth")


class TestGenomicValuesPagingValidation:
    """Paging arguments are checked before anything is urlencoded.

    Paging on this route is one-based, unlike the dictionary search's
    zero-based ``page``, so ``page=0`` is out of range here.
    """

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"page": 0}, "`page` must be 1 or greater"),
            ({"page": -1}, "`page` must be 1 or greater"),
            ({"size": 0}, "`size` must be 1 or greater"),
            ({"size": -1}, "`size` must be 1 or greater"),
            ({"page": "2"}, "`page` must be an integer"),
            ({"page": 1.5}, "`page` must be an integer"),
            ({"page": True}, "`page` must be an integer"),
            ({"size": "50"}, "`size` must be an integer"),
            ({"size": False}, "`size` must be an integer"),
        ],
    )
    def test_out_of_range_or_wrong_type_raises_before_any_request(
        self, kwargs, expected
    ):
        client = _FakeClient({"results": []})

        with pytest.raises(PicSureValidationError, match=expected):
            search_genomic_values(client, "Gene_with_variant", backend="auth", **kwargs)

        assert client.last_path is None

    def test_the_first_page_is_one_not_zero(self):
        client = _FakeClient({"results": ["BRCA1"], "page": 1, "total": 1})

        search_genomic_values(client, "Gene_with_variant", backend="auth", page=1)

        assert "page=1" in client.last_path


@respx.mock
def test_consent_denied_raises_typed_error():
    respx.get(GENOMIC_VALUES_URL).mock(
        return_value=httpx.Response(
            403,
            json={
                "errorType": "consent_denied",
                "message": "You no longer have consent for this saved result",
            },
        )
    )

    with pytest.raises(PicSureConsentDeniedError) as exc_info:
        search_genomic_values(
            PicSureClient(base_url=BASE_URL, token=TOKEN),
            "Gene_with_variant",
            backend="auth",
        )

    exc = exc_info.value
    assert exc.status_code == 403
    assert exc.error_type == "consent_denied"
    assert exc.server_message == "You no longer have consent for this saved result"


VALUES_ROUTE_PREFIX = f"{BASE_URL}{search_values_path('auth')}"


def _values_route():
    """Match any GET on the values route, whatever the query encoding."""
    return respx.get(url__startswith=VALUES_ROUTE_PREFIX)


class TestGenomicValuesErrorBranches:
    """The error branches of ``search_genomic_values``."""

    @respx.mock
    def test_server_error_reports_a_server_failure(self):
        respx.get(GENOMIC_VALUES_URL).mock(
            return_value=httpx.Response(500, text="ri_error 500")
        )
        with pytest.raises(PicSureServerError) as exc_info:
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Gene_with_variant",
                backend="auth",
            )
        assert "the genomic value lookup" in str(exc_info.value)

    @pytest.mark.parametrize("status", [418, 451, 502, 503])
    @respx.mock
    def test_unexpected_status_is_translated_not_leaked(self, status):
        """Statuses with no dedicated branch still surface as public errors."""
        respx.get(GENOMIC_VALUES_URL).mock(
            return_value=httpx.Response(status, text="unexpected")
        )
        with pytest.raises(PicSureError) as exc_info:
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Gene_with_variant",
                backend="auth",
            )
        assert not isinstance(exc_info.value, TransportError)

    @respx.mock
    def test_missing_endpoint_reports_unsupported_deployment(self):
        respx.get(GENOMIC_VALUES_URL).mock(
            return_value=httpx.Response(404, text="not found")
        )
        with pytest.raises(PicSureQueryError) as exc_info:
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Gene_with_variant",
                backend="auth",
            )
        message = str(exc_info.value)
        assert "endpoint not found" in message
        assert "may not support genomic value lookups" in message

    @respx.mock
    def test_expired_token_reports_authentication(self):
        respx.get(GENOMIC_VALUES_URL).mock(
            return_value=httpx.Response(401, text="Token invalid or expired.")
        )
        with pytest.raises(PicSureAuthenticationError):
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Gene_with_variant",
                backend="auth",
            )

    @respx.mock
    def test_forbidden_reports_authorization(self):
        respx.get(GENOMIC_VALUES_URL).mock(
            return_value=httpx.Response(403, text="forbidden")
        )
        with pytest.raises(PicSureAuthorizationError):
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Gene_with_variant",
                backend="auth",
            )

    @respx.mock
    def test_bad_request_reports_validation(self):
        respx.get(GENOMIC_VALUES_URL).mock(
            return_value=httpx.Response(400, text="bad genomicConceptPath")
        )
        with pytest.raises(PicSureValidationError):
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Gene_with_variant",
                backend="auth",
            )

    @respx.mock
    def test_rate_limited_reports_connection_error(self):
        respx.get(GENOMIC_VALUES_URL).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "30"})
        )
        with pytest.raises(PicSureConnectionError, match="Rate limited"):
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Gene_with_variant",
                backend="auth",
            )


class TestGenomicValuesNonAnnotationConcept:
    """A concept that is not a genomic annotation.

    Verified live: the server answers HTTP 200 with a zero-length body and
    no content type for a phenotypic concept path or an unknown key, which
    left ``get_json`` with nothing to decode and leaked a raw
    ``json.decoder.JSONDecodeError`` out of the library.
    """

    @respx.mock
    def test_empty_body_raises_a_picsure_error(self):
        path = "\\Consent QA\\phs999901\\Categorical\\Exclusive marker\\"
        _values_route().mock(return_value=httpx.Response(200, content=b""))
        with pytest.raises(PicSureQueryError) as exc_info:
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN), path, backend="auth"
            )

        message = str(exc_info.value)
        assert "no genomic values payload" in message
        assert "may not be a genomic annotation" in message
        assert path in message

    @respx.mock
    def test_unknown_key_raises_a_picsure_error(self):
        _values_route().mock(return_value=httpx.Response(200, content=b""))
        with pytest.raises(PicSureQueryError, match="no genomic values payload"):
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Totally_Not_A_Key",
                backend="auth",
            )

    @respx.mock
    def test_whitespace_body_is_treated_as_empty(self):
        _values_route().mock(return_value=httpx.Response(200, content=b"  \n"))
        with pytest.raises(PicSureQueryError, match="no genomic values payload"):
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Totally_Not_A_Key",
                backend="auth",
            )

    @respx.mock
    @pytest.mark.parametrize("content", [b"<html>nope</html>", b"null", b"7"])
    def test_non_empty_undecodable_body_keeps_the_decoder_message(self, content):
        """Only the empty body means "not a genomic annotation".

        A proxy page or a scalar payload says nothing about the concept, so
        the decode error keeps its own message instead of blaming the key.
        """
        respx.get(GENOMIC_VALUES_URL).mock(
            return_value=httpx.Response(200, content=content)
        )
        with pytest.raises(PicSureQueryError) as exc_info:
            search_genomic_values(
                PicSureClient(base_url=BASE_URL, token=TOKEN),
                "Gene_with_variant",
                backend="auth",
            )

        assert "genomic annotation" not in str(exc_info.value)


class TestGenomicValuesValueList:
    """Empty and malformed value lists."""

    def test_empty_results_list_is_an_empty_frame_not_an_error(self):
        """Live, a term matching nothing returns an empty results list."""
        client = _FakeClient({"results": [], "page": 1, "total": 0})
        df = search_genomic_values(client, "Gene_with_variant", backend="auth")
        assert list(df.columns) == ["value"]
        assert df.empty
        assert df.attrs["total"] == 0

    def test_page_past_the_end_is_an_empty_frame(self):
        """Live, page 99 returns an empty results list with the total intact."""
        client = _FakeClient({"results": [], "page": 99, "total": 8})
        df = search_genomic_values(client, "Gene_with_variant", backend="auth", page=99)
        assert df.empty
        assert df.attrs["total"] == 8
        assert df.attrs["page"] == 99

    def test_results_not_a_list_raises(self):
        client = _FakeClient({"results": "BRCA1", "total": 1})
        with pytest.raises(PicSureQueryError, match="'results' list"):
            search_genomic_values(client, "Gene_with_variant", backend="auth")

    def test_results_null_raises(self):
        client = _FakeClient({"results": None})
        with pytest.raises(PicSureQueryError, match="'results' list"):
            search_genomic_values(client, "Gene_with_variant", backend="auth")

    def test_top_level_list_raises(self):
        client = _FakeClient(["BRCA1", "BRCA2"])
        with pytest.raises(PicSureQueryError, match="'results' list"):
            search_genomic_values(client, "Gene_with_variant", backend="auth")

    def test_malformed_response_message_shows_a_bounded_preview(self):
        client = _FakeClient({"unexpected": "x" * 500})
        with pytest.raises(PicSureQueryError) as exc_info:
            search_genomic_values(client, "Gene_with_variant", backend="auth")
        assert len(str(exc_info.value)) < 400

    def test_non_string_values_are_coerced(self):
        client = _FakeClient({"results": [1, 2.5, None], "page": 1, "total": 3})
        df = search_genomic_values(client, "Gene_with_variant", backend="auth")
        assert df["value"].tolist() == ["1", "2.5", "None"]

    @pytest.mark.parametrize("bad", ["", "   ", "\t"])
    def test_blank_concept_path_raises(self, bad):
        with pytest.raises(PicSureValidationError, match="non-empty"):
            search_genomic_values(_FakeClient({"results": []}), bad, backend="auth")

    def test_non_string_concept_path_raises(self):
        with pytest.raises(PicSureValidationError, match="non-empty"):
            search_genomic_values(_FakeClient({"results": []}), None, backend="auth")


class TestGenomicValuesRequiresGenomicSupport:
    """A deployment without genomic support."""

    def test_session_refuses_before_any_request(self):
        from picsure._models.session import Session

        client = _FakeClient({"results": ["BRCA1"]})
        session = Session(
            client=client,
            user_email="u",
            token_expiration="N/A",
            supports_genomic=False,
        )
        with pytest.raises(PicSureValidationError) as exc_info:
            session.searchGenomicValues("Gene_with_variant")

        message = str(exc_info.value)
        assert "Genomic operations require an authorized platform" in message
        assert client.last_path is None


LIVE_GENOMIC_VALUES: dict[str, list[str]] = {
    "Gene_with_variant": [
        "CONSENTQA902_1",
        "CONSENTQA902_2",
        "CONSENTQA902_3",
        "CONSENTQA902_4",
        "CONSENTQA906_1",
        "CONSENTQA906_2",
        "CONSENTQA906_3",
        "CONSENTQA906_4",
    ],
    "Variant_severity": ["MODERATE", "MODIFIER", "HIGH", "LOW"],
    "Variant_class": ["SNV", "INDEL"],
    "Variant_consequence_calculated": [
        "missense_variant",
        "stop_gained",
        "synonymous_variant",
        "intron_variant",
    ],
    "Variant_frequency_as_text": [
        "Low_frequency",
        "Ultra_rare",
        "Rare",
        "Common",
    ],
}
"""Values captured live on 2026-09-10 from a PIC-SURE stack with genomic data.

Fetched with ``GET /picsure/hpds/auth/search/values?genomicConceptPath=<key>``,
so these are the values ``searchGenomicValues`` hands a caller.
"""


class TestDiscoveryToBuilderRoundTrip:
    """Every discovered value must be buildable.

    ``searchGenomicValues`` and ``buildGenomicFilter`` are the two halves of
    one workflow: discover the valid values for a key, then filter on them.
    This is the test that stops the two vocabularies drifting apart again:
    it walks the values the discovery call returns and feeds each one back
    into the builder for the same key.
    """

    @pytest.mark.parametrize("concept_path", sorted(LIVE_GENOMIC_VALUES))
    def test_every_discovered_value_is_accepted_individually(self, concept_path):
        from picsure import buildGenomicFilter

        client = _FakeClient(
            {
                "results": LIVE_GENOMIC_VALUES[concept_path],
                "page": 1,
                "total": len(LIVE_GENOMIC_VALUES[concept_path]),
            }
        )
        df = search_genomic_values(client, concept_path, backend="auth")
        assert not df.empty

        for value in df["value"].tolist():
            gf = buildGenomicFilter(concept_path, values=value)
            assert gf.values, f"{concept_path}={value!r} produced no filter values"

    @pytest.mark.parametrize("concept_path", sorted(LIVE_GENOMIC_VALUES))
    def test_all_discovered_values_accepted_together(self, concept_path):
        from picsure import buildGenomicFilter

        client = _FakeClient(
            {
                "results": LIVE_GENOMIC_VALUES[concept_path],
                "page": 1,
                "total": len(LIVE_GENOMIC_VALUES[concept_path]),
            }
        )
        df = search_genomic_values(client, concept_path, backend="auth")
        gf = buildGenomicFilter(concept_path, values=df["value"].tolist())
        assert gf.values

    @pytest.mark.parametrize("concept_path", sorted(LIVE_GENOMIC_VALUES))
    def test_discovered_values_round_trip_onto_their_own_key(self, concept_path):
        from picsure import buildGenomicFilter

        values = LIVE_GENOMIC_VALUES[concept_path]
        gf = buildGenomicFilter(concept_path, values=values)
        assert gf.key == concept_path
        assert set(gf.values or ()) == set(values)

    def test_severity_buckets_are_not_discovered_values(self):
        """The bucket labels are this adapter's own; the server never reports them."""
        from picsure._models.genomic_filter import known_severities

        discovered = set(LIVE_GENOMIC_VALUES["Variant_severity"])
        assert discovered.isdisjoint(set(known_severities()))

    def test_discovered_severity_values_match_the_impact_vocabulary(self):
        from picsure._models.genomic_filter import known_impacts

        assert set(LIVE_GENOMIC_VALUES["Variant_severity"]) == set(known_impacts())
