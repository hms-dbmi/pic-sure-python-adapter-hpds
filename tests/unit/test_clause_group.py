import dataclasses

import pytest

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.query import Query
from picsure.errors import PicSureValidationError


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


class TestClauseGroupImmutability:
    def test_stores_a_list_argument_as_a_tuple(self):
        group = ClauseGroup(clauses=[_sex_clause()], operator=GroupOperator.AND)

        assert isinstance(group.clauses, tuple)

    def test_is_hashable(self):
        group = ClauseGroup(clauses=(_sex_clause(),), operator=GroupOperator.AND)

        assert isinstance(hash(group), int)

    def test_nested_group_is_hashable(self):
        inner = ClauseGroup(clauses=(_sex_clause(),), operator=GroupOperator.OR)
        outer = ClauseGroup(clauses=(_sex_clause(), inner), operator=GroupOperator.AND)

        assert isinstance(hash(outer), int)

    def test_works_as_a_dict_key(self):
        group = ClauseGroup(clauses=(_sex_clause(),), operator=GroupOperator.AND)

        assert {group: "seen"}[group] == "seen"

    def test_equal_groups_collapse_in_a_set(self):
        a = ClauseGroup(clauses=(_sex_clause(),), operator=GroupOperator.AND)
        b = ClauseGroup(clauses=(_sex_clause(),), operator=GroupOperator.AND)

        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_attribute_assignment_is_refused(self):
        group = ClauseGroup(clauses=(_sex_clause(),), operator=GroupOperator.AND)

        with pytest.raises(dataclasses.FrozenInstanceError):
            group.operator = GroupOperator.OR

    def test_clauses_cannot_be_appended_to(self):
        group = ClauseGroup(clauses=(_sex_clause(),), operator=GroupOperator.AND)

        with pytest.raises(AttributeError):
            group.clauses.append(_sex_clause())


class TestClauseGroupInputTypes:
    def test_accepts_a_generator_of_clauses(self):
        group = ClauseGroup(
            clauses=(clause for clause in [_sex_clause(), _age_clause()]),
            operator=GroupOperator.AND,
        )

        assert group.clauses == (_sex_clause(), _age_clause())

    def test_bare_clause_is_refused_naming_the_expected_type(self):
        with pytest.raises(PicSureValidationError, match="Clause or ClauseGroup"):
            ClauseGroup(clauses=_sex_clause(), operator=GroupOperator.AND)

    def test_bare_group_is_refused_naming_what_was_passed(self):
        inner = ClauseGroup(clauses=(_sex_clause(),), operator=GroupOperator.OR)

        with pytest.raises(PicSureValidationError, match="bare ClauseGroup"):
            ClauseGroup(clauses=inner, operator=GroupOperator.AND)

    def test_a_string_is_refused_rather_than_split_into_characters(self):
        with pytest.raises(PicSureValidationError, match="not a string"):
            ClauseGroup(clauses="abc", operator=GroupOperator.AND)

    def test_a_query_container_is_refused_inside_the_error_hierarchy(self):
        """A Query is not iterable, so tuple() alone raised a raw TypeError."""
        query = Query(phenotypicFilter=_sex_clause())

        with pytest.raises(PicSureValidationError) as exc_info:
            ClauseGroup(clauses=query, operator=GroupOperator.AND)

        message = str(exc_info.value)
        assert "Query" in message
        assert "cannot be iterated" in message
        assert "phenotypicFilter" in message

    def test_a_non_iterable_container_is_refused_naming_its_type(self):
        with pytest.raises(PicSureValidationError) as exc_info:
            ClauseGroup(clauses=42, operator=GroupOperator.AND)

        message = str(exc_info.value)
        assert "int" in message
        assert "cannot be iterated" in message
        assert "buildClause()" in message

    def test_a_list_of_clauses_still_builds(self):
        group = ClauseGroup(
            clauses=[_sex_clause(), _age_clause()], operator=GroupOperator.AND
        )

        assert group.clauses == (_sex_clause(), _age_clause())

    def test_a_tuple_of_clauses_still_builds(self):
        group = ClauseGroup(
            clauses=(_sex_clause(), _age_clause()), operator=GroupOperator.OR
        )

        assert group.clauses == (_sex_clause(), _age_clause())


class TestClauseGroupChildTypes:
    """Only a Clause or a ClauseGroup carries the group's wire contract."""

    def test_a_query_child_is_refused_with_the_composable_part_named(self):
        query = Query(phenotypicFilter=_sex_clause())

        with pytest.raises(PicSureValidationError) as exc_info:
            ClauseGroup(clauses=[query, _age_clause()], operator=GroupOperator.AND)

        message = str(exc_info.value)
        assert "index 0" in message
        assert "Query" in message
        assert "phenotypicFilter" in message

    def test_a_string_child_is_refused_naming_its_position(self):
        with pytest.raises(PicSureValidationError) as exc_info:
            ClauseGroup(clauses=[_sex_clause(), "\\x\\"], operator=GroupOperator.AND)

        message = str(exc_info.value)
        assert "index 1" in message
        assert "str" in message
        assert "buildClause()" in message

    def test_an_arbitrary_object_child_is_refused(self):
        with pytest.raises(PicSureValidationError, match="not a Clause or ClauseGroup"):
            ClauseGroup(clauses=[object()], operator=GroupOperator.AND)

    def test_a_mix_of_clauses_and_nested_groups_still_builds(self):
        inner = ClauseGroup(clauses=[_age_clause()], operator=GroupOperator.OR)

        group = ClauseGroup(clauses=[_sex_clause(), inner], operator=GroupOperator.AND)

        assert group.clauses == (_sex_clause(), inner)
        assert group.to_query_json()["operator"] == "AND"
