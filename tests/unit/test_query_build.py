import pytest

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._services.query_build import buildClauseGroup, createClause
from picsure.errors import PicSureValidationError


class TestCreateClause:
    def test_categorical_filter(self):
        clause = createClause(
            "\\phs1\\sex\\",
            type=ClauseType.FILTER,
            categories="Male",
        )
        assert isinstance(clause, Clause)
        assert clause.keys == ["\\phs1\\sex\\"]
        assert clause.categories == ["Male"]

    def test_keys_string_normalized_to_list(self):
        clause = createClause("\\path\\", type=ClauseType.SELECT)
        assert clause.keys == ["\\path\\"]

    def test_keys_list_preserved(self):
        clause = createClause(
            ["\\p1\\", "\\p2\\"],
            type=ClauseType.SELECT,
        )
        assert clause.keys == ["\\p1\\", "\\p2\\"]

    def test_categories_string_normalized_to_list(self):
        clause = createClause(
            "\\path\\",
            type=ClauseType.FILTER,
            categories="Male",
        )
        assert clause.categories == ["Male"]

    def test_categories_list_preserved(self):
        clause = createClause(
            "\\path\\",
            type=ClauseType.FILTER,
            categories=["Male", "Female"],
        )
        assert clause.categories == ["Male", "Female"]

    def test_continuous_filter_min_only(self):
        clause = createClause(
            "\\path\\",
            type=ClauseType.FILTER,
            min=40.0,
        )
        assert clause.min == 40.0
        assert clause.max is None

    def test_continuous_filter_max_only(self):
        clause = createClause(
            "\\path\\",
            type=ClauseType.FILTER,
            max=100.0,
        )
        assert clause.max == 100.0
        assert clause.min is None

    def test_continuous_filter_min_and_max(self):
        clause = createClause(
            "\\path\\",
            type=ClauseType.FILTER,
            min=18.0,
            max=65.0,
        )
        assert clause.min == 18.0
        assert clause.max == 65.0

    def test_anyrecord(self):
        clause = createClause("\\path\\", type=ClauseType.ANYRECORD)
        assert clause.type == ClauseType.ANYRECORD
        assert clause.categories is None
        assert clause.min is None

    def test_select(self):
        clause = createClause("\\path\\", type=ClauseType.SELECT)
        assert clause.type == ClauseType.SELECT

    def test_require(self):
        clause = createClause("\\path\\", type=ClauseType.REQUIRE)
        assert clause.type == ClauseType.REQUIRE


class TestCreateClauseValidation:
    def test_anyrecord_with_categories_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            createClause(
                "\\path\\",
                type=ClauseType.ANYRECORD,
                categories="Male",
            )

    def test_anyrecord_with_categories_message_is_actionable(self):
        with pytest.raises(PicSureValidationError, match="Remove the categories"):
            createClause(
                "\\path\\",
                type=ClauseType.ANYRECORD,
                categories=["x"],
            )

    def test_anyrecord_with_min_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            createClause(
                "\\path\\",
                type=ClauseType.ANYRECORD,
                min=10.0,
            )

    def test_anyrecord_with_max_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            createClause(
                "\\path\\",
                type=ClauseType.ANYRECORD,
                max=100.0,
            )

    def test_filter_without_criteria_raises(self):
        with pytest.raises(PicSureValidationError, match="FILTER"):
            createClause("\\path\\", type=ClauseType.FILTER)

    def test_filter_without_criteria_message_is_actionable(self):
        with pytest.raises(PicSureValidationError, match="categories.*min.*max"):
            createClause("\\path\\", type=ClauseType.FILTER)


class TestBuildClauseGroup:
    def test_and_group(self):
        c1 = createClause("\\p1\\", type=ClauseType.FILTER, categories="A")
        c2 = createClause("\\p2\\", type=ClauseType.FILTER, categories="B")
        group = buildClauseGroup([c1, c2], root=GroupOperator.AND)
        assert isinstance(group, ClauseGroup)
        assert group.operator == GroupOperator.AND
        assert len(group.clauses) == 2

    def test_or_group(self):
        c1 = createClause("\\p1\\", type=ClauseType.FILTER, categories="A")
        c2 = createClause("\\p2\\", type=ClauseType.FILTER, categories="B")
        group = buildClauseGroup([c1, c2], root=GroupOperator.OR)
        assert group.operator == GroupOperator.OR

    def test_default_root_is_and(self):
        c1 = createClause("\\p1\\", type=ClauseType.FILTER, categories="A")
        group = buildClauseGroup([c1])
        assert group.operator == GroupOperator.AND

    def test_nested_groups(self):
        c1 = createClause("\\p1\\", type=ClauseType.FILTER, categories="A")
        c2 = createClause("\\p2\\", type=ClauseType.FILTER, categories="B")
        inner = buildClauseGroup([c1, c2], root=GroupOperator.OR)
        c3 = createClause("\\p3\\", type=ClauseType.FILTER, min=40.0)
        outer = buildClauseGroup([c3, inner], root=GroupOperator.AND)
        assert len(outer.clauses) == 2
        assert isinstance(outer.clauses[1], ClauseGroup)

    def test_empty_list_raises(self):
        with pytest.raises(PicSureValidationError, match="at least one"):
            buildClauseGroup([])

    def test_serializes_end_to_end(self):
        sex = createClause("\\sex\\", type=ClauseType.FILTER, categories="Male")
        age = createClause("\\age\\", type=ClauseType.FILTER, min=40.0)
        copd = createClause("\\copd\\", type=ClauseType.FILTER, categories="Yes")
        asthma = createClause("\\asthma\\", type=ClauseType.ANYRECORD)

        copd_or_asthma = buildClauseGroup([copd, asthma], root=GroupOperator.OR)
        full = buildClauseGroup(
            [sex, age, copd_or_asthma], root=GroupOperator.AND
        )

        result = full.to_query_json()
        assert result["type"] == "and"
        children = result["children"]
        assert len(children) == 3  # type: ignore[arg-type]
        assert children[0]["clauseType"] == "filter"  # type: ignore[index]
        assert children[2]["type"] == "or"  # type: ignore[index]
