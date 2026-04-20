import pandas as pd

import picsure
from picsure._models.facet import FacetSet


class TestSearchLive:
    def test_search_returns_dataframe(
        self, test_token, test_platform, test_search_term
    ):
        session = picsure.connect(platform=test_platform, token=test_token)
        df = session.search(test_search_term)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "conceptPath" in df.columns

    def test_search_empty_term_returns_results(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        df = session.search()
        assert isinstance(df, pd.DataFrame)

    def test_search_no_match_returns_empty(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        df = session.search("zzz_definitely_no_match_xyz_12345")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_facets_returns_facet_set(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        fs = session.facets()
        assert isinstance(fs, FacetSet)
        view = fs.view()
        assert len(view) > 0

    def test_show_all_facets_returns_dataframe(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        df = session.showAllFacets()
        assert isinstance(df, pd.DataFrame)
        assert "category" in df.columns
        assert "value" in df.columns

    def test_search_with_facets(self, test_token, test_platform, test_search_term):
        session = picsure.connect(platform=test_platform, token=test_token)
        fs = session.facets()
        categories = list(fs.view().keys())
        if categories:
            first_cat = categories[0]
            first_values = fs.view()[first_cat][:1]
            fs.add(first_cat, first_values if first_values else [])
            df = session.search(test_search_term, facets=fs)
            assert isinstance(df, pd.DataFrame)

    def test_search_include_values_false(
        self, test_token, test_platform, test_search_term
    ):
        session = picsure.connect(platform=test_platform, token=test_token)
        df = session.search(test_search_term, include_values=False)
        assert isinstance(df, pd.DataFrame)
        assert "values" not in df.columns
