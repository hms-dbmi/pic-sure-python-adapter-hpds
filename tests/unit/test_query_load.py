import pytest

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._services.query_load import _parse_phenotypic
from picsure.errors import PicSureQueryError, PicSureValidationError


class TestParsePhenotypicLeaf:
    def test_filter_leaf_with_categories(self):
        node = {
            "phenotypicFilterType": "FILTER",
            "conceptPath": "\\phs1\\sex\\",
            "values": ["Male"],
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.keys == ["\\phs1\\sex\\"]
        assert result.type == ClauseType.FILTER
        assert result.categories == ["Male"]
        assert result.min is None
        assert result.max is None

    def test_filter_leaf_with_min_and_max(self):
        node = {
            "phenotypicFilterType": "FILTER",
            "conceptPath": "\\phs1\\age\\",
            "min": 40.0,
            "max": 65.5,
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.type == ClauseType.FILTER
        assert result.min == 40.0
        assert result.max == 65.5
        assert result.categories is None

    def test_filter_leaf_with_min_only(self):
        node = {
            "phenotypicFilterType": "FILTER",
            "conceptPath": "\\phs1\\age\\",
            "min": 40.0,
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.min == 40.0
        assert result.max is None

    def test_required_leaf(self):
        node = {
            "phenotypicFilterType": "REQUIRED",
            "conceptPath": "\\phs1\\bmi\\",
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.type == ClauseType.REQUIRE
        assert result.keys == ["\\phs1\\bmi\\"]

    def test_any_record_of_leaf(self):
        node = {
            "phenotypicFilterType": "ANY_RECORD_OF",
            "conceptPath": "\\phs1\\meds\\",
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, Clause)
        assert result.type == ClauseType.ANYRECORD

    def test_unknown_filter_type_raises(self):
        node = {
            "phenotypicFilterType": "MYSTERY",
            "conceptPath": "\\phs1\\x\\",
            "not": False,
        }
        with pytest.raises(PicSureQueryError, match="MYSTERY"):
            _parse_phenotypic(node)

    def test_leaf_with_not_true_raises(self):
        node = {
            "phenotypicFilterType": "FILTER",
            "conceptPath": "\\phs1\\sex\\",
            "values": ["Male"],
            "not": True,
        }
        with pytest.raises(PicSureValidationError, match="NOT"):
            _parse_phenotypic(node)

    def test_leaf_missing_concept_path_raises(self):
        node = {"phenotypicFilterType": "REQUIRED", "not": False}
        with pytest.raises(PicSureQueryError, match="conceptPath"):
            _parse_phenotypic(node)


class TestParsePhenotypicSubquery:
    def _filter(self, path: str, val: str) -> dict:  # type: ignore[type-arg]
        return {
            "phenotypicFilterType": "FILTER",
            "conceptPath": path,
            "values": [val],
            "not": False,
        }

    def test_and_subquery(self):
        node = {
            "operator": "AND",
            "phenotypicClauses": [
                self._filter("\\phs1\\sex\\", "Male"),
                self._filter("\\phs1\\copd\\", "Yes"),
            ],
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, ClauseGroup)
        assert result.operator == GroupOperator.AND
        assert len(result.clauses) == 2
        assert all(isinstance(c, Clause) for c in result.clauses)

    def test_or_subquery(self):
        node = {
            "operator": "OR",
            "phenotypicClauses": [
                self._filter("\\phs1\\copd\\", "Yes"),
                self._filter("\\phs1\\asthma\\", "Yes"),
            ],
            "not": False,
        }
        result = _parse_phenotypic(node)
        assert isinstance(result, ClauseGroup)
        assert result.operator == GroupOperator.OR

    def test_nested_subquery(self):
        inner = {
            "operator": "OR",
            "phenotypicClauses": [
                self._filter("\\phs1\\copd\\", "Yes"),
                self._filter("\\phs1\\asthma\\", "Yes"),
            ],
            "not": False,
        }
        outer = {
            "operator": "AND",
            "phenotypicClauses": [self._filter("\\phs1\\sex\\", "Male"), inner],
            "not": False,
        }
        result = _parse_phenotypic(outer)
        assert isinstance(result, ClauseGroup)
        assert result.operator == GroupOperator.AND
        nested = result.clauses[1]
        assert isinstance(nested, ClauseGroup)
        assert nested.operator == GroupOperator.OR

    def test_subquery_with_not_true_raises(self):
        node = {
            "operator": "AND",
            "phenotypicClauses": [self._filter("\\phs1\\sex\\", "Male")],
            "not": True,
        }
        with pytest.raises(PicSureValidationError, match="NOT"):
            _parse_phenotypic(node)

    def test_unknown_operator_raises(self):
        node = {
            "operator": "XOR",
            "phenotypicClauses": [self._filter("\\phs1\\sex\\", "Male")],
            "not": False,
        }
        with pytest.raises(PicSureQueryError, match="XOR"):
            _parse_phenotypic(node)

    def test_subquery_missing_clauses_raises(self):
        node = {"operator": "AND", "not": False}
        with pytest.raises(PicSureQueryError, match="phenotypicClauses"):
            _parse_phenotypic(node)

    def test_unknown_node_shape_raises(self):
        node = {"foo": "bar"}
        with pytest.raises(PicSureQueryError):
            _parse_phenotypic(node)
