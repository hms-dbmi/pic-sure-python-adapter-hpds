import pytest

from picsure._transport.platforms import resolve_platform_url
from picsure.errors import PicSureValidationError


class TestResolvePlatformUrl:
    def test_bdc_authorized(self):
        url = resolve_platform_url("BDC Authorized")
        assert url.startswith("https://")
        assert "picsure" in url.lower() or "bdc" in url.lower()

    def test_bdc_open(self):
        url = resolve_platform_url("BDC Open")
        assert url.startswith("https://")

    def test_demo(self):
        url = resolve_platform_url("Demo")
        assert url.startswith("https://")

    def test_aim_ahead(self):
        url = resolve_platform_url("AIM-AHEAD")
        assert url.startswith("https://")

    def test_case_insensitive(self):
        url_lower = resolve_platform_url("bdc authorized")
        url_upper = resolve_platform_url("BDC AUTHORIZED")
        url_mixed = resolve_platform_url("Bdc Authorized")
        assert url_lower == url_upper == url_mixed

    def test_custom_url_returned_as_is(self):
        custom = "https://my-picsure.example.com"
        assert resolve_platform_url(custom) == custom

    def test_custom_url_http(self):
        custom = "http://localhost:8080"
        assert resolve_platform_url(custom) == custom

    def test_custom_url_trailing_slash_stripped(self):
        custom = "https://my-picsure.example.com/"
        assert resolve_platform_url(custom) == "https://my-picsure.example.com"

    def test_unknown_platform_raises(self):
        with pytest.raises(PicSureValidationError, match="not a recognized platform"):
            resolve_platform_url("NonExistentPlatform")

    def test_unknown_platform_lists_valid_options(self):
        with pytest.raises(PicSureValidationError, match="BDC Authorized"):
            resolve_platform_url("typo")
