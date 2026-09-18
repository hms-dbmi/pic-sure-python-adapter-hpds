from __future__ import annotations

import pytest

from picsure._services._hpds_paths import (
    canonical_server_id,
    named_dataset_item_path,
    query_id_from_submit_response,
    query_metadata_path,
    query_prefix,
    query_result_path,
    query_status_path,
    query_submit_path,
    search_values_path,
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

    def test_the_message_does_not_claim_no_request_was_sent(self):
        """The value came back from the server, so a request had been sent."""
        with pytest.raises(PicSureQueryError) as excinfo:
            canonical_server_id("abc-123", description="The record identifier")

        assert "not sent" not in str(excinfo.value)
        assert "malformed response" in str(excinfo.value)

    def test_a_blank_identifier_is_refused(self):
        with pytest.raises(PicSureQueryError, match="missing or is not a string"):
            canonical_server_id("   ", description="The record identifier")

    def test_a_non_string_identifier_is_refused(self):
        with pytest.raises(PicSureQueryError, match="missing or is not a string"):
            canonical_server_id({"uuid": QUERY_ID}, description="The record identifier")


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


class TestTheCanonicalIdIsNotAPathSegment:
    """The validator returns the id; a path builder is what escapes it."""

    def test_a_query_id_round_trips_unescaped(self):
        assert canonical_server_id(QUERY_ID, description="The query id") == QUERY_ID

    def test_an_uppercase_id_comes_back_canonical(self):
        assert (
            canonical_server_id(QUERY_ID.upper(), description="The query id")
            == QUERY_ID
        )

    def test_a_named_dataset_uuid_round_trips_unescaped(self):
        assert (
            canonical_server_id(OTHER_ID, description="The record identifier")
            == OTHER_ID
        )

    @pytest.mark.parametrize(
        ("builder", "suffix"),
        [
            (query_status_path, "status"),
            (query_result_path, "result"),
            (query_metadata_path, "metadata"),
        ],
    )
    def test_a_validated_id_is_escaped_exactly_once(self, builder, suffix):
        validated = canonical_server_id(QUERY_ID, description="The query id")

        assert builder("auth", validated) == (
            f"/picsure/hpds/auth/v3/query/{QUERY_ID}/{suffix}"
        )
        assert "%25" not in builder("auth", validated)


class TestNamedDatasetItemPath:
    def test_a_uuid_reaches_the_path_unchanged(self):
        assert named_dataset_item_path(OTHER_ID) == (
            f"/picsure/operations/dataset/named/{OTHER_ID}"
        )

    def test_it_gains_no_trailing_slash(self):
        assert not named_dataset_item_path(OTHER_ID).endswith("/")

    def test_a_slash_cannot_leave_its_segment(self):
        path = named_dataset_item_path(TRAVERSAL)

        assert "/../" not in path
        assert "%2F" in path


class TestBackendIsCheckedBeforeItIsInterpolated:
    """An unrecognized backend would otherwise 404 every request silently."""

    @pytest.mark.parametrize("backend", ["", "AUTH", "auth/../open", "authorized"])
    def test_query_prefix_refuses_it(self, backend):
        with pytest.raises(PicSureValidationError, match="backend must be one of"):
            query_prefix(backend, v3=True)

    @pytest.mark.parametrize("backend", ["", "AUTH", "auth/../open", "authorized"])
    def test_search_values_path_refuses_it(self, backend):
        with pytest.raises(PicSureValidationError, match="backend must be one of"):
            search_values_path(backend)

    @pytest.mark.parametrize(
        "builder",
        [query_status_path, query_result_path, query_metadata_path],
    )
    def test_the_lifecycle_builders_refuse_it(self, builder):
        with pytest.raises(PicSureValidationError, match="backend must be one of"):
            builder("authorized", QUERY_ID)

    def test_the_submit_path_refuses_it(self):
        with pytest.raises(PicSureValidationError, match="backend must be one of"):
            query_submit_path("authorized")

    @pytest.mark.parametrize("backend", ["auth", "open"])
    def test_both_real_backends_are_accepted(self, backend):
        assert query_submit_path(backend) == f"/picsure/hpds/{backend}/v3/query"
        assert search_values_path(backend) == (f"/picsure/hpds/{backend}/search/values")
