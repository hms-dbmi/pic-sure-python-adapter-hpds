"""Message-level tests for the shared transport-to-public translator.

The strings asserted here are the product surface: they are what a
researcher reads when a call fails, so they are pinned exactly rather
than matched loosely.
"""

import pytest

from picsure._services._errors import (
    rate_limit_message,
    translate_transport_error,
)
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportConsentDeniedError,
    TransportConsentLookupError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportServerError,
    TransportTLSError,
    TransportValidationError,
)
from picsure.errors import (
    PicSureAuthenticationError,
    PicSureAuthError,
    PicSureAuthorizationError,
    PicSureConnectionError,
    PicSureConsentDeniedError,
    PicSureConsentLookupError,
    PicSureError,
    PicSureQueryError,
    PicSureServerError,
    PicSureTLSError,
    PicSureValidationError,
)

OPERATION = "the dictionary search"


class TestUnauthenticated:
    """401 — the token itself is the problem."""

    def test_401_raises_authentication_error(self):
        result = translate_transport_error(
            TransportAuthenticationError(401, "Token is invalid or expired"),
            operation=OPERATION,
        )
        assert type(result) is PicSureAuthenticationError

    def test_401_message_names_the_token_and_says_how_to_fix_it(self):
        result = translate_transport_error(
            TransportAuthenticationError(401, "Token is invalid or expired"),
            operation=OPERATION,
        )
        assert str(result) == (
            "Your PIC-SURE token was rejected on the dictionary search (HTTP 401). "
            "The token is missing, malformed, or expired — this is not a "
            "permissions problem and not a server outage. Copy a fresh token from "
            "the PIC-SURE user interface and pass it as picsure.connect(token=...)."
            " The server said: Token is invalid or expired"
        )

    def test_401_message_does_not_blame_availability(self):
        result = translate_transport_error(
            TransportAuthenticationError(401, "unauthorized"),
            operation=OPERATION,
        )
        assert "unavailable" not in str(result)
        assert "could not reach" not in str(result).lower()

    def test_401_truncates_a_long_server_body(self):
        result = translate_transport_error(
            TransportAuthenticationError(401, "x" * 500),
            operation=OPERATION,
        )
        assert str(result).endswith("The server said: " + "x" * 200)

    def test_401_with_an_empty_body_omits_the_server_quote(self):
        result = translate_transport_error(
            TransportAuthenticationError(401, ""), operation=OPERATION
        )
        assert "The server said" not in str(result)


class TestUnauthorized:
    """403 — the token is fine, the permission is not."""

    def test_403_raises_authorization_error(self):
        result = translate_transport_error(
            TransportAuthenticationError(403, "Forbidden"),
            operation=OPERATION,
        )
        assert type(result) is PicSureAuthorizationError

    def test_403_message_names_the_permission_not_the_token(self):
        result = translate_transport_error(
            TransportAuthenticationError(403, "Forbidden"),
            operation=OPERATION,
        )
        assert str(result) == (
            "PIC-SURE refused the dictionary search (HTTP 403): this account is "
            "not authorized for it. This is a permissions decision, not a server "
            "outage. Check that the account holds the privilege or study approval "
            "the request needs; if it should, the token may be stale or issued for "
            "a different environment, so try a fresh one. The server said: Forbidden"
        )

    def test_403_message_does_not_blame_availability(self):
        result = translate_transport_error(
            TransportAuthenticationError(403, "Forbidden"),
            operation=OPERATION,
        )
        assert "unavailable" not in str(result)

    def test_403_does_not_promise_the_token_is_valid(self):
        """PSAMA answers 403 for a stale token on /user/me/consents."""
        result = translate_transport_error(
            TransportAuthenticationError(403, "Forbidden"),
            operation=OPERATION,
        )
        message = str(result)
        assert "token is valid" not in message
        assert "the token may be stale" in message

    def test_403_with_an_empty_body_omits_the_server_quote(self):
        result = translate_transport_error(
            TransportAuthenticationError(403, ""), operation=OPERATION
        )
        assert "The server said" not in str(result)
        assert str(result).endswith("so try a fresh one.")


class TestConsentDenied:
    """403 + errorType consent_denied — a refinement of "not permitted"."""

    def _translate(self):
        return translate_transport_error(
            TransportConsentDeniedError(
                403,
                '{"errorType":"consent_denied","message":"Consent does not permit '
                'this query"}',
                "consent_denied",
                "Consent does not permit this query",
            ),
            operation=OPERATION,
        )

    def test_raises_consent_denied_error(self):
        assert type(self._translate()) is PicSureConsentDeniedError

    def test_message_separates_consent_from_token_validity(self):
        assert str(self._translate()) == (
            "Consent denied for the dictionary search (HTTP 403). This is a "
            "consent decision, not an outage: your approved consents do not cover "
            "the data this request touches. The server said: Consent does not "
            "permit this query"
        )

    def test_carries_the_server_payload(self):
        result = self._translate()
        assert result.status_code == 403
        assert result.error_type == "consent_denied"
        assert result.server_message == "Consent does not permit this query"


class TestConsentLookupFailed:
    """502 + errorType consent_lookup_failed — a server-side fault."""

    def _translate(self):
        return translate_transport_error(
            TransportConsentLookupError(
                502,
                '{"errorType":"consent_lookup_failed","message":"Unable to verify '
                "the caller's consents\"}",
                "consent_lookup_failed",
                "Unable to verify the caller's consents",
            ),
            operation=OPERATION,
        )

    def test_raises_consent_lookup_error(self):
        assert type(self._translate()) is PicSureConsentLookupError

    def test_message_blames_neither_the_token_nor_the_approvals(self):
        assert str(self._translate()) == (
            "The server could not resolve your consent permissions for the "
            "dictionary search (HTTP 502). This is a failure inside PIC-SURE, not "
            "a problem with your token or your approvals; try again shortly. The "
            "server said: Unable to verify the caller's consents"
        )

    def test_carries_the_server_payload(self):
        result = self._translate()
        assert result.status_code == 502
        assert result.error_type == "consent_lookup_failed"


class TestUnreachableServer:
    """Nothing came back — the third cause."""

    def test_connection_failure_raises_connection_error(self):
        result = translate_transport_error(
            TransportConnectionError("Connection refused"),
            operation=OPERATION,
        )
        assert type(result) is PicSureConnectionError
        assert str(result) == (
            "Could not reach the PIC-SURE server for the dictionary search. The "
            "server may be temporarily unavailable, or the network path to it is "
            "down. Details: Connection refused"
        )

    def test_certificate_failure_raises_tls_error_verbatim(self):
        message = (
            "TLS certificate verification failed for nhanes-dev.hms.harvard.edu: "
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed. Pass "
            "verify=False or set PICSURE_SSL_VERIFY."
        )
        result = translate_transport_error(
            TransportTLSError(message), operation=OPERATION
        )
        assert type(result) is PicSureTLSError
        assert str(result) == message

    def test_5xx_raises_server_error(self):
        result = translate_transport_error(
            TransportServerError(500, "Internal Server Error"),
            operation=OPERATION,
        )
        assert type(result) is PicSureServerError
        assert str(result) == (
            "The server failed to complete the dictionary search (HTTP 500) and "
            "may be temporarily unavailable. Try again shortly. The server said: "
            "Internal Server Error"
        )


class TestRemainingStatuses:
    def test_400_raises_validation_error(self):
        result = translate_transport_error(
            TransportValidationError(400, "Bad Request"), operation=OPERATION
        )
        assert type(result) is PicSureValidationError
        assert str(result) == (
            "The server rejected the dictionary search (HTTP 400). The server "
            "said: Bad Request"
        )

    def test_404_raises_query_error(self):
        result = translate_transport_error(
            TransportNotFoundError(404, "no such route"), operation=OPERATION
        )
        assert type(result) is PicSureQueryError
        assert str(result) == (
            "The endpoint for the dictionary search returned HTTP 404. The server "
            "said: no such route"
        )

    def test_429_names_the_operation_and_the_retry_delay(self):
        result = translate_transport_error(
            TransportRateLimitError(429, "slow down", retry_after=30),
            operation=OPERATION,
        )
        assert type(result) is PicSureConnectionError
        assert str(result) == (
            "Rate limited on the dictionary search; server said retry after 30 seconds."
        )

    def test_429_without_retry_after_still_advises_waiting(self):
        result = translate_transport_error(
            TransportRateLimitError(429, "slow down"), operation=OPERATION
        )
        assert str(result) == (
            "Rate limited on the dictionary search. Please wait and try again."
        )

    def test_unclassified_transport_error_falls_back_to_connection_error(self):
        from picsure._transport.errors import TransportError

        result = translate_transport_error(
            TransportError("something odd"), operation=OPERATION
        )
        assert type(result) is PicSureConnectionError


class TestRateLimitMessage:
    def test_suffix_is_appended_after_rate_limited(self):
        assert rate_limit_message(
            TransportRateLimitError(429, "", retry_after=5), suffix=" on the query"
        ) == ("Rate limited on the query; server said retry after 5 seconds.")

    def test_bare_message_when_no_suffix_and_no_retry_after(self):
        assert rate_limit_message(TransportRateLimitError(429, "")) == (
            "Rate limited. Please wait and try again."
        )


class TestGrammar:
    """The templates must read as sentences for every operation phrase."""

    OPERATIONS = [
        "the dictionary search",
        "the dictionary facets lookup",
        "the PSAMA consent lookup",
        "the query",
        "the saved-query load",
        "the genomic value lookup",
        "the PFB export download",
        "the saveQueryByName query submit",
    ]

    @pytest.mark.parametrize("operation", OPERATIONS)
    def test_operation_is_named_and_never_trails_a_bare_verb(self, operation):
        """The old template produced "Could not fetch consents PSAMA."."""
        errors = [
            TransportAuthenticationError(401, "body"),
            TransportAuthenticationError(403, "body"),
            TransportValidationError(400, "body"),
            TransportNotFoundError(404, "body"),
            TransportServerError(500, "body"),
            TransportConnectionError("refused"),
        ]
        for exc in errors:
            message = str(translate_transport_error(exc, operation=operation))
            assert operation in message
            assert "  " not in message
            assert (
                message.split(operation)[0]
                .rstrip()
                .endswith(("on", "for", "rejected", "refused", "complete"))
            )


class TestNoTokenLeakage:
    """A token must never reach a message, even if the server echoes one."""

    def test_translator_adds_nothing_but_the_server_body(self):
        token = "eyJhbGciOiJIUzI1NiJ9.super-secret-payload.signature"
        for exc in (
            TransportAuthenticationError(401, "rejected"),
            TransportAuthenticationError(403, "forbidden"),
            TransportServerError(500, "boom"),
            TransportConnectionError("refused"),
        ):
            assert token not in str(translate_transport_error(exc, operation=OPERATION))


class TestTranslatorReturnsPublicErrors:
    def test_every_branch_returns_a_picsure_error(self):
        errors = [
            TransportAuthenticationError(401, "b"),
            TransportAuthenticationError(403, "b"),
            TransportConsentDeniedError(403, "b", "consent_denied", "m"),
            TransportConsentLookupError(502, "b", "consent_lookup_failed", "m"),
            TransportValidationError(400, "b"),
            TransportNotFoundError(404, "b"),
            TransportRateLimitError(429, "b"),
            TransportServerError(500, "b"),
            TransportTLSError("bad cert"),
            TransportConnectionError("refused"),
        ]
        for exc in errors:
            assert isinstance(
                translate_transport_error(exc, operation=OPERATION), PicSureError
            )

    def test_both_refusal_statuses_are_catchable_as_auth_error(self):
        for status in (401, 403):
            result = translate_transport_error(
                TransportAuthenticationError(status, "b"), operation=OPERATION
            )
            assert isinstance(result, PicSureAuthError)
