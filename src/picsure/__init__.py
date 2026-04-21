"""PIC-SURE Python API adapter."""

from picsure._models.clause import Clause, ClauseType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.count_result import CountResult
from picsure._models.facet import FacetSet
from picsure._models.query import Query
from picsure._models.session import Session
from picsure._services.connect import connect
from picsure._services.query_build import buildClauseGroup, createClause
from picsure._transport.platforms import Platform
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureError,
    PicSureQueryError,
    PicSureValidationError,
)

__all__ = [
    "buildClauseGroup",
    "connect",
    "createClause",
    "Clause",
    "ClauseGroup",
    "ClauseType",
    "CountResult",
    "FacetSet",
    "GroupOperator",
    "PicSureAuthError",
    "PicSureConnectionError",
    "PicSureError",
    "PicSureQueryError",
    "PicSureValidationError",
    "Platform",
    "Query",
    "Session",
]
