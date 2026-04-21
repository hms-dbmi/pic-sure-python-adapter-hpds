from pathlib import Path
from unittest.mock import patch

import httpx
import pandas as pd
import pytest
import respx

from picsure._models.clause import Clause, ClauseType
from picsure._services.export import export_csv, export_pfb, export_tsv
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

BASE_URL = "https://test.example.com"
TOKEN = "test-token"
RESOURCE_UUID = "resource-uuid-aaaa-1111"
QUERY_ID = "abc-123"

SUBMIT_URL = f"{BASE_URL}/picsure/v3/query"
STATUS_URL = f"{BASE_URL}/picsure/v3/query/{QUERY_ID}/status"
RESULT_URL = f"{BASE_URL}/picsure/v3/query/{QUERY_ID}/result"


def _make_client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _simple_clause() -> Clause:
    return Clause(keys=["\\phs1\\sex\\"], type=ClauseType.FILTER, categories=["Male"])


def _submit_ok() -> httpx.Response:
    return httpx.Response(200, json={"picsureResultId": QUERY_ID})


def _status(value: str) -> httpx.Response:
    return httpx.Response(200, json={"status": value})


class TestExportPFBHappyPath:
    @respx.mock
    def test_writes_bytes_to_file_after_polling(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(
            side_effect=[_status("PENDING"), _status("AVAILABLE")]
        )
        respx.post(RESULT_URL).mock(
            return_value=httpx.Response(200, content=b"pfb_content")
        )

        output = tmp_path / "out.pfb"
        with patch("picsure._services.export.time.sleep") as sleep_mock:
            export_pfb(_make_client(), RESOURCE_UUID, _simple_clause(), output)

        assert output.exists()
        assert output.read_bytes() == b"pfb_content"
        # .part should have been promoted away
        assert not (tmp_path / "out.pfb.part").exists()
        # One poll between PENDING and AVAILABLE means one sleep at 1s.
        sleep_mock.assert_called_once_with(1.0)

    @respx.mock
    def test_sends_pfb_result_type_and_resource_uuid(self, tmp_path):
        import json

        submit_route = respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(return_value=_status("AVAILABLE"))
        respx.post(RESULT_URL).mock(return_value=httpx.Response(200, content=b"pfb"))

        with patch("picsure._services.export.time.sleep"):
            export_pfb(
                _make_client(),
                RESOURCE_UUID,
                _simple_clause(),
                tmp_path / "out.pfb",
            )

        body = json.loads(submit_route.calls[0].request.content)
        assert body["query"]["expectedResultType"] == "DATAFRAME_PFB"
        assert body["resourceUUID"] == RESOURCE_UUID

    @respx.mock
    def test_accepts_string_path(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(return_value=_status("AVAILABLE"))
        respx.post(RESULT_URL).mock(return_value=httpx.Response(200, content=b"data"))

        output = str(tmp_path / "test.pfb")
        with patch("picsure._services.export.time.sleep"):
            export_pfb(_make_client(), RESOURCE_UUID, _simple_clause(), output)
        assert Path(output).exists()


class TestExportPFBBackoff:
    @respx.mock
    def test_exponential_backoff_sequence(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        # 6 PENDING responses, then AVAILABLE.
        respx.post(STATUS_URL).mock(
            side_effect=[
                _status("PENDING"),
                _status("PENDING"),
                _status("PENDING"),
                _status("PENDING"),
                _status("PENDING"),
                _status("PENDING"),
                _status("AVAILABLE"),
            ]
        )
        respx.post(RESULT_URL).mock(return_value=httpx.Response(200, content=b"x"))

        with patch("picsure._services.export.time.sleep") as sleep_mock:
            export_pfb(
                _make_client(),
                RESOURCE_UUID,
                _simple_clause(),
                tmp_path / "out.pfb",
            )

        intervals = [call.args[0] for call in sleep_mock.call_args_list]
        assert intervals == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]

    @respx.mock
    def test_backoff_caps_at_60_seconds(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(
            side_effect=[_status("PENDING")] * 10 + [_status("AVAILABLE")]
        )
        respx.post(RESULT_URL).mock(return_value=httpx.Response(200, content=b"x"))

        with (
            patch("picsure._services.export.time.sleep") as sleep_mock,
            patch(
                "picsure._services.export.time.monotonic",
                side_effect=list(range(100)),
            ),
        ):
            export_pfb(
                _make_client(),
                RESOURCE_UUID,
                _simple_clause(),
                tmp_path / "out.pfb",
            )

        intervals = [call.args[0] for call in sleep_mock.call_args_list]
        # After the 6th interval (32s), subsequent values must all be 60s.
        assert intervals[:6] == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
        assert all(v == 60.0 for v in intervals[6:])


class TestExportPFBTimeout:
    @respx.mock
    def test_total_timeout_raises_after_10_minutes(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(return_value=_status("PENDING"))

        # Patching export.time.monotonic mutates the real time module, so
        # PicSureClient._request (dev-mode timing) also consumes values.
        # Feed a generator that yields 0.0 until export's elapsed check,
        # then 700.0 (>= 600) to trip the timeout.
        def _monotonic_values():
            # Submit's _request(start), export's start, status' _request(start)
            yield from (0.0, 0.0, 0.0)
            # Export's elapsed check and anything after.
            while True:
                yield 700.0

        with (
            patch("picsure._services.export.time.sleep"),
            patch(
                "picsure._services.export.time.monotonic",
                side_effect=_monotonic_values(),
            ),
            pytest.raises(PicSureConnectionError, match="10 minutes"),
        ):
            export_pfb(
                _make_client(),
                RESOURCE_UUID,
                _simple_clause(),
                tmp_path / "out.pfb",
            )

        assert not (tmp_path / "out.pfb").exists()
        assert not (tmp_path / "out.pfb.part").exists()


class TestExportPFB4xx:
    @respx.mock
    def test_submit_400_raises_validation_error(self, tmp_path):
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(400, json={"error": "bad query"})
        )

        output = tmp_path / "out.pfb"
        with pytest.raises(PicSureValidationError):
            export_pfb(_make_client(), RESOURCE_UUID, _simple_clause(), output)

        assert not output.exists()
        assert not (tmp_path / "out.pfb.part").exists()

    @respx.mock
    def test_status_404_raises_query_error(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(return_value=httpx.Response(404, text=""))

        output = tmp_path / "out.pfb"
        with (
            patch("picsure._services.export.time.sleep"),
            pytest.raises(PicSureQueryError),
        ):
            export_pfb(_make_client(), RESOURCE_UUID, _simple_clause(), output)

        assert not output.exists()
        assert not (tmp_path / "out.pfb.part").exists()

    @respx.mock
    def test_result_422_raises_validation_error(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(return_value=_status("AVAILABLE"))
        respx.post(RESULT_URL).mock(
            return_value=httpx.Response(422, json={"error": "bad state"})
        )

        output = tmp_path / "out.pfb"
        with (
            patch("picsure._services.export.time.sleep"),
            pytest.raises(PicSureValidationError),
        ):
            export_pfb(_make_client(), RESOURCE_UUID, _simple_clause(), output)

        assert not output.exists()
        assert not (tmp_path / "out.pfb.part").exists()

    @respx.mock
    def test_server_error_on_submit_raises_connection_error(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=httpx.Response(500, text="error"))

        output = tmp_path / "out.pfb"
        with pytest.raises(PicSureConnectionError):
            export_pfb(_make_client(), RESOURCE_UUID, _simple_clause(), output)

        assert not output.exists()


class TestExportPFBAtomicWrite:
    @respx.mock
    def test_disk_write_failure_removes_partial(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(return_value=_status("AVAILABLE"))
        respx.post(RESULT_URL).mock(
            return_value=httpx.Response(200, content=b"pfb_content")
        )

        output = tmp_path / "out.pfb"
        part = tmp_path / "out.pfb.part"

        # Simulate a disk failure during the final os.replace step.
        with (
            patch("picsure._services.export.time.sleep"),
            patch(
                "picsure._services.export.os.replace",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(PicSureConnectionError, match="out.pfb"),
        ):
            export_pfb(_make_client(), RESOURCE_UUID, _simple_clause(), output)

        # Neither the final file nor the .part file should remain.
        assert not output.exists()
        assert not part.exists()

    @respx.mock
    def test_stream_write_failure_removes_partial(self, tmp_path):
        respx.post(SUBMIT_URL).mock(return_value=_submit_ok())
        respx.post(STATUS_URL).mock(return_value=_status("AVAILABLE"))
        respx.post(RESULT_URL).mock(
            return_value=httpx.Response(200, content=b"pfb_content")
        )

        output = tmp_path / "out.pfb"
        part = tmp_path / "out.pfb.part"

        def boom(_response, _part_path):  # noqa: ANN001
            # Simulate a partial write that already left bytes behind.
            part.write_bytes(b"partial")
            raise OSError("no space left on device")

        with (
            patch("picsure._services.export.time.sleep"),
            patch("picsure._services.export._stream_to_file", side_effect=boom),
            pytest.raises(PicSureConnectionError, match="out.pfb"),
        ):
            export_pfb(_make_client(), RESOURCE_UUID, _simple_clause(), output)

        assert not output.exists()
        assert not part.exists()


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
