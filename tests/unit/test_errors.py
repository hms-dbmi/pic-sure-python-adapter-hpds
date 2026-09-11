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


class _CertRejectingTransport:
    """An httpx transport that fails the way an untrusted certificate does.

    respx replaces a side-effect exception's ``__cause__`` with its own
    wrapper, which destroys the chain the adapter inspects, so the TLS
    path is driven through a real transport instead.
    """

    def __init__(self):
        self.call_count = 0

    def handle_request(self, request):
        import ssl

        import httpx

        self.call_count += 1
        try:
            raise ssl.SSLCertVerificationError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "self-signed certificate (_ssl.c:1017)"
            )
        except ssl.SSLCertVerificationError as cause:
            raise httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
                request=request,
            ) from cause


def _filter_clause():
    """A minimal phenotypic clause, so runQuery reaches the HTTP layer."""
    from picsure._models.clause import Clause, PhenotypicFilterType

    return Clause(
        keys=["\\phs1\\sex\\"],
        type=PhenotypicFilterType.FILTER,
        categories=["Male"],
    )


class TestHierarchyThroughRunQuery:
    """What each failure is catchable as, driven through a public method.

    ``Session.runQuery`` is used rather than constructing exceptions
    directly so the assertions cover the whole path: transport mapping,
    the shared translator, and the class hierarchy together.
    """

    BASE_URL = "https://test.example.com"

    def _session(self):
        import picsure
        from picsure._models.session import Session
        from picsure._transport.client import PicSureClient

        assert picsure  # the public package must import the new types
        return Session(
            client=PicSureClient(base_url=self.BASE_URL, token="test-token"),
            user_email="u@example.com",
            token_expiration="N/A",
            backend="auth",
        )

    def _query_url(self):
        from picsure._services._hpds_paths import query_prefix

        return f"{self.BASE_URL}{query_prefix('auth', v3=True)}/query/sync"

    def _run(self, response):
        import respx

        with respx.mock:
            respx.post(self._query_url()).mock(**response)
            return self._session().runQuery(_filter_clause(), type="count")

    def _raises(self, response):
        import pytest

        with pytest.raises(PicSureError) as exc_info:
            self._run(response)
        return exc_info.value

    def test_401_is_an_authentication_error_and_an_auth_error(self):
        import httpx

        from picsure.errors import PicSureAuthenticationError

        exc = self._raises(
            {"return_value": httpx.Response(401, text="Token is invalid or expired")}
        )
        assert isinstance(exc, PicSureAuthenticationError)
        assert isinstance(exc, PicSureAuthError)
        assert not isinstance(exc, PicSureConnectionError)
        assert "token" in str(exc).lower()
        assert "unavailable" not in str(exc)

    def test_403_is_an_authorization_error_and_an_auth_error(self):
        import httpx

        from picsure.errors import PicSureAuthenticationError, PicSureAuthorizationError

        exc = self._raises({"return_value": httpx.Response(403, text="Forbidden")})
        assert isinstance(exc, PicSureAuthorizationError)
        assert isinstance(exc, PicSureAuthError)
        assert not isinstance(exc, PicSureAuthenticationError)
        assert not isinstance(exc, PicSureConnectionError)

    def test_consent_denial_is_catchable_as_an_auth_error(self):
        import httpx

        from picsure.errors import (
            PicSureAuthorizationError,
            PicSureConsentDeniedError,
        )

        exc = self._raises(
            {
                "return_value": httpx.Response(
                    403,
                    json={
                        "errorType": "consent_denied",
                        "message": "Consent does not permit this query",
                    },
                )
            }
        )
        assert isinstance(exc, PicSureConsentDeniedError)
        assert isinstance(exc, PicSureAuthorizationError)
        assert isinstance(exc, PicSureAuthError)
        assert not isinstance(exc, PicSureConnectionError)

    def test_every_403_is_an_auth_error_with_or_without_a_structured_body(self):
        import httpx

        plain = self._raises({"return_value": httpx.Response(403, text="Forbidden")})
        structured = self._raises(
            {
                "return_value": httpx.Response(
                    403,
                    json={"errorType": "consent_denied", "message": "no consent"},
                )
            }
        )
        assert isinstance(plain, PicSureAuthError)
        assert isinstance(structured, PicSureAuthError)

    def test_consent_lookup_failure_is_a_server_error_not_an_auth_error(self):
        import httpx

        from picsure.errors import PicSureConsentLookupError, PicSureServerError

        exc = self._raises(
            {
                "return_value": httpx.Response(
                    502,
                    json={
                        "errorType": "consent_lookup_failed",
                        "message": "Unable to verify the caller's consents",
                    },
                )
            }
        )
        assert isinstance(exc, PicSureConsentLookupError)
        assert isinstance(exc, PicSureServerError)
        assert isinstance(exc, PicSureConnectionError)
        assert not isinstance(exc, PicSureAuthError)

    def test_plain_5xx_is_a_server_error(self):
        import httpx

        from picsure.errors import PicSureServerError

        exc = self._raises({"return_value": httpx.Response(500, text="boom")})
        assert isinstance(exc, PicSureServerError)
        assert isinstance(exc, PicSureConnectionError)
        assert not isinstance(exc, PicSureAuthError)

    def test_unreachable_server_is_a_plain_connection_error(self):
        import httpx

        from picsure.errors import PicSureServerError, PicSureTLSError

        exc = self._raises({"side_effect": httpx.ConnectError("Connection refused")})
        assert isinstance(exc, PicSureConnectionError)
        assert not isinstance(exc, PicSureTLSError)
        assert not isinstance(exc, PicSureServerError)
        assert not isinstance(exc, PicSureAuthError)

    def _session_behind_a_bad_certificate(self, transport):
        import httpx

        from picsure._models.session import Session
        from picsure._transport.client import PicSureClient

        client = PicSureClient(base_url=self.BASE_URL, token="test-token")
        client._http = httpx.Client(base_url=self.BASE_URL, transport=transport)
        return Session(
            client=client,
            user_email="u@example.com",
            token_expiration="N/A",
            backend="auth",
        )

    def test_rejected_certificate_is_a_tls_error(self):
        import pytest

        from picsure.errors import PicSureTLSError

        session = self._session_behind_a_bad_certificate(_CertRejectingTransport())
        with pytest.raises(PicSureError) as exc_info:
            session.runQuery(_filter_clause(), type="count")

        exc = exc_info.value
        assert isinstance(exc, PicSureTLSError)
        assert isinstance(exc, PicSureConnectionError)
        assert not isinstance(exc, PicSureAuthError)
        message = str(exc)
        assert "TLS certificate verification failed" in message
        assert "test.example.com" in message
        assert "verify=False" in message
        assert "PICSURE_SSL_VERIFY" in message
        assert "temporarily unavailable" not in message

    def test_rejected_certificate_is_not_retried(self):
        import pytest

        transport = _CertRejectingTransport()
        session = self._session_behind_a_bad_certificate(transport)
        with pytest.raises(PicSureConnectionError):
            session.runQuery(_filter_clause(), type="count")
        assert transport.call_count == 1


class TestHierarchyShape:
    def test_consent_errors_sit_in_the_branch_that_matches_their_cause(self):
        from picsure.errors import (
            PicSureAuthorizationError,
            PicSureConsentDeniedError,
            PicSureConsentLookupError,
            PicSureServerError,
        )

        assert issubclass(PicSureConsentDeniedError, PicSureAuthorizationError)
        assert issubclass(PicSureConsentDeniedError, PicSureAuthError)
        assert not issubclass(PicSureConsentDeniedError, PicSureConnectionError)
        assert issubclass(PicSureConsentLookupError, PicSureServerError)
        assert not issubclass(PicSureConsentLookupError, PicSureAuthError)

    def test_new_types_are_exported_from_the_package(self):
        import picsure

        for name in (
            "PicSureAuthenticationError",
            "PicSureAuthorizationError",
            "PicSureServerError",
            "PicSureTLSError",
        ):
            assert name in picsure.__all__
            assert getattr(picsure, name).__name__ == name
