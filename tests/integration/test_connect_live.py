import pandas as pd
import pytest

import picsure
from picsure._models.session import Session
from picsure._transport.platforms import Platform


def _requires_auth(test_platform: Platform | str) -> bool:
    if isinstance(test_platform, Platform):
        return test_platform.requires_auth
    return True


class TestConnectLive:
    def test_connect_returns_session(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        assert isinstance(session, Session)

    def test_connect_session_has_email(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        if _requires_auth(test_platform):
            assert "@" in session._user_email
        else:
            assert session._user_email == "anonymous"

    def test_connect_session_has_resources(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        df = session.getResourceID()
        assert isinstance(df, pd.DataFrame)
        if _requires_auth(test_platform):
            assert len(df) > 0

    def test_connect_prints_success(self, test_token, test_platform, capsys):
        picsure.connect(platform=test_platform, token=test_token)
        captured = capsys.readouterr().out.lower()
        assert "successfully connected" in captured
        if _requires_auth(test_platform):
            assert "token expires" in captured
        else:
            assert "open access" in captured

    def test_connect_bad_token_raises_error(self, test_platform):
        if not _requires_auth(test_platform):
            pytest.skip("Open-access platforms don't validate tokens on connect.")
        with pytest.raises(picsure.PicSureError):
            picsure.connect(platform=test_platform, token="definitely-invalid-token")
