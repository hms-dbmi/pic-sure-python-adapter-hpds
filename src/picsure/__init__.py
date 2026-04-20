"""PIC-SURE Python API adapter."""

import os

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.facet import FacetSet
from picsure._models.query import Query
from picsure._models.session import Session
from picsure._services.connect import connect
from picsure._services.query_build import buildClauseGroup, createClause
from picsure._transport.platforms import Platform
from picsure.errors import PicSureError


def set_dev_mode(enabled: bool) -> None:
    """Set the ``PICSURE_DEV_MODE`` environment variable.

    Affects the **next** call to :func:`connect`. Existing ``Session``
    objects are not mutated; reconnect to pick up the change.
    """
    if enabled:
        os.environ["PICSURE_DEV_MODE"] = "1"
    else:
        os.environ.pop("PICSURE_DEV_MODE", None)


__all__ = [
    "buildClauseGroup",
    "connect",
    "createClause",
    "set_dev_mode",
    "Clause",
    "ClauseGroup",
    "ClauseType",
    "FacetSet",
    "GroupOperator",
    "PicSureError",
    "Platform",
    "Query",
    "Session",
]
