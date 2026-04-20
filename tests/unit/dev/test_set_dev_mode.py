import os

import pytest

import picsure


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("PICSURE_DEV_MODE", raising=False)


def test_set_dev_mode_true_sets_env():
    picsure.set_dev_mode(True)
    assert os.environ["PICSURE_DEV_MODE"] == "1"


def test_set_dev_mode_false_unsets_env():
    os.environ["PICSURE_DEV_MODE"] = "1"
    picsure.set_dev_mode(False)
    assert "PICSURE_DEV_MODE" not in os.environ


def test_set_dev_mode_false_when_already_unset_is_noop():
    picsure.set_dev_mode(False)
    assert "PICSURE_DEV_MODE" not in os.environ


def test_set_dev_mode_is_exported_from_package():
    assert "set_dev_mode" in picsure.__all__
