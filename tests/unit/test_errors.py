from picsure.errors import (
    PicSureError,
    PicSureAuthError,
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)


class TestErrorHierarchy:
    def test_base_error_is_exception(self):
        assert issubclass(PicSureError, Exception)

    def test_auth_error_is_picsure_error(self):
        assert issubclass(PicSureAuthError, PicSureError)

    def test_connection_error_is_picsure_error(self):
        assert issubclass(PicSureConnectionError, PicSureError)

    def test_query_error_is_picsure_error(self):
        assert issubclass(PicSureQueryError, PicSureError)

    def test_validation_error_is_picsure_error(self):
        assert issubclass(PicSureValidationError, PicSureError)

    def test_catch_all_subclasses_with_base(self):
        for cls in (
            PicSureAuthError,
            PicSureConnectionError,
            PicSureQueryError,
            PicSureValidationError,
        ):
            with_message = cls("something went wrong")
            try:
                raise with_message
            except PicSureError as exc:
                assert str(exc) == "something went wrong"

    def test_subclasses_are_distinct(self):
        classes = {
            PicSureAuthError,
            PicSureConnectionError,
            PicSureQueryError,
            PicSureValidationError,
        }
        assert len(classes) == 4

    def test_error_preserves_cause(self):
        original = ValueError("root cause")
        try:
            raise PicSureAuthError("token expired") from original
        except PicSureError as exc:
            assert exc.__cause__ is original
