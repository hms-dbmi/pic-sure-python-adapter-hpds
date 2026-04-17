from __future__ import annotations

import sys

import pandas as pd

from picsure._models.dictionary import DictionaryEntry
from picsure._models.facet import FacetCategory, FacetSet
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import PicSureConnectionError

_CONCEPTS_PATH = "/picsure/proxy/dictionary-api/concepts"
_FACETS_PATH = "/picsure/proxy/dictionary-api/facets"

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


def fetch_total_concepts(
    client: PicSureClient,
    consents: list[str] | None = None,
) -> int:
    """Probe the concepts endpoint to discover how many concepts exist.

    The backend paginates results; to fetch all concepts in a single
    call we need a page size equal to the total number of concepts.
    This helper issues a minimal ``page_size=1`` request and returns
    ``totalElements`` from the response.

    Args:
        client: Authenticated HTTP client.
        consents: Optional consent list for authorized deployments.

    Returns:
        Total number of concepts available to the user.  ``0`` if the
        response omits ``totalElements``.
    """
    body = _build_concepts_body(term="", facets=None, consents=consents)
    url = f"{_CONCEPTS_PATH}?page_number=0&page_size=1"

    try:
        data = client.post_json(url, body=body)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not initialize the data dictionary. "
            "The server may be temporarily unavailable."
        ) from exc

    total = data.get("totalElements", 0)
    try:
        return int(total)
    except (TypeError, ValueError):
        return 0


def search(
    client: PicSureClient,
    term: str = "",
    facets: FacetSet | None = None,
    include_values: bool = True,
    consents: list[str] | None = None,
    page_size: int | None = None,
) -> pd.DataFrame:
    """Search the PIC-SURE data dictionary.

    Issues a single POST to ``/picsure/proxy/dictionary-api/concepts``
    with ``page_size`` large enough to return every match.  The
    session computes ``page_size`` at connect time by probing
    ``totalElements``.

    Args:
        client: Authenticated HTTP client.
        term: Search term (empty string returns all concepts).
        facets: Optional FacetSet to narrow results.
        include_values: If False, omit the values column.
        consents: Optional consent list.  Passed through in the body
            for authorized deployments; omitted when ``None`` or empty.
        page_size: Page size for the request.  Should be the total
            number of concepts (from :func:`fetch_total_concepts`) so
            the entire result set comes back in one page.  If omitted
            or non-positive, defaults to ``100``.

    Returns:
        DataFrame of matching dictionary entries.
    """
    effective_page_size = page_size if page_size and page_size > 0 else 100
    body = _build_concepts_body(term=term, facets=facets, consents=consents)
    url = f"{_CONCEPTS_PATH}?page_number=0&page_size={effective_page_size}"

    try:
        data = client.post_json(url, body=body)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not complete search. The server may be temporarily unavailable."
        ) from exc

    entries = [DictionaryEntry.from_dict(r) for r in data.get("content", [])]
    entries = _deduplicate(entries)

    columns = _COLUMNS_WITH_VALUES if include_values else _COLUMNS_WITHOUT_VALUES

    if not entries:
        print("Note: search returned 0 results.", file=sys.stderr)
        return pd.DataFrame(columns=columns)

    return _entries_to_dataframe(entries, include_values)


def fetch_facets(
    client: PicSureClient,
    consents: list[str] | None = None,
) -> list[FacetCategory]:
    """Fetch all available facet categories from the server.

    POSTs to ``/picsure/proxy/dictionary-api/facets`` with the same
    body shape as :func:`search`.  The response is a top-level array
    of facet categories (not wrapped in an object).
    """
    body = _build_concepts_body(term="", facets=None, consents=consents)

    try:
        data = client.post_json(_FACETS_PATH, body=body)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not fetch facets. The server may be temporarily unavailable."
        ) from exc

    # /facets returns a JSON array at the top level. PicSureClient.post_json
    # is typed as returning dict, but the parsed JSON can be a list here.
    raw_categories = data if isinstance(data, list) else data.get("facets", [])
    return [FacetCategory.from_dict(f) for f in raw_categories]


def show_all_facets(
    client: PicSureClient,
    consents: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch all facet categories and return as a flat DataFrame.

    Columns: ``category``, ``display`` (category's display), ``value``
    (option identifier to pass to ``FacetSet.add``), ``count``.

    Some facet categories are hierarchical (e.g.
    Consortium_Curated_Facets).  Every option is flattened into its
    own row regardless of depth.
    """
    categories = fetch_facets(client, consents=consents)
    rows: list[dict[str, object]] = []
    for cat in categories:
        for opt in _walk_options(cat.options):
            rows.append(
                {
                    "category": cat.name,
                    "display": cat.display,
                    "value": opt.value,
                    "count": opt.count,
                }
            )
    if not rows:
        return pd.DataFrame(columns=["category", "display", "value", "count"])
    return pd.DataFrame(rows)


def _walk_options(options: list[FacetCategory]) -> list[FacetCategory]:
    """Yield every option and its descendants in depth-first order."""
    result: list[FacetCategory] = []
    stack: list[FacetCategory] = list(reversed(options))
    while stack:
        opt = stack.pop()
        result.append(opt)
        # ``children`` is only defined on Facet, not FacetCategory; the
        # type annotation above is approximate — we only call this on
        # Facet lists.  Kept loose to avoid a circular import.
        children = getattr(opt, "children", None) or []
        stack.extend(reversed(children))
    return result


def _build_concepts_body(
    term: str,
    facets: FacetSet | None,
    consents: list[str] | None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "search": term,
        "facets": facets.to_request_facets() if facets else [],
    }
    if consents:
        body["consents"] = list(consents)
    return body


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
