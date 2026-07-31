import re
from pathlib import Path

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

    # Only the PATH is trimmed: a HOST named "picsure" (a container name or
    # an /etc/hosts entry in a local dev stack) must survive intact.
    def test_host_named_picsure_survives(self):
        assert normalize_base_url("http://picsure") == "http://picsure"

    def test_host_named_picsure_with_trailing_slash_survives(self):
        assert normalize_base_url("https://picsure/") == "https://picsure"

    def test_host_named_picsure_with_port_survives(self):
        assert normalize_base_url("http://picsure:8080") == "http://picsure:8080"

    def test_host_named_picsure_keeps_its_picsure_path_trimmed(self):
        assert normalize_base_url("http://picsure:8080/picsure") == (
            "http://picsure:8080"
        )


class TestRouteTableIsTheOnlySourceOfPaths:
    """No service may hand the client a path literal of its own.

    The ``/picsure`` ingress prefix cannot be enforced in the transport
    layer (PSAMA is deliberately unprefixed), so the guard is here: every
    request path must come from :mod:`picsure._paths`.  A new service that
    writes ``client.get_json("/whatever")`` would silently bypass the route
    table -- and the prefix with it.
    """

    # e.g. client.post_json("/dictionary/concepts", ...) or
    # client.get_json(f"/hpds/{backend}/v3/query")
    _CALL_WITH_LITERAL_PATH = re.compile(
        r"""client\.(?:get|post|put)_(?:json|raw)(?:_stream)?\(\s*[a-z]*["']/"""
    )

    def test_no_path_literals_outside_the_route_table(self):
        source_root = Path(__file__).resolve().parents[2] / "src" / "picsure"
        offenders = [
            f"{path.relative_to(source_root)}:{lineno}: {line.strip()}"
            for path in sorted(source_root.rglob("*.py"))
            if path.name != "_paths.py"
            for lineno, line in enumerate(path.read_text().splitlines(), start=1)
            if self._CALL_WITH_LITERAL_PATH.search(line)
        ]

        assert not offenders, (
            "Request paths must be defined in picsure/_paths.py, not inlined "
            "at the call site (the /picsure ingress prefix lives there): "
            + "; ".join(offenders)
        )

    def test_guard_regex_actually_matches_a_violation(self):
        assert self._CALL_WITH_LITERAL_PATH.search('client.get_json("/hpds/auth")')
        assert self._CALL_WITH_LITERAL_PATH.search(
            'client.post_raw_stream(f"/hpds/{backend}/v3/query")'
        )
        assert not self._CALL_WITH_LITERAL_PATH.search("client.get_json(path)")


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
