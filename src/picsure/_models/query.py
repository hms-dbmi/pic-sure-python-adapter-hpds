from __future__ import annotations

from typing import TypeAlias

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup

Query: TypeAlias = Clause | ClauseGroup
"""A query is either a single Clause or a ClauseGroup of nested clauses."""
