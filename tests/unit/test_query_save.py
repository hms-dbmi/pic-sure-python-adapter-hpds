from __future__ import annotations

import json

import httpx
import pytest
import respx

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._services._hpds_paths import query_prefix
from picsure._services.query_save import (
    _NAME_PUNCTUATION,
    _NAMED_DATASET_COLLECTION_PATH,
    _NAMED_DATASET_ITEM_PATH,
    _validate_name,
    save_query_by_name,
)
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureQueryError,
    PicSureServerError,
    PicSureValidationError,
)

BASE_URL = "https://api.example.com"
TOKEN = "test-token"
QUERY_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
NAMED_DATASET_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

LIST_URL = f"{BASE_URL}{_NAMED_DATASET_COLLECTION_PATH}"
SUBMIT_URL = f"{BASE_URL}{query_prefix('auth', v3=True)}/query"
SAVE_URL = f"{BASE_URL}{_NAMED_DATASET_COLLECTION_PATH}"
_ITEM_URL = f"{BASE_URL}" + _NAMED_DATASET_ITEM_PATH.format(
    named_dataset_id=NAMED_DATASET_ID
)


def _client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _clause() -> Clause:
    return Clause(keys=["\\a\\"], type=PhenotypicFilterType.FILTER, categories=["x"])


def _mock_overwrite_listing() -> respx.Route:
    """Mock a listing with one record named "fun", so overwrite has a target."""
    return respx.get(LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "uuid": NAMED_DATASET_ID,
                    "name": "fun",
                    "queryId": "qid-old",
                    "archived": False,
                    "metadata": {},
                }
            ],
        )
    )


class TestSaveQueryByNameHappyPath:
    @respx.mock
    def test_creates_new_named_dataset(self):
        listing = respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        submit = respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        save = respx.post(SAVE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": NAMED_DATASET_ID,
                    "name": "fun",
                    "queryId": QUERY_ID,
                    "user": "u",
                    "archived": False,
                    "metadata": {},
                },
            )
        )

        qid = save_query_by_name(
            _client(),
            _clause(),
            "fun",
            backend="auth",
        )

        assert qid == QUERY_ID
        assert listing.called
        assert submit.called
        assert save.called

        # Verify POST body to /dataset/named/ carries the fresh query id.
        save_body = json.loads(save.calls.last.request.content)
        assert save_body == {
            "queryId": QUERY_ID,
            "name": "fun",
            "archived": False,
            "metadata": {},
        }

    @respx.mock
    def test_tolerates_results_envelope_on_list(self):
        # Some shapes wrap the list in {"results": [...]}; we accept either.
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json={"results": []}))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        save = respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        qid = save_query_by_name(
            _client(),
            _clause(),
            "fun",
            backend="auth",
        )
        assert qid == QUERY_ID
        assert save.called

    @respx.mock
    def test_submit_response_uses_resource_result_id_when_only_field(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"resourceResultId": QUERY_ID})
        )
        respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        qid = save_query_by_name(
            _client(),
            _clause(),
            "fun",
            backend="auth",
        )
        assert qid == QUERY_ID


class TestSaveQueryByNameBodilessWrites:
    """The record is written before the response body is read.

    The operations service may answer the create with a bodiless 201 and
    the update with a 204, so neither may be reported as a failure: a
    caller who retried a "failed" save would meet the duplicate-name
    refusal for a record that is already there.
    """

    @respx.mock
    def test_create_answering_201_with_no_body_still_returns_the_query_id(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        save = respx.post(SAVE_URL).mock(return_value=httpx.Response(201))

        qid = save_query_by_name(_client(), _clause(), "fun", backend="auth")

        assert qid == QUERY_ID
        assert save.called

    @respx.mock
    def test_update_answering_204_still_returns_the_query_id(self):
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": NAMED_DATASET_ID,
                        "name": "fun",
                        "queryId": "qid-old",
                        "archived": False,
                        "metadata": {},
                    }
                ],
            )
        )
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        put = respx.put(
            f"{BASE_URL}{_NAMED_DATASET_ITEM_PATH.format(named_dataset_id=NAMED_DATASET_ID)}"
        ).mock(return_value=httpx.Response(204))

        qid = save_query_by_name(
            _client(),
            _clause(),
            "fun",
            backend="auth",
            overwrite=True,
        )

        assert qid == QUERY_ID
        assert put.called


class TestSaveQueryByNameDuplicates:
    @respx.mock
    def test_refuses_duplicate_without_overwrite(self):
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": NAMED_DATASET_ID,
                        "name": "fun",
                        "queryId": "qid-old",
                        "archived": False,
                        "metadata": {},
                    }
                ],
            )
        )
        # Make sure the submit/save endpoints aren't called.
        submit = respx.post(SUBMIT_URL).mock(return_value=httpx.Response(500))
        save = respx.post(SAVE_URL).mock(return_value=httpx.Response(500))

        with pytest.raises(PicSureValidationError, match="already exists"):
            save_query_by_name(
                _client(),
                _clause(),
                "fun",
                backend="auth",
            )

        assert not submit.called
        assert not save.called

    @respx.mock
    def test_overwrite_true_repoints_via_put_and_preserves_metadata(self):
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": NAMED_DATASET_ID,
                        "name": "fun",
                        "queryId": "qid-old",
                        "archived": True,
                        "metadata": {"tag": "v1"},
                    }
                ],
            )
        )
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        put = respx.put(
            f"{BASE_URL}{_NAMED_DATASET_ITEM_PATH.format(named_dataset_id=NAMED_DATASET_ID)}"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": NAMED_DATASET_ID,
                    "name": "fun",
                    "queryId": QUERY_ID,
                    "archived": True,
                    "metadata": {"tag": "v1"},
                },
            )
        )
        # The collection POST must NOT be called on the overwrite path.
        create = respx.post(SAVE_URL).mock(return_value=httpx.Response(500))

        qid = save_query_by_name(
            _client(),
            _clause(),
            "fun",
            backend="auth",
            overwrite=True,
        )

        assert qid == QUERY_ID
        assert put.called
        assert not create.called

        body = json.loads(put.calls.last.request.content)
        assert body == {
            "queryId": QUERY_ID,
            "name": "fun",
            "archived": True,
            "metadata": {"tag": "v1"},
        }

    @respx.mock
    def test_overwrite_matched_record_without_uuid_raises_query_error(self):
        # A matched record lacking a uuid must raise a clean PicSureQueryError
        # instead of crashing with KeyError on existing["uuid"].
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "name": "fun",
                        "queryId": "qid-old",
                        "archived": False,
                        "metadata": {},
                    }
                ],
            )
        )
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )

        with pytest.raises(PicSureQueryError, match="missing its identifier"):
            save_query_by_name(
                _client(),
                _clause(),
                "fun",
                backend="auth",
                overwrite=True,
            )

    @respx.mock
    def test_overwrite_true_creates_when_no_existing_record(self):
        # overwrite=True should still create-via-POST if there is no match.
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        save = respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        qid = save_query_by_name(
            _client(),
            _clause(),
            "fun",
            backend="auth",
            overwrite=True,
        )
        assert qid == QUERY_ID
        assert save.called


class TestSaveQueryByNameServerSuppliedIds:
    """Ids the listing and the submit carry are the server's, so both are checked.

    httpx normalizes ``..`` segments, so an unchecked uuid re-points the
    authenticated overwrite PUT at another route on the same host, and the
    save still reports success.
    """

    @respx.mock
    def test_a_traversal_uuid_in_the_listing_is_never_sent(self):
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "../../../psama/user/me",
                        "name": "fun",
                        "queryId": "qid-old",
                        "archived": False,
                        "metadata": {},
                    }
                ],
            )
        )
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )

        with pytest.raises(PicSureQueryError, match="not a UUID"):
            save_query_by_name(
                _client(), _clause(), "fun", backend="auth", overwrite=True
            )

        assert [call.request.method for call in respx.calls] == ["GET", "POST"]

    @respx.mock
    def test_a_traversal_query_id_in_the_submit_is_never_saved(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(
                200, json={"picsureResultId": "../../../psama/user/me"}
            )
        )
        save = respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        with pytest.raises(PicSureQueryError, match="not a UUID"):
            save_query_by_name(_client(), _clause(), "fun", backend="auth")

        assert not save.called

    @respx.mock
    def test_a_uuid_still_reaches_the_item_path(self):
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": NAMED_DATASET_ID,
                        "name": "fun",
                        "queryId": "qid-old",
                        "archived": False,
                        "metadata": {},
                    }
                ],
            )
        )
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        put = respx.put(
            f"{BASE_URL}{_NAMED_DATASET_ITEM_PATH.format(named_dataset_id=NAMED_DATASET_ID)}"
        ).mock(return_value=httpx.Response(204))

        qid = save_query_by_name(
            _client(), _clause(), "fun", backend="auth", overwrite=True
        )

        assert qid == QUERY_ID
        assert put.called


class TestSaveQueryByNameOpenAccess:
    def test_refuses_when_open_backend(self):
        # No network — the guard fires before any HTTP call.
        with pytest.raises(PicSureValidationError, match="open-access"):
            save_query_by_name(
                _client(),
                _clause(),
                "fun",
                backend="open",
            )


class TestSaveQueryByNameNameValidation:
    @pytest.mark.parametrize(
        "bad_name",
        [
            "name with <bad>",
            "name|with|pipes",
            "trailing*",
            "tab\there",
        ],
    )
    def test_rejects_bad_characters(self, bad_name):
        with pytest.raises(
            PicSureValidationError, match="characters the server rejects"
        ):
            save_query_by_name(
                _client(),
                _clause(),
                bad_name,
                backend="auth",
            )

    @pytest.mark.parametrize(
        "bad_name",
        [
            "My Query\n",
            "trailing newline\n",
        ],
    )
    def test_rejects_trailing_newline(self, bad_name):
        with pytest.raises(
            PicSureValidationError, match="characters the server rejects"
        ):
            save_query_by_name(
                _client(),
                _clause(),
                bad_name,
                backend="auth",
            )

    @pytest.mark.parametrize(
        "bad_name",
        [
            "café",
            "查询",
            "Ünïcode cohort",
            "naïve-2026",
            "Ω",
            "emoji \U0001f600",
        ],
    )
    def test_rejects_non_ascii_names(self, bad_name):
        r"""Names Python's Unicode ``\w`` accepts but Java's ASCII ``\w`` rejects."""
        with pytest.raises(PicSureValidationError, match="non-Latin"):
            save_query_by_name(
                _client(),
                _clause(),
                bad_name,
                backend="auth",
            )

    def test_non_ascii_name_rejected_before_any_request(self):
        """No respx mock is installed, so a name that slipped through fails later."""
        with pytest.raises(
            PicSureValidationError, match="characters the server rejects"
        ):
            save_query_by_name(_client(), _clause(), "café", backend="auth")

    def test_error_names_the_offending_characters(self):
        with pytest.raises(PicSureValidationError) as excinfo:
            save_query_by_name(_client(), _clause(), "café <x>", backend="auth")
        message = str(excinfo.value)
        assert "'é'" in message
        assert "'<'" in message
        assert "'>'" in message
        assert "no query was submitted" in message

    def test_error_states_what_is_allowed(self):
        with pytest.raises(PicSureValidationError) as excinfo:
            save_query_by_name(_client(), _clause(), "bad|name", backend="auth")
        assert "ASCII letters, digits, underscore, space" in str(excinfo.value)

    def test_rejects_empty_name(self):
        with pytest.raises(PicSureValidationError, match="non-empty"):
            save_query_by_name(
                _client(),
                _clause(),
                "",
                backend="auth",
            )

    def test_rejects_overlong_name(self):
        too_long = "a" * 256
        with pytest.raises(PicSureValidationError, match="255"):
            save_query_by_name(
                _client(),
                _clause(),
                too_long,
                backend="auth",
            )

    @pytest.mark.parametrize(
        "good_name",
        [
            "Cohort 2026-Q2",
            "ALS-11796 smoke",
            "name (v1)",
            "path/to/cohort",
            "weird?+=[]",
        ],
    )
    @respx.mock
    def test_accepts_allowed_characters(self, good_name):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        qid = save_query_by_name(
            _client(),
            _clause(),
            good_name,
            backend="auth",
        )
        assert qid == QUERY_ID


class TestSaveQueryByNameTransportErrors:
    @respx.mock
    def test_listing_401_raises_auth_error(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(401, text="nope"))

        with pytest.raises(PicSureAuthError):
            save_query_by_name(
                _client(),
                _clause(),
                "fun",
                backend="auth",
            )

    @respx.mock
    def test_submit_400_raises_validation_error(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(return_value=httpx.Response(400, text="bad query"))

        with pytest.raises(PicSureValidationError, match="submit"):
            save_query_by_name(
                _client(),
                _clause(),
                "fun",
                backend="auth",
            )

    @respx.mock
    def test_save_500_raises_connection_error(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        respx.post(SAVE_URL).mock(return_value=httpx.Response(500, text="boom"))

        with pytest.raises(PicSureConnectionError):
            save_query_by_name(
                _client(),
                _clause(),
                "fun",
                backend="auth",
            )

    @respx.mock
    def test_overwrite_put_500_raises_server_error_naming_the_update(self):
        """A failed overwrite must not be reported as a completed save.

        The bodiless-write handler directly above this one returns on an
        empty body, so a genuine failure on the PUT has to be seen to fail:
        swallowing it would hand back a query id for a record still
        pointing at the previous query.
        """
        _mock_overwrite_listing()
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        put = respx.put(_ITEM_URL).mock(return_value=httpx.Response(500, text="boom"))

        with pytest.raises(PicSureServerError) as excinfo:
            save_query_by_name(
                _client(), _clause(), "fun", backend="auth", overwrite=True
            )

        assert put.called
        assert "the saved-query update" in str(excinfo.value)

    @respx.mock
    def test_overwrite_put_401_raises_an_auth_error(self):
        _mock_overwrite_listing()
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": QUERY_ID})
        )
        put = respx.put(_ITEM_URL).mock(return_value=httpx.Response(401, text="nope"))

        with pytest.raises(PicSureAuthError):
            save_query_by_name(
                _client(), _clause(), "fun", backend="auth", overwrite=True
            )

        assert put.called

    @respx.mock
    def test_submit_response_without_query_id_raises_query_error(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"unrelated": "field"})
        )

        with pytest.raises(PicSureQueryError, match="picsureResultId"):
            save_query_by_name(
                _client(),
                _clause(),
                "fun",
                backend="auth",
            )


class TestNameAllowListIsOneConstant:
    def test_every_listed_punctuation_character_is_accepted(self):
        for char in _NAME_PUNCTUATION:
            _validate_name(f"cohort{char}1")

    def test_message_lists_every_allowed_punctuation_character(self):
        with pytest.raises(PicSureValidationError) as excinfo:
            _validate_name("bad|name")

        message = str(excinfo.value)
        for char in _NAME_PUNCTUATION:
            assert f" {char} " in message or f" {char}." in message

    def test_message_still_reads_as_before(self):
        with pytest.raises(PicSureValidationError) as excinfo:
            _validate_name("bad|name")

        assert "- \\ / ? + = [ ] . ( ) : \" '." in str(excinfo.value)
