from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureError,
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


class TestTransportErrors:
    def test_transport_validation_error_round_trip(self):
        from picsure._transport.errors import (
            TransportError,
            TransportValidationError,
        )

        exc = TransportValidationError(400, "Bad Request body")
        assert isinstance(exc, TransportError)
        assert exc.status_code == 400
        assert exc.body == "Bad Request body"
        assert "400" in str(exc)
        assert "Bad Request body" in str(exc)

    def test_transport_not_found_error_round_trip(self):
        from picsure._transport.errors import (
            TransportError,
            TransportNotFoundError,
        )

        exc = TransportNotFoundError(404, "Resource missing")
        assert isinstance(exc, TransportError)
        assert exc.status_code == 404
        assert exc.body == "Resource missing"
        assert "404" in str(exc)

    def test_transport_rate_limit_error_round_trip(self):
        from picsure._transport.errors import (
            TransportError,
            TransportRateLimitError,
        )

        exc = TransportRateLimitError(429, "Too many requests", retry_after=30)
        assert isinstance(exc, TransportError)
        assert exc.status_code == 429
        assert exc.body == "Too many requests"
        assert exc.retry_after == 30
        assert "429" in str(exc)

    def test_transport_rate_limit_error_retry_after_optional(self):
        from picsure._transport.errors import TransportRateLimitError

        exc = TransportRateLimitError(429, "slow down", retry_after=None)
        assert exc.retry_after is None
