import pytest

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._services.query_build import buildQuery, createSubQuery
from picsure.errors import PicSureValidationError


class TestCreateClause:
    def test_categorical_filter(self):
        clause = createSubQuery(
            "\\phs1\\sex\\",
            type=PhenotypicFilterType.FILTER,
            categories="Male",
        )
        assert isinstance(clause, Clause)
        assert clause.keys == ["\\phs1\\sex\\"]
        assert clause.categories == ["Male"]

    def test_keys_string_normalized_to_list(self):
        clause = createSubQuery("\\path\\", type=PhenotypicFilterType.SELECT)
        assert clause.keys == ["\\path\\"]

    def test_keys_list_preserved(self):
        clause = createSubQuery(
            ["\\p1\\", "\\p2\\"],
            type=PhenotypicFilterType.SELECT,
        )
        assert clause.keys == ["\\p1\\", "\\p2\\"]

    def test_categories_string_normalized_to_list(self):
        clause = createSubQuery(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            categories="Male",
        )
        assert clause.categories == ["Male"]

    def test_categories_list_preserved(self):
        clause = createSubQuery(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            categories=["Male", "Female"],
        )
        assert clause.categories == ["Male", "Female"]

    def test_continuous_filter_min_only(self):
        clause = createSubQuery(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            min=40.0,
        )
        assert clause.min == 40.0
        assert clause.max is None

    def test_continuous_filter_max_only(self):
        clause = createSubQuery(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            max=100.0,
        )
        assert clause.max == 100.0
        assert clause.min is None

    def test_continuous_filter_min_and_max(self):
        clause = createSubQuery(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            min=18.0,
            max=65.0,
        )
        assert clause.min == 18.0
        assert clause.max == 65.0

    def test_anyrecord(self):
        clause = createSubQuery("\\path\\", type=PhenotypicFilterType.ANYRECORD)
        assert clause.type == PhenotypicFilterType.ANYRECORD
        assert clause.categories is None
        assert clause.min is None

    def test_select(self):
        clause = createSubQuery("\\path\\", type=PhenotypicFilterType.SELECT)
        assert clause.type == PhenotypicFilterType.SELECT

    def test_require(self):
        clause = createSubQuery("\\path\\", type=PhenotypicFilterType.REQUIRE)
        assert clause.type == PhenotypicFilterType.REQUIRE


class TestCreateClauseValidation:
    def test_anyrecord_with_categories_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                categories="Male",
            )

    def test_anyrecord_with_categories_message_is_actionable(self):
        with pytest.raises(PicSureValidationError, match="Remove the categories"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                categories=["x"],
            )

    def test_anyrecord_with_min_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                min=10.0,
            )

    def test_anyrecord_with_max_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                max=100.0,
            )

    def test_filter_without_criteria_raises(self):
        with pytest.raises(PicSureValidationError, match="FILTER"):
            createSubQuery("\\path\\", type=PhenotypicFilterType.FILTER)

    def test_filter_without_criteria_message_is_actionable(self):
        with pytest.raises(PicSureValidationError, match="categories.*min.*max"):
            createSubQuery("\\path\\", type=PhenotypicFilterType.FILTER)

    def test_filter_with_categories_and_min_raises(self):
        with pytest.raises(PicSureValidationError, match="FILTER"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.FILTER,
                categories="Male",
                min=40.0,
            )

    def test_filter_with_categories_and_max_raises(self):
        with pytest.raises(PicSureValidationError, match="FILTER"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.FILTER,
                categories=["Male"],
                max=100.0,
            )

    def test_filter_with_categories_and_min_message_mentions_both(self):
        with pytest.raises(PicSureValidationError, match="categories and min/max"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.FILTER,
                categories="Male",
                min=40.0,
            )

    def test_require_with_categories_raises(self):
        with pytest.raises(PicSureValidationError, match="REQUIRE"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.REQUIRE,
                categories="Male",
            )

    def test_require_with_min_raises(self):
        with pytest.raises(PicSureValidationError, match="REQUIRE"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.REQUIRE,
                min=10.0,
            )

    def test_require_with_max_raises(self):
        with pytest.raises(PicSureValidationError, match="REQUIRE"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.REQUIRE,
                max=100.0,
            )

    def test_select_with_categories_raises(self):
        with pytest.raises(PicSureValidationError, match="SELECT"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.SELECT,
                categories="Male",
            )

    def test_select_with_min_raises(self):
        with pytest.raises(PicSureValidationError, match="SELECT"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.SELECT,
                min=10.0,
            )

    def test_select_with_max_raises(self):
        with pytest.raises(PicSureValidationError, match="SELECT"):
            createSubQuery(
                "\\path\\",
                type=PhenotypicFilterType.SELECT,
                max=100.0,
            )

    def test_empty_keys_list_raises(self):
        with pytest.raises(PicSureValidationError, match="at least one concept path"):
            createSubQuery([], type=PhenotypicFilterType.FILTER, categories="x")

    def test_empty_keys_list_on_select_raises(self):
        with pytest.raises(PicSureValidationError, match="at least one concept path"):
            createSubQuery([], type=PhenotypicFilterType.SELECT)


class TestBuildClauseGroup:
    def test_and_group(self):
        c1 = createSubQuery("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = createSubQuery("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        group = buildQuery([c1, c2], operator=GroupOperator.AND)
        assert isinstance(group, ClauseGroup)
        assert group.operator == GroupOperator.AND
        assert len(group.clauses) == 2

    def test_or_group(self):
        c1 = createSubQuery("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = createSubQuery("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        group = buildQuery([c1, c2], operator=GroupOperator.OR)
        assert group.operator == GroupOperator.OR

    def test_default_operator_is_and(self):
        c1 = createSubQuery("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        group = buildQuery([c1])
        assert group.operator == GroupOperator.AND

    def test_nested_groups(self):
        c1 = createSubQuery("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = createSubQuery("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        inner = buildQuery([c1, c2], operator=GroupOperator.OR)
        c3 = createSubQuery("\\p3\\", type=PhenotypicFilterType.FILTER, min=40.0)
        outer = buildQuery([c3, inner], operator=GroupOperator.AND)
        assert len(outer.clauses) == 2
        assert isinstance(outer.clauses[1], ClauseGroup)

    def test_empty_list_raises(self):
        with pytest.raises(PicSureValidationError, match="at least one"):
            buildQuery([])

    def test_serializes_end_to_end(self):
        sex = createSubQuery(
            "\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male"
        )
        age = createSubQuery("\\age\\", type=PhenotypicFilterType.FILTER, min=40.0)
        copd = createSubQuery(
            "\\copd\\", type=PhenotypicFilterType.FILTER, categories="Yes"
        )
        asthma = createSubQuery("\\asthma\\", type=PhenotypicFilterType.ANYRECORD)

        copd_or_asthma = buildQuery([copd, asthma], operator=GroupOperator.OR)
        full = buildQuery([sex, age, copd_or_asthma], operator=GroupOperator.AND)

        result = full.to_query_json()
        assert result["operator"] == "AND"
        children = result["phenotypicClauses"]
        assert len(children) == 3  # type: ignore[arg-type]
        assert children[0]["phenotypicFilterType"] == "FILTER"  # type: ignore[index]
        assert children[0]["conceptPath"] == "\\sex\\"  # type: ignore[index]
        assert children[2]["operator"] == "OR"  # type: ignore[index]
