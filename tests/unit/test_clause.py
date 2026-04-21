import pytest

from picsure._models.clause import Clause, ClauseType
from picsure._services.query_build import createClause
from picsure.errors import PicSureValidationError


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
        assert result["phenotypicFilterType"] == "FILTER"
        assert result["conceptPath"] == "\\phs1\\sex\\"
        assert result["not"] is False
        assert result["values"] == ["Male", "Female"]
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
        assert result["phenotypicFilterType"] == "FILTER"
        assert result["conceptPath"] == "\\phs1\\age\\"
        assert result["min"] == 18.0
        assert result["max"] == 65.0
        assert "values" not in result

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
        assert result["phenotypicFilterType"] == "ANY_RECORD_OF"
        assert result["conceptPath"] == "\\phs1\\insomnia\\"
        assert result["not"] is False
        assert "values" not in result
        assert "min" not in result
        assert "max" not in result

    def test_require_json(self):
        clause = Clause(keys=["\\path\\"], type=ClauseType.REQUIRE)
        result = clause.to_query_json()
        assert result["phenotypicFilterType"] == "REQUIRED"
        assert result["conceptPath"] == "\\path\\"
        assert result["not"] is False

    def test_select_raises(self):
        clause = Clause(keys=["\\path\\"], type=ClauseType.SELECT)
        with pytest.raises(PicSureValidationError, match="SELECT clauses"):
            clause.to_query_json()

    def test_multi_key_wrapped_in_or_subquery(self):
        clause = Clause(
            keys=["\\path_a\\", "\\path_b\\"],
            type=ClauseType.ANYRECORD,
        )
        result = clause.to_query_json()
        assert result["operator"] == "OR"
        assert result["not"] is False
        assert len(result["phenotypicClauses"]) == 2  # type: ignore[arg-type]
        leaf_a, leaf_b = result["phenotypicClauses"]  # type: ignore[misc]
        assert leaf_a["conceptPath"] == "\\path_a\\"
        assert leaf_b["conceptPath"] == "\\path_b\\"
        assert leaf_a["phenotypicFilterType"] == "ANY_RECORD_OF"


class TestClauseSelectPaths:
    def test_select_returns_keys(self):
        clause = Clause(keys=["\\a\\", "\\b\\"], type=ClauseType.SELECT)
        assert clause.select_paths() == ["\\a\\", "\\b\\"]

    def test_filter_returns_empty(self):
        clause = Clause(keys=["\\a\\"], type=ClauseType.FILTER, categories=["x"])
        assert clause.select_paths() == []

    def test_anyrecord_returns_empty(self):
        clause = Clause(keys=["\\a\\"], type=ClauseType.ANYRECORD)
        assert clause.select_paths() == []

    def test_require_returns_empty(self):
        clause = Clause(keys=["\\a\\"], type=ClauseType.REQUIRE)
        assert clause.select_paths() == []


class TestCreateClauseDefensiveCopies:
    def test_mutating_keys_list_after_construction_does_not_affect_clause(self):
        keys = ["\\p1\\", "\\p2\\"]
        clause = createClause(keys, type=ClauseType.SELECT)
        keys.append("\\p3\\")
        assert clause.keys == ["\\p1\\", "\\p2\\"]

    def test_mutating_categories_list_after_construction_does_not_affect_clause(self):
        categories = ["Male", "Female"]
        clause = createClause(
            "\\path\\",
            type=ClauseType.FILTER,
            categories=categories,
        )
        categories.append("Other")
        assert clause.categories == ["Male", "Female"]

    def test_mutating_keys_list_does_not_affect_clause_via_clear(self):
        keys = ["\\p1\\", "\\p2\\"]
        clause = createClause(
            keys,
            type=ClauseType.FILTER,
            categories=["x"],
        )
        keys.clear()
        assert clause.keys == ["\\p1\\", "\\p2\\"]

    def test_mutating_categories_list_does_not_affect_clause_via_clear(self):
        categories = ["Male"]
        clause = createClause(
            "\\path\\",
            type=ClauseType.FILTER,
            categories=categories,
        )
        categories.clear()
        assert clause.categories == ["Male"]
