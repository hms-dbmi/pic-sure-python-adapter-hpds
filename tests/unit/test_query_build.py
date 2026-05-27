import pytest

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.query import Query
from picsure._services.query_build import buildClause, buildClauseGroup, buildQuery
from picsure.errors import PicSureValidationError


class TestBuildClause:
    def test_categorical_filter(self):
        clause = buildClause(
            "\\phs1\\sex\\",
            type=PhenotypicFilterType.FILTER,
            categories="Male",
        )
        assert isinstance(clause, Clause)
        assert clause.keys == ["\\phs1\\sex\\"]
        assert clause.categories == ["Male"]

    def test_keys_list_preserved(self):
        clause = buildClause(
            ["\\p1\\", "\\p2\\"],
            type=PhenotypicFilterType.ANYRECORD,
        )
        assert clause.keys == ["\\p1\\", "\\p2\\"]

    def test_categories_list_preserved(self):
        clause = buildClause(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            categories=["Male", "Female"],
        )
        assert clause.categories == ["Male", "Female"]

    def test_continuous_filter_min_only(self):
        clause = buildClause(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            min=40.0,
        )
        assert clause.min == 40.0
        assert clause.max is None

    def test_continuous_filter_min_and_max(self):
        clause = buildClause(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            min=18.0,
            max=65.0,
        )
        assert clause.min == 18.0
        assert clause.max == 65.0

    def test_anyrecord(self):
        clause = buildClause("\\path\\", type=PhenotypicFilterType.ANYRECORD)
        assert clause.type == PhenotypicFilterType.ANYRECORD
        assert clause.categories is None
        assert clause.min is None

    def test_require(self):
        clause = buildClause("\\path\\", type=PhenotypicFilterType.REQUIRE)
        assert clause.type == PhenotypicFilterType.REQUIRE


class TestBuildClauseValidation:
    def test_anyrecord_with_categories_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                categories="Male",
            )

    def test_anyrecord_with_categories_message_is_actionable(self):
        with pytest.raises(PicSureValidationError, match="Remove the categories"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                categories=["x"],
            )

    def test_anyrecord_with_min_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                min=10.0,
            )

    def test_filter_without_criteria_raises(self):
        with pytest.raises(PicSureValidationError, match="FILTER"):
            buildClause("\\path\\", type=PhenotypicFilterType.FILTER)

    def test_filter_without_criteria_message_is_actionable(self):
        with pytest.raises(PicSureValidationError, match="categories.*min.*max"):
            buildClause("\\path\\", type=PhenotypicFilterType.FILTER)

    def test_filter_with_categories_and_min_raises(self):
        with pytest.raises(PicSureValidationError, match="FILTER"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.FILTER,
                categories="Male",
                min=40.0,
            )

    def test_filter_with_categories_and_min_message_mentions_both(self):
        with pytest.raises(PicSureValidationError, match="categories and min/max"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.FILTER,
                categories="Male",
                min=40.0,
            )

    def test_require_with_categories_raises(self):
        with pytest.raises(PicSureValidationError, match="REQUIRE"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.REQUIRE,
                categories="Male",
            )

    def test_require_with_min_raises(self):
        with pytest.raises(PicSureValidationError, match="REQUIRE"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.REQUIRE,
                min=10.0,
            )

    def test_empty_keys_list_raises(self):
        with pytest.raises(PicSureValidationError, match="at least one concept path"):
            buildClause([], type=PhenotypicFilterType.FILTER, categories="x")


class TestSelectRemoved:
    def test_select_member_is_gone(self):
        assert not hasattr(PhenotypicFilterType, "SELECT")


class TestBuildClauseGroup:
    def test_and_group(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = buildClause("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        group = buildClauseGroup([c1, c2], operator=GroupOperator.AND)
        assert isinstance(group, ClauseGroup)
        assert group.operator == GroupOperator.AND
        assert len(group.clauses) == 2

    def test_or_group(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = buildClause("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        group = buildClauseGroup([c1, c2], operator=GroupOperator.OR)
        assert group.operator == GroupOperator.OR

    def test_default_operator_is_and(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        group = buildClauseGroup([c1])
        assert group.operator == GroupOperator.AND

    def test_nested_groups(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = buildClause("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        inner = buildClauseGroup([c1, c2], operator=GroupOperator.OR)
        c3 = buildClause("\\p3\\", type=PhenotypicFilterType.FILTER, min=40.0)
        outer = buildClauseGroup([c3, inner], operator=GroupOperator.AND)
        assert len(outer.clauses) == 2
        assert isinstance(outer.clauses[1], ClauseGroup)

    def test_empty_list_raises(self):
        with pytest.raises(PicSureValidationError, match="at least one"):
            buildClauseGroup([])

    def test_copies_caller_list(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = buildClause("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        clauses = [c1, c2]
        group = buildClauseGroup(clauses, operator=GroupOperator.AND)
        clauses.append(
            buildClause("\\p3\\", type=PhenotypicFilterType.FILTER, categories="C")
        )
        assert len(group.clauses) == 2

    def test_serializes_end_to_end(self):
        sex = buildClause(
            "\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male"
        )
        age = buildClause("\\age\\", type=PhenotypicFilterType.FILTER, min=40.0)
        copd = buildClause(
            "\\copd\\", type=PhenotypicFilterType.FILTER, categories="Yes"
        )
        asthma = buildClause("\\asthma\\", type=PhenotypicFilterType.ANYRECORD)

        copd_or_asthma = buildClauseGroup([copd, asthma], operator=GroupOperator.OR)
        full = buildClauseGroup([sex, age, copd_or_asthma], operator=GroupOperator.AND)

        result = full.to_query_json()
        assert result["operator"] == "AND"
        children = result["phenotypicClauses"]
        assert len(children) == 3  # type: ignore[arg-type]
        assert children[0]["phenotypicFilterType"] == "FILTER"  # type: ignore[index]
        assert children[0]["conceptPath"] == "\\sex\\"  # type: ignore[index]
        assert children[2]["operator"] == "OR"  # type: ignore[index]


class TestBuildQuery:
    def test_filter_and_include_concepts(self):
        males = buildClause(
            "\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male"
        )
        q = buildQuery(phenotypicFilter=males, includeConcepts=["\\bmi\\", "\\hdl\\"])
        assert isinstance(q, Query)
        assert q.phenotypicFilter is males
        assert q.includeConcepts == ("\\bmi\\", "\\hdl\\")

    def test_filter_only(self):
        males = buildClause(
            "\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male"
        )
        q = buildQuery(phenotypicFilter=males)
        assert q.phenotypicFilter is males
        assert q.includeConcepts == ()

    def test_include_only(self):
        q = buildQuery(includeConcepts=["\\bmi\\"])
        assert q.phenotypicFilter is None
        assert q.includeConcepts == ("\\bmi\\",)

    def test_include_concepts_string_normalized(self):
        q = buildQuery(includeConcepts="\\bmi\\")
        assert q.includeConcepts == ("\\bmi\\",)

    def test_include_concepts_dedup_preserves_order(self):
        q = buildQuery(includeConcepts=["\\b\\", "\\a\\", "\\b\\", "\\c\\", "\\a\\"])
        assert q.includeConcepts == ("\\b\\", "\\a\\", "\\c\\")

    def test_accepts_clause_group_filter(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        group = buildClauseGroup([c1])
        q = buildQuery(phenotypicFilter=group, includeConcepts="\\bmi\\")
        assert q.phenotypicFilter is group

    def test_empty_raises(self):
        with pytest.raises(PicSureValidationError, match="requires a phenotypicFilter"):
            buildQuery()

    def test_bad_filter_type_raises(self):
        with pytest.raises(
            PicSureValidationError, match="must be a Clause or ClauseGroup"
        ):
            buildQuery(phenotypicFilter=["not", "a", "clause"], includeConcepts="\\b\\")

    def test_query_is_frozen(self):
        q = buildQuery(includeConcepts="\\bmi\\")
        with pytest.raises((AttributeError, TypeError)):
            q.includeConcepts = ("\\x\\",)  # type: ignore[misc]
