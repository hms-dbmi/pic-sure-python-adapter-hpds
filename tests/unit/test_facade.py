import picsure


class TestPublicFacade:
    def test_connect_is_importable(self):
        assert callable(picsure.connect)

    def test_picsure_error_is_importable(self):
        assert issubclass(picsure.PicSureError, Exception)

    def test_session_is_importable(self):
        assert picsure.Session is not None

    def test_all_contains_expected_names(self):
        expected = {"connect", "PicSureError", "Session"}
        assert expected.issubset(set(picsure.__all__))

    def test_internal_modules_not_in_all(self):
        for name in picsure.__all__:
            assert not name.startswith("_")
