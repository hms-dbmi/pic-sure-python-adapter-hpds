"""Tests for the participant-bearing label.

Every case is a body, because the body is the only thing the classifier
reads. The call sites used to pass a realistic path and method as well,
which read as coverage of a path-based decision that this module does
not make.
"""

from picsure._dev.redaction import body_is_sensitive


def test_search_body_is_not_participant_like():
    body = {"query": "blood pressure", "searchQueryType": "ALL"}
    assert not body_is_sensitive(body)


def test_dataframe_query_is_participant_like():
    body = {"query": {"expectedResultType": "DATAFRAME", "fields": []}}
    assert body_is_sensitive(body)


def test_count_query_is_not_participant_like():
    body = {"query": {"expectedResultType": "COUNT", "fields": []}}
    assert not body_is_sensitive(body)


def test_absent_body_is_not_participant_like():
    assert not body_is_sensitive(None)


def test_list_body_is_not_participant_like():
    assert not body_is_sensitive([{"query": {}}])


def test_pfb_export_is_participant_like():
    body = {"query": {"expectedResultType": "DATAFRAME_PFB"}}
    assert body_is_sensitive(body)


def test_a_body_carrying_no_query_object_is_not_participant_like():
    body = {"uuid-1": "hpds"}
    assert not body_is_sensitive(body)


def test_vcf_excerpt_query_is_participant_like():
    """A VCF excerpt carries one genotype column per patient."""
    body = {"query": {"expectedResultType": "VCF_EXCERPT", "fields": []}}
    assert body_is_sensitive(body)


def test_aggregate_vcf_excerpt_query_is_not_participant_like():
    """Aggregate output is variant-level, with no patient row in it."""
    body = {"query": {"expectedResultType": "AGGREGATE_VCF_EXCERPT", "fields": []}}
    assert not body_is_sensitive(body)


def test_variant_count_query_is_not_participant_like():
    body = {"query": {"expectedResultType": "VARIANT_COUNT_FOR_QUERY", "fields": []}}
    assert not body_is_sensitive(body)


def test_variant_list_query_is_not_participant_like():
    body = {"query": {"expectedResultType": "VARIANT_LIST_FOR_QUERY", "fields": []}}
    assert not body_is_sensitive(body)
