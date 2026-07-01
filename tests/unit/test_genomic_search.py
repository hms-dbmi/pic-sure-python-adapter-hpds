import pytest

from picsure._services.genomic_search import search_genomic_values
from picsure.errors import PicSureQueryError, PicSureValidationError


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
        client, "RID", "Gene_with_variant", query="BRCA", page=1, size=50
    )
    assert client.last_path == (
        "/picsure/search/RID/values/"
        "?genomicConceptPath=Gene_with_variant&query=BRCA&page=1&size=50"
    )


def test_returns_value_dataframe():
    client = _FakeClient({"results": ["BRCA1", "BRCA2"], "page": 1, "total": 2})
    df = search_genomic_values(client, "RID", "Gene_with_variant")
    assert list(df.columns) == ["value"]
    assert df["value"].tolist() == ["BRCA1", "BRCA2"]


def test_preserves_pagination_metadata_in_attrs():
    client = _FakeClient({"results": ["BRCA1"], "page": 2, "total": 41719})
    df = search_genomic_values(client, "RID", "Gene_with_variant", page=2, size=20)
    assert df.attrs["total"] == 41719
    assert df.attrs["page"] == 2
    assert df.attrs["size"] == 20
    assert df.attrs["genomic_concept_path"] == "Gene_with_variant"


def test_malformed_response_raises():
    client = _FakeClient({"unexpected": True})
    with pytest.raises(PicSureQueryError, match="results"):
        search_genomic_values(client, "RID", "Gene_with_variant")


def test_blank_key_raises():
    client = _FakeClient({"results": []})
    with pytest.raises(PicSureValidationError, match="non-empty"):
        search_genomic_values(client, "RID", "   ")
