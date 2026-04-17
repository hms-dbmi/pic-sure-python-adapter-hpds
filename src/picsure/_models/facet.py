from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from picsure.errors import PicSureValidationError


@dataclass(frozen=True)
class Facet:
    """A single facet option with its count.

    ``value`` is the identifier used when filtering (e.g. the study
    dbGaP accession ``phs000007``).  ``display`` is a human-readable
    label (e.g. ``"FHS (phs000007)"``).  ``description`` is an
    optional longer description from the server.
    """

    value: str
    count: int
    display: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Facet:
        raw_count = data.get("count", 0)
        raw_value = data.get("name", data.get("value"))
        return cls(
            value=str(raw_value) if raw_value is not None else "",
            count=int(cast(int, raw_count)),
            display=str(data.get("display") or ""),
            description=str(data.get("description") or ""),
        )


@dataclass(frozen=True)
class FacetCategory:
    """A facet group containing multiple options."""

    name: str
    display: str
    options: list[Facet] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> FacetCategory:
        raw_options = data.get("facets", data.get("categories", []))
        options: list[Facet] = (
            [Facet.from_dict(cast(dict[str, object], c)) for c in raw_options]
            if isinstance(raw_options, list)
            else []
        )
        return cls(
            name=str(data.get("name", "")),
            display=str(data.get("display", "")),
            options=options,
            description=str(data.get("description") or ""),
        )


class FacetSet:
    """Mutable container for facet selections.

    Created by ``Session.facets()``. Add selections with ``add()``,
    then pass the FacetSet to ``Session.search()`` to narrow results.
    """

    def __init__(self, available: list[FacetCategory]) -> None:
        self._available: dict[str, FacetCategory] = {cat.name: cat for cat in available}
        self._selected: dict[str, list[str]] = {}

    def add(self, category: str, values: str | list[str]) -> None:
        """Add values to a facet category.

        Args:
            category: The facet category name (e.g. "study_ids").
            values: One or more values to select.

        Raises:
            PicSureValidationError: If the category is not valid.
        """
        self._validate_category(category)
        if isinstance(values, str):
            values = [values]
        self._selected.setdefault(category, []).extend(values)

    def view(self) -> dict[str, list[str]]:
        """Return current selections as a dict of category -> selected values."""
        return {name: list(self._selected.get(name, [])) for name in self._available}

    def clear(self, category: str | None = None) -> None:
        """Clear selections. If category is given, clear only that category."""
        if category is not None:
            self._validate_category(category)
            self._selected.pop(category, None)
        else:
            self._selected.clear()

    def to_request_facets(self) -> list[dict[str, object]]:
        """Serialize selected facets for the search request body."""
        return [
            {"name": name, "values": values}
            for name, values in self._selected.items()
            if values
        ]

    def _validate_category(self, category: str) -> None:
        if category not in self._available:
            valid = ", ".join(sorted(self._available.keys()))
            raise PicSureValidationError(
                f"'{category}' is not a valid facet category. "
                f"Valid categories: {valid}."
            )
