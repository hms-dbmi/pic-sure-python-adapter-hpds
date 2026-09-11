from __future__ import annotations

import sys

import pandas as pd

from picsure._models.dictionary import DictionaryEntry
from picsure._models.facet import FacetCategory, FacetSet
from picsure._services._errors import translate_transport_error
from picsure._transport.client import PicSureClient, json_object
from picsure._transport.errors import TransportError
from picsure.errors import PicSureValidationError

_CONCEPTS_PATH = "/picsure/dictionary/concepts"
_FACETS_PATH = "/picsure/dictionary/facets"

_SEARCH_OPERATION = "the dictionary search"
_FACETS_OPERATION = "the dictionary facets lookup"

# ``/concepts`` answers with a Spring Data ``Page`` envelope -- ``content``
# alongside ``totalElements``, ``totalPages``, ``number``, ``size``, ``first``
# and ``last``.  Paging is zero-based through the ``page_number`` and
# ``page_size`` query parameters.
_DEFAULT_PAGE_SIZE = 500

# Largest ``page_size`` the backend accepts: Java ``Integer.MAX_VALUE``.  One
# above it overflows the int binding and comes back as HTTP 400.
_SERVER_MAX_PAGE_SIZE = 2_147_483_647

# Ceiling on rows an unpaged search accumulates before it refuses to continue.
# Without it, a caller who omits ``page`` on a production-sized dictionary
# walks the whole thing into one DataFrame.
_MAX_UNPAGED_ROWS = 100_000

_COLUMNS_WITH_VALUES = [
    "conceptPath",
    "name",
    "display",
    "description",
    "dataType",
    "studyId",
    "values",
    "min",
    "max",
    "allowFiltering",
    "meta",
    "studyAcronym",
]

_COLUMNS_WITHOUT_VALUES = [
    "conceptPath",
    "name",
    "display",
    "description",
    "dataType",
    "studyId",
    "min",
    "max",
    "allowFiltering",
    "meta",
    "studyAcronym",
]


def searchDictionary(  # noqa: N802
    client: PicSureClient,
    term: str = "",
    facets: FacetSet | None = None,
    include_values: bool = True,
    consents: list[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> pd.DataFrame:
    """Search the PIC-SURE data dictionary.

    POSTs to ``/picsure/dictionary/concepts``, which answers with a
    zero-based Spring Data ``Page``.

    Omitting ``page`` returns the complete result set, collected by
    walking the pages in ``page_size`` chunks.  Passing ``page``
    returns that one page and nothing else.

    Either way the returned DataFrame carries the page metadata in
    :attr:`pandas.DataFrame.attrs`:

    - ``total_elements`` — server's total match count, or ``None`` if
      the response omitted it
    - ``has_more`` — whether further pages exist beyond what was returned
    - ``page`` — the requested page, or ``None`` when every page was collected
    - ``page_size`` — rows requested per HTTP call
    - ``pages_fetched`` — number of HTTP calls made

    Args:
        client: Authenticated HTTP client.
        term: Search term (empty string returns all concepts).
        facets: Optional FacetSet to narrow results.
        include_values: If False, omit the values column.
        consents: Optional consent list.  Passed through in the body
            for authorized deployments; omitted when ``None`` or empty.
        page: Zero-based page to return.  ``None`` (the default)
            collects every page.
        page_size: Rows per HTTP request.  Defaults to
            :data:`_DEFAULT_PAGE_SIZE`.

    Returns:
        DataFrame of matching dictionary entries.

    Raises:
        PicSureValidationError: If ``page`` or ``page_size`` is out of
            range, or if an unpaged search matches more than
            :data:`_MAX_UNPAGED_ROWS` concepts.
    """
    effective_page_size = _resolve_page_size(page_size)
    _validate_page(page)
    body = _build_concepts_body(term=term, facets=facets, consents=consents)

    if page is None:
        content, total_elements, has_more, pages_fetched = _fetch_all_pages(
            client, body, effective_page_size
        )
    else:
        data = _request_page(client, body, page, effective_page_size)
        content = _page_content(data)
        total_elements = _page_total(data)
        has_more = _page_has_more(data, page, effective_page_size, len(content))
        pages_fetched = 1

    entries = _deduplicate([DictionaryEntry.from_dict(r) for r in content])
    columns = _COLUMNS_WITH_VALUES if include_values else _COLUMNS_WITHOUT_VALUES

    if entries:
        df = _entries_to_dataframe(entries, include_values)
    else:
        print("Note: search returned 0 results.", file=sys.stderr)
        df = pd.DataFrame(columns=columns)

    df.attrs.update(
        {
            "total_elements": total_elements,
            "has_more": has_more,
            "page": page,
            "page_size": effective_page_size,
            "pages_fetched": pages_fetched,
        }
    )
    return df


def _validate_page(page: int | None) -> None:
    if page is None:
        return
    if not isinstance(page, int) or isinstance(page, bool):
        raise PicSureValidationError("`page` must be an integer or None.")
    if page < 0:
        raise PicSureValidationError(
            f"`page` must be 0 or greater (got {page}); pages are zero-based."
        )


def _resolve_page_size(page_size: int | None) -> int:
    if page_size is None:
        return _DEFAULT_PAGE_SIZE
    if not isinstance(page_size, int) or isinstance(page_size, bool):
        raise PicSureValidationError("`page_size` must be an integer or None.")
    if page_size < 1:
        raise PicSureValidationError(
            f"`page_size` must be 1 or greater (got {page_size})."
        )
    if page_size > _SERVER_MAX_PAGE_SIZE:
        raise PicSureValidationError(
            f"`page_size` must be at most {_SERVER_MAX_PAGE_SIZE} (got "
            f"{page_size}); the server rejects anything larger with HTTP 400."
        )
    return page_size


def _request_page(
    client: PicSureClient,
    body: dict[str, object],
    page: int,
    page_size: int,
) -> dict[str, object]:
    url = f"{_CONCEPTS_PATH}?page_number={page}&page_size={page_size}"
    try:
        payload = client.post_json(url, body=body)
    except TransportError as exc:
        raise translate_transport_error(exc, operation=_SEARCH_OPERATION) from exc
    return json_object(payload, path=url)


def _page_content(data: dict[str, object]) -> list[dict[str, object]]:
    content = data.get("content")
    return content if isinstance(content, list) else []


def _page_total(data: dict[str, object]) -> int | None:
    total = data.get("totalElements")
    if isinstance(total, bool) or not isinstance(total, int):
        return None
    return total


def _page_has_more(
    data: dict[str, object],
    page: int,
    page_size: int,
    returned: int,
) -> bool:
    """Decide whether pages remain after the one just read.

    Prefers the envelope's ``last`` flag.  Falls back to comparing the
    rows consumed so far against ``totalElements``, and finally to
    "a completely full page probably has a successor".
    """
    last = data.get("last")
    if isinstance(last, bool):
        return not last
    total = _page_total(data)
    if total is not None:
        return (page * page_size) + returned < total
    return returned > 0 and returned == page_size


def _unpaged_ceiling_error(matched: int | None) -> PicSureValidationError:
    matched_repr = (
        f"matched {matched} concepts" if matched is not None else "matched too many"
    )
    return PicSureValidationError(
        f"The dictionary search {matched_repr}, above the "
        f"{_MAX_UNPAGED_ROWS}-row limit for a single unpaged call. Read the "
        "results a page at a time -- pass page=0, then page=1, and so on, "
        "using the `has_more` and `total_elements` entries of each returned "
        "DataFrame's `.attrs` to know when to stop. Supplying `term` or "
        "`facets` will also reduce the match count."
    )


def _fetch_all_pages(
    client: PicSureClient,
    body: dict[str, object],
    page_size: int,
) -> tuple[list[dict[str, object]], int | None, bool, int]:
    """Walk every page of a concepts search and return the rows as one list.

    Returns the accumulated content, the server's ``totalElements`` (or
    ``None``), ``has_more`` (always ``False`` on a completed walk), and
    the number of requests issued.
    """
    content: list[dict[str, object]] = []
    total_elements: int | None = None
    page = 0
    while True:
        data = _request_page(client, body, page, page_size)
        total_elements = _page_total(data)
        if total_elements is not None and total_elements > _MAX_UNPAGED_ROWS:
            raise _unpaged_ceiling_error(total_elements)
        page_rows = _page_content(data)
        content.extend(page_rows)
        pages_fetched = page + 1
        if not page_rows or not _page_has_more(data, page, page_size, len(page_rows)):
            return content, total_elements, False, pages_fetched
        if len(content) > _MAX_UNPAGED_ROWS:
            raise _unpaged_ceiling_error(total_elements)
        page += 1


def fetch_facets(
    client: PicSureClient,
    consents: list[str] | None = None,
    term: str = "",
    facets: FacetSet | None = None,
) -> list[FacetCategory]:
    """Fetch facet categories from the server.

    POSTs to ``/picsure/dictionary/facets`` with the same body shape as
    :func:`searchDictionary`.  The response is a top-level array of
    facet categories -- not wrapped in an object, and not paginated.

    Args:
        client: Authenticated HTTP client.
        consents: Optional consent list for authorized deployments.
        term: Optional search term. When provided, the returned counts
            reflect only concepts matching the term.  When omitted (the
            default), counts are global across the whole dictionary.
        facets: Optional :class:`FacetSet` of current selections. When
            provided, the returned counts reflect how many additional
            concepts each option would match given the selections — the
            shape the UI's facet sidebar uses to preview "adding this
            filter narrows by N." When omitted, counts are unconditioned
            on any selection.

    Returns:
        List of facet categories.  Counts are contextual when ``term``
        and/or ``facets`` is supplied; global otherwise.
    """
    body = _build_concepts_body(term=term, facets=facets, consents=consents)

    try:
        data = client.post_json(_FACETS_PATH, body=body)
    except TransportError as exc:
        raise translate_transport_error(exc, operation=_FACETS_OPERATION) from exc

    # /facets answers with a JSON array at the top level; the dict branch
    # covers a deployment that wraps it in a ``facets`` key instead.
    raw_categories = data if isinstance(data, list) else data.get("facets", [])
    return [FacetCategory.from_dict(f) for f in raw_categories]


_SHOW_ALL_FACETS_COLUMNS = [
    "category",
    "Category Display",
    "display",
    "description",
    "value",
    "count",
]


def show_all_facets(
    client: PicSureClient,
    consents: list[str] | None = None,
    term: str = "",
    facets: FacetSet | None = None,
) -> pd.DataFrame:
    """Fetch all facet categories and return as a flat DataFrame.

    Columns:

    - ``category`` — category identifier (pass to ``FacetSet.add``)
    - ``Category Display`` — human-readable category label
    - ``display`` — facet option's display label
    - ``description`` — facet option's description
    - ``value`` — option identifier (pass to ``FacetSet.add``)
    - ``count`` — option count

    Some facet categories are hierarchical (e.g.
    Consortium_Curated_Facets).  Every option is flattened into its
    own row regardless of depth.

    Counts are contextual to ``term``/``facets`` when provided; global
    when both are omitted.  See :func:`fetch_facets` for details.
    """
    categories = fetch_facets(client, consents=consents, term=term, facets=facets)
    rows: list[dict[str, object]] = []
    for cat in categories:
        for root in cat.options:
            for opt in root.walk():
                rows.append(
                    {
                        "category": cat.name,
                        "Category Display": cat.display,
                        "display": opt.display,
                        "description": opt.description,
                        "value": opt.value,
                        "count": opt.count,
                    }
                )
    if not rows:
        return pd.DataFrame(columns=_SHOW_ALL_FACETS_COLUMNS)
    return pd.DataFrame(rows)


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
    # Keyed on concept_path only; on BDC this is unique per concept, but if
    # a future deployment reuses path fragments across datasets this may
    # collapse distinct rows.
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
    cols: dict[str, list[object]] = {
        "conceptPath": [e.concept_path for e in entries],
        "name": [e.name for e in entries],
        "display": [e.display for e in entries],
        "description": [e.description for e in entries],
        "dataType": [e.data_type for e in entries],
        "studyId": [e.study_id for e in entries],
    }
    if include_values:
        cols["values"] = [e.values for e in entries]
    cols["min"] = [e.min for e in entries]
    cols["max"] = [e.max for e in entries]
    cols["allowFiltering"] = [e.allow_filtering for e in entries]
    cols["meta"] = [e.meta for e in entries]
    cols["studyAcronym"] = [e.study_acronym for e in entries]
    return pd.DataFrame(cols)
