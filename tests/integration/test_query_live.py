import pandas as pd

import picsure
from picsure import ClauseType, createClause


class TestRunQueryLive:
    def test_count_returns_int(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause("\\age\\", type=ClauseType.ANYRECORD)
        result = session.runQuery(clause, type="count")
        assert isinstance(result, int)
        assert result >= 0

    def test_participant_returns_dataframe(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause("\\age\\", type=ClauseType.ANYRECORD)
        df = session.runQuery(clause, type="participant")
        assert isinstance(df, pd.DataFrame)

    def test_invalid_type_raises(self, test_token, test_platform):
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause("\\age\\", type=ClauseType.ANYRECORD)
        with __import__("pytest").raises(picsure.PicSureError):
            session.runQuery(clause, type="invalid_type")
