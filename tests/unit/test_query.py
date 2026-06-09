from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.query import Query


class TestQueryTypeAlias:
    def test_clause_is_valid_query(self):
        clause = Clause(
            keys=["\\path\\"],
            type=PhenotypicFilterType.FILTER,
            categories=["Male"],
        )
        q: Query = clause
        assert q is clause

    def test_clause_group_is_valid_query(self):
        group = ClauseGroup(
            clauses=[
                Clause(
                    keys=["\\p1\\"], type=PhenotypicFilterType.FILTER, categories=["A"]
                ),
                Clause(keys=["\\p2\\"], type=PhenotypicFilterType.ANYRECORD),
            ],
            operator=GroupOperator.AND,
        )
        q: Query = group
        assert q is group

    def test_query_has_to_query_json(self):
        clause = Clause(keys=["\\path\\"], type=PhenotypicFilterType.REQUIRE)
        q: Query = clause
        result = q.to_query_json()
        assert result["phenotypicFilterType"] == "REQUIRED"
        assert result["conceptPath"] == "\\path\\"


def test_query_genomic_filters_defaults_empty():
    from picsure import Query

    assert Query().genomicFilters == ()
