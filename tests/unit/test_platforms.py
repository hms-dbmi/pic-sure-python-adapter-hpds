import pytest

from picsure._transport.platforms import Platform, PlatformInfo, resolve_platform
from picsure.errors import PicSureValidationError


class TestPlatformEnum:
    def test_bdc_authorized_and_open_share_domain(self):
        assert Platform.BDC_AUTHORIZED.url == Platform.BDC_OPEN.url

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

    def test_known_platform_propagates_include_consents(self):
        assert resolve_platform(Platform.BDC_AUTHORIZED).include_consents is True
        assert resolve_platform(Platform.BDC_OPEN).include_consents is False

    def test_known_platform_include_consents_override(self):
        # BDC_OPEN needs no auth, so consent scoping has to be turned on
        # together with it -- see TestContradictoryFlags.
        info = resolve_platform(
            Platform.BDC_OPEN, include_consents=True, requires_auth=True
        )
        assert info.include_consents is True

    def test_bdc_open_resolves_to_same_url(self):
        auth = resolve_platform(Platform.BDC_AUTHORIZED)
        open_ = resolve_platform(Platform.BDC_OPEN)
        assert auth.url == open_.url

    def test_custom_url_returned_as_is(self):
        info = resolve_platform("https://my-picsure.example.com")
        assert info.url == "https://my-picsure.example.com"

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
        # BDC_AUTHORIZED carries include_consents=True, so dropping auth
        # alone is the contradiction; drop both to describe an open
        # deployment at that URL.
        info = resolve_platform(
            Platform.BDC_AUTHORIZED, requires_auth=False, include_consents=False
        )
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


class TestBackendIsOneValue:
    """PL-13: routing and the connect banner read a single derived value."""

    def test_authorized_platform_is_the_auth_backend(self):
        assert resolve_platform(Platform.BDC_AUTHORIZED).backend == "auth"

    def test_open_platform_is_the_open_backend(self):
        assert resolve_platform(Platform.BDC_OPEN).backend == "open"

    def test_custom_url_defaults_to_the_auth_backend(self):
        assert resolve_platform("https://my-picsure.example.com").backend == "auth"

    def test_custom_url_without_auth_is_the_open_backend(self):
        info = resolve_platform("https://my-picsure.example.com", requires_auth=False)
        assert info.backend == "open"

    def test_consent_scoping_never_lands_on_the_open_backend(self):
        # The combination that used to print "open access" while routing
        # to /hpds/auth is now unrepresentable, so the two cannot drift.
        for platform in (Platform.BDC_AUTHORIZED, "https://my-picsure.example.com"):
            info = resolve_platform(platform, include_consents=True)
            assert info.include_consents is True
            assert info.backend == "auth"


class TestContradictoryFlags:
    """PL-13: consent scoping on an unauthenticated connection is rejected."""

    def test_custom_url_consents_without_auth_raises(self):
        with pytest.raises(PicSureValidationError, match="include_consents=True"):
            resolve_platform(
                "https://my-picsure.example.com",
                include_consents=True,
                requires_auth=False,
            )

    def test_known_platform_consents_without_auth_raises(self):
        # BDC_AUTHORIZED's own include_consents=True survives the
        # requires_auth=False override, so this is the same contradiction
        # reached without naming include_consents at all.
        with pytest.raises(PicSureValidationError, match="include_consents=True"):
            resolve_platform(Platform.BDC_AUTHORIZED, requires_auth=False)

    def test_message_names_both_escape_hatches(self):
        with pytest.raises(PicSureValidationError) as exc_info:
            resolve_platform(Platform.BDC_AUTHORIZED, requires_auth=False)
        message = str(exc_info.value)
        assert "include_consents=False" in message
        assert "Platform.BDC_OPEN" in message

    def test_direct_construction_is_validated_too(self):
        with pytest.raises(PicSureValidationError):
            PlatformInfo(
                url="https://my-picsure.example.com",
                include_consents=True,
                requires_auth=False,
            )


class TestCustomUrlMarker:
    """PL-08: connect() needs to know the flags were guessed, not recorded."""

    def test_custom_url_is_marked(self):
        assert resolve_platform("https://my-picsure.example.com").is_custom_url is True

    def test_known_platform_is_not_marked(self):
        assert resolve_platform(Platform.BDC_AUTHORIZED).is_custom_url is False
