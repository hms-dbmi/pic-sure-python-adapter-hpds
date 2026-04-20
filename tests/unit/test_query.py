from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.query import Query


class TestQueryTypeAlias:
    def test_clause_is_valid_query(self):
        clause = Clause(
            keys=["\\path\\"],
            type=ClauseType.FILTER,
            categories=["Male"],
        )
        q: Query = clause
        assert q is clause

    def test_clause_group_is_valid_query(self):
        group = ClauseGroup(
            clauses=[
                Clause(keys=["\\p1\\"], type=ClauseType.FILTER, categories=["A"]),
                Clause(keys=["\\p2\\"], type=ClauseType.ANYRECORD),
            ],
            operator=GroupOperator.AND,
        )
        q: Query = group
        assert q is group

    def test_query_has_to_query_json(self):
        clause = Clause(keys=["\\path\\"], type=ClauseType.REQUIRE)
        q: Query = clause
        result = q.to_query_json()
        assert result["phenotypicFilterType"] == "REQUIRED"
        assert result["conceptPath"] == "\\path\\"
