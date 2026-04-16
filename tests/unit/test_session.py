from unittest.mock import MagicMock

import pandas as pd

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
