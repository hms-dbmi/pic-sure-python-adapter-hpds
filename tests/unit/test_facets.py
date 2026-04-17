import pytest

from picsure._models.facet import Facet, FacetCategory, FacetSet
from picsure.errors import PicSureValidationError


class TestFacet:
    def test_from_dict_new_shape(self):
        data = {
            "name": "phs000007",
            "display": "FHS (phs000007)",
            "description": "Framingham Cohort",
            "count": 54984,
        }
        facet = Facet.from_dict(data)
        assert facet.value == "phs000007"
        assert facet.display == "FHS (phs000007)"
        assert facet.description == "Framingham Cohort"
        assert facet.count == 54984

    def test_from_dict_legacy_value_key(self):
        data = {"value": "phs000007", "count": 42}
        facet = Facet.from_dict(data)
        assert facet.value == "phs000007"
        assert facet.count == 42
        assert facet.display == ""

    def test_frozen(self):
        facet = Facet(value="test", count=10)
        with pytest.raises(AttributeError):
            facet.value = "changed"  # type: ignore[misc]


class TestFacetCategory:
    def test_from_dict_new_shape(self):
        data = {
            "name": "dataset_id",
            "display": "Dataset",
            "description": "First node of concept path",
            "facets": [
                {"name": "phs000007", "display": "FHS (phs000007)", "count": 42},
                {"name": "phs000179", "display": "COPDGene (phs000179)", "count": 15},
            ],
        }
        cat = FacetCategory.from_dict(data)
        assert cat.name == "dataset_id"
        assert cat.display == "Dataset"
        assert cat.description == "First node of concept path"
        assert len(cat.options) == 2
        assert cat.options[0].value == "phs000007"
        assert cat.options[0].display == "FHS (phs000007)"
        assert cat.options[1].count == 15

    def test_from_dict_legacy_shape(self):
        data = {
            "name": "study_ids",
            "display": "Study",
            "categories": [
                {"value": "phs000007", "count": 42},
                {"value": "phs000179", "count": 15},
            ],
        }
        cat = FacetCategory.from_dict(data)
        assert cat.options[0].value == "phs000007"
        assert cat.options[1].count == 15

    def test_from_dict_empty_options(self):
        data = {"name": "empty", "display": "Empty", "facets": []}
        cat = FacetCategory.from_dict(data)
        assert cat.options == []

    def test_from_dict_list_from_fixture(self, facets_response):
        cats = [FacetCategory.from_dict(f) for f in facets_response]
        assert len(cats) == 3
        names = [c.name for c in cats]
        assert names == ["dataset_id", "data_type", "Consortium_Curated_Facets"]

    def test_from_dict_parses_children(self, facets_response):
        cats = [FacetCategory.from_dict(f) for f in facets_response]
        curated = cats[2]
        parent = curated.options[0]
        assert parent.value == "RECOVER Adult Curated"
        assert len(parent.children) == 2
        assert parent.children[0].value == "Infected"
        assert parent.children[0].count == 84173
        assert parent.children[1].value == "Non-infected"

    def test_frozen(self):
        cat = FacetCategory(name="test", display="Test", options=[])
        with pytest.raises(AttributeError):
            cat.name = "changed"  # type: ignore[misc]


class TestFacetSet:
    def _make_facet_set(self) -> FacetSet:
        categories = [
            FacetCategory(
                name="study_ids",
                display="Study",
                options=[
                    Facet(value="phs000007", count=42),
                    Facet(value="phs000179", count=15),
                ],
            ),
            FacetCategory(
                name="data_type",
                display="Data Type",
                options=[
                    Facet(value="categorical", count=30),
                    Facet(value="continuous", count=27),
                ],
            ),
        ]
        return FacetSet(categories)

    def test_view_empty_on_creation(self):
        fs = self._make_facet_set()
        view = fs.view()
        assert view == {"study_ids": [], "data_type": []}

    def test_add_single_value(self):
        fs = self._make_facet_set()
        fs.add("study_ids", "phs000007")
        view = fs.view()
        assert view["study_ids"] == ["phs000007"]
        assert view["data_type"] == []

    def test_add_list_of_values(self):
        fs = self._make_facet_set()
        fs.add("study_ids", ["phs000007", "phs000179"])
        assert fs.view()["study_ids"] == ["phs000007", "phs000179"]

    def test_add_multiple_calls_accumulate(self):
        fs = self._make_facet_set()
        fs.add("study_ids", "phs000007")
        fs.add("study_ids", "phs000179")
        assert fs.view()["study_ids"] == ["phs000007", "phs000179"]

    def test_add_invalid_category_raises(self):
        fs = self._make_facet_set()
        with pytest.raises(PicSureValidationError, match="not a valid facet category"):
            fs.add("nonexistent", "value")

    def test_add_invalid_category_lists_valid(self):
        fs = self._make_facet_set()
        with pytest.raises(PicSureValidationError, match="study_ids"):
            fs.add("nonexistent", "value")

    def test_to_request_facets_empty(self):
        fs = self._make_facet_set()
        assert fs.to_request_facets() == []

    def test_to_request_facets_with_selections(self):
        fs = self._make_facet_set()
        fs.add("study_ids", "phs000007")
        fs.add("data_type", "categorical")
        result = fs.to_request_facets()
        assert len(result) == 2
        categories = {r["category"] for r in result}
        assert categories == {"study_ids", "data_type"}
        study_facet = next(r for r in result if r["category"] == "study_ids")
        assert study_facet["name"] == "phs000007"
        assert study_facet["count"] == 42
        assert study_facet["categoryRef"] == {
            "name": "study_ids",
            "display": "Study",
            "description": "",
        }
        assert study_facet["children"] == []
        assert study_facet["fullName"] is None
        assert study_facet["meta"] is None

    def test_to_request_facets_multiple_values_same_category(self):
        fs = self._make_facet_set()
        fs.add("study_ids", ["phs000007", "phs000179"])
        result = fs.to_request_facets()
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"phs000007", "phs000179"}
        for entry in result:
            assert entry["category"] == "study_ids"
            assert entry["categoryRef"]["name"] == "study_ids"

    def test_to_request_facets_unknown_value_falls_back(self):
        fs = self._make_facet_set()
        # Skip validation by reaching into internal state so we can
        # exercise the "not in catalog" branch.
        fs._selected["study_ids"] = ["phs999999"]
        result = fs.to_request_facets()
        assert result[0]["name"] == "phs999999"
        assert result[0]["display"] == "phs999999"
        assert result[0]["count"] == 0

    def test_parses_arbitrarily_deep_tree(self):
        """A tree far deeper than Python's default recursion limit must parse."""
        import sys

        depth = sys.getrecursionlimit() * 3  # ~3000 by default
        leaf: dict[str, object] = {"name": f"lvl{depth}", "count": 0, "children": []}
        node = leaf
        for lvl in range(depth - 1, -1, -1):
            node = {"name": f"lvl{lvl}", "count": 0, "children": [node]}

        root = Facet.from_dict(node)

        # Walk iteratively to verify structure integrity at every level.
        cur: Facet | None = root
        seen = 0
        while cur is not None:
            assert cur.value == f"lvl{seen}"
            cur = cur.children[0] if cur.children else None
            seen += 1
        assert seen == depth + 1  # one node per level

    def test_to_request_facets_finds_nested_child(self):
        # Build a FacetSet with a hierarchical category.
        parent = Facet(
            value="RECOVER Adult Curated",
            count=142749,
            display="RECOVER Adult Curated",
            children=[
                Facet(value="Infected", count=84173, display="Infected"),
                Facet(value="Non-infected", count=58320, display="Non-infected"),
            ],
        )
        fs = FacetSet(
            [
                FacetCategory(
                    name="Consortium_Curated_Facets",
                    display="Consortium Curated Facets",
                    options=[parent],
                )
            ]
        )
        fs.add("Consortium_Curated_Facets", "Infected")
        result = fs.to_request_facets()
        assert result[0]["name"] == "Infected"
        assert result[0]["count"] == 84173
        assert result[0]["display"] == "Infected"

    def test_clear(self):
        fs = self._make_facet_set()
        fs.add("study_ids", "phs000007")
        fs.clear()
        assert fs.view() == {"study_ids": [], "data_type": []}

    def test_clear_category(self):
        fs = self._make_facet_set()
        fs.add("study_ids", "phs000007")
        fs.add("data_type", "categorical")
        fs.clear("study_ids")
        assert fs.view()["study_ids"] == []
        assert fs.view()["data_type"] == ["categorical"]

    def test_clear_invalid_category_raises(self):
        fs = self._make_facet_set()
        with pytest.raises(PicSureValidationError, match="not a valid facet category"):
            fs.clear("nonexistent")
