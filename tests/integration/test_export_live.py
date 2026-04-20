import pytest

import picsure
from picsure import ClauseType, createClause
from picsure._transport.platforms import Platform


def _requires_auth(test_platform: Platform | str) -> bool:
    if isinstance(test_platform, Platform):
        return test_platform.requires_auth
    return True


class TestExportLive:
    def test_export_csv(self, test_token, test_platform, test_concept_path, tmp_path):
        if not _requires_auth(test_platform):
            pytest.skip(
                "exportCSV depends on a participant-query DataFrame, "
                "which is authorized-only."
            )
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause(test_concept_path, type=ClauseType.REQUIRE)
        df = session.runQuery(clause, type="participant")
        output = tmp_path / "test.csv"
        session.exportCSV(df, output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_export_tsv(self, test_token, test_platform, test_concept_path, tmp_path):
        if not _requires_auth(test_platform):
            pytest.skip(
                "exportTSV depends on a participant-query DataFrame, "
                "which is authorized-only."
            )
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause(test_concept_path, type=ClauseType.REQUIRE)
        df = session.runQuery(clause, type="participant")
        output = tmp_path / "test.tsv"
        session.exportTSV(df, output)
        assert output.exists()
        assert output.stat().st_size > 0
