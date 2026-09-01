import httpx
import pytest
import respx

from picsure._services._hpds_paths import search_values_path
from picsure._services.genomic_search import search_genomic_values
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureConsentDeniedError,
    PicSureQueryError,
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
