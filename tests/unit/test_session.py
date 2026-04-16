from unittest.mock import MagicMock

import httpx
import pandas as pd
import respx

from picsure._models.resource import Resource
from picsure._models.session import Session


def _make_session(
    resources: list[Resource] | None = None,
    email: str = "user@example.com",
    expiration: str = "2026-06-15T00:00:00Z",
) -> Session:
    client = MagicMock()
    if resources is None:
        resources = [
            Resource(uuid="uuid-1", name="Resource A", description="Desc A"),
            Resource(uuid="uuid-2", name="Resource B", description="Desc B"),
        ]
    return Session(
        client=client,
        user_email=email,
        token_expiration=expiration,
        resources=resources,
    )


class TestSession:
    def test_stores_user_email(self):
        session = _make_session(email="test@uni.edu")
        assert session._user_email == "test@uni.edu"

    def test_stores_token_expiration(self):
        session = _make_session(expiration="2026-12-31T00:00:00Z")
        assert session._token_expiration == "2026-12-31T00:00:00Z"

    def test_get_resource_id_returns_dataframe(self):
        session = _make_session()
        df = session.getResourceID()
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["uuid", "name", "description"]
        assert len(df) == 2

    def test_get_resource_id_values(self):
        resources = [
            Resource(uuid="aaa", name="Res A", description="Desc A"),
        ]
        session = _make_session(resources=resources)
        df = session.getResourceID()
        assert df.iloc[0]["uuid"] == "aaa"
        assert df.iloc[0]["name"] == "Res A"
        assert df.iloc[0]["description"] == "Desc A"

    def test_get_resource_id_empty(self):
        session = _make_session(resources=[])
        df = session.getResourceID()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == ["uuid", "name", "description"]

    def test_stores_resource_uuid(self):
        client = MagicMock()
        session = Session(
            client=client,
            user_email="u@e.com",
            token_expiration="",
            resources=[],
            resource_uuid="my-uuid",
        )
        assert session._resource_uuid == "my-uuid"

    def test_resource_uuid_defaults_to_none(self):
        session = _make_session()
        assert session._resource_uuid is None

    def test_set_resource_id(self):
        session = _make_session()
        session.setResourceID("uuid-1")
        assert session._resource_uuid == "uuid-1"

    def test_set_resource_id_invalid_raises(self):
        import pytest

        from picsure.errors import PicSureValidationError

        session = _make_session()
        with pytest.raises(PicSureValidationError, match="not a valid resource UUID"):
            session.setResourceID("nonexistent-uuid")

    def test_set_resource_id_overrides_existing(self):
        client = MagicMock()
        resources = [
            Resource(uuid="uuid-1", name="A", description=""),
            Resource(uuid="uuid-2", name="B", description=""),
        ]
        session = Session(
            client=client,
            user_email="u@e.com",
            token_expiration="",
            resources=resources,
            resource_uuid="uuid-1",
        )
        session.setResourceID("uuid-2")
        assert session._resource_uuid == "uuid-2"

    def test_set_resource_id_by_name(self):
        session = _make_session()
        session.setResourceIDByName("Resource B")
        assert session._resource_uuid == "uuid-2"

    def test_set_resource_id_by_name_invalid_raises(self):
        import pytest

        from picsure.errors import PicSureValidationError

        session = _make_session()
        with pytest.raises(PicSureValidationError, match="does not match"):
            session.setResourceIDByName("nonexistent")

    def test_set_resource_id_by_name_lists_valid(self):
        import pytest

        from picsure.errors import PicSureValidationError

        session = _make_session()
        with pytest.raises(PicSureValidationError, match="Resource A"):
            session.setResourceIDByName("nope")


class TestSessionDefaultResourceUuid:
    def test_returns_explicit_resource_uuid_when_set(self):
        client = MagicMock()
        resources = [
            Resource(uuid="uuid-1", name="A", description=""),
            Resource(uuid="uuid-2", name="B", description=""),
        ]
        session = Session(
            client=client,
            user_email="u@e.com",
            token_expiration="",
            resources=resources,
            resource_uuid="uuid-2",
        )
        assert session._default_resource_uuid() == "uuid-2"

    def test_returns_first_resource_when_not_set(self):
        session = _make_session()
        assert session._default_resource_uuid() == "uuid-1"

    def test_raises_when_no_resources(self):
        session = _make_session(resources=[])
        with __import__("pytest").raises(
            __import__("picsure.errors", fromlist=["PicSureError"]).PicSureError,
            match="No resources",
        ):
            session._default_resource_uuid()


BASE_URL = "https://test.example.com"
TOKEN = "test-token"


def _make_live_session(
    resource_uuid: str = "resource-uuid-aaaa-1111",
) -> Session:
    from picsure._transport.client import PicSureClient

    client = PicSureClient(base_url=BASE_URL, token=TOKEN)
    resources = [Resource(uuid=resource_uuid, name="Test", description="")]
    return Session(
        client=client,
        user_email="test@test.com",
        token_expiration="2026-12-31T00:00:00Z",
        resources=resources,
    )


class TestSessionSearch:
    @respx.mock
    def test_search_returns_dataframe(self, search_response):
        respx.post(
            f"{BASE_URL}/picsure/search/resource-uuid-aaaa-1111"
        ).mock(return_value=httpx.Response(200, json=search_response))

        session = _make_live_session()
        df = session.search("sex")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    @respx.mock
    def test_search_empty_term(self, search_response):
        respx.post(
            f"{BASE_URL}/picsure/search/resource-uuid-aaaa-1111"
        ).mock(return_value=httpx.Response(200, json=search_response))

        session = _make_live_session()
        df = session.search()

        assert isinstance(df, pd.DataFrame)


class TestSessionFacets:
    @respx.mock
    def test_facets_returns_facet_set(self, search_response):
        respx.post(
            f"{BASE_URL}/picsure/search/resource-uuid-aaaa-1111"
        ).mock(return_value=httpx.Response(200, json=search_response))

        session = _make_live_session()
        fs = session.facets()

        from picsure._models.facet import FacetSet

        assert isinstance(fs, FacetSet)
        view = fs.view()
        assert "study_ids" in view
        assert "data_type" in view

    @respx.mock
    def test_facets_can_add_and_use_in_search(self, search_response):
        route = respx.post(
            f"{BASE_URL}/picsure/search/resource-uuid-aaaa-1111"
        ).mock(return_value=httpx.Response(200, json=search_response))

        session = _make_live_session()
        fs = session.facets()
        fs.add("study_ids", "phs000007")
        session.search("sex", facets=fs)

        import json

        last_body = json.loads(route.calls[-1].request.content)
        assert last_body["query"]["includedFacets"][0]["name"] == "study_ids"


class TestSessionShowAllFacets:
    @respx.mock
    def test_show_all_facets_returns_dataframe(self, search_response):
        respx.post(
            f"{BASE_URL}/picsure/search/resource-uuid-aaaa-1111"
        ).mock(return_value=httpx.Response(200, json=search_response))

        session = _make_live_session()
        df = session.showAllFacets()

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["category", "display", "value", "count"]
        assert len(df) == 4
