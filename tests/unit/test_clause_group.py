import pytest

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator


class TestGroupOperator:
    def test_and_value(self):
        assert GroupOperator.AND.value == "AND"

    def test_or_value(self):
        assert GroupOperator.OR.value == "OR"


def _sex_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\sex\\"],
        type=PhenotypicFilterType.FILTER,
        categories=["Male"],
    )


def _age_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\age\\"],
        type=PhenotypicFilterType.FILTER,
        min=40.0,
    )


def _copd_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\copd\\"],
        type=PhenotypicFilterType.FILTER,
        categories=["Yes"],
    )


def _asthma_clause() -> Clause:
    return Clause(
        keys=["\\phs1\\asthma\\"],
        type=PhenotypicFilterType.FILTER,
        categories=["Yes, recent"],
    )


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


class TestClauseGroupConceptPaths:
    def test_flat_group_returns_paths_in_order(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _age_clause()],
            operator=GroupOperator.AND,
        )
        assert group.concept_paths() == ["\\phs1\\sex\\", "\\phs1\\age\\"]

    def test_nested_group_flattens_depth_first_in_order(self):
        inner = ClauseGroup(
            clauses=[_copd_clause(), _asthma_clause()],
            operator=GroupOperator.OR,
        )
        outer = ClauseGroup(
            clauses=[_sex_clause(), _age_clause(), inner],
            operator=GroupOperator.AND,
        )
        assert outer.concept_paths() == [
            "\\phs1\\sex\\",
            "\\phs1\\age\\",
            "\\phs1\\copd\\",
            "\\phs1\\asthma\\",
        ]

    def test_multi_key_clause_contributes_all_keys(self):
        multi = Clause(
            keys=["\\path_a\\", "\\path_b\\"],
            type=PhenotypicFilterType.ANYRECORD,
        )
        group = ClauseGroup(clauses=[_sex_clause(), multi], operator=GroupOperator.AND)
        assert group.concept_paths() == [
            "\\phs1\\sex\\",
            "\\path_a\\",
            "\\path_b\\",
        ]


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
