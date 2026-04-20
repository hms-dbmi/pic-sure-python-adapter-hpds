import pandas as pd
import pytest

import picsure
from picsure import ClauseType, createClause

from .conftest import requires_auth


class TestRunQueryLive:
    def test_count_returns_int(self, test_token, test_platform, test_concept_path):
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause(test_concept_path, type=ClauseType.REQUIRE)
        result = session.runQuery(clause, type="count")
        assert isinstance(result, int)
        assert result >= 0

    def test_participant_returns_dataframe(
        self, test_token, test_platform, test_concept_path
    ):
        if not requires_auth(test_platform):
            pytest.skip(
                "DATAFRAME result type is authorized-only; "
                "open-access platforms don't support participant queries."
            )
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause(test_concept_path, type=ClauseType.REQUIRE)
        df = session.runQuery(clause, type="participant")
        assert isinstance(df, pd.DataFrame)

    def test_invalid_type_raises(self, test_token, test_platform, test_concept_path):
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause(test_concept_path, type=ClauseType.REQUIRE)
        with pytest.raises(picsure.PicSureError):
            session.runQuery(clause, type="invalid_type")
