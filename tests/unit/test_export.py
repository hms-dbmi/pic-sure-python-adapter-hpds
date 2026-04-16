from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

from picsure._models.clause import Clause, ClauseType
from picsure._services.export import export_csv, export_pfb, export_tsv
from picsure._transport.client import PicSureClient
from picsure.errors import PicSureConnectionError

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
RESOURCE_UUID = "resource-uuid-aaaa-1111"
QUERY_URL = f"{BASE_URL}/picsure/query/sync"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _simple_clause() -> Clause:
    return Clause(keys=["\\phs1\\sex\\"], type=ClauseType.FILTER, categories=["Male"])


class TestExportPFB:
    @respx.mock
    def test_writes_bytes_to_file(self, tmp_path):
        pfb_bytes = b"\x00PFB_MOCK_DATA\x01\x02\x03"
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=pfb_bytes))

        output = tmp_path / "test.pfb"
        client = _make_client()
        export_pfb(client, RESOURCE_UUID, _simple_clause(), output)

        assert output.exists()
        assert output.read_bytes() == pfb_bytes

    @respx.mock
    def test_sends_pfb_result_type(self):
        route = respx.post(QUERY_URL).mock(
            return_value=httpx.Response(200, content=b"pfb")
        )
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pfb") as f:
            client = _make_client()
            export_pfb(client, RESOURCE_UUID, _simple_clause(), f.name)

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["expectedResultType"] == "PFB"
        assert body["resourceUUID"] == RESOURCE_UUID

    @respx.mock
    def test_server_error_raises_connection_error(self, tmp_path):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(500, text="error"))
        client = _make_client()
        with pytest.raises(PicSureConnectionError, match="PFB"):
            export_pfb(client, RESOURCE_UUID, _simple_clause(), tmp_path / "out.pfb")

    @respx.mock
    def test_accepts_string_path(self, tmp_path):
        respx.post(QUERY_URL).mock(return_value=httpx.Response(200, content=b"data"))
        output = str(tmp_path / "test.pfb")
        client = _make_client()
        export_pfb(client, RESOURCE_UUID, _simple_clause(), output)
        assert Path(output).exists()


class TestExportCSV:
    def test_writes_csv_file(self, tmp_path):
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        output = tmp_path / "test.csv"
        export_csv(df, output)

        assert output.exists()
        content = output.read_text()
        assert "id,name" in content
        assert "1,A" in content
        assert "2,B" in content

    def test_no_index_column(self, tmp_path):
        df = pd.DataFrame({"x": [1]})
        output = tmp_path / "test.csv"
        export_csv(df, output)

        content = output.read_text()
        lines = content.strip().splitlines()
        assert lines[0] == "x"
        assert lines[1] == "1"

    def test_accepts_string_path(self, tmp_path):
        df = pd.DataFrame({"x": [1]})
        output = str(tmp_path / "test.csv")
        export_csv(df, output)
        assert Path(output).exists()

    def test_empty_dataframe(self, tmp_path):
        df = pd.DataFrame(columns=["a", "b"])
        output = tmp_path / "empty.csv"
        export_csv(df, output)

        content = output.read_text().strip()
        assert content == "a,b"


class TestExportTSV:
    def test_writes_tsv_file(self, tmp_path):
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        output = tmp_path / "test.tsv"
        export_tsv(df, output)

        assert output.exists()
        content = output.read_text()
        assert "id\tname" in content
        assert "1\tA" in content

    def test_no_index_column(self, tmp_path):
        df = pd.DataFrame({"x": [1]})
        output = tmp_path / "test.tsv"
        export_tsv(df, output)

        content = output.read_text()
        lines = content.strip().splitlines()
        assert lines[0] == "x"
        assert lines[1] == "1"

    def test_accepts_string_path(self, tmp_path):
        df = pd.DataFrame({"x": [1]})
        output = str(tmp_path / "test.tsv")
        export_tsv(df, output)
        assert Path(output).exists()
