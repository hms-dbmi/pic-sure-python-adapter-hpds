"""Unit tests for picsure._models.query_type."""

from picsure._models.query_type import QueryType


class TestQueryTypeMembers:
    def test_count_value(self):
        assert QueryType.COUNT.value == "count"

    def test_participant_value(self):
        assert QueryType.PARTICIPANT.value == "participant"

    def test_timestamp_value(self):
        assert QueryType.TIMESTAMP.value == "timestamp"

    def test_cross_count_value(self):
        assert QueryType.CROSS_COUNT.value == "cross_count"


def test_new_variant_query_types_present():
    from picsure import QueryType

    assert QueryType.VARIANT_COUNT.value == "variant_count"
    assert QueryType.VARIANT_LIST.value == "variant_list"
    assert QueryType.VCF_EXCERPT.value == "vcf_excerpt"
    assert QueryType.AGGREGATE_VCF_EXCERPT.value == "aggregate_vcf_excerpt"
