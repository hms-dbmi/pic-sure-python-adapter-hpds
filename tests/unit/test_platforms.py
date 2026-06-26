import pytest

from picsure._transport.platforms import Platform, PlatformInfo, resolve_platform
from picsure.errors import PicSureValidationError


class TestPlatformEnum:
    def test_bdc_authorized_and_open_share_domain(self):
        assert Platform.BDC_AUTHORIZED.url == Platform.BDC_OPEN.url

    def test_bdc_authorized_and_open_differ_by_uuid(self):
        assert Platform.BDC_AUTHORIZED.resource_uuid != Platform.BDC_OPEN.resource_uuid

    def test_authorized_platforms_include_consents(self):
        assert Platform.BDC_AUTHORIZED.include_consents is True
        assert Platform.BDC_DEV_AUTHORIZED.include_consents is True
        assert Platform.BDC_PREDEV_AUTHORIZED.include_consents is True

    def test_open_platforms_do_not_include_consents(self):
        assert Platform.BDC_OPEN.include_consents is False
        assert Platform.BDC_DEV_OPEN.include_consents is False
        assert Platform.BDC_PREDEV_OPEN.include_consents is False

    def test_authorized_platforms_require_auth(self):
        assert Platform.BDC_AUTHORIZED.requires_auth is True
        assert Platform.BDC_DEV_AUTHORIZED.requires_auth is True
        assert Platform.BDC_PREDEV_AUTHORIZED.requires_auth is True
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
        info = resolve_platform("https://my-picsure.example.com", include_consents=True)
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
        info = resolve_platform("https://my-picsure.example.com", requires_auth=False)
        assert info.requires_auth is False

    def test_custom_url_trailing_slash_stripped(self):
        info = resolve_platform("https://my-picsure.example.com/")
        assert info.url == "https://my-picsure.example.com"

    def test_unknown_string_raises(self):
        with pytest.raises(PicSureValidationError, match="not a recognized platform"):
            resolve_platform("NonExistentPlatform")

    def test_unknown_string_lists_enum_member_forms(self):
        with pytest.raises(PicSureValidationError, match=r"Platform\.BDC_AUTHORIZED"):
            resolve_platform("typo")

    def test_unknown_string_does_not_list_labels_as_valid_input(self):
        with pytest.raises(PicSureValidationError) as exc_info:
            resolve_platform("typo")
        msg = str(exc_info.value)
        assert "full URL" in msg
        # Human labels must not be presented as valid input forms.
        assert "Valid platforms:" not in msg

    def test_nhanes_open_resolves(self):
        info = resolve_platform(Platform.NHANES_OPEN)
        assert info.url.startswith("https://")
        assert info.resource_uuid is not None


def test_authorized_platforms_support_genomic():
    assert Platform.BDC_AUTHORIZED.supports_genomic is True
    assert Platform.BDC_DEV_AUTHORIZED.supports_genomic is True
    assert Platform.BDC_PREDEV_AUTHORIZED.supports_genomic is True
    assert Platform.NHANES_AUTHORIZED.supports_genomic is True


def test_open_platforms_do_not_support_genomic():
    for p in (
        Platform.BDC_OPEN,
        Platform.BDC_DEV_OPEN,
        Platform.BDC_PREDEV_OPEN,
        Platform.NHANES_OPEN,
    ):
        assert p.supports_genomic is False


def test_resolve_platform_threads_supports_genomic():
    assert resolve_platform(Platform.BDC_AUTHORIZED).supports_genomic is True
    assert resolve_platform(Platform.BDC_OPEN).supports_genomic is False


def test_resolve_platform_custom_url_defaults_false():
    assert resolve_platform("https://my-picsure.example.com").supports_genomic is False


def test_resolve_platform_custom_url_override_true():
    info = resolve_platform("https://my-picsure.example.com", supports_genomic=True)
    assert info.supports_genomic is True


def test_resolve_platform_member_override_false():
    info = resolve_platform(Platform.BDC_AUTHORIZED, supports_genomic=False)
    assert info.supports_genomic is False
