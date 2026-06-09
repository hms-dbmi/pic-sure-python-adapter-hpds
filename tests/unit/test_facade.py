import picsure


class TestPublicFacade:
    def test_connect_is_importable(self):
        assert callable(picsure.connect)

    def test_picsure_error_is_importable(self):
        assert issubclass(picsure.PicSureError, Exception)

    def test_picsure_error_subclasses_are_importable(self):
        assert issubclass(picsure.PicSureAuthError, picsure.PicSureError)
        assert issubclass(picsure.PicSureConnectionError, picsure.PicSureError)
        assert issubclass(picsure.PicSureQueryError, picsure.PicSureError)
        assert issubclass(picsure.PicSureValidationError, picsure.PicSureError)

    def test_all_contains_expected_names(self):
        expected = {
            "connect",
            "PicSureAuthError",
            "PicSureConnectionError",
            "PicSureError",
            "PicSureQueryError",
            "PicSureValidationError",
            "Platform",
            "Session",
            "FacetSet",
            "buildClause",
            "buildClauseGroup",
            "buildQuery",
            "PhenotypicFilterType",
            "GroupOperator",
            "Clause",
            "ClauseGroup",
            "Query",
            "QueryType",
        }
        assert expected.issubset(set(picsure.__all__))

    def test_internal_modules_not_in_all(self):
        for name in picsure.__all__:
            assert not name.startswith("_")

    def test_build_clause_is_callable(self):
        assert callable(picsure.buildClause)

    def test_build_clause_group_is_callable(self):
        assert callable(picsure.buildClauseGroup)

    def test_build_query_is_callable(self):
        assert callable(picsure.buildQuery)

    def test_query_type_re_exported_at_top_level(self):
        from picsure._models.query_type import QueryType as Internal

        assert picsure.QueryType is Internal

    def test_platform_is_importable(self):
        assert picsure.Platform.BDC_AUTHORIZED.url.startswith("https://")
        assert picsure.Platform.BDC_DEV_OPEN.requires_auth is False


def test_genomic_exports_present():
    import picsure

    for name in (
        "buildGenomicFilter",
        "GenomicFilter",
        "VariantFrequency",
        "Zygosity",
    ):
        assert hasattr(picsure, name), name
        assert name in picsure.__all__, name
