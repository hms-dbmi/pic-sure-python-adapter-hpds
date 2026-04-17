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
    optional longer description from the server.  ``children`` holds
    nested sub-options for hierarchical facet categories (e.g.
    Consortium_Curated_Facets → RECOVER Adult Curated → Infected).
    """

    value: str
    count: int
    display: str = ""
    description: str = ""
    children: list[Facet] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Facet:
        # Iterative build so arbitrarily deep facet trees don't blow
        # Python's recursion limit.  Two phases:
        #   1. DFS the input, recording each node and which indices
        #      are its children (order-preserved).
        #   2. Build Facets in reverse index order so every parent's
        #      children are already constructed when referenced.
        flat: list[dict[str, object]] = []
        children_of: dict[int, list[int]] = {}
        pending: list[tuple[dict[str, object], int]] = [(data, -1)]
        while pending:
            node, parent_idx = pending.pop()
            idx = len(flat)
            flat.append(node)
            if parent_idx >= 0:
                children_of.setdefault(parent_idx, []).append(idx)
            raw_children = node.get("children", [])
            if isinstance(raw_children, list):
                # Reverse so LIFO pop yields original sibling order.
                for child in reversed(raw_children):
                    if isinstance(child, dict):
                        pending.append((cast(dict[str, object], child), idx))

        facets: list[Facet | None] = [None] * len(flat)
        for idx in range(len(flat) - 1, -1, -1):
            node = flat[idx]
            child_indices = children_of.get(idx, [])
            own_children = [cast(Facet, facets[i]) for i in child_indices]
            raw_count = node.get("count", 0)
            raw_value = node.get("name", node.get("value"))
            facets[idx] = cls(
                value=str(raw_value) if raw_value is not None else "",
                count=int(cast(int, raw_count)),
                display=str(node.get("display") or ""),
                description=str(node.get("description") or ""),
                children=own_children,
            )

        return cast(Facet, facets[0])


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
        """Serialize selected facets for the concepts/facets request body.

        The backend expects each selected option to arrive as the full
        facet object (the shape returned by ``/dictionary-api/facets``)
        with an added ``categoryRef`` pointing back at its category.
        """
        result: list[dict[str, object]] = []
        for cat_name, values in self._selected.items():
            if not values:
                continue
            cat = self._available[cat_name]
            category_ref = {
                "name": cat.name,
                "display": cat.display,
                "description": cat.description,
            }
            by_value = _flatten_options_by_value(cat.options)
            for value in values:
                opt = by_value.get(value)
                display = opt.display if opt is not None else value
                description = opt.description if opt is not None else ""
                count = opt.count if opt is not None else 0
                result.append(
                    {
                        "name": value,
                        "display": display,
                        "description": description,
                        "fullName": None,
                        "count": count,
                        "children": [],
                        "category": cat.name,
                        "meta": None,
                        "categoryRef": category_ref,
                    }
                )
        return result

    def _validate_category(self, category: str) -> None:
        if category not in self._available:
            valid = ", ".join(sorted(self._available.keys()))
            raise PicSureValidationError(
                f"'{category}' is not a valid facet category. "
                f"Valid categories: {valid}."
            )


def _flatten_options_by_value(options: list[Facet]) -> dict[str, Facet]:
    """Return a map of value → Facet covering the tree of options."""
    result: dict[str, Facet] = {}
    stack: list[Facet] = list(options)
    while stack:
        opt = stack.pop()
        result[opt.value] = opt
        stack.extend(opt.children)
    return result
