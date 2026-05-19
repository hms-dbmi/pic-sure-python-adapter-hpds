from __future__ import annotations

import json

import httpx
import pytest
import respx

from picsure._models.clause import Clause, ClauseType
from picsure._services.query_save import save_query_by_name
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

BASE_URL = "https://api.example.com"
TOKEN = "test-token"
RESOURCE_UUID = "res-uuid-1111"

LIST_URL = f"{BASE_URL}/picsure/dataset/named"
SUBMIT_URL = f"{BASE_URL}/picsure/v3/query"
SAVE_URL = f"{BASE_URL}/picsure/dataset/named"


def _client() -> PicSureClient:
    return PicSureClient(base_url=BASE_URL, token=TOKEN)


def _clause() -> Clause:
    return Clause(keys=["\\a\\"], type=ClauseType.FILTER, categories=["x"])


class TestSaveQueryByNameHappyPath:
    @respx.mock
    def test_creates_new_named_dataset(self):
        listing = respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        submit = respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": "qid-123"})
        )
        save = respx.post(SAVE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "nd-abc",
                    "name": "fun",
                    "queryId": "qid-123",
                    "user": "u",
                    "archived": False,
                    "metadata": {},
                },
            )
        )

        qid = save_query_by_name(
            _client(),
            RESOURCE_UUID,
            _clause(),
            "fun",
            use_legacy_query_path=False,
        )

        assert qid == "qid-123"
        assert listing.called
        assert submit.called
        assert save.called

        # Verify POST body to /dataset/named/ carries the fresh query id.
        save_body = json.loads(save.calls.last.request.content)
        assert save_body == {
            "queryId": "qid-123",
            "name": "fun",
            "archived": False,
            "metadata": {},
        }

    @respx.mock
    def test_tolerates_results_envelope_on_list(self):
        # Some shapes wrap the list in {"results": [...]}; we accept either.
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json={"results": []}))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": "qid-9"})
        )
        save = respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        qid = save_query_by_name(
            _client(),
            RESOURCE_UUID,
            _clause(),
            "fun",
            use_legacy_query_path=False,
        )
        assert qid == "qid-9"
        assert save.called

    @respx.mock
    def test_submit_response_uses_resource_result_id_when_only_field(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"resourceResultId": "qid-fallback"})
        )
        respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        qid = save_query_by_name(
            _client(),
            RESOURCE_UUID,
            _clause(),
            "fun",
            use_legacy_query_path=False,
        )
        assert qid == "qid-fallback"


class TestSaveQueryByNameDuplicates:
    @respx.mock
    def test_refuses_duplicate_without_overwrite(self):
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "nd-old",
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
                RESOURCE_UUID,
                _clause(),
                "fun",
                use_legacy_query_path=False,
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
                        "uuid": "nd-old",
                        "name": "fun",
                        "queryId": "qid-old",
                        "archived": True,
                        "metadata": {"tag": "v1"},
                    }
                ],
            )
        )
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": "qid-new"})
        )
        put = respx.put(f"{BASE_URL}/picsure/dataset/named/nd-old").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "nd-old",
                    "name": "fun",
                    "queryId": "qid-new",
                    "archived": True,
                    "metadata": {"tag": "v1"},
                },
            )
        )
        # The collection POST must NOT be called on the overwrite path.
        create = respx.post(SAVE_URL).mock(return_value=httpx.Response(500))

        qid = save_query_by_name(
            _client(),
            RESOURCE_UUID,
            _clause(),
            "fun",
            use_legacy_query_path=False,
            overwrite=True,
        )

        assert qid == "qid-new"
        assert put.called
        assert not create.called

        body = json.loads(put.calls.last.request.content)
        assert body == {
            "queryId": "qid-new",
            "name": "fun",
            "archived": True,
            "metadata": {"tag": "v1"},
        }

    @respx.mock
    def test_overwrite_true_creates_when_no_existing_record(self):
        # overwrite=True should still create-via-POST if there is no match.
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": "qid-new"})
        )
        save = respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        qid = save_query_by_name(
            _client(),
            RESOURCE_UUID,
            _clause(),
            "fun",
            use_legacy_query_path=False,
            overwrite=True,
        )
        assert qid == "qid-new"
        assert save.called


class TestSaveQueryByNameOpenAccess:
    def test_refuses_when_use_legacy_query_path_true(self):
        # No network — the guard fires before any HTTP call.
        with pytest.raises(PicSureValidationError, match="open-access"):
            save_query_by_name(
                _client(),
                RESOURCE_UUID,
                _clause(),
                "fun",
                use_legacy_query_path=True,
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
        with pytest.raises(PicSureValidationError, match="unsupported characters"):
            save_query_by_name(
                _client(),
                RESOURCE_UUID,
                _clause(),
                bad_name,
                use_legacy_query_path=False,
            )

    def test_rejects_empty_name(self):
        with pytest.raises(PicSureValidationError, match="non-empty"):
            save_query_by_name(
                _client(),
                RESOURCE_UUID,
                _clause(),
                "",
                use_legacy_query_path=False,
            )

    def test_rejects_overlong_name(self):
        too_long = "a" * 256
        with pytest.raises(PicSureValidationError, match="255"):
            save_query_by_name(
                _client(),
                RESOURCE_UUID,
                _clause(),
                too_long,
                use_legacy_query_path=False,
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
            return_value=httpx.Response(200, json={"picsureResultId": "qid-z"})
        )
        respx.post(SAVE_URL).mock(return_value=httpx.Response(200, json={}))

        qid = save_query_by_name(
            _client(),
            RESOURCE_UUID,
            _clause(),
            good_name,
            use_legacy_query_path=False,
        )
        assert qid == "qid-z"


class TestSaveQueryByNameTransportErrors:
    @respx.mock
    def test_listing_401_raises_auth_error(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(401, text="nope"))

        with pytest.raises(PicSureAuthError):
            save_query_by_name(
                _client(),
                RESOURCE_UUID,
                _clause(),
                "fun",
                use_legacy_query_path=False,
            )

    @respx.mock
    def test_submit_400_raises_validation_error(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(return_value=httpx.Response(400, text="bad query"))

        with pytest.raises(PicSureValidationError, match="submit"):
            save_query_by_name(
                _client(),
                RESOURCE_UUID,
                _clause(),
                "fun",
                use_legacy_query_path=False,
            )

    @respx.mock
    def test_save_500_raises_connection_error(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"picsureResultId": "qid-x"})
        )
        respx.post(SAVE_URL).mock(return_value=httpx.Response(500, text="boom"))

        with pytest.raises(PicSureConnectionError):
            save_query_by_name(
                _client(),
                RESOURCE_UUID,
                _clause(),
                "fun",
                use_legacy_query_path=False,
            )

    @respx.mock
    def test_submit_response_without_query_id_raises_query_error(self):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[]))
        respx.post(SUBMIT_URL).mock(
            return_value=httpx.Response(200, json={"unrelated": "field"})
        )

        with pytest.raises(PicSureQueryError, match="picsureResultId"):
            save_query_by_name(
                _client(),
                RESOURCE_UUID,
                _clause(),
                "fun",
                use_legacy_query_path=False,
            )
