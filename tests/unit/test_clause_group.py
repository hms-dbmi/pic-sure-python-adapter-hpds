import pytest

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure.errors import PicSureValidationError


class TestGroupOperator:
    def test_and_value(self):
        assert GroupOperator.AND.value == "AND"

    def test_or_value(self):
        assert GroupOperator.OR.value == "OR"

    def test_all_members(self):
        assert set(GroupOperator) == {GroupOperator.AND, GroupOperator.OR}


def _sex_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\sex\\"],
        type=ClauseType.FILTER,
        categories=["Male"],
    )


def _age_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\age\\"],
        type=ClauseType.FILTER,
        min=40.0,
    )


def _copd_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\copd\\"],
        type=ClauseType.FILTER,
        categories=["Yes"],
    )


def _asthma_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\asthma\\"],
        type=ClauseType.FILTER,
        categories=["Yes, recent"],
    )


def _select_clause() -> Clause:
    return Clause(keys=["\\phs1\\output\\"], type=ClauseType.SELECT)


class TestClauseGroup:
    def test_and_group(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _age_clause()],
            operator=GroupOperator.AND,
        )
        assert group.operator == GroupOperator.AND
        assert len(group.clauses) == 2

    def test_or_group(self):
        group = ClauseGroup(
            clauses=[_copd_clause(), _asthma_clause()],
            operator=GroupOperator.OR,
        )
        assert group.operator == GroupOperator.OR

    def test_frozen(self):
        group = ClauseGroup(
            clauses=[_sex_clause()],
            operator=GroupOperator.AND,
        )
        with pytest.raises(AttributeError):
            group.operator = GroupOperator.OR  # type: ignore[misc]

    def test_nested_groups(self):
        inner = ClauseGroup(
            clauses=[_copd_clause(), _asthma_clause()],
            operator=GroupOperator.OR,
        )
        outer = ClauseGroup(
            clauses=[_sex_clause(), _age_clause(), inner],
            operator=GroupOperator.AND,
        )
        assert len(outer.clauses) == 3
        assert isinstance(outer.clauses[2], ClauseGroup)


class TestClauseGroupToQueryJson:
    def test_simple_and_group(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _age_clause()],
            operator=GroupOperator.AND,
        )
        result = group.to_query_json()
        assert result["operator"] == "AND"
        assert result["not"] is False
        children = result["phenotypicClauses"]
        assert len(children) == 2  # type: ignore[arg-type]
        assert children[0]["phenotypicFilterType"] == "FILTER"  # type: ignore[index]
        assert children[0]["conceptPath"] == "\\phs1\\sex\\"  # type: ignore[index]

    def test_simple_or_group(self):
        group = ClauseGroup(
            clauses=[_copd_clause(), _asthma_clause()],
            operator=GroupOperator.OR,
        )
        result = group.to_query_json()
        assert result["operator"] == "OR"

    def test_nested_json(self):
        copd_or_asthma = ClauseGroup(
            clauses=[_copd_clause(), _asthma_clause()],
            operator=GroupOperator.OR,
        )
        full = ClauseGroup(
            clauses=[_sex_clause(), _age_clause(), copd_or_asthma],
            operator=GroupOperator.AND,
        )
        result = full.to_query_json()
        assert result["operator"] == "AND"
        children = result["phenotypicClauses"]
        assert len(children) == 3  # type: ignore[arg-type]
        assert children[0]["phenotypicFilterType"] == "FILTER"  # type: ignore[index]
        assert children[1]["phenotypicFilterType"] == "FILTER"  # type: ignore[index]
        assert children[2]["operator"] == "OR"  # type: ignore[index]
        assert len(children[2]["phenotypicClauses"]) == 2  # type: ignore[index]

    def test_deeply_nested_json(self):
        inner_or = ClauseGroup(
            clauses=[_copd_clause(), _asthma_clause()],
            operator=GroupOperator.OR,
        )
        mid_and = ClauseGroup(
            clauses=[_age_clause(), inner_or],
            operator=GroupOperator.AND,
        )
        outer_or = ClauseGroup(
            clauses=[_sex_clause(), mid_and],
            operator=GroupOperator.OR,
        )
        result = outer_or.to_query_json()
        assert result["operator"] == "OR"
        children = result["phenotypicClauses"]
        assert children[1]["operator"] == "AND"  # type: ignore[index]
        grandchildren = children[1]["phenotypicClauses"]  # type: ignore[index]
        assert grandchildren[1]["operator"] == "OR"

    def test_mixed_group_with_select_raises(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _select_clause()],
            operator=GroupOperator.AND,
        )
        with pytest.raises(PicSureValidationError, match="SELECT"):
            group.to_query_json()

    def test_mixed_group_error_mentions_select_paths(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _select_clause()],
            operator=GroupOperator.AND,
        )
        with pytest.raises(PicSureValidationError, match="select_paths"):
            group.to_query_json()

    def test_all_select_group_raises(self):
        group = ClauseGroup(
            clauses=[_select_clause(), _select_clause()],
            operator=GroupOperator.AND,
        )
        with pytest.raises(PicSureValidationError, match="SELECT"):
            group.to_query_json()

    def test_nested_group_with_deep_select_raises(self):
        inner = ClauseGroup(
            clauses=[_age_clause(), _select_clause()],
            operator=GroupOperator.OR,
        )
        outer = ClauseGroup(
            clauses=[_sex_clause(), inner],
            operator=GroupOperator.AND,
        )
        with pytest.raises(PicSureValidationError, match="SELECT"):
            outer.to_query_json()

    def test_pure_phenotypic_group_still_serializes(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _age_clause()],
            operator=GroupOperator.AND,
        )
        result = group.to_query_json()
        children = result["phenotypicClauses"]
        assert len(children) == 2  # type: ignore[arg-type]
        assert children[0]["conceptPath"] == "\\phs1\\sex\\"  # type: ignore[index]

    def test_pure_select_group_select_paths_still_works(self):
        group = ClauseGroup(
            clauses=[_select_clause(), _select_clause()],
            operator=GroupOperator.AND,
        )
        assert group.select_paths() == ["\\phs1\\output\\", "\\phs1\\output\\"]
        assert group.has_phenotypic() is False


class TestClauseGroupSelectPaths:
    def test_flat_selects_collected(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _select_clause()],
            operator=GroupOperator.AND,
        )
        assert group.select_paths() == ["\\phs1\\output\\"]

    def test_nested_selects_collected(self):
        inner = ClauseGroup(
            clauses=[_select_clause()],
            operator=GroupOperator.AND,
        )
        outer = ClauseGroup(
            clauses=[_sex_clause(), inner],
            operator=GroupOperator.AND,
        )
        assert outer.select_paths() == ["\\phs1\\output\\"]


class TestClauseGroupHasPhenotypic:
    def test_true_for_filter(self):
        group = ClauseGroup(clauses=[_sex_clause()], operator=GroupOperator.AND)
        assert group.has_phenotypic() is True

    def test_false_for_selects_only(self):
        group = ClauseGroup(
            clauses=[_select_clause(), _select_clause()],
            operator=GroupOperator.AND,
        )
        assert group.has_phenotypic() is False

    def test_true_for_nested_filter(self):
        inner = ClauseGroup(
            clauses=[_sex_clause()],
            operator=GroupOperator.AND,
        )
        outer = ClauseGroup(
            clauses=[_select_clause(), inner],
            operator=GroupOperator.AND,
        )
        assert outer.has_phenotypic() is True


class TestClauseGroupPhenotypicOnly:
    def test_strips_top_level_selects(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _select_clause(), _age_clause()],
            operator=GroupOperator.AND,
        )
        stripped = group.phenotypic_only()
        assert stripped is not None
        assert len(stripped.clauses) == 2
        assert stripped.operator == GroupOperator.AND
        assert all(
            isinstance(c, Clause) and c.type != ClauseType.SELECT
            for c in stripped.clauses
        )

    def test_returns_none_when_only_selects(self):
        group = ClauseGroup(
            clauses=[_select_clause(), _select_clause()],
            operator=GroupOperator.AND,
        )
        assert group.phenotypic_only() is None

    def test_strips_recursively_in_nested_group(self):
        inner = ClauseGroup(
            clauses=[_age_clause(), _select_clause()],
            operator=GroupOperator.OR,
        )
        outer = ClauseGroup(
            clauses=[_sex_clause(), _select_clause(), inner],
            operator=GroupOperator.AND,
        )
        stripped = outer.phenotypic_only()
        assert stripped is not None
        assert len(stripped.clauses) == 2  # _sex_clause() and stripped inner
        nested = stripped.clauses[1]
        assert isinstance(nested, ClauseGroup)
        assert len(nested.clauses) == 1
        assert isinstance(nested.clauses[0], Clause)
        assert nested.clauses[0].type == ClauseType.FILTER

    def test_drops_nested_group_that_becomes_empty(self):
        inner = ClauseGroup(
            clauses=[_select_clause(), _select_clause()],
            operator=GroupOperator.OR,
        )
        outer = ClauseGroup(
            clauses=[_sex_clause(), inner],
            operator=GroupOperator.AND,
        )
        stripped = outer.phenotypic_only()
        assert stripped is not None
        assert len(stripped.clauses) == 1
        assert isinstance(stripped.clauses[0], Clause)
        assert stripped.clauses[0].type == ClauseType.FILTER

    def test_returns_none_when_everything_strips(self):
        inner = ClauseGroup(
            clauses=[_select_clause()],
            operator=GroupOperator.AND,
        )
        outer = ClauseGroup(
            clauses=[_select_clause(), inner],
            operator=GroupOperator.AND,
        )
        assert outer.phenotypic_only() is None

    def test_pure_phenotypic_group_returned_as_equivalent(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _age_clause()],
            operator=GroupOperator.AND,
        )
        stripped = group.phenotypic_only()
        assert stripped is not None
        assert stripped.operator == GroupOperator.AND
        assert len(stripped.clauses) == 2

    def test_to_query_json_works_on_stripped_group(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _select_clause(), _age_clause()],
            operator=GroupOperator.AND,
        )
        stripped = group.phenotypic_only()
        assert stripped is not None
        result = stripped.to_query_json()
        assert result["operator"] == "AND"
        assert len(result["phenotypicClauses"]) == 2  # type: ignore[arg-type]
