from __future__ import annotations

import pytest

from picsure import (
    Clause,
    ClauseGroup,
    GroupOperator,
    PhenotypicFilterType,
    Query,
    buildClause,
    buildClauseGroup,
    buildQuery,
    removeSubQuery,
    replaceClause,
)
from picsure.errors import PicSureValidationError


def _clause(path: str, category: str) -> Clause:
    return buildClause(path, type=PhenotypicFilterType.FILTER, categories=category)


def _flatten(node: Clause | ClauseGroup) -> list[Clause]:
    if isinstance(node, ClauseGroup):
        return [c for child in node.clauses for c in _flatten(child)]
    return [node]


class TestRemoveSubQuery:
    def test_removes_match_at_top_level(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        q = buildClauseGroup([a, b], operator=GroupOperator.AND)

        pruned = removeSubQuery(q, a)

        assert isinstance(pruned, ClauseGroup)
        assert pruned.clauses == [b]
        assert pruned.operator == GroupOperator.AND

    def test_removes_match_nested_keeping_siblings(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        inner = buildClauseGroup([a, b], operator=GroupOperator.OR)
        outer = buildClauseGroup([inner, c], operator=GroupOperator.AND)

        pruned = removeSubQuery(outer, a)

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
        inner = buildClauseGroup([a], operator=GroupOperator.AND)
        outer = buildClauseGroup([inner, c], operator=GroupOperator.AND)

        pruned = removeSubQuery(outer, a)

        assert isinstance(pruned, ClauseGroup)
        assert pruned.clauses == [c]

    def test_removing_entire_query_raises(self):
        a = _clause("\\a\\", "x")

        with pytest.raises(PicSureValidationError, match="entire query"):
            removeSubQuery(a, a)

    def test_removing_only_child_collapses_to_empty_and_raises(self):
        a = _clause("\\a\\", "x")
        q = buildClauseGroup([a], operator=GroupOperator.AND)

        with pytest.raises(PicSureValidationError, match="entire query"):
            removeSubQuery(q, a)

    def test_removing_all_nested_clauses_raises(self):
        a = _clause("\\a\\", "x")
        inner = buildClauseGroup([a], operator=GroupOperator.OR)
        outer = buildClauseGroup([inner], operator=GroupOperator.AND)

        with pytest.raises(PicSureValidationError, match="entire query"):
            removeSubQuery(outer, a)

    def test_no_op_when_target_absent(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        missing = _clause("\\zz\\", "q")
        q = buildClauseGroup([a, b], operator=GroupOperator.AND)

        pruned = removeSubQuery(q, missing)

        assert pruned == q

    def test_rejects_non_query_target(self):
        a = _clause("\\a\\", "x")
        with pytest.raises(PicSureValidationError, match="`target` must be"):
            removeSubQuery(a, "not-a-clause")  # type: ignore[arg-type]

    def test_rejects_non_query_query(self):
        a = _clause("\\a\\", "x")
        with pytest.raises(PicSureValidationError, match="`query` must be"):
            removeSubQuery(42, a)  # type: ignore[arg-type]


class TestReplaceClause:
    def test_swaps_every_match(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        inner = buildClauseGroup([a, b], operator=GroupOperator.OR)
        outer = buildClauseGroup([a, inner], operator=GroupOperator.AND)

        replaced = replaceClause(outer, a, c)

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
        q = buildClauseGroup([a, b], operator=GroupOperator.AND)

        replaced = replaceClause(q, missing, replacement)

        assert replaced == q

    def test_replace_preserves_operator_and_structure(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        q = buildClauseGroup([a, b], operator=GroupOperator.OR)

        replaced = replaceClause(q, a, c)

        assert isinstance(replaced, ClauseGroup)
        assert replaced.operator == GroupOperator.OR
        assert replaced.clauses == [c, b]

    def test_replacement_can_be_a_group(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        d = _clause("\\d\\", "w")
        sub = buildClauseGroup([c, d], operator=GroupOperator.OR)
        q = buildClauseGroup([a, b], operator=GroupOperator.AND)

        replaced = replaceClause(q, a, sub)

        assert isinstance(replaced, ClauseGroup)
        assert replaced.clauses[0] == sub
        assert replaced.clauses[1] == b

    def test_rejects_non_query_replacement(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        q = buildClauseGroup([a, b], operator=GroupOperator.AND)
        with pytest.raises(PicSureValidationError, match="`replacement` must be"):
            replaceClause(q, a, None)  # type: ignore[arg-type]


class TestEditQueryContainer:
    def test_remove_unwraps_and_preserves_include_concepts(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        group = buildClauseGroup([a, b], operator=GroupOperator.AND)
        query = buildQuery(phenotypicFilter=group, includeConcepts=["\\out\\"])

        pruned = removeSubQuery(query, a)

        assert isinstance(pruned, Query)
        assert pruned.includeConcepts == ("\\out\\",)
        assert isinstance(pruned.phenotypicFilter, ClauseGroup)
        assert pruned.phenotypicFilter.clauses == [b]

    def test_replace_unwraps_and_preserves_include_concepts(self):
        a = _clause("\\a\\", "x")
        b = _clause("\\b\\", "y")
        c = _clause("\\c\\", "z")
        group = buildClauseGroup([a, b], operator=GroupOperator.OR)
        query = buildQuery(phenotypicFilter=group, includeConcepts=["\\out\\"])

        replaced = replaceClause(query, a, c)

        assert isinstance(replaced, Query)
        assert replaced.includeConcepts == ("\\out\\",)
        assert isinstance(replaced.phenotypicFilter, ClauseGroup)
        assert replaced.phenotypicFilter.clauses == [c, b]

    def test_remove_on_include_only_query_raises(self):
        a = _clause("\\a\\", "x")
        query = buildQuery(includeConcepts=["\\out\\"])
        with pytest.raises(PicSureValidationError, match="no phenotypic filter"):
            removeSubQuery(query, a)

    def test_replace_on_include_only_query_raises(self):
        a = _clause("\\a\\", "x")
        c = _clause("\\c\\", "z")
        query = buildQuery(includeConcepts=["\\out\\"])
        with pytest.raises(PicSureValidationError, match="no phenotypic filter"):
            replaceClause(query, a, c)


def test_remove_subquery_preserves_genomic_filters():
    from picsure import (
        PhenotypicFilterType,
        Query,
        buildClause,
        buildClauseGroup,
        buildQuery,
        removeSubQuery,
    )
    from picsure._services.query_build import buildGenomicFilter

    gf = buildGenomicFilter("Gene_with_variant", values=["BRCA1"])
    c1 = buildClause("\\a\\", type=PhenotypicFilterType.FILTER, categories="X")
    c2 = buildClause("\\b\\", type=PhenotypicFilterType.FILTER, categories="Y")
    grp = buildClauseGroup([c1, c2])
    q = buildQuery(phenotypicFilter=grp, genomicFilters=gf)

    result = removeSubQuery(q, c2)
    assert isinstance(result, Query)
    assert result.genomicFilters == (gf,)


def test_replace_clause_preserves_genomic_filters():
    from picsure import (
        PhenotypicFilterType,
        Query,
        buildClause,
        buildQuery,
        replaceClause,
    )
    from picsure._services.query_build import buildGenomicFilter

    gf = buildGenomicFilter("Gene_with_variant", values=["BRCA1"])
    c1 = buildClause("\\a\\", type=PhenotypicFilterType.FILTER, categories="X")
    c2 = buildClause("\\b\\", type=PhenotypicFilterType.FILTER, categories="Y")
    q = buildQuery(phenotypicFilter=c1, genomicFilters=gf)

    result = replaceClause(q, c1, c2)
    assert isinstance(result, Query)
    assert result.genomicFilters == (gf,)
