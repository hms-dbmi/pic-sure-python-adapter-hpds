from __future__ import annotations

import json
import re
from io import BytesIO, StringIO

import pandas as pd

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.count_result import CountResult
from picsure._models.genomic_filter import GenomicFilter
from picsure._models.query import Query
from picsure._models.query_type import QueryType
from picsure._services._errors import rate_limit_message
from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportValidationError,
)
from picsure.errors import (
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

_PICSURE_QUERY_SYNC_PATH = "/picsure/v3/query/sync"
# BDC's API gateway gates the v3 sync endpoint as authorized-only and
# rejects open-access requests with 401 even when "request-source: Open"
# is set.  Open-only deployments must use the legacy path instead.
_PICSURE_QUERY_SYNC_PATH_LEGACY = "/picsure/query/sync"

_VALID_QUERY_TYPES: dict[str, str] = {
    "count": "COUNT",
    "participant": "DATAFRAME",
    "timestamp": "DATAFRAME_TIMESERIES",
    "cross_count": "CROSS_COUNT",
    "variant_count": "VARIANT_COUNT_FOR_QUERY",
    "variant_list": "VARIANT_LIST_FOR_QUERY",
    "vcf_excerpt": "VCF_EXCERPT",
    "aggregate_vcf_excerpt": "AGGREGATE_VCF_EXCERPT",
}

_COUNT_EXACT = re.compile(r"^(\d+)$")
_COUNT_NOISY = re.compile(r"^(\d+)\s*\u00b1\s*(\d+)$")
_COUNT_SUPPRESSED = re.compile(r"^<\s*(\d+)$")


def run_query(
    client: PicSureClient,
    resource_uuid: str,
    query: Query | Clause | ClauseGroup,
    query_type: QueryType | str,
    *,
    use_legacy_query_path: bool = False,
) -> CountResult | dict[str, CountResult] | pd.DataFrame | int | list[str]:
    """Execute a query against PIC-SURE and return the result.

    Args:
        client: Authenticated HTTP client.
        resource_uuid: The resource to query.
        query: A Query, Clause, or ClauseGroup built with
            buildQuery/buildClause/buildClauseGroup.
        query_type: A :class:`QueryType` member (e.g. ``QueryType.COUNT``)
            or one of the strings ``"count"``, ``"participant"``,
            ``"timestamp"``, ``"cross_count"``.
        use_legacy_query_path: When ``True``, send the request to the
            legacy ``/picsure/query/sync`` endpoint instead of the v3
            path.  Open-only deployments (no auth, no consents) must
            use the legacy path because the BDC API gateway rejects
            open-access traffic on the v3 endpoint with HTTP 401.

    Returns:
        - ``count``        → :class:`CountResult`
        - ``cross_count``  → ``dict[str, CountResult]`` keyed by concept path
        - ``participant``  → :class:`pandas.DataFrame`
        - ``timestamp``    → :class:`pandas.DataFrame`
        - ``variant_count`` → ``int``
        - ``variant_list``  → ``list[str]``
        - ``vcf_excerpt`` / ``aggregate_vcf_excerpt`` → :class:`pandas.DataFrame`

    Note:
        For ``participant`` and ``timestamp`` queries, a patient with multiple
        observations on the same concept appears as a single cell containing
        all values joined by ``\\t`` (tab). Use ``df[col].str.split("\\t")``
        to get a list-valued column when you need the individual observations.

    Raises:
        PicSureValidationError: If the query type is invalid.
        PicSureConnectionError: If the server is unreachable.
        PicSureQueryError: If the server response cannot be parsed.
    """
    resolved_type = _resolve_query_type(query_type)
    body = build_query_body(query, resource_uuid, resolved_type)
    path = (
        _PICSURE_QUERY_SYNC_PATH_LEGACY
        if use_legacy_query_path
        else _PICSURE_QUERY_SYNC_PATH
    )

    try:
        raw = client.post_raw(path, body=body)
    except TransportValidationError as exc:
        raise PicSureValidationError(
            f"Server rejected the query (HTTP {exc.status_code}): {exc.body[:200]}"
        ) from exc
    except TransportNotFoundError as exc:
        raise PicSureQueryError(
            f"Query endpoint not found (HTTP {exc.status_code}): {exc.body[:200]}"
        ) from exc
    except TransportRateLimitError as exc:
        raise PicSureConnectionError(rate_limit_message(exc)) from exc
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not execute query. The server may be temporarily unavailable."
        ) from exc

    if resolved_type == "COUNT":
        return _parse_count(raw)
    if resolved_type == "CROSS_COUNT":
        return _parse_cross_count(raw)
    if resolved_type == "VARIANT_COUNT_FOR_QUERY":
        return _parse_variant_count(raw)
    if resolved_type == "VARIANT_LIST_FOR_QUERY":
        return _parse_variant_list(raw)
    if resolved_type in ("VCF_EXCERPT", "AGGREGATE_VCF_EXCERPT"):
        return _parse_vcf_excerpt(raw)
    return _parse_dataframe(raw)


def build_query_body(
    query: Query | Clause | ClauseGroup,
    resource_uuid: str,
    expected_result_type: str,
) -> dict[str, object]:
    """Assemble the v3 ``/picsure/v3/query/sync`` request body.

    Normalizes the query into a phenotypic filter tree and a list of
    ``includeConcepts``; the tree becomes ``phenotypicClause`` and the
    concept paths become the top-level ``select`` array.

    Notes:
        ``authorizationFilters`` is intentionally omitted from the body.
        PSAMA populates it server-side from the user's token; sending a
        client-asserted list (especially with a long-term token) is
        treated as tampering and can be rejected with a 401.
    """
    filter_tree, select_paths, genomic = _split(query)
    phenotypic = filter_tree.to_query_json() if filter_tree is not None else None
    return {
        "query": {
            "select": select_paths,
            "phenotypicClause": phenotypic,
            "genomicFilters": [g.to_query_json() for g in genomic],
            "expectedResultType": expected_result_type,
            "picsureId": None,
            "id": None,
        },
        "resourceUUID": resource_uuid,
    }


def _split(
    query: Query | Clause | ClauseGroup,
) -> tuple[Clause | ClauseGroup | None, list[str], tuple[GenomicFilter, ...]]:
    """Normalize a runnable query into (filter tree, select paths, genomic).

    Every concept path referenced in the filter tree is folded into the
    select paths, so a query's filter variables are returned as output
    columns without being repeated in ``includeConcepts``. Genomic filters
    do not contribute to ``select``.
    Explicit ``includeConcepts`` keep their position; filter-derived paths
    are appended in tree-traversal order; duplicates are dropped.
    """
    if isinstance(query, Query):
        filter_tree: Clause | ClauseGroup | None = query.phenotypicFilter
        select = list(query.includeConcepts)
        genomic: tuple[GenomicFilter, ...] = query.genomicFilters
    elif isinstance(query, (Clause, ClauseGroup)):
        filter_tree = query
        select = []
        genomic = ()
    else:
        raise PicSureValidationError(
            "Query must be a Clause, ClauseGroup, or Query. Use "
            "buildClause()/buildClauseGroup()/buildQuery() to construct one."
        )

    if filter_tree is not None:
        select.extend(filter_tree.concept_paths())
    return filter_tree, list(dict.fromkeys(select)), genomic


def _resolve_query_type(query_type: QueryType | str) -> str:
    valid = ", ".join(_VALID_QUERY_TYPES.keys())
    if isinstance(query_type, QueryType):
        key = query_type.value
    elif isinstance(query_type, str):
        key = query_type.lower().strip()
    else:
        raise PicSureValidationError(
            f"'{query_type}' is not a valid query type. Pass a QueryType "
            f"member or one of: {valid}."
        )
    if key not in _VALID_QUERY_TYPES:
        raise PicSureValidationError(
            f"'{query_type}' is not a valid query type. Pass a QueryType "
            f"member or one of: {valid}."
        )
    return _VALID_QUERY_TYPES[key]


def _parse_count_string(s: str) -> CountResult:
    """Parse a single PIC-SURE count string into a :class:`CountResult`.

    Recognises three shapes the server emits:

    - ``"42"``      — exact value
    - ``"11309 ±3"`` — noisy (additive margin)
    - ``"< 10"``    — suppressed (below threshold)

    Anything else raises :class:`PicSureQueryError` loudly rather than
    silently coercing.
    """
    text = s.strip()
    if m := _COUNT_EXACT.match(text):
        return CountResult(value=int(m.group(1)), margin=None, cap=None, raw=text)
    if m := _COUNT_NOISY.match(text):
        return CountResult(
            value=int(m.group(1)),
            margin=int(m.group(2)),
            cap=None,
            raw=text,
        )
    if m := _COUNT_SUPPRESSED.match(text):
        return CountResult(value=None, margin=None, cap=int(m.group(1)), raw=text)
    raise PicSureQueryError(
        f"Expected a count response (e.g. '42', '11309 \u00b13', '< 10'), "
        f"but got: '{text[:200]}'"
    )


def _parse_count(raw: bytes) -> CountResult:
    """Decode and parse a bytes count response."""
    return _parse_count_string(raw.decode("utf-8"))


def _parse_cross_count(raw: bytes) -> dict[str, CountResult]:
    """Parse a CROSS_COUNT response into a mapping of concept path → count.

    The server returns a JSON object. Each value may be an exact integer
    (direct HPDS response, ``Map<String, Integer>``) or a count string
    (aggregate-obfuscated response, e.g. ``"42"``, ``"11309 \u00b13"``,
    or ``"< 10"``). Both are parsed into :class:`CountResult`.

    Malformed JSON, non-object top-level values, and malformed count
    values all raise :class:`PicSureQueryError`.
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = raw[:200]
        raise PicSureQueryError(
            f"Expected a cross-count JSON object, but got: {preview!r}"
        ) from exc
    if not isinstance(data, dict):
        raise PicSureQueryError(
            f"Expected a cross-count JSON object, got {type(data).__name__}"
        )
    result: dict[str, CountResult] = {}
    for path, v in data.items():
        key = str(path)
        # bool is an int subclass in Python; guard against True/False
        # masquerading as valid counts.
        if isinstance(v, int) and not isinstance(v, bool):
            result[key] = CountResult(value=v, margin=None, cap=None, raw=str(v))
        else:
            result[key] = _parse_count_string(str(v))
    return result


def _parse_dataframe(raw: bytes) -> pd.DataFrame:
    if not raw.strip():
        return pd.DataFrame()
    try:
        return pd.read_csv(BytesIO(raw), encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PicSureQueryError(
            f"Server returned a malformed CSV response: {raw[:200]!r}"
        ) from exc
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise PicSureQueryError(
            f"Server returned a malformed CSV response: {raw[:200]!r}"
        ) from exc


_QUERY_TYPE_NOT_ALLOWED = "query type not allowed"
_NO_VARIANTS_FOUND = "No Variants Found"


def _parse_variant_count(raw: bytes) -> int:
    """Parse a VARIANT_COUNT_FOR_QUERY response into an integer.

    The server returns the count of distinct matching variant specs as a
    plain integer string. (Unlike patient counts, variant counts are not
    obfuscated; the integration test confirms this against the live server.)
    """
    text = raw.decode("utf-8").strip()
    if _QUERY_TYPE_NOT_ALLOWED in text:
        raise PicSureQueryError(
            f"The server rejected the variant-count query: '{text[:200]}'. "
            "This result type may be disabled on this deployment."
        )
    try:
        return int(text)
    except ValueError as exc:
        raise PicSureQueryError(
            f"Expected an integer variant count, but got: '{text[:200]}'"
        ) from exc


def _parse_variant_list(raw: bytes) -> list[str]:
    """Parse a VARIANT_LIST_FOR_QUERY response into a list of variant specs.

    The server returns ``"[" + specs.join(", ") + "]"``. Each spec is itself
    six comma-separated fields
    (``chromosome,offset,ref,alt,gene,consequence``), so the specs must be
    split on the joiner's ``", "`` (comma-space) — splitting on a bare ``","``
    would shred each spec into its fields. Within a spec the commas have no
    trailing space, so ``", "`` only occurs between specs.
    """
    text = raw.decode("utf-8").strip()
    if _QUERY_TYPE_NOT_ALLOWED in text:
        raise PicSureQueryError(
            f"The server rejected the variant-list query: '{text[:200]}'. "
            "This result type may be disabled on this deployment."
        )
    if not (text.startswith("[") and text.endswith("]")):
        raise PicSureQueryError(
            "Expected a bracketed variant list like "
            "'[7,100000,A,T,CHD8,missense_variant, ...]', "
            f"but got: '{text[:200]}'"
        )
    inner = text[1:-1].strip()
    if not inner:
        return []
    return [tok.strip() for tok in inner.split(", ") if tok.strip()]


def _parse_vcf_excerpt(raw: bytes) -> pd.DataFrame:
    """Parse a (AGGREGATE_)VCF_EXCERPT tab-separated response into a DataFrame.

    Maps the ``"No Variants Found"`` sentinel to an empty DataFrame and
    raises on the ``"... query type not allowed"`` body. The column set is
    server-driven (info columns vary by deployment), so no fixed schema is
    assumed.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PicSureQueryError(
            f"Server returned a malformed VCF excerpt: {raw[:200]!r}"
        ) from exc
    stripped = text.strip()
    if not stripped or stripped.startswith(_NO_VARIANTS_FOUND):
        return pd.DataFrame()
    if _QUERY_TYPE_NOT_ALLOWED in stripped:
        raise PicSureQueryError(
            f"The server rejected the VCF-excerpt query: '{stripped[:200]}'. "
            "This result type may be disabled on this deployment."
        )
    try:
        return pd.read_csv(StringIO(text), sep="\t")
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise PicSureQueryError(
            f"Server returned a malformed VCF excerpt: {raw[:200]!r}"
        ) from exc
