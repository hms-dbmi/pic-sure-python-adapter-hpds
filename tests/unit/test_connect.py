import base64
import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest
import respx

from picsure._models.session import Session
from picsure._services.connect import _token_expiration_from_jwt, connect
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
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


def _mock_connect_flow(
    resources_response: dict,
    host: str = BASE_URL,
) -> None:
    respx.get(f"{host}/picsure/info/resources").mock(
        return_value=httpx.Response(200, json=resources_response)
    )


class TestConnectSuccess:
    @respx.mock
    def test_returns_session(self, resources_response):
        _mock_connect_flow(resources_response)
        session = connect(platform=BASE_URL, token=TOKEN)
        assert isinstance(session, Session)

    @respx.mock
    def test_session_has_correct_email(self, resources_response):
        _mock_connect_flow(resources_response)
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session._user_email == "researcher@university.edu"

    @respx.mock
    def test_session_has_resources(self, resources_response):
        _mock_connect_flow(resources_response)
        session = connect(platform=BASE_URL, token=TOKEN)
        assert len(session._resources) == 2
        uuids = {r.uuid for r in session._resources}
        assert "resource-uuid-aaaa-1111" in uuids

    @respx.mock
    def test_custom_url_has_no_resource_uuid(self, resources_response):
        _mock_connect_flow(resources_response)
        session = connect(platform=BASE_URL, token=TOKEN)
        assert session._resource_uuid is None

    @respx.mock
    def test_prints_success_message(self, resources_response, capsys):
        _mock_connect_flow(resources_response)
        connect(platform=BASE_URL, token=TOKEN)
        captured = capsys.readouterr()
        assert "successfully connected" in captured.out.lower()
        assert "researcher@university.edu" in captured.out

    @respx.mock
    def test_prints_token_expiration(self, resources_response, capsys):
        _mock_connect_flow(resources_response)
        connect(platform=BASE_URL, token=TOKEN)
        captured = capsys.readouterr()
        assert "token expires" in captured.out.lower()
        assert "2026-06-15" in captured.out


class TestConnectAuthErrors:
    @respx.mock
    def test_401_raises_auth_error(self):
        # /info/resources is now the first authenticated call, so it owns
        # the friendly bad-token message the profile call used to surface.
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        with pytest.raises(PicSureAuthError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)

        msg = str(exc_info.value)
        assert "invalid or expired" in msg.lower()
        assert "picsure.connect()" in msg


class TestConnectConnectionErrors:
    @respx.mock
    def test_network_error_raises_connection_error(self):
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(PicSureConnectionError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)

        msg = str(exc_info.value)
        assert "resources" in msg.lower()

    @respx.mock
    def test_resource_fetch_failure_raises_connection_error(self):
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(PicSureConnectionError) as exc_info:
            connect(platform=BASE_URL, token=TOKEN)

        msg = str(exc_info.value)
        assert "resources" in msg.lower()

    @respx.mock
    def test_null_resources_payload_raises_connection_error(self):
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(
                200, content=b"null", headers={"content-type": "application/json"}
            )
        )

        with pytest.raises(PicSureConnectionError, match="unexpected resources"):
            connect(platform=BASE_URL, token=TOKEN)


class TestConnectResourceUuid:
    @respx.mock
    def test_explicit_uuid_overrides_platform(self, resources_response):
        _mock_connect_flow(resources_response)
        session = connect(
            platform=BASE_URL, token=TOKEN, resource_uuid="my-custom-uuid"
        )
        assert session._resource_uuid == "my-custom-uuid"

    @respx.mock
    def test_custom_url_no_uuid_prints_resources(self, resources_response, capsys):
        _mock_connect_flow(resources_response)
        connect(platform=BASE_URL, token=TOKEN)
        captured = capsys.readouterr()
        assert "Available resources" in captured.out
        assert "setResourceID" in captured.out

    @respx.mock
    def test_custom_url_with_uuid_no_prompt(self, resources_response, capsys):
        _mock_connect_flow(resources_response)
        connect(platform=BASE_URL, token=TOKEN, resource_uuid="resource-uuid-aaaa-1111")
        captured = capsys.readouterr()
        assert "Available resources" not in captured.out


class TestConnectValidation:
    def test_invalid_platform_raises_validation_error(self):
        with pytest.raises(PicSureValidationError):
            connect(platform="NotARealPlatform", token=TOKEN)

    def test_empty_token_on_requires_auth_raises(self):
        from picsure._transport.platforms import Platform

        with pytest.raises(PicSureValidationError, match="requires a token"):
            connect(platform=Platform.BDC_AUTHORIZED, token="")


class TestConnectConsents:
    _TEMPLATE_URL = f"{BASE_URL}/psama/user/me/queryTemplate/"
    _CONSENT_PAYLOAD = {
        "queryTemplate": (
            '{"categoryFilters":{"\\\\_consents\\\\":["phs000007.c1","phs001013.c1"]}}'
        )
    }

    @respx.mock
    def test_custom_url_skips_consent_fetch_by_default(self, resources_response):
        _mock_connect_flow(resources_response)
        template_route = respx.get(self._TEMPLATE_URL).mock(
            return_value=httpx.Response(200, json=self._CONSENT_PAYLOAD)
        )

        session = connect(platform=BASE_URL, token=TOKEN)

        assert template_route.called is False
        assert session.consents == []

    @respx.mock
    def test_include_consents_kwarg_fetches_consents(self, resources_response):
        _mock_connect_flow(resources_response)
        respx.get(self._TEMPLATE_URL).mock(
            return_value=httpx.Response(200, json=self._CONSENT_PAYLOAD)
        )

        session = connect(platform=BASE_URL, token=TOKEN, include_consents=True)

        assert session.consents == ["phs000007.c1", "phs001013.c1"]

    @respx.mock
    def test_include_consents_false_override_skips_fetch(self, resources_response):
        from picsure._transport.platforms import Platform

        prod_url = Platform.BDC_AUTHORIZED.url
        _mock_connect_flow(resources_response, host=prod_url)
        template_route = respx.get(f"{prod_url}/psama/user/me/queryTemplate/").mock(
            return_value=httpx.Response(200, json=self._CONSENT_PAYLOAD)
        )

        session = connect(
            platform=Platform.BDC_AUTHORIZED, token=TOKEN, include_consents=False
        )

        assert template_route.called is False
        assert session.consents == []


class TestConnectOpenAccess:
    @respx.mock
    def test_open_platform_connects_anonymously(self, resources_response):
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_OPEN.url
        respx.get(f"{host}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(platform=Platform.BDC_DEV_OPEN)

        assert session._user_email == "anonymous"
        assert session._token_expiration == "N/A"
        assert session.consents == []

    @respx.mock
    def test_open_platform_skips_consent_fetch(self, resources_response):
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_OPEN.url
        respx.get(f"{host}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )
        template_route = respx.get(f"{host}/psama/user/me/queryTemplate/").mock(
            return_value=httpx.Response(200, json={})
        )

        connect(platform=Platform.BDC_DEV_OPEN)

        assert template_route.called is False

    @respx.mock
    def test_open_platform_resources_401_degrades_to_empty(self):
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_OPEN.url
        respx.get(f"{host}/picsure/info/resources").mock(
            return_value=httpx.Response(401)
        )

        session = connect(platform=Platform.BDC_DEV_OPEN)

        assert session._resources == []

    @respx.mock
    def test_open_platform_no_auth_header_sent(self, resources_response):
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_OPEN.url
        resources_route = respx.get(f"{host}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        connect(platform=Platform.BDC_DEV_OPEN)

        assert "authorization" not in resources_route.calls[0].request.headers

    @respx.mock
    def test_open_platform_success_message(self, resources_response, capsys):
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_OPEN.url
        respx.get(f"{host}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        connect(platform=Platform.BDC_DEV_OPEN)

        out = capsys.readouterr().out
        assert "open access" in out.lower()
        assert "token expires" not in out.lower()

    @respx.mock
    def test_requires_auth_false_override_on_custom_url(self, resources_response):
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(platform=BASE_URL, requires_auth=False)

        assert session._user_email == "anonymous"


class TestConnectLegacyQueryPath:
    @respx.mock
    def test_bdc_open_uses_legacy_query_path(self, resources_response):
        # BDC's API gateway 401s open-access requests on /picsure/v3/query/sync.
        # connect() must flip the session over to /picsure/query/sync whenever
        # neither auth nor consents are required.
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_OPEN.url
        respx.get(f"{host}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(platform=Platform.BDC_DEV_OPEN)

        assert session._use_legacy_query_path is True

    @respx.mock
    def test_authorized_platform_uses_v3_query_path(self, resources_response):
        from picsure._transport.platforms import Platform

        host = Platform.BDC_DEV_AUTHORIZED.url
        _mock_connect_flow(resources_response, host=host)
        respx.get(f"{host}/psama/user/me/queryTemplate/").mock(
            return_value=httpx.Response(200, json={})
        )

        session = connect(platform=Platform.BDC_DEV_AUTHORIZED, token=TOKEN)

        # BDC Authorized requires both auth AND consents; it stays on v3.
        assert session._use_legacy_query_path is False

    @respx.mock
    def test_custom_url_default_uses_v3_query_path(self, resources_response):
        # Custom URLs default to requires_auth=True, so legacy routing
        # stays off.
        _mock_connect_flow(resources_response)

        session = connect(platform=BASE_URL, token=TOKEN)

        assert session._use_legacy_query_path is False

    @respx.mock
    def test_custom_url_open_override_uses_legacy_query_path(self, resources_response):
        # Custom URL with requires_auth=False AND no consents — flag flips on.
        respx.get(f"{BASE_URL}/picsure/info/resources").mock(
            return_value=httpx.Response(200, json=resources_response)
        )

        session = connect(platform=BASE_URL, requires_auth=False)

        assert session._use_legacy_query_path is True

    @respx.mock
    def test_consents_only_keeps_v3_query_path(self, resources_response):
        # If the deployment requires consents (even with auth on), it's
        # an authorized backend — stay on v3.
        _mock_connect_flow(resources_response)
        respx.get(f"{BASE_URL}/psama/user/me/queryTemplate/").mock(
            return_value=httpx.Response(200, json={})
        )

        session = connect(
            platform=BASE_URL,
            token=TOKEN,
            include_consents=True,
        )

        assert session._use_legacy_query_path is False


class TestConnectSupportsGenomic:
    @respx.mock
    def test_connect_threads_supports_genomic_override(self, resources_response):
        _mock_connect_flow(resources_response)
        session = connect(platform=BASE_URL, token=TOKEN, supports_genomic=True)
        assert session._supports_genomic is True

    @respx.mock
    def test_connect_supports_genomic_defaults_false(self, resources_response):
        _mock_connect_flow(resources_response)
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
    @respx.mock
    def test_connect_sends_session_id_and_default_client_type(self, resources_response):
        _mock_connect_flow(resources_response)
        session = connect(platform=BASE_URL, token=TOKEN)

        # session.session_id is a freshly generated uuid4 string.
        assert uuid.UUID(session.session_id)

        # Every request in the flow carries the correlation headers.
        first_req = respx.calls[0].request
        assert first_req.headers["x-session-id"] == session.session_id
        assert first_req.headers["x-client-type"] == "PYTHON_ADAPTER"
        assert first_req.headers["user-agent"].startswith("picsure-python-adapter/")

    @respx.mock
    def test_connect_forwards_client_type_override(self, resources_response):
        _mock_connect_flow(resources_response)
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
    def test_each_connect_gets_a_distinct_session_id(self, resources_response):
        _mock_connect_flow(resources_response)
        first = connect(platform=BASE_URL, token=TOKEN)
        second = connect(platform=BASE_URL, token=TOKEN)
        assert first.session_id != second.session_id
