import pandas as pd

import picsure
from picsure._models.session import Session


class TestConnectLive:
    def test_connect_returns_session(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        assert isinstance(session, Session)

    def test_connect_session_has_email(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        assert "@" in session._user_email

    def test_connect_session_has_resources(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        df = session.getResourceID()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_connect_prints_success(self, test_token, test_platform, capsys):
        picsure.connect(platform=test_platform, token=test_token)
        captured = capsys.readouterr()
        assert "successfully connected" in captured.out.lower()
        assert "token expires" in captured.out.lower()

    def test_connect_bad_token_raises_error(self, test_platform):
        with __import__("pytest").raises(picsure.PicSureError):
            picsure.connect(platform=test_platform, token="definitely-invalid-token")
