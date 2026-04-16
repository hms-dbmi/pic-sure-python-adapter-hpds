import pytest

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator


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
        assert result["type"] == "and"
        assert len(result["children"]) == 2  # type: ignore[arg-type]
        assert result["children"][0]["clauseType"] == "filter"  # type: ignore[index]

    def test_simple_or_group(self):
        group = ClauseGroup(
            clauses=[_copd_clause(), _asthma_clause()],
            operator=GroupOperator.OR,
        )
        result = group.to_query_json()
        assert result["type"] == "or"

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
        assert result["type"] == "and"
        children = result["children"]
        assert len(children) == 3  # type: ignore[arg-type]
        assert children[0]["type"] == "clause"  # type: ignore[index]
        assert children[1]["type"] == "clause"  # type: ignore[index]
        assert children[2]["type"] == "or"  # type: ignore[index]
        assert len(children[2]["children"]) == 2  # type: ignore[index]

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
        assert result["type"] == "or"
        children = result["children"]
        assert children[1]["type"] == "and"  # type: ignore[index]
        grandchildren = children[1]["children"]  # type: ignore[index]
        assert grandchildren[1]["type"] == "or"
