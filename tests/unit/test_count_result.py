import dataclasses

import pytest

from picsure._models.count_result import CountResult


class TestCountResult:
    def test_exact_value(self):
        r = CountResult(value=42, margin=None, cap=None, raw="42")
        assert r.value == 42
        assert r.margin is None
        assert r.cap is None
        assert r.obfuscated is False

    def test_noisy_value(self):
        r = CountResult(value=11309, margin=3, cap=None, raw="11309 ±3")
        assert r.value == 11309
        assert r.margin == 3
        assert r.cap is None
        assert r.obfuscated is True

    def test_suppressed_value(self):
        r = CountResult(value=None, margin=None, cap=10, raw="< 10")
        assert r.value is None
        assert r.margin is None
        assert r.cap == 10
        assert r.obfuscated is True

    def test_frozen(self):
        r = CountResult(value=1, margin=None, cap=None, raw="1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.value = 2  # type: ignore[misc]

    def test_exported_from_top_level(self):
        import picsure

        assert picsure.CountResult is CountResult
