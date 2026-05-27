import pytest

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._services.query_build import buildClause


class TestPhenotypicFilterType:
    def test_filter_value(self):
        assert PhenotypicFilterType.FILTER.value == "filter"

    def test_anyrecord_value(self):
        assert PhenotypicFilterType.ANYRECORD.value == "anyrecord"

    def test_require_value(self):
        assert PhenotypicFilterType.REQUIRE.value == "require"

    def test_select_member_removed(self):
        assert not hasattr(PhenotypicFilterType, "SELECT")


class TestClause:
    def test_categorical_filter(self):
        clause = Clause(
            keys=["\\phs1\\sex\\"],
            type=PhenotypicFilterType.FILTER,
            categories=["Male"],
        )
        assert clause.keys == ["\\phs1\\sex\\"]
        assert clause.type == PhenotypicFilterType.FILTER
        assert clause.categories == ["Male"]
        assert clause.min is None
        assert clause.max is None

    def test_continuous_filter(self):
        clause = Clause(
            keys=["\\phs1\\age\\"],
            type=PhenotypicFilterType.FILTER,
            min=40.0,
            max=80.0,
        )
        assert clause.min == 40.0
        assert clause.max == 80.0
        assert clause.categories is None

    def test_anyrecord(self):
        clause = Clause(
            keys=["\\phs1\\insomnia\\"],
            type=PhenotypicFilterType.ANYRECORD,
        )
        assert clause.type == PhenotypicFilterType.ANYRECORD
        assert clause.categories is None
        assert clause.min is None
        assert clause.max is None

    def test_frozen(self):
        clause = Clause(
            keys=["\\path\\"], type=PhenotypicFilterType.FILTER, categories=["x"]
        )
        with pytest.raises(AttributeError):
            clause.type = PhenotypicFilterType.ANYRECORD  # type: ignore[misc]

    def test_multiple_keys(self):
        clause = Clause(
            keys=["\\path1\\", "\\path2\\"],
            type=PhenotypicFilterType.ANYRECORD,
        )
        assert len(clause.keys) == 2


class TestClauseToQueryJson:
    def test_categorical_filter_json(self):
        clause = Clause(
            keys=["\\phs1\\sex\\"],
            type=PhenotypicFilterType.FILTER,
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
            type=PhenotypicFilterType.FILTER,
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
            type=PhenotypicFilterType.FILTER,
            min=40.0,
        )
        result = clause.to_query_json()
        assert result["min"] == 40.0
        assert "max" not in result

    def test_anyrecord_json(self):
        clause = Clause(
            keys=["\\phs1\\insomnia\\"],
            type=PhenotypicFilterType.ANYRECORD,
        )
        result = clause.to_query_json()
        assert result["phenotypicFilterType"] == "ANY_RECORD_OF"
        assert result["conceptPath"] == "\\phs1\\insomnia\\"
        assert result["not"] is False
        assert "values" not in result
        assert "min" not in result
        assert "max" not in result

    def test_require_json(self):
        clause = Clause(keys=["\\path\\"], type=PhenotypicFilterType.REQUIRE)
        result = clause.to_query_json()
        assert result["phenotypicFilterType"] == "REQUIRED"
        assert result["conceptPath"] == "\\path\\"
        assert result["not"] is False

    def test_multi_key_wrapped_in_or_subquery(self):
        clause = Clause(
            keys=["\\path_a\\", "\\path_b\\"],
            type=PhenotypicFilterType.ANYRECORD,
        )
        result = clause.to_query_json()
        assert result["operator"] == "OR"
        assert result["not"] is False
        assert len(result["phenotypicClauses"]) == 2  # type: ignore[arg-type]
        leaf_a, leaf_b = result["phenotypicClauses"]  # type: ignore[misc]
        assert leaf_a["conceptPath"] == "\\path_a\\"
        assert leaf_b["conceptPath"] == "\\path_b\\"
        assert leaf_a["phenotypicFilterType"] == "ANY_RECORD_OF"


class TestBuildClauseDefensiveCopies:
    def test_mutating_keys_list_after_construction_does_not_affect_clause(self):
        keys = ["\\p1\\", "\\p2\\"]
        clause = buildClause(keys, type=PhenotypicFilterType.ANYRECORD)
        keys.append("\\p3\\")
        assert clause.keys == ["\\p1\\", "\\p2\\"]

    def test_mutating_categories_list_after_construction_does_not_affect_clause(self):
        categories = ["Male", "Female"]
        clause = buildClause(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            categories=categories,
        )
        categories.append("Other")
        assert clause.categories == ["Male", "Female"]
