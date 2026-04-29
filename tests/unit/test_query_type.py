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

    def test_member_count(self):
        assert len(QueryType) == 4

    def test_member_names(self):
        assert {m.name for m in QueryType} == {
            "COUNT",
            "PARTICIPANT",
            "TIMESTAMP",
            "CROSS_COUNT",
        }
