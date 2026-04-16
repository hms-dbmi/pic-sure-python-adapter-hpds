import picsure
from picsure import ClauseType, createClause


class TestExportLive:
    def test_export_csv(self, test_token, test_platform, tmp_path):
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause("\\age\\", type=ClauseType.ANYRECORD)
        df = session.runQuery(clause, type="participant")
        output = tmp_path / "test.csv"
        session.exportCSV(df, output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_export_tsv(self, test_token, test_platform, tmp_path):
        session = picsure.connect(platform=test_platform, token=test_token)
        clause = createClause("\\age\\", type=ClauseType.ANYRECORD)
        df = session.runQuery(clause, type="participant")
        output = tmp_path / "test.tsv"
        session.exportTSV(df, output)
        assert output.exists()
        content = output.read_text()
        assert "\t" in content
