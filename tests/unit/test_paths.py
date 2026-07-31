import httpx
import respx

from picsure._paths import (
    CONCEPTS_PATH,
    FACETS_PATH,
    GATEWAY_PREFIX,
    NAMED_DATASET_COLLECTION_PATH,
    NAMED_DATASET_ITEM_PATH,
    PSAMA_QUERY_TEMPLATE_PATH,
    normalize_base_url,
    query_metadata_path,
    query_prefix,
    search_values_path,
)
from picsure._transport.client import PicSureClient

TOKEN = "test-token-abc123"


class TestGatewayPrefixedPaths:
    """Every gateway-bound route carries the /picsure ingress prefix.

    Deployments front the API with httpd, which strips ``/picsure/`` before
    the gateway sees the request -- the same convention the web client uses
    (``PIC-SURE-Frontend/src/lib/paths.ts``).
    """

    def test_prefix_is_picsure(self):
        assert GATEWAY_PREFIX == "/picsure"

    def test_hpds_query_prefix(self):
        assert query_prefix("auth") == "/picsure/hpds/auth/v3"
        assert query_prefix("open") == "/picsure/hpds/open/v3"

    def test_hpds_search_values(self):
        assert search_values_path("auth") == "/picsure/hpds/auth/v3/search/values"

    def test_hpds_query_metadata(self):
        assert (
            query_metadata_path("auth", "abc-123")
            == "/picsure/hpds/auth/v3/query/abc-123/metadata"
        )

    def test_dictionary_paths(self):
        assert CONCEPTS_PATH == "/picsure/dictionary/concepts"
        assert FACETS_PATH == "/picsure/dictionary/facets"

    def test_operations_paths(self):
        assert NAMED_DATASET_COLLECTION_PATH == "/picsure/operations/dataset/named"
        assert NAMED_DATASET_ITEM_PATH.format(named_dataset_id="nd-1") == (
            "/picsure/operations/dataset/named/nd-1"
        )

    def test_psama_is_not_gateway_bound(self):
        # httpd proxies /psama/** straight to the auth service, bypassing the
        # gateway -- so this route must NOT carry the /picsure prefix.
        assert PSAMA_QUERY_TEMPLATE_PATH == "/psama/user/me/queryTemplate/"
        assert not PSAMA_QUERY_TEMPLATE_PATH.startswith(GATEWAY_PREFIX)


class TestNormalizeBaseUrl:
    """connect() takes the bare origin; a stray /picsure must not double up."""

    def test_bare_origin_is_unchanged(self):
        assert normalize_base_url("https://host.example.com") == (
            "https://host.example.com"
        )

    def test_trailing_slash_is_trimmed(self):
        assert normalize_base_url("https://host.example.com/") == (
            "https://host.example.com"
        )

    def test_trailing_picsure_is_trimmed(self):
        assert normalize_base_url("https://host.example.com/picsure") == (
            "https://host.example.com"
        )

    def test_trailing_picsure_with_slash_is_trimmed(self):
        assert normalize_base_url("https://host.example.com/picsure/") == (
            "https://host.example.com"
        )

    def test_trailing_picsure_is_case_insensitive(self):
        assert normalize_base_url("https://host.example.com/PicSure/") == (
            "https://host.example.com"
        )

    def test_repeated_picsure_segments_are_trimmed(self):
        assert normalize_base_url("https://host.example.com/picsure/picsure") == (
            "https://host.example.com"
        )

    def test_surrounding_whitespace_is_trimmed(self):
        assert normalize_base_url("  https://host.example.com/picsure  ") == (
            "https://host.example.com"
        )

    def test_unrelated_context_path_is_preserved(self):
        assert normalize_base_url("https://host.example.com/gateway/") == (
            "https://host.example.com/gateway"
        )


class TestClientPrefixOnTheWire:
    @respx.mock
    def test_bare_origin_hits_the_prefixed_route(self):
        route = respx.post("https://host.example.com/picsure/hpds/auth/v3/query").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(base_url="https://host.example.com", token=TOKEN)
        client.post_json(query_prefix("auth") + "/query", body={})

        assert route.called

    @respx.mock
    def test_origin_already_ending_in_picsure_is_not_doubled(self):
        route = respx.post("https://host.example.com/picsure/hpds/auth/v3/query").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client = PicSureClient(base_url="https://host.example.com/picsure", token=TOKEN)
        client.post_json(query_prefix("auth") + "/query", body={})

        assert route.called
