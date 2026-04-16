from __future__ import annotations

import sys

import pandas as pd

from picsure._models.dictionary import DictionaryEntry
from picsure._models.facet import FacetCategory, FacetSet
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import PicSureConnectionError

_PICSURE_SEARCH_PATH = "/picsure/search"

_COLUMNS_WITH_VALUES = [
    "conceptPath",
    "name",
    "display",
    "description",
    "dataType",
    "studyId",
    "values",
]

_COLUMNS_WITHOUT_VALUES = [
    "conceptPath",
    "name",
    "display",
    "description",
    "dataType",
    "studyId",
]


def search(
    client: PicSureClient,
    resource_uuid: str,
    term: str = "",
    facets: FacetSet | None = None,
    include_values: bool = True,
) -> pd.DataFrame:
    """Search the PIC-SURE data dictionary.

    Args:
        client: Authenticated HTTP client.
        resource_uuid: The resource to search.
        term: Search term (empty string returns all).
        facets: Optional FacetSet to narrow results.
        include_values: If False, omit the values column.

    Returns:
        DataFrame of matching dictionary entries.
    """
    body = _build_search_request(term, facets, include_values)
    url = f"{_PICSURE_SEARCH_PATH}/{resource_uuid}"

    try:
        data = client.post_json(url, body=body)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not complete search. The server may be temporarily unavailable."
        ) from exc

    entries = [DictionaryEntry.from_dict(r) for r in data.get("results", [])]
    entries = _deduplicate(entries)

    columns = _COLUMNS_WITH_VALUES if include_values else _COLUMNS_WITHOUT_VALUES

    if not entries:
        print("Note: search returned 0 results.", file=sys.stderr)
        return pd.DataFrame(columns=columns)

    return _entries_to_dataframe(entries, include_values)


def fetch_facets(
    client: PicSureClient,
    resource_uuid: str,
) -> list[FacetCategory]:
    """Fetch all available facet categories from the server."""
    body = _build_search_request(term="", facets=None, include_values=False)
    url = f"{_PICSURE_SEARCH_PATH}/{resource_uuid}"

    try:
        data = client.post_json(url, body=body)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not fetch facets. The server may be temporarily unavailable."
        ) from exc

    return [FacetCategory.from_dict(f) for f in data.get("facets", [])]


def show_all_facets(
    client: PicSureClient,
    resource_uuid: str,
) -> pd.DataFrame:
    """Fetch all facet categories and return as a flat DataFrame."""
    categories = fetch_facets(client, resource_uuid)
    rows: list[dict[str, object]] = [
        {
            "category": cat.name,
            "display": cat.display,
            "value": opt.value,
            "count": opt.count,
        }
        for cat in categories
        for opt in cat.options
    ]
    if not rows:
        return pd.DataFrame(columns=["category", "display", "value", "count"])
    return pd.DataFrame(rows)


def _build_search_request(
    term: str,
    facets: FacetSet | None,
    include_values: bool,
) -> dict[str, object]:
    included_facets = facets.to_request_facets() if facets else []
    return {
        "query": {
            "searchTerm": term,
            "includedFacets": included_facets,
            "returnValues": include_values,
        }
    }


def _deduplicate(entries: list[DictionaryEntry]) -> list[DictionaryEntry]:
    seen: set[str] = set()
    result: list[DictionaryEntry] = []
    for entry in entries:
        if entry.concept_path not in seen:
            seen.add(entry.concept_path)
            result.append(entry)
    return result


def _entries_to_dataframe(
    entries: list[DictionaryEntry],
    include_values: bool,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for e in entries:
        row: dict[str, object] = {
            "conceptPath": e.concept_path,
            "name": e.name,
            "display": e.display,
            "description": e.description,
            "dataType": e.data_type,
            "studyId": e.study_id,
        }
        if include_values:
            row["values"] = e.values
        rows.append(row)
    return pd.DataFrame(rows)
