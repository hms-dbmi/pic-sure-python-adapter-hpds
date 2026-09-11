import base64
import json
import ssl
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from picsure._models.session import Session
from picsure._services.connect import (
    _VALIDATION_PATH,
    _token_expiration_from_jwt,
    connect,
)
from picsure._services.consents import _CONSENTS_KEY, _CONSENTS_PATH
from picsure._transport.client import (
    DATA_TIMEOUT_SECONDS,
    VALIDATION_TIMEOUT_SECONDS,
)
from picsure.errors import (
    PicSureAuthenticationError,
    PicSureAuthError,
    PicSureConnectionError,
    PicSureTLSError,
    PicSureValidationError,
)


def _b64(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()


def _make_jwt(exp: int | float | None) -> str:
    """Build an unsigned JWT with the given exp claim (epoch seconds)."""
    body: dict = {"sub": "test-user"}
    if exp is not None:
        body["exp"] = exp
    return _make_jwt_claims(**body)


def _make_jwt_claims(**claims: object) -> str:
    """Build an unsigned JWT carrying the given payload claims."""
    header = _b64({"alg": "none", "typ": "JWT"})
    return f"{header}.{_b64(dict(claims))}.sig"


def _epoch_in(**delta: float) -> int:
    """An epoch-second value offset from now, so tests never go stale.

    The previous fixed expiry (2026-06-15) silently became a past date,
    which is the defect PL-04 describes -- a test suite pinned to a
    calendar date reproduces it.
    """
    return int((datetime.now(timezone.utc) + timedelta(**delta)).timestamp())


BASE_URL = "https://test.example.com"
_JWT_EXP = _epoch_in(days=30)
# The connect banner reads the email from the token when the server sends
# none, so the default test token carries the email the tests assert on.
TOKEN = _make_jwt_claims(
    sub="test-user", email="researcher@university.edu", exp=_JWT_EXP
)
EXPECTED_EXPIRY = datetime.fromtimestamp(_JWT_EXP, tz=timezone.utc).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)

# What PSAMA's /user/me answers with. The real record also carries a
# `token` field, which the adapter must never surface; it is included
# here so a test would catch it leaking into the banner.
USER_RECORD = {
    "uuid": "e23d9260-3324-4528-8c2c-7bd3dcb4aa74",
    "email": "researcher@university.edu",
    "privileges": ["API_ACCESS", "PIC_SURE_ANY_QUERY"],
    "token": "server-echoed-token-value",
    "acceptedTOS": True,
}

_CONSENT_PAYLOAD = {"consents": {_CONSENTS_KEY: ["phs000007.c1", "phs001013.c1"]}}


def _mock_validation(
    base_url: str = BASE_URL,
    *,
    status: int = 200,
    payload: object = None,
    **kwargs: object,
) -> respx.Route:
    """Mock the one request connect() makes to validate the connection."""
    if kwargs:
        return respx.get(f"{base_url}{_VALIDATION_PATH}").mock(**kwargs)
    body = USER_RECORD if payload is None else payload
    return respx.get(f"{base_url}{_VALIDATION_PATH}").mock(
        return_value=httpx.Response(status, json=body)
    )


def _mock_connect(base_url: str = BASE_URL, **kwargs: object) -> respx.Route:
    """Mock every request a default authorized connect makes.

    That is the validation call plus the consent-detection probe: a
    custom URL with a token and no stated consent preference probes for
    consent scoping, so a test that mocks only the first request fails on
    the second.
    """
    route = _mock_validation(base_url, **kwargs)
    _mock_consents(base_url, payload={"consents": {}})
    return route


def _mock_consents(base_url: str = BASE_URL, *, payload: object = None) -> respx.Route:
    body = _CONSENT_PAYLOAD if payload is None else payload
    return respx.get(f"{base_url}{_CONSENTS_PATH}").mock(
        return_value=httpx.Response(200, json=body)
    )


class _CertRejectingTransport(httpx.BaseTransport):
    """A transport that fails the way an untrusted certificate really does.

    respx overwrites a side-effect exception's ``__cause__`` with its own
    wrapper, which destroys the chain the adapter walks to recognise a
    certificate failure. Driving a real httpx transport keeps the chain
    intact.
    """

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            raise ssl.SSLCertVerificationError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "self signed certificate"
            )
        except ssl.SSLCertVerificationError as cause:
            raise httpx.ConnectError(
                "certificate verify failed", request=request
            ) from cause


@pytest.fixture
def cert_rejecting_transport(monkeypatch):
    """Make every httpx.Client connect#'s certificate check fail."""
    real_init = httpx.Client.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = _CertRejectingTransport()
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched)


@pytest.fixture
def httpx_client_spy(monkeypatch):
    """Record the kwargs every httpx.Client built during a connect received."""
    seen: list[dict] = []
    real_init = httpx.Client.__init__

    def patched(self, *args, **kwargs):
        seen.append(dict(kwargs))
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched)
    return seen


class TestConnectSuccess:
    @respx.mock
    def test_returns_session(self):
        _mock_connect()
        session = connect(platform=BASE_URL, token=TOKEN)
        assert isinstance(session, Session)

    @respx.mock
    def test_session_has_correct_email(self):
        _mock_connect()
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session.user_email == "researcher@university.edu"

    @respx.mock
    def test_prints_success_message(self, capsys):
        _mock_connect()
        connect(platform=BASE_URL, token=TOKEN)
        captured = capsys.readouterr()
        assert "successfully connected" in captured.out.lower()
        assert "researcher@university.edu" in captured.out

    @respx.mock
    def test_prints_token_expiration(self, capsys):
        _mock_connect()
        connect(platform=BASE_URL, token=TOKEN)
        captured = capsys.readouterr()
        assert "token expires" in captured.out.lower()
        assert EXPECTED_EXPIRY in captured.out

    @respx.mock
    def test_never_prints_the_server_echoed_token(self, capsys):
        _mock_connect()
        connect(platform=BASE_URL, token=TOKEN)
        captured = capsys.readouterr()
        assert "server-echoed-token-value" not in captured.out + captured.err


class TestConnectValidatesTheConnection:
    """RL-3: one real request on connect, on every platform."""

    @respx.mock
    def test_authorized_connect_calls_psama_user_me(self):
        route = _mock_connect()
        connect(platform=BASE_URL, token=TOKEN)
        assert route.called
        assert respx.calls[0].request.url.path == _VALIDATION_PATH

    @respx.mock
    def test_validation_is_not_gated_on_consents(self):
        # The old connect() sent a request only when include_consents was
        # on; the default custom-URL path sent nothing at all.
        route = _mock_validation()
        connect(platform=BASE_URL, token=TOKEN, include_consents=False)
        assert route.called

    @respx.mock
    def test_open_platform_also_sends_a_request(self):
        from picsure._transport.platforms import Platform

        route = _mock_validation(Platform.BDC_DEV_OPEN.url)
        connect(platform=Platform.BDC_DEV_OPEN)
        assert route.called

    @respx.mock
    def test_unresolvable_host_raises_connection_error(self):
        _mock_validation(
            side_effect=httpx.ConnectError("[Errno 8] nodename nor servname provided")
        )
        with pytest.raises(PicSureConnectionError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)
        assert "Could not reach the PIC-SURE server" in str(exc_info.value)

    @respx.mock
    def test_unresolvable_host_fails_open_platforms_too(self):
        from picsure._transport.platforms import Platform

        _mock_validation(
            Platform.BDC_DEV_OPEN.url,
            side_effect=httpx.ConnectError("nodename nor servname provided"),
        )
        with pytest.raises(PicSureConnectionError):
            connect(platform=Platform.BDC_DEV_OPEN)

    @respx.mock
    def test_401_raises_an_authentication_error(self):
        _mock_validation(status=401, payload={"errorType": "unauthorized"})
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)
        assert "token was rejected" in str(exc_info.value)

    @respx.mock
    def test_403_raises_an_auth_error(self):
        # PSAMA answers 403, not 401, to /user/me with a token it will not
        # accept, so the refusal has to land in the auth family either way.
        _mock_validation(status=403, payload={})
        with pytest.raises(PicSureAuthError):
            connect(platform=BASE_URL, token=TOKEN)

    @respx.mock
    def test_403_does_not_fail_an_open_connection(self):
        # PSAMA refuses an unauthenticated /user/me. That refusal is
        # itself proof the host exists and speaks PIC-SURE, which is all
        # an anonymous connection can verify.
        from picsure._transport.platforms import Platform

        _mock_validation(Platform.BDC_DEV_OPEN.url, status=403, payload={})
        session = connect(platform=Platform.BDC_DEV_OPEN)
        assert session.user_email == "anonymous"

    @respx.mock
    def test_2xx_with_unexpected_payload_names_the_url(self):
        _mock_validation(payload={"greeting": "hello"})
        with pytest.raises(PicSureConnectionError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)
        message = str(exc_info.value)
        assert "may not be a PIC-SURE endpoint" in message
        assert BASE_URL in message

    @respx.mock
    def test_2xx_with_non_json_body_names_the_url(self):
        respx.get(f"{BASE_URL}{_VALIDATION_PATH}").mock(
            return_value=httpx.Response(200, text="<html>login page</html>")
        )
        with pytest.raises(PicSureConnectionError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)
        assert "may not be a PIC-SURE endpoint" in str(exc_info.value)

    @respx.mock
    def test_2xx_with_a_json_list_names_the_url(self):
        _mock_validation(payload=[{"uuid": "not-a-record"}])
        with pytest.raises(PicSureConnectionError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)
        assert "may not be a PIC-SURE endpoint" in str(exc_info.value)

    @respx.mock
    def test_server_email_wins_over_the_token_claim(self):
        _mock_connect(payload={"uuid": "u-1", "email": "server-truth@university.edu"})
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session.user_email == "server-truth@university.edu"

    @respx.mock
    def test_falls_back_to_the_token_claim_when_the_server_sends_no_email(self):
        _mock_connect(payload={"uuid": "u-1", "privileges": []})
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session.user_email == "researcher@university.edu"

    def test_rejected_certificate_raises_a_tls_error(self, cert_rejecting_transport):
        with pytest.raises(PicSureTLSError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)
        message = str(exc_info.value)
        assert "TLS certificate verification failed" in message
        assert "test.example.com" in message


class TestConnectValidateOptOut:
    """RL-3: skipping validation must be the caller's stated choice."""

    @respx.mock
    def test_validate_false_sends_nothing(self):
        connect(platform=BASE_URL, token=TOKEN, validate=False)
        assert len(respx.calls) == 0

    @respx.mock
    def test_validate_false_still_returns_a_session(self):
        session = connect(platform=BASE_URL, token=TOKEN, validate=False)
        assert isinstance(session, Session)
        assert session.user_email == "researcher@university.edu"

    @respx.mock
    def test_validate_false_skips_the_local_token_checks(self):
        # Offline and mocked use passes placeholder tokens; the opt-out
        # has to cover those too or it is not usable.
        session = connect(platform=BASE_URL, token="placeholder", validate=False)
        assert isinstance(session, Session)

    @respx.mock
    def test_validation_is_on_by_default(self):
        route = _mock_connect()
        connect(platform=BASE_URL, token=TOKEN)
        assert route.called


class TestConnectHonoursVerify:
    """RL-3: validating against a certificate we would not trust proves nothing."""

    @respx.mock
    def test_verify_false_reaches_the_client_that_validates(self, httpx_client_spy):
        _mock_connect()
        session = connect(platform=BASE_URL, token=TOKEN, verify=False)

        # Exactly one httpx client is built, so the validating request
        # cannot have gone through a second, default-verifying one.
        assert len(httpx_client_spy) == 1
        assert httpx_client_spy[0]["verify"] is False
        context = session._client._http._transport._pool._ssl_context
        assert context.verify_mode is ssl.CERT_NONE

    @respx.mock
    def test_verify_default_leaves_verification_on(self, httpx_client_spy):
        _mock_connect()
        session = connect(platform=BASE_URL, token=TOKEN)

        assert httpx_client_spy[0]["verify"] is True
        context = session._client._http._transport._pool._ssl_context
        assert context.verify_mode is ssl.CERT_REQUIRED


class TestConnectLocalTokenChecks:
    """RL-3: refuse a token that cannot work before spending a round trip."""

    @respx.mock
    def test_non_jwt_token_raises_before_any_request(self):
        _mock_validation()
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            connect(platform=BASE_URL, token="not-a-jwt")
        assert "three non-empty dot-separated segments" in str(exc_info.value)
        assert len(respx.calls) == 0

    @respx.mock
    def test_two_segment_token_raises(self):
        with pytest.raises(PicSureAuthenticationError):
            connect(platform=BASE_URL, token="header.payload")

    @respx.mock
    def test_empty_segment_token_raises(self):
        with pytest.raises(PicSureAuthenticationError):
            connect(platform=BASE_URL, token="header..signature")

    @respx.mock
    def test_undecodable_payload_raises(self):
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            connect(platform=BASE_URL, token="header.@@@not-base64@@@.signature")
        assert "base64url" in str(exc_info.value)
        assert len(respx.calls) == 0

    @respx.mock
    def test_message_tells_the_user_where_to_get_a_token(self):
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            connect(platform=BASE_URL, token="not-a-jwt")
        assert "PIC-SURE user interface" in str(exc_info.value)

    @respx.mock
    def test_a_token_without_an_exp_claim_is_accepted(self):
        # Unreadable expiry is not the same as expired; the server is the
        # verdict, and it accepted this one.
        _mock_connect()
        session = connect(platform=BASE_URL, token=_make_jwt(None))
        assert session.token_expiration == "unknown"

    @respx.mock
    def test_claims_are_never_treated_as_authorization(self):
        # A token whose claims look fine is still refused when the server
        # refuses it.
        _mock_validation(status=401, payload={})
        with pytest.raises(PicSureAuthError):
            connect(platform=BASE_URL, token=TOKEN)


class TestConnectTokenExpiry:
    """PL-04: never print a past expiry date under a success banner."""

    @respx.mock
    def test_expired_token_raises_naming_the_expiry(self):
        _mock_validation()
        expired = _make_jwt_claims(sub="u", exp=_epoch_in(days=-3))
        with pytest.raises(PicSureAuthenticationError) as exc_info:
            connect(platform=BASE_URL, token=expired)
        message = str(exc_info.value)
        assert "expired on" in message
        assert "3 days ago" in message

    @respx.mock
    def test_expired_token_sends_no_request(self):
        _mock_validation()
        expired = _make_jwt_claims(sub="u", exp=_epoch_in(days=-3))
        with pytest.raises(PicSureAuthenticationError):
            connect(platform=BASE_URL, token=expired)
        assert len(respx.calls) == 0

    @respx.mock
    def test_a_token_inside_the_clock_skew_allowance_is_accepted(self):
        _mock_connect()
        just_expired = _make_jwt_claims(sub="u", exp=_epoch_in(seconds=-5))
        session = connect(platform=BASE_URL, token=just_expired)
        assert isinstance(session, Session)

    @respx.mock
    def test_token_expiring_within_a_day_warns(self, capsys):
        _mock_connect()
        # Offset off the hour boundary: the duration is floored, so an
        # exact 6h expiry renders as "5 hours" once a millisecond passes.
        soon = _make_jwt_claims(sub="u", exp=_epoch_in(hours=6, minutes=30))
        connect(platform=BASE_URL, token=soon)
        err = capsys.readouterr().err
        assert "expires on" in err
        assert "6 hours" in err

    @respx.mock
    def test_token_valid_for_weeks_does_not_warn(self, capsys):
        _mock_connect()
        connect(platform=BASE_URL, token=TOKEN)
        assert "expires on" not in capsys.readouterr().err

    @respx.mock
    def test_validate_false_warns_instead_of_printing_a_past_date_silently(
        self, capsys
    ):
        expired = _make_jwt_claims(sub="u", exp=_epoch_in(days=-2))
        connect(platform=BASE_URL, token=expired, validate=False)
        captured = capsys.readouterr()
        # The banner still shows the date, but it is no longer presented
        # as success with nothing said about it.
        assert "expired on" in captured.err
        assert "validate=False" in captured.err


class TestConnectValidationTimeout:
    """PYR-4: two deadlines, and the short one covers the connect check."""

    def test_the_two_deadlines_are_distinct_named_values(self):
        assert DATA_TIMEOUT_SECONDS == 600.0
        assert VALIDATION_TIMEOUT_SECONDS == 15.0
        assert VALIDATION_TIMEOUT_SECONDS < DATA_TIMEOUT_SECONDS

    @respx.mock
    def test_validation_request_uses_the_short_deadline(self):
        _mock_connect()
        connect(platform=BASE_URL, token=TOKEN)
        timeout = respx.calls[0].request.extensions["timeout"]
        assert timeout["connect"] == VALIDATION_TIMEOUT_SECONDS
        assert timeout["read"] == VALIDATION_TIMEOUT_SECONDS

    @respx.mock
    def test_session_defaults_to_the_ten_minute_data_deadline(self):
        _mock_connect()
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session._client._timeout == DATA_TIMEOUT_SECONDS

    @respx.mock
    def test_timeout_argument_overrides_the_data_deadline(self):
        _mock_connect()
        session = connect(platform=BASE_URL, token=TOKEN, timeout=42.0)
        assert session._client._timeout == 42.0

    @respx.mock
    def test_timeout_argument_does_not_lengthen_the_validation_deadline(self):
        # The whole point: a mistyped hostname must not sit on the data
        # deadline, however long the caller set that.
        _mock_connect()
        connect(platform=BASE_URL, token=TOKEN, timeout=3600.0)
        timeout = respx.calls[0].request.extensions["timeout"]
        assert timeout["read"] == VALIDATION_TIMEOUT_SECONDS


class TestResourceUuidRemoved:
    @respx.mock
    def test_keyword_raises_type_error(self):
        with pytest.raises(TypeError, match="resource_uuid"):
            connect(platform=BASE_URL, token=TOKEN, resource_uuid="my-custom-uuid")

    @respx.mock
    def test_third_positional_argument_raises_type_error(self):
        # resource_uuid used to be the third positional parameter. Now that
        # it is gone the call fails loudly rather than binding the UUID to
        # a keyword-only argument.
        with pytest.raises(TypeError):
            connect(BASE_URL, TOKEN, "my-custom-uuid")


class TestConnectValidation:
    def test_invalid_platform_raises_validation_error(self):
        with pytest.raises(PicSureValidationError):
            connect(platform="NotARealPlatform", token=TOKEN)

    def test_empty_token_on_requires_auth_raises(self):
        from picsure._transport.platforms import Platform

        with pytest.raises(PicSureValidationError, match="requires a token"):
            connect(platform=Platform.BDC_AUTHORIZED, token="")

    def test_consents_without_auth_raises(self):
        with pytest.raises(PicSureValidationError, match="include_consents=True"):
            connect(platform=BASE_URL, include_consents=True, requires_auth=False)

    def test_contradiction_is_caught_before_any_client_is_built(self):
        # No token is passed, so a validation error is the only correct
        # outcome; a "requires a token" error would mean the flags were
        # accepted first.
        with pytest.raises(PicSureValidationError) as exc_info:
            connect(platform=BASE_URL, include_consents=True, requires_auth=False)
        assert "requires a token" not in str(exc_info.value)


class TestConnectConsents:
    @respx.mock
    def test_include_consents_kwarg_fetches_consents(self):
        _mock_validation()
        _mock_consents()

        session = connect(platform=BASE_URL, token=TOKEN, include_consents=True)

        assert session.consents == ["phs000007.c1", "phs001013.c1"]

    @respx.mock
    def test_include_consents_false_override_skips_fetch(self):
        from picsure._transport.platforms import Platform

        prod_url = Platform.BDC_AUTHORIZED.url
        _mock_validation(prod_url)
        consents_route = _mock_consents(prod_url)

        session = connect(
            platform=Platform.BDC_AUTHORIZED, token=TOKEN, include_consents=False
        )

        assert consents_route.called is False
        assert session.consents == []

    @respx.mock
    def test_explicit_false_on_a_custom_url_does_not_probe(self):
        _mock_validation()
        consents_route = _mock_consents()

        session = connect(platform=BASE_URL, token=TOKEN, include_consents=False)

        assert consents_route.called is False
        assert session.consents == []

    @respx.mock
    def test_known_platform_without_consents_does_not_probe(self):
        from picsure._transport.platforms import Platform

        _mock_validation(Platform.NHANES_AUTHORIZED.url.rstrip("/"))
        consents_route = _mock_consents(Platform.NHANES_AUTHORIZED.url.rstrip("/"))

        session = connect(platform=Platform.NHANES_AUTHORIZED, token=TOKEN)

        assert consents_route.called is False
        assert session.consents == []


class TestConnectConsentDetection:
    """PL-08: a custom URL must not silently return unscoped results."""

    @respx.mock
    def test_custom_url_detects_consent_scoping(self):
        _mock_validation()
        _mock_consents()

        session = connect(platform=BASE_URL, token=TOKEN)

        assert session.consents == ["phs000007.c1", "phs001013.c1"]

    @respx.mock
    def test_detection_says_it_turned_scoping_on(self, capsys):
        _mock_validation()
        _mock_consents()

        connect(platform=BASE_URL, token=TOKEN)

        err = capsys.readouterr().err
        assert "consent scoping detected" in err
        assert "2 consents" in err

    @respx.mock
    def test_empty_consent_record_warns_naming_the_argument(self, capsys):
        _mock_validation()
        _mock_consents(payload={"consents": {}})

        session = connect(platform=BASE_URL, token=TOKEN)

        assert session.consents == []
        err = capsys.readouterr().err
        assert "include_consents=True" in err
        assert "every study" in err

    @respx.mock
    def test_absent_consent_route_warns_rather_than_failing(self, capsys):
        _mock_validation()
        respx.get(f"{BASE_URL}{_CONSENTS_PATH}").mock(
            return_value=httpx.Response(404, json={"errorType": "not_found"})
        )

        session = connect(platform=BASE_URL, token=TOKEN)

        assert session.consents == []
        assert "include_consents=True" in capsys.readouterr().err

    @respx.mock
    def test_warning_also_names_the_genomic_argument(self, capsys):
        _mock_validation()
        _mock_consents(payload={"consents": {}})

        connect(platform=BASE_URL, token=TOKEN)

        assert "supports_genomic=True" in capsys.readouterr().err

    @respx.mock
    def test_no_genomic_hint_once_genomic_is_enabled(self, capsys):
        _mock_validation()
        _mock_consents(payload={"consents": {}})

        connect(platform=BASE_URL, token=TOKEN, supports_genomic=True)

        assert "supports_genomic=True" not in capsys.readouterr().err

    @respx.mock
    def test_known_platform_never_warns_about_capabilities(self, capsys):
        from picsure._transport.platforms import Platform

        _mock_validation(Platform.BDC_DEV_AUTHORIZED.url)
        _mock_consents(Platform.BDC_DEV_AUTHORIZED.url)

        connect(platform=Platform.BDC_DEV_AUTHORIZED, token=TOKEN)

        assert "assumed rather than known" not in capsys.readouterr().err

    @respx.mock
    def test_open_custom_url_is_not_warned_about_consents(self, capsys):
        _mock_validation(status=403, payload={})

        connect(platform=BASE_URL, requires_auth=False)

        assert "include_consents=True" not in capsys.readouterr().err

    @respx.mock
    def test_validate_false_warns_because_it_cannot_detect(self, capsys):
        connect(platform=BASE_URL, token=TOKEN, validate=False)

        err = capsys.readouterr().err
        assert "could not be checked" in err
        assert len(respx.calls) == 0

    @respx.mock
    def test_detection_only_ever_turns_scoping_on(self):
        # A deployment that answers with consents cannot turn scoping off
        # for a platform whose recorded policy says it is on.
        from picsure._transport.platforms import Platform

        _mock_validation(Platform.BDC_DEV_AUTHORIZED.url)
        _mock_consents(Platform.BDC_DEV_AUTHORIZED.url, payload={"consents": {}})

        session = connect(platform=Platform.BDC_DEV_AUTHORIZED, token=TOKEN)

        assert session.consents == []
        assert session._backend == "auth"


class TestConnectOpenAccess:
    @respx.mock
    def test_open_platform_connects_anonymously(self):
        from picsure._transport.platforms import Platform

        _mock_validation(Platform.BDC_DEV_OPEN.url, status=403, payload={})

        session = connect(platform=Platform.BDC_DEV_OPEN)

        assert session.user_email == "anonymous"
        assert session.token_expiration == "N/A"
        assert session.consents == []

    @respx.mock
    def test_open_platform_success_message(self, capsys):
        from picsure._transport.platforms import Platform

        _mock_validation(Platform.BDC_DEV_OPEN.url, status=403, payload={})

        connect(platform=Platform.BDC_DEV_OPEN)

        out = capsys.readouterr().out
        assert "open access" in out.lower()
        assert "token expires" not in out.lower()

    @respx.mock
    def test_requires_auth_false_override_on_custom_url(self):
        _mock_validation(status=403, payload={})

        session = connect(platform=BASE_URL, requires_auth=False)

        assert session.user_email == "anonymous"

    @respx.mock
    def test_open_connect_ignores_a_psama_user_record(self):
        # A deployment that happens to answer /user/me does not turn an
        # anonymous connection into an identified one.
        from picsure._transport.platforms import Platform

        _mock_validation(Platform.BDC_DEV_OPEN.url)

        session = connect(platform=Platform.BDC_DEV_OPEN)

        assert session.user_email == "anonymous"


class TestConnectBackendSelection:
    @respx.mock
    def test_bdc_open_uses_open_backend(self):
        # Open-access (no auth) routes to the /hpds/open backend
        # (which now also uses the versioned /v3 query lifecycle).
        from picsure._transport.platforms import Platform

        _mock_validation(Platform.BDC_DEV_OPEN.url, status=403, payload={})

        session = connect(platform=Platform.BDC_DEV_OPEN)

        assert session._backend == "open"

    @respx.mock
    def test_authorized_platform_uses_auth_backend(self):
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_AUTHORIZED.url
        _mock_validation(host)
        _mock_consents(host, payload={})

        session = connect(platform=Platform.BDC_DEV_AUTHORIZED, token=TOKEN)

        # BDC Authorized requires both auth AND consents; routes to /hpds/auth.
        assert session._backend == "auth"

    @respx.mock
    def test_custom_url_default_uses_auth_backend(self):
        # Custom URLs default to requires_auth=True, so they route to /hpds/auth.
        _mock_validation()
        _mock_consents(payload={})

        session = connect(platform=BASE_URL, token=TOKEN)

        assert session._backend == "auth"

    @respx.mock
    def test_custom_url_open_override_uses_open_backend(self):
        _mock_validation(status=403, payload={})

        session = connect(platform=BASE_URL, requires_auth=False)

        assert session._backend == "open"

    @respx.mock
    def test_consents_only_keeps_auth_backend(self):
        _mock_validation()
        _mock_consents(payload={})

        session = connect(platform=BASE_URL, token=TOKEN, include_consents=True)

        assert session._backend == "auth"


class TestBannerAgreesWithRouting:
    """PL-13: the words the user reads and the path the queries take."""

    @respx.mock
    def test_authorized_banner_never_says_open_access(self, capsys):
        _mock_validation()
        _mock_consents()

        session = connect(platform=BASE_URL, token=TOKEN, include_consents=True)

        out = capsys.readouterr().out
        assert session._backend == "auth"
        assert "open access" not in out.lower()
        assert "as user" in out

    @respx.mock
    def test_open_banner_only_appears_on_the_open_backend(self, capsys):
        _mock_validation(status=403, payload={})

        session = connect(platform=BASE_URL, requires_auth=False)

        out = capsys.readouterr().out
        assert session._backend == "open"
        assert "open access" in out.lower()

    @respx.mock
    def test_the_misleading_combination_no_longer_exists(self):
        # requires_auth=False with include_consents=True is what printed
        # "open access" while routing to /hpds/auth and returning exact
        # counts. It is now refused outright.
        with pytest.raises(PicSureValidationError):
            connect(
                platform=BASE_URL,
                token=TOKEN,
                requires_auth=False,
                include_consents=True,
            )


class TestConnectSupportsGenomic:
    @respx.mock
    def test_connect_threads_supports_genomic_override(self):
        _mock_validation()
        _mock_consents(payload={})
        session = connect(platform=BASE_URL, token=TOKEN, supports_genomic=True)
        assert session._supports_genomic is True

    @respx.mock
    def test_connect_supports_genomic_defaults_false(self):
        _mock_validation()
        _mock_consents(payload={})
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session._supports_genomic is False


class TestTokenExpirationFromJwt:
    def test_extracts_exp_claim(self):
        token = _make_jwt(_JWT_EXP)
        assert _token_expiration_from_jwt(token) == EXPECTED_EXPIRY

    def test_missing_exp_returns_unknown(self):
        assert _token_expiration_from_jwt(_make_jwt(None)) == "unknown"

    def test_non_jwt_returns_unknown(self):
        assert _token_expiration_from_jwt("not-a-jwt") == "unknown"

    def test_garbage_payload_returns_unknown(self):
        assert _token_expiration_from_jwt("aaa.@@@.bbb") == "unknown"

    def test_non_numeric_exp_returns_unknown(self):
        assert _token_expiration_from_jwt(_make_jwt("tomorrow")) == "unknown"  # type: ignore[arg-type]

    def test_out_of_range_exp_returns_unknown(self):
        assert _token_expiration_from_jwt(_make_jwt(10**30)) == "unknown"


class TestEmailFromJwt:
    def test_reads_email_claim(self):
        from picsure._services.connect import _email_from_jwt

        token = _make_jwt_claims(email="user@example.com", sub="abc")
        assert _email_from_jwt(token) == "user@example.com"

    def test_falls_back_to_preferred_username(self):
        from picsure._services.connect import _email_from_jwt

        token = _make_jwt_claims(preferred_username="jdoe@idp", sub="abc")
        assert _email_from_jwt(token) == "jdoe@idp"

    def test_falls_back_to_sub(self):
        from picsure._services.connect import _email_from_jwt

        token = _make_jwt_claims(sub="subject-123")
        assert _email_from_jwt(token) == "subject-123"

    def test_empty_email_skips_to_next_claim(self):
        from picsure._services.connect import _email_from_jwt

        token = _make_jwt_claims(email="   ", preferred_username="jdoe@idp")
        assert _email_from_jwt(token) == "jdoe@idp"

    def test_no_usable_claim_returns_unknown(self):
        from picsure._services.connect import _email_from_jwt

        token = _make_jwt_claims(name="First Last")
        assert _email_from_jwt(token) == "unknown"

    def test_non_jwt_returns_unknown(self):
        from picsure._services.connect import _email_from_jwt

        assert _email_from_jwt("not-a-jwt") == "unknown"


class TestDescribeAge:
    def test_days(self):
        from picsure._services.connect import _describe_age

        assert _describe_age(timedelta(days=3, hours=2)) == "3 days"

    def test_single_day_is_singular(self):
        from picsure._services.connect import _describe_age

        assert _describe_age(timedelta(days=1)) == "1 day"

    def test_hours(self):
        from picsure._services.connect import _describe_age

        assert _describe_age(timedelta(hours=5)) == "5 hours"

    def test_minutes(self):
        from picsure._services.connect import _describe_age

        assert _describe_age(timedelta(minutes=7)) == "7 minutes"

    def test_seconds(self):
        from picsure._services.connect import _describe_age

        assert _describe_age(timedelta(seconds=1)) == "1 second"


class TestConnectCorrelationHeaders:
    @respx.mock
    def test_connect_sends_session_id_and_default_client_type(self):
        _mock_validation()
        _mock_consents()
        session = connect(platform=BASE_URL, token=TOKEN)

        # session.session_id is a freshly generated uuid4 string.
        assert uuid.UUID(session.session_id)

        # Every request in the flow carries the correlation headers.
        first_req = respx.calls[0].request
        assert first_req.headers["x-session-id"] == session.session_id
        assert first_req.headers["x-client-type"] == "PYTHON_ADAPTER"
        assert first_req.headers["user-agent"].startswith("picsure-python-adapter/")

    @respx.mock
    def test_connect_forwards_client_type_override(self):
        _mock_validation()
        _mock_consents()
        session = connect(platform=BASE_URL, token=TOKEN, client_type="R_ADAPTER")

        assert respx.calls[0].request.headers["x-client-type"] == "R_ADAPTER"
        assert (
            respx.calls[0]
            .request.headers["user-agent"]
            .startswith("picsure-r-adapter/")
        )
        # session_id is still generated regardless of client_type.
        assert uuid.UUID(session.session_id)

    @respx.mock
    def test_each_connect_gets_a_distinct_session_id(self):
        _mock_validation()
        _mock_consents()
        first = connect(platform=BASE_URL, token=TOKEN)
        second = connect(platform=BASE_URL, token=TOKEN)
        assert first.session_id != second.session_id
