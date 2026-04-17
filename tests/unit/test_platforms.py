import pytest

from picsure._transport.platforms import Platform, PlatformInfo, resolve_platform
from picsure.errors import PicSureValidationError


class TestPlatformEnum:
    def test_bdc_authorized_and_open_share_domain(self):
        assert Platform.BDC_AUTHORIZED.url == Platform.BDC_OPEN.url

    def test_bdc_authorized_and_open_differ_by_uuid(self):
        assert Platform.BDC_AUTHORIZED.resource_uuid != Platform.BDC_OPEN.resource_uuid

    def test_all_members_have_url(self):
        for p in Platform:
            assert p.url.startswith("https://")

    def test_all_members_have_resource_uuid(self):
        for p in Platform:
            assert isinstance(p.resource_uuid, str)

    def test_all_members_have_label(self):
        for p in Platform:
            assert p.label

    def test_authorized_platforms_include_consents(self):
        assert Platform.BDC_AUTHORIZED.include_consents is True
        assert Platform.BDC_DEV_AUTHORIZED.include_consents is True
        assert Platform.BDC_PREDEV_AUTHORIZED.include_consents is True

    def test_open_platforms_do_not_include_consents(self):
        assert Platform.BDC_OPEN.include_consents is False
        assert Platform.BDC_DEV_OPEN.include_consents is False
        assert Platform.BDC_PREDEV_OPEN.include_consents is False

    def test_aim_ahead_includes_consents(self):
        assert Platform.AIM_AHEAD.include_consents is True

    def test_nhanes_does_not_include_consents(self):
        assert Platform.NHANES_AUTHORIZED.include_consents is False
        assert Platform.NHANES_OPEN.include_consents is False

    def test_authorized_platforms_require_auth(self):
        assert Platform.BDC_AUTHORIZED.requires_auth is True
        assert Platform.BDC_DEV_AUTHORIZED.requires_auth is True
        assert Platform.BDC_PREDEV_AUTHORIZED.requires_auth is True
        assert Platform.AIM_AHEAD.requires_auth is True
        assert Platform.NHANES_AUTHORIZED.requires_auth is True

    def test_open_platforms_do_not_require_auth(self):
        assert Platform.BDC_OPEN.requires_auth is False
        assert Platform.BDC_DEV_OPEN.requires_auth is False
        assert Platform.BDC_PREDEV_OPEN.requires_auth is False
        assert Platform.NHANES_OPEN.requires_auth is False


class TestResolvePlatform:
    def test_known_platform_returns_platform_info(self):
        info = resolve_platform(Platform.BDC_AUTHORIZED)
        assert isinstance(info, PlatformInfo)
        assert info.url == Platform.BDC_AUTHORIZED.url
        assert info.resource_uuid == Platform.BDC_AUTHORIZED.resource_uuid

    def test_known_platform_propagates_include_consents(self):
        assert resolve_platform(Platform.BDC_AUTHORIZED).include_consents is True
        assert resolve_platform(Platform.BDC_OPEN).include_consents is False

    def test_known_platform_include_consents_override(self):
        info = resolve_platform(Platform.BDC_OPEN, include_consents=True)
        assert info.include_consents is True

    def test_bdc_open_returns_same_url_different_uuid(self):
        auth = resolve_platform(Platform.BDC_AUTHORIZED)
        open_ = resolve_platform(Platform.BDC_OPEN)
        assert auth.url == open_.url
        assert auth.resource_uuid != open_.resource_uuid

    def test_custom_url_returned_as_is(self):
        info = resolve_platform("https://my-picsure.example.com")
        assert info.url == "https://my-picsure.example.com"
        assert info.resource_uuid is None

    def test_custom_url_defaults_to_no_consents(self):
        info = resolve_platform("https://my-picsure.example.com")
        assert info.include_consents is False

    def test_custom_url_include_consents_override(self):
        info = resolve_platform(
            "https://my-picsure.example.com", include_consents=True
        )
        assert info.include_consents is True

    def test_known_platform_propagates_requires_auth(self):
        assert resolve_platform(Platform.BDC_AUTHORIZED).requires_auth is True
        assert resolve_platform(Platform.BDC_OPEN).requires_auth is False

    def test_known_platform_requires_auth_override(self):
        info = resolve_platform(Platform.BDC_AUTHORIZED, requires_auth=False)
        assert info.requires_auth is False

    def test_custom_url_defaults_to_requires_auth(self):
        info = resolve_platform("https://my-picsure.example.com")
        assert info.requires_auth is True

    def test_custom_url_requires_auth_override(self):
        info = resolve_platform(
            "https://my-picsure.example.com", requires_auth=False
        )
        assert info.requires_auth is False

    def test_custom_url_http(self):
        info = resolve_platform("http://localhost:8080")
        assert info.url == "http://localhost:8080"
        assert info.resource_uuid is None

    def test_custom_url_trailing_slash_stripped(self):
        info = resolve_platform("https://my-picsure.example.com/")
        assert info.url == "https://my-picsure.example.com"

    def test_unknown_string_raises(self):
        with pytest.raises(PicSureValidationError, match="not a recognized platform"):
            resolve_platform("NonExistentPlatform")

    def test_unknown_string_lists_valid_options(self):
        with pytest.raises(PicSureValidationError, match="BDC Authorized"):
            resolve_platform("typo")

    def test_nhanes_open_resolves(self):
        info = resolve_platform(Platform.NHANES_OPEN)
        assert info.url.startswith("https://")
        assert info.resource_uuid is not None

    def test_aim_ahead_resolves(self):
        info = resolve_platform(Platform.AIM_AHEAD)
        assert info.url.startswith("https://")
        assert info.resource_uuid is not None
