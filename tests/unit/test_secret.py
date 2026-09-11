"""Tests for SecretToken and for the traceback exposure it exists to close.

The leak tests render a traceback the way pytest renders a failing test
(``funcargs=True``, which is what ``--tb=long`` uses) and measure the
longest contiguous run of token characters in the output.  A synthetic
token is used, so nothing here depends on a real credential; the shape
is what matters -- a long, high-entropy, dot-separated string whose
substrings do not occur by chance in source text.
"""

from __future__ import annotations

import copy
import pickle

import httpx
import pytest
import respx

from picsure._transport.client import PicSureClient
from picsure._transport.secret import SecretToken, as_secret_token

BASE_URL = "https://secret.example.com"

# A well-formed synthetic JWT: three segments, a payload that really is
# base64url-encoded JSON, and long enough that any leak shows up as a run
# far longer than the incidental two- or three-character matches ordinary
# source text produces by chance.  No real credential is involved.
SECRET_VALUE = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImxlYWstcHJvY"
    "mVAZXhhbXBsZS5pbnZhbGlkIiwic3ViIjoic3ludGhldGljLXN1YmplY3QtZm9"
    "yLXRyYWNlYmFjay1sZWFrLXJlZ3Jlc3Npb24tdGVzdCIsInByZWZlcnJlZF91c"
    "2VybmFtZSI6ImxlYWstcHJvYmUiLCJleHAiOjQxMDI0NDQ4MDAsImlzcyI6Imh"
    "0dHBzOi8vcHNhbWEuZXhhbXBsZS5pbnZhbGlkIiwianRpIjoiMDAwMDAwMDAwM"
    "DAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMCJ9.AAECAwQFBgcICQoLDA"
    "0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7"
    "PD0-Pw"
)

# Anything at or below this is incidental overlap with ordinary source text,
# not token material.  The defect being regressed measured 118 characters by
# default and the whole token under --showlocals.
MAX_INCIDENTAL_RUN = 8


def longest_token_run(haystack: str) -> int:
    """Longest contiguous substring of SECRET_VALUE present in ``haystack``."""
    best = 0
    for start in range(len(SECRET_VALUE)):
        if len(SECRET_VALUE) - start <= best:
            break
        length = best + 1
        while (
            start + length <= len(SECRET_VALUE)
            and SECRET_VALUE[start : start + length] in haystack
        ):
            length += 1
        best = max(best, length - 1)
    return best


class TestSecretTokenRendering:
    def test_repr_str_and_format_are_one_fixed_placeholder(self):
        secret = SecretToken(SECRET_VALUE)
        # Percent formatting is the point of the test, not a style slip:
        # it is one of the two paths a str subclass would have kept
        # working in silently.
        percent = "%s" % (secret,)  # noqa: UP031
        renderings = [repr(secret), str(secret), f"{secret}", percent]

        assert len(set(renderings)) == 1
        for rendering in renderings:
            assert longest_token_run(rendering) <= MAX_INCIDENTAL_RUN

    def test_a_format_spec_does_not_change_the_placeholder(self):
        secret = SecretToken(SECRET_VALUE)

        assert f"{secret:>60}" == repr(secret)

    def test_rendering_discloses_neither_a_prefix_nor_the_length(self):
        rendered = repr(SecretToken(SECRET_VALUE))

        assert SECRET_VALUE[:8] not in rendered
        assert str(len(SECRET_VALUE)) not in rendered

    def test_an_empty_token_renders_the_same_as_a_populated_one(self):
        assert repr(SecretToken("")) == repr(SecretToken(SECRET_VALUE))


class TestSecretTokenAccess:
    def test_reveal_returns_the_wire_ready_value(self):
        assert SecretToken(SECRET_VALUE).reveal() == SECRET_VALUE

    def test_the_value_is_stripped_once_in_the_constructor(self):
        assert SecretToken(f"  {SECRET_VALUE}\n").reveal() == SECRET_VALUE

    def test_it_is_not_a_str_subclass(self):
        # A str subclass would keep working silently in f-strings and %
        # formatting, which is the exact failure mode being removed.
        assert not isinstance(SecretToken(SECRET_VALUE), str)

    def test_a_missed_call_site_fails_naming_reveal(self):
        secret = SecretToken(SECRET_VALUE)

        with pytest.raises(AttributeError, match=r"reveal\(\)"):
            secret.strip()

    def test_it_carries_no_instance_dict(self):
        assert not hasattr(SecretToken(SECRET_VALUE), "__dict__")

    def test_it_is_immutable(self):
        secret = SecretToken(SECRET_VALUE)

        with pytest.raises(AttributeError, match="immutable"):
            secret._value = "replaced"

    def test_it_does_not_compare_equal_to_the_equivalent_str(self):
        assert SecretToken(SECRET_VALUE) != SECRET_VALUE

    def test_the_value_cannot_be_deleted(self):
        secret = SecretToken(SECRET_VALUE)

        with pytest.raises(AttributeError, match="immutable"):
            del secret._value

    def test_a_missing_dunder_reports_itself_plainly(self):
        # Protocol probes such as copy's look up dunders and expect a bare
        # AttributeError; answering those with the reveal() advice would
        # turn a normal negative lookup into a confusing message.
        secret = SecretToken(SECRET_VALUE)

        assert not hasattr(secret, "__wrapped__")
        with pytest.raises(AttributeError, match="^__wrapped__$"):
            secret.__getattr__("__wrapped__")


class TestSecretTokenTruthiness:
    @pytest.mark.parametrize("value", ["", "   ", "\n\t"])
    def test_a_blank_token_is_falsey(self, value):
        assert not SecretToken(value)

    def test_a_populated_token_is_truthy(self):
        assert SecretToken(SECRET_VALUE)


class TestAsSecretToken:
    def test_a_str_is_wrapped(self):
        assert isinstance(as_secret_token(SECRET_VALUE), SecretToken)

    def test_wrapping_is_idempotent(self):
        secret = SecretToken(SECRET_VALUE)

        assert as_secret_token(secret) is secret

    def test_the_constructor_also_accepts_a_secret_token(self):
        assert SecretToken(SecretToken(SECRET_VALUE)).reveal() == SECRET_VALUE


class TestSecretTokenDoesNotDecayToStr:
    def test_copy_returns_a_secret_token(self):
        secret = SecretToken(SECRET_VALUE)

        assert copy.copy(secret) is secret

    def test_deepcopy_returns_a_secret_token(self):
        secret = SecretToken(SECRET_VALUE)

        assert copy.deepcopy(secret) is secret

    @pytest.mark.parametrize("protocol", [0, 2, pickle.HIGHEST_PROTOCOL])
    def test_pickling_is_refused(self, protocol):
        with pytest.raises(TypeError, match="cannot be pickled"):
            pickle.dumps(SecretToken(SECRET_VALUE), protocol=protocol)


class TestWireFormatIsUnchanged:
    @respx.mock
    def test_the_bearer_header_carries_the_exact_stripped_token(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        PicSureClient(base_url=BASE_URL, token=f"  {SECRET_VALUE}  ").get_json(
            "/some/path"
        )

        assert route.calls[0].request.headers["authorization"] == (
            f"Bearer {SECRET_VALUE}"
        )

    @respx.mock
    def test_a_secret_token_and_a_str_produce_the_same_request(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        PicSureClient(base_url=BASE_URL, token=SECRET_VALUE).get_json("/some/path")
        PicSureClient(base_url=BASE_URL, token=SecretToken(SECRET_VALUE)).get_json(
            "/some/path"
        )

        first, second = (call.request.headers for call in route.calls)
        assert first["authorization"] == second["authorization"]
        assert first["request-source"] == second["request-source"] == "Authorized"

    @respx.mock
    def test_the_request_source_switch_still_keys_on_truthiness(self):
        route = respx.get(f"{BASE_URL}/some/path").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        PicSureClient(base_url=BASE_URL, token="   ").get_json("/some/path")

        request = route.calls[0].request
        assert "authorization" not in request.headers
        assert request.headers["request-source"] == "Open"
