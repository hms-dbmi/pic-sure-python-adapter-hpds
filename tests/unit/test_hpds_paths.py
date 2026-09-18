from __future__ import annotations

import pytest

from picsure._services._hpds_paths import (
    query_id_from_submit_response,
    query_metadata_path,
    query_result_path,
    query_status_path,
    query_submit_path,
    server_id_segment,
)
from picsure.errors import PicSureQueryError, PicSureValidationError

QUERY_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
OTHER_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
THIRD_ID = "6b2f4d1e-9c3a-4f5b-8d7e-1a2b3c4d5e6f"
TRAVERSAL = "../../../psama/user/me"


class TestSubmitResponsePreferenceOrder:
    def test_picsure_result_id_wins(self):
        response = {
            "picsureResultId": QUERY_ID,
            "resourceResultId": OTHER_ID,
            "queryId": THIRD_ID,
        }
        assert query_id_from_submit_response(response, operation="the export") == (
            QUERY_ID
        )

    def test_resource_result_id_is_read_next(self):
        response = {"resourceResultId": OTHER_ID, "queryId": THIRD_ID}
        assert query_id_from_submit_response(response, operation="the export") == (
            OTHER_ID
        )

    def test_query_id_is_read_last(self):
        response = {"queryId": THIRD_ID}
        assert query_id_from_submit_response(response, operation="the export") == (
            THIRD_ID
        )

    def test_an_empty_or_non_string_field_is_skipped(self):
        response = {"picsureResultId": "", "resourceResultId": 7, "queryId": THIRD_ID}
        assert query_id_from_submit_response(response, operation="the export") == (
            THIRD_ID
        )

    def test_no_id_at_all_names_the_expected_field(self):
        with pytest.raises(PicSureQueryError, match="picsureResultId"):
            query_id_from_submit_response({"unrelated": "x"}, operation="the export")

    def test_an_uppercase_uuid_is_canonicalized(self):
        response = {"picsureResultId": QUERY_ID.upper()}
        assert query_id_from_submit_response(response, operation="the export") == (
            QUERY_ID
        )


class TestServerSuppliedIdIsRefused:
    """A server id that is not a UUID is a malformed response, not bad input."""

    def test_a_traversal_id_raises_a_query_error(self):
        with pytest.raises(PicSureQueryError) as excinfo:
            query_id_from_submit_response(
                {"picsureResultId": TRAVERSAL}, operation="the export"
            )

        assert TRAVERSAL in str(excinfo.value)
        assert not isinstance(excinfo.value, PicSureValidationError)

    def test_a_non_uuid_id_raises_a_query_error(self):
        with pytest.raises(PicSureQueryError, match="not a UUID"):
            query_id_from_submit_response(
                {"picsureResultId": "abc-123"}, operation="the export"
            )

    def test_a_blank_identifier_is_refused(self):
        with pytest.raises(PicSureQueryError, match="missing or is not a string"):
            server_id_segment("   ", description="The record identifier")

    def test_a_non_string_identifier_is_refused(self):
        with pytest.raises(PicSureQueryError, match="missing or is not a string"):
            server_id_segment({"uuid": QUERY_ID}, description="The record identifier")


class TestQueryLifecyclePaths:
    def test_submit_path_is_the_versioned_query_route(self):
        assert query_submit_path("auth") == "/picsure/hpds/auth/v3/query"

    @pytest.mark.parametrize(
        ("builder", "suffix"),
        [
            (query_status_path, "status"),
            (query_result_path, "result"),
            (query_metadata_path, "metadata"),
        ],
    )
    def test_a_uuid_reaches_the_path_unchanged(self, builder, suffix):
        assert builder("auth", QUERY_ID) == (
            f"/picsure/hpds/auth/v3/query/{QUERY_ID}/{suffix}"
        )

    @pytest.mark.parametrize(
        "builder",
        [query_status_path, query_result_path, query_metadata_path],
    )
    def test_a_slash_cannot_leave_its_segment(self, builder):
        path = builder("auth", TRAVERSAL)

        assert "/../" not in path
        assert "%2F" in path
