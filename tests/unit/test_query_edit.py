from __future__ import annotations

import pytest

from picsure import (
    Clause,
    ClauseGroup,
    ClauseType,
    GroupOperator,
    buildQuery,
    createSubQuery,
    removeSubQuery,
    replaceClause,
)
from picsure.errors import PicSureValidationError


def _clause(path: str, category: str) -> Clause:
    return createSubQuery(path, type=ClauseType.FILTER, categories=category)


def _flatten(node: Clause | ClauseGroup) -> list[Clause]:
    if isinstance(node, ClauseGroup):
        return [c for child in node.clauses for c in _flatten(child)]
    return [node]


class TestRemoveSubQuery:
    def test_removes_match_at_top_level(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        q = buildQuery([a, b], operator=GroupOperator.AND)

        pruned = removeSubQuery(a, q)

        assert isinstance(pruned, ClauseGroup)
        assert pruned.clauses == [b]
        assert pruned.operator == GroupOperator.AND

    def test_removes_match_nested_keeping_siblings(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        inner = buildQuery([a, b], operator=GroupOperator.OR)
        outer = buildQuery([inner, c], operator=GroupOperator.AND)

        pruned = removeSubQuery(a, outer)

        # inner becomes a 1-clause group [b]; outer keeps both children.
        assert isinstance(pruned, ClauseGroup)
        assert len(pruned.clauses) == 2
        first = pruned.clauses[0]
        assert isinstance(first, ClauseGroup)
        assert first.clauses == [b]
        assert first.operator == GroupOperator.OR
        assert pruned.clauses[1] == c

    def test_emptied_inner_group_is_dropped(self):
        a = _clause("\\a\\", "x")
        c = _clause("\\c\\", "z")
        inner = buildQuery([a], operator=GroupOperator.AND)
        outer = buildQuery([inner, c], operator=GroupOperator.AND)

        pruned = removeSubQuery(a, outer)

        assert isinstance(pruned, ClauseGroup)
        assert pruned.clauses == [c]

    def test_removing_entire_query_raises(self):
        a = _clause("\\a\\", "x")

        with pytest.raises(PicSureValidationError, match="entire query"):
            removeSubQuery(a, a)

    def test_removing_only_child_collapses_to_empty_and_raises(self):
        a = _clause("\\a\\", "x")
        q = buildQuery([a], operator=GroupOperator.AND)

        with pytest.raises(PicSureValidationError, match="entire query"):
            removeSubQuery(a, q)

    def test_removing_all_nested_clauses_raises(self):
        a = _clause("\\a\\", "x")
        inner = buildQuery([a], operator=GroupOperator.OR)
        outer = buildQuery([inner], operator=GroupOperator.AND)

        with pytest.raises(PicSureValidationError, match="entire query"):
            removeSubQuery(a, outer)

    def test_no_op_when_target_absent(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        missing = _clause("\\zz\\", "q")
        q = buildQuery([a, b], operator=GroupOperator.AND)

        pruned = removeSubQuery(missing, q)

        assert pruned == q

    def test_rejects_non_query_target(self):
        a = _clause("\\a\\", "x")
        with pytest.raises(PicSureValidationError, match="`target` must be"):
            removeSubQuery("not-a-clause", a)  # type: ignore[arg-type]

    def test_rejects_non_query_query(self):
        a = _clause("\\a\\", "x")
        with pytest.raises(PicSureValidationError, match="`query` must be"):
            removeSubQuery(a, 42)  # type: ignore[arg-type]


class TestReplaceClause:
    def test_swaps_every_match(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        inner = buildQuery([a, b], operator=GroupOperator.OR)
        outer = buildQuery([a, inner], operator=GroupOperator.AND)

        replaced = replaceClause(a, outer, c)

        flat = _flatten(replaced)
        assert a not in flat
        assert flat.count(c) == 2
        assert b in flat

    def test_swap_at_root_returns_replacement(self):
        a = _clause("\\a\\", "x")
        c = _clause("\\c\\", "z")

        replaced = replaceClause(a, a, c)

        assert replaced == c

    def test_no_op_when_target_absent(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        missing = _clause("\\zz\\", "q")
        replacement = _clause("\\rr\\", "r")
        q = buildQuery([a, b], operator=GroupOperator.AND)

        replaced = replaceClause(missing, q, replacement)

        assert replaced == q

    def test_replace_preserves_operator_and_structure(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        q = buildQuery([a, b], operator=GroupOperator.OR)

        replaced = replaceClause(a, q, c)

        assert isinstance(replaced, ClauseGroup)
        assert replaced.operator == GroupOperator.OR
        assert replaced.clauses == [c, b]

    def test_replacement_can_be_a_group(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        d = _clause("\\d\\", "w")
        sub = buildQuery([c, d], operator=GroupOperator.OR)
        q = buildQuery([a, b], operator=GroupOperator.AND)

        replaced = replaceClause(a, q, sub)

        assert isinstance(replaced, ClauseGroup)
        assert replaced.clauses[0] == sub
        assert replaced.clauses[1] == b

    def test_rejects_non_query_replacement(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        q = buildQuery([a, b], operator=GroupOperator.AND)
        with pytest.raises(PicSureValidationError, match="`replacement` must be"):
            replaceClause(a, q, None)  # type: ignore[arg-type]
