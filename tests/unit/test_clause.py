import pytest

from picsure._models.clause import Clause, ClauseType


class TestClauseType:
    def test_filter_value(self):
        assert ClauseType.FILTER.value == "filter"

    def test_anyrecord_value(self):
        assert ClauseType.ANYRECORD.value == "anyrecord"

    def test_select_value(self):
        assert ClauseType.SELECT.value == "select"

    def test_require_value(self):
        assert ClauseType.REQUIRE.value == "require"

    def test_all_members(self):
        assert set(ClauseType) == {
            ClauseType.FILTER,
            ClauseType.ANYRECORD,
            ClauseType.SELECT,
            ClauseType.REQUIRE,
        }


class TestClause:
    def test_categorical_filter(self):
        clause = Clause(
            keys=["\\phs1\\sex\\"],
            type=ClauseType.FILTER,
            categories=["Male"],
        )
        assert clause.keys == ["\\phs1\\sex\\"]
        assert clause.type == ClauseType.FILTER
        assert clause.categories == ["Male"]
        assert clause.min is None
        assert clause.max is None

    def test_continuous_filter(self):
        clause = Clause(
            keys=["\\phs1\\age\\"],
            type=ClauseType.FILTER,
            min=40.0,
            max=80.0,
        )
        assert clause.min == 40.0
        assert clause.max == 80.0
        assert clause.categories is None

    def test_anyrecord(self):
        clause = Clause(
            keys=["\\phs1\\insomnia\\"],
            type=ClauseType.ANYRECORD,
        )
        assert clause.type == ClauseType.ANYRECORD
        assert clause.categories is None
        assert clause.min is None
        assert clause.max is None

    def test_frozen(self):
        clause = Clause(keys=["\\path\\"], type=ClauseType.FILTER, categories=["x"])
        with pytest.raises(AttributeError):
            clause.type = ClauseType.ANYRECORD  # type: ignore[misc]

    def test_multiple_keys(self):
        clause = Clause(
            keys=["\\path1\\", "\\path2\\"],
            type=ClauseType.SELECT,
        )
        assert len(clause.keys) == 2


class TestClauseToQueryJson:
    def test_categorical_filter_json(self):
        clause = Clause(
            keys=["\\phs1\\sex\\"],
            type=ClauseType.FILTER,
            categories=["Male", "Female"],
        )
        result = clause.to_query_json()
        assert result["type"] == "clause"
        assert result["clauseType"] == "filter"
        assert result["keys"] == ["\\phs1\\sex\\"]
        assert result["categories"] == ["Male", "Female"]
        assert "min" not in result
        assert "max" not in result

    def test_continuous_filter_json(self):
        clause = Clause(
            keys=["\\phs1\\age\\"],
            type=ClauseType.FILTER,
            min=18.0,
            max=65.0,
        )
        result = clause.to_query_json()
        assert result["clauseType"] == "filter"
        assert result["min"] == 18.0
        assert result["max"] == 65.0
        assert "categories" not in result

    def test_min_only_json(self):
        clause = Clause(
            keys=["\\phs1\\age\\"],
            type=ClauseType.FILTER,
            min=40.0,
        )
        result = clause.to_query_json()
        assert result["min"] == 40.0
        assert "max" not in result

    def test_anyrecord_json(self):
        clause = Clause(
            keys=["\\phs1\\insomnia\\"],
            type=ClauseType.ANYRECORD,
        )
        result = clause.to_query_json()
        assert result["type"] == "clause"
        assert result["clauseType"] == "anyrecord"
        assert result["keys"] == ["\\phs1\\insomnia\\"]
        assert "categories" not in result
        assert "min" not in result
        assert "max" not in result

    def test_select_json(self):
        clause = Clause(keys=["\\path\\"], type=ClauseType.SELECT)
        result = clause.to_query_json()
        assert result["clauseType"] == "select"

    def test_require_json(self):
        clause = Clause(keys=["\\path\\"], type=ClauseType.REQUIRE)
        result = clause.to_query_json()
        assert result["clauseType"] == "require"
