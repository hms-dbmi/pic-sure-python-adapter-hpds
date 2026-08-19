import base64
import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest
import respx

from picsure._models.session import Session
from picsure._services.connect import _token_expiration_from_jwt, connect
from picsure._services.consents import _CONSENTS_KEY, _CONSENTS_PATH
from picsure.errors import (
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


BASE_URL = "https://test.example.com"
# 2026-06-15T00:00:00Z = 1781568000 epoch seconds.
_JWT_EXP = int(datetime(2026, 6, 15, tzinfo=timezone.utc).timestamp())
# The connect banner now reads the email straight from the token, so the
# default test token carries the email that the tests assert on.
TOKEN = _make_jwt_claims(
    sub="test-user", email="researcher@university.edu", exp=_JWT_EXP
)

# connect() no longer discovers resources via /info/resources — the resource
# registry was removed and the gateway routes by URL path — so a plain
# authorized connect (token, no consents) makes no HTTP call at all.  The
# consent fetch is the only connect-time request, and only when consents are
# requested; the tests that need a request to inspect drive that path.


class TestConnectSuccess:
    @respx.mock
    def test_returns_session(self):
        session = connect(platform=BASE_URL, token=TOKEN)
        assert isinstance(session, Session)

    @respx.mock
    def test_session_has_correct_email(self):
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session._user_email == "researcher@university.edu"

    @respx.mock
    def test_session_has_no_resources(self):
        # The resource registry is gone: sessions start with no resources.
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session._resources == []

    @respx.mock
    def test_custom_url_has_no_resource_uuid(self):
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session._resource_uuid is None

    @respx.mock
    def test_makes_no_registry_request(self):
        # A plain authorized connect performs zero HTTP calls now.
        connect(platform=BASE_URL, token=TOKEN)
        assert len(respx.calls) == 0

    @respx.mock
    def test_prints_success_message(self, capsys):
        connect(platform=BASE_URL, token=TOKEN)
        captured = capsys.readouterr()
        assert "successfully connected" in captured.out.lower()
        assert "researcher@university.edu" in captured.out

    @respx.mock
    def test_prints_token_expiration(self, capsys):
        connect(platform=BASE_URL, token=TOKEN)
        captured = capsys.readouterr()
        assert "token expires" in captured.out.lower()
        assert "2026-06-15" in captured.out


class TestConnectResourceUuid:
    @respx.mock
    def test_explicit_uuid_is_stored(self):
        # resource_uuid is retained for backwards compatibility; it is stored
        # but no longer selects a backend.
        session = connect(
            platform=BASE_URL, token=TOKEN, resource_uuid="my-custom-uuid"
        )
        assert session._resource_uuid == "my-custom-uuid"


class TestConnectValidation:
    def test_invalid_platform_raises_validation_error(self):
        with pytest.raises(PicSureValidationError):
            connect(platform="NotARealPlatform", token=TOKEN)

    def test_empty_token_on_requires_auth_raises(self):
        from picsure._transport.platforms import Platform

        with pytest.raises(PicSureValidationError, match="requires a token"):
            connect(platform=Platform.BDC_AUTHORIZED, token="")


class TestConnectConsents:
    _CONSENTS_URL = f"{BASE_URL}{_CONSENTS_PATH}"
    _CONSENT_PAYLOAD = {"consents": {_CONSENTS_KEY: ["phs000007.c1", "phs001013.c1"]}}

    @respx.mock
    def test_custom_url_skips_consent_fetch_by_default(self):
        consents_route = respx.get(self._CONSENTS_URL).mock(
            return_value=httpx.Response(200, json=self._CONSENT_PAYLOAD)
        )

        session = connect(platform=BASE_URL, token=TOKEN)

        assert consents_route.called is False
        assert session.consents == []

    @respx.mock
    def test_include_consents_kwarg_fetches_consents(self):
        respx.get(self._CONSENTS_URL).mock(
            return_value=httpx.Response(200, json=self._CONSENT_PAYLOAD)
        )

        session = connect(platform=BASE_URL, token=TOKEN, include_consents=True)

        assert session.consents == ["phs000007.c1", "phs001013.c1"]

    @respx.mock
    def test_include_consents_false_override_skips_fetch(self):
        from picsure._transport.platforms import Platform

        prod_url = Platform.BDC_AUTHORIZED.url
        consents_route = respx.get(f"{prod_url}{_CONSENTS_PATH}").mock(
            return_value=httpx.Response(200, json=self._CONSENT_PAYLOAD)
        )

        session = connect(
            platform=Platform.BDC_AUTHORIZED, token=TOKEN, include_consents=False
        )

        assert consents_route.called is False
        assert session.consents == []


class TestConnectOpenAccess:
    @respx.mock
    def test_open_platform_connects_anonymously(self):
        from picsure._transport.platforms import Platform

        session = connect(platform=Platform.BDC_DEV_OPEN)

        assert session._user_email == "anonymous"
        assert session._token_expiration == "N/A"
        assert session.consents == []

    @respx.mock
    def test_open_platform_makes_no_request(self):
        from picsure._transport.platforms import Platform

        connect(platform=Platform.BDC_DEV_OPEN)

        assert len(respx.calls) == 0

    @respx.mock
    def test_open_platform_success_message(self, capsys):
        from picsure._transport.platforms import Platform

        connect(platform=Platform.BDC_DEV_OPEN)

        out = capsys.readouterr().out
        assert "open access" in out.lower()
        assert "token expires" not in out.lower()

    @respx.mock
    def test_requires_auth_false_override_on_custom_url(self):
        session = connect(platform=BASE_URL, requires_auth=False)

        assert session._user_email == "anonymous"


class TestConnectBackendSelection:
    @respx.mock
    def test_bdc_open_uses_open_backend(self):
        # Open-access (no auth, no consents) routes to the /hpds/open backend
        # (which now also uses the versioned /v3 query lifecycle).
        from picsure._transport.platforms import Platform

        session = connect(platform=Platform.BDC_DEV_OPEN)

        assert session._backend == "open"

    @respx.mock
    def test_authorized_platform_uses_auth_backend(self):
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_AUTHORIZED.url
        respx.get(f"{host}{_CONSENTS_PATH}").mock(
            return_value=httpx.Response(200, json={})
        )

        session = connect(platform=Platform.BDC_DEV_AUTHORIZED, token=TOKEN)

        # BDC Authorized requires both auth AND consents; routes to /hpds/auth.
        assert session._backend == "auth"

    @respx.mock
    def test_custom_url_default_uses_auth_backend(self):
        # Custom URLs default to requires_auth=True, so they route to /hpds/auth.
        session = connect(platform=BASE_URL, token=TOKEN)

        assert session._backend == "auth"

    @respx.mock
    def test_custom_url_open_override_uses_open_backend(self):
        # Custom URL with requires_auth=False AND no consents => /hpds/open.
        session = connect(platform=BASE_URL, requires_auth=False)

        assert session._backend == "open"

    @respx.mock
    def test_consents_only_keeps_auth_backend(self):
        # If the deployment requires consents (even with auth on), it's an
        # authorized backend — routes to /hpds/auth.
        respx.get(f"{BASE_URL}{_CONSENTS_PATH}").mock(
            return_value=httpx.Response(200, json={})
        )

        session = connect(
            platform=BASE_URL,
            token=TOKEN,
            include_consents=True,
        )

        assert session._backend == "auth"


class TestConnectSupportsGenomic:
    @respx.mock
    def test_connect_threads_supports_genomic_override(self):
        session = connect(platform=BASE_URL, token=TOKEN, supports_genomic=True)
        assert session._supports_genomic is True

    @respx.mock
    def test_connect_supports_genomic_defaults_false(self):
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session._supports_genomic is False


class TestTokenExpirationFromJwt:
    def test_extracts_exp_claim(self):
        token = _make_jwt(_JWT_EXP)
        assert _token_expiration_from_jwt(token) == "2026-06-15T00:00:00Z"

    def test_missing_exp_returns_unknown(self):
        assert _token_expiration_from_jwt(_make_jwt(None)) == "unknown"

    def test_non_jwt_returns_unknown(self):
        assert _token_expiration_from_jwt("not-a-jwt") == "unknown"

    def test_garbage_payload_returns_unknown(self):
        assert _token_expiration_from_jwt("aaa.@@@.bbb") == "unknown"

    def test_non_numeric_exp_returns_unknown(self):
        assert _token_expiration_from_jwt(_make_jwt("tomorrow")) == "unknown"  # type: ignore[arg-type]


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


class TestConnectCorrelationHeaders:
    _CONSENTS_URL = f"{BASE_URL}{_CONSENTS_PATH}"

    @respx.mock
    def test_connect_sends_session_id_and_default_client_type(self):
        # Drive the consent fetch so there is a request to inspect.
        respx.get(self._CONSENTS_URL).mock(return_value=httpx.Response(200, json={}))
        session = connect(platform=BASE_URL, token=TOKEN, include_consents=True)

        # session.session_id is a freshly generated uuid4 string.
        assert uuid.UUID(session.session_id)

        # Every request in the flow carries the correlation headers.
        first_req = respx.calls[0].request
        assert first_req.headers["x-session-id"] == session.session_id
        assert first_req.headers["x-client-type"] == "PYTHON_ADAPTER"
        assert first_req.headers["user-agent"].startswith("picsure-python-adapter/")

    @respx.mock
    def test_connect_forwards_client_type_override(self):
        respx.get(self._CONSENTS_URL).mock(return_value=httpx.Response(200, json={}))
        session = connect(
            platform=BASE_URL,
            token=TOKEN,
            include_consents=True,
            client_type="R_ADAPTER",
        )

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
        first = connect(platform=BASE_URL, token=TOKEN)
        second = connect(platform=BASE_URL, token=TOKEN)
        assert first.session_id != second.session_id
