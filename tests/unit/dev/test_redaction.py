from picsure._dev.redaction import body_is_sensitive

_QUERY_PATH = "/picsure/hpds/auth/v3/query/sync"


def test_search_body_is_not_participant_like():
    body = {"query": "blood pressure", "searchQueryType": "ALL"}
    assert not body_is_sensitive("/picsure/search/abc", "POST", body)


def test_dataframe_query_is_participant_like():
    body = {"query": {"expectedResultType": "DATAFRAME", "fields": []}}
    assert body_is_sensitive("/picsure/query/sync", "POST", body)


def test_count_query_is_not_participant_like():
    body = {"query": {"expectedResultType": "COUNT", "fields": []}}
    assert not body_is_sensitive("/picsure/query/sync", "POST", body)


def test_absent_body_is_not_participant_like():
    assert not body_is_sensitive("/picsure/search/abc", "POST", None)


def test_list_body_is_not_participant_like():
    assert not body_is_sensitive("/picsure/dictionary/facets", "POST", [{"query": {}}])


def test_pfb_export_is_participant_like():
    body = {"query": {"expectedResultType": "DATAFRAME_PFB"}}
    assert body_is_sensitive("/picsure/query/sync", "POST", body)


def test_async_pfb_query_is_participant_like():
    """The async PFB export posts the same body to a path with no suffix.

    The decision is made on the body's shape, not on the path, so
    /picsure/v3/query is classified the same as /query/sync.
    """
    body = {"query": {"expectedResultType": "DATAFRAME_PFB", "fields": []}}
    assert body_is_sensitive("/picsure/v3/query", "POST", body)


def test_async_count_query_is_not_participant_like():
    body = {"query": {"expectedResultType": "COUNT", "fields": []}}
    assert not body_is_sensitive("/picsure/v3/query", "POST", body)


def test_info_resources_body_is_not_participant_like():
    body = {"uuid-1": "hpds"}
    assert not body_is_sensitive("/picsure/info/resources", "GET", body)


def test_vcf_excerpt_query_is_participant_like():
    """A VCF excerpt carries one genotype column per patient."""
    body = {"query": {"expectedResultType": "VCF_EXCERPT", "fields": []}}
    assert body_is_sensitive(_QUERY_PATH, "POST", body)


def test_aggregate_vcf_excerpt_query_is_not_participant_like():
    """Aggregate output is variant-level, with no patient row in it."""
    body = {"query": {"expectedResultType": "AGGREGATE_VCF_EXCERPT", "fields": []}}
    assert not body_is_sensitive(_QUERY_PATH, "POST", body)


def test_variant_count_query_is_not_participant_like():
    body = {"query": {"expectedResultType": "VARIANT_COUNT_FOR_QUERY", "fields": []}}
    assert not body_is_sensitive(_QUERY_PATH, "POST", body)


def test_variant_list_query_is_not_participant_like():
    body = {"query": {"expectedResultType": "VARIANT_LIST_FOR_QUERY", "fields": []}}
    assert not body_is_sensitive(_QUERY_PATH, "POST", body)
