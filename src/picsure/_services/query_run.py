from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import NoReturn

import pandas as pd

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.count_result import CountResult
from picsure._models.genomic_filter import GenomicFilter
from picsure._models.query import Query
from picsure._models.query_type import QueryType
from picsure._services._errors import translate_transport_error
from picsure._services._hpds_paths import query_prefix
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError, TransportServerError
from picsure.errors import PicSureQueryError, PicSureValidationError

_QUERY_OPERATION = "the query"

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

# Result types that ask the backend for variant-level output rather than a
# patient cohort.  BDC does not serve these yet; a 5xx (or an empty response)
# for one of them means "unsupported on this deployment", not a transient
# outage, so it is surfaced as a clear PicSureQueryError.
_VARIANT_RESULT_TYPES = frozenset(
    {
        "VARIANT_COUNT_FOR_QUERY",
        "VARIANT_LIST_FOR_QUERY",
        "VCF_EXCERPT",
        "AGGREGATE_VCF_EXCERPT",
    }
)

# Result types that come back as a CSV cohort export rather than a short
# JSON or count body.  These are the only ones large enough to be worth
# streaming: a participant download for a big cohort can run to hundreds of
# megabytes.  (VCF excerpts have their own parser and are not included.)
_DATAFRAME_RESULT_TYPES = frozenset({"DATAFRAME", "DATAFRAME_TIMESERIES"})

# How much of a download to quote back in a parse-failure message, and how
# much to read at a time when checking whether a body is blank.
_PREVIEW_BYTES = 200
_SCAN_BYTES = 64 * 1024

_COUNT_EXACT = re.compile(r"^(\d+)$")
_COUNT_NOISY = re.compile(r"^(\d+)\s*\u00b1\s*(\d+)$")
_COUNT_SUPPRESSED = re.compile(r"^<\s*(\d+)$")


def run_query(
    client: PicSureClient,
    query: Query | Clause | ClauseGroup,
    query_type: QueryType | str,
    *,
    backend: str,
) -> CountResult | dict[str, CountResult] | pd.DataFrame | list[str]:
    """Execute a query against PIC-SURE and return the result.

    Args:
        client: Authenticated HTTP client.
        query: A Query, Clause, or ClauseGroup built with
            buildQuery/buildClause/buildClauseGroup.
        query_type: A :class:`QueryType` member (e.g. ``QueryType.COUNT``)
            or one of the strings ``"count"``, ``"participant"``,
            ``"timestamp"``, ``"cross_count"``.
        backend: ``"auth"`` or ``"open"`` selects the HPDS backend by
            URL path. Both backends use their versioned v3 query route.

    Returns:
        - ``count``        → :class:`CountResult`
        - ``cross_count``  → ``dict[str, CountResult]`` keyed by concept path
        - ``participant``  → :class:`pandas.DataFrame`
        - ``timestamp``    → :class:`pandas.DataFrame`
        - ``variant_count`` → :class:`CountResult` (handles obfuscation)
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
    body = build_query_body(query, resolved_type)
    path = query_prefix(backend, v3=True) + "/query/sync"

    if resolved_type in _DATAFRAME_RESULT_TYPES:
        return _run_dataframe_query(client, path, body, resolved_type)

    try:
        raw = client.post_raw(path, body=body)
    except TransportError as exc:
        _raise_query_error(exc, resolved_type)

    if resolved_type == "COUNT":
        return _parse_count(raw, context=_describe_filters(body))
    if resolved_type == "CROSS_COUNT":
        return _parse_cross_count(raw)
    if resolved_type == "VARIANT_COUNT_FOR_QUERY":
        return _parse_variant_count(raw, context=_describe_filters(body))
    if resolved_type == "VARIANT_LIST_FOR_QUERY":
        return _parse_variant_list(raw)
    return _parse_vcf_excerpt(raw)


def _raise_query_error(exc: TransportError, resolved_type: str) -> NoReturn:
    """Re-raise a transport failure from a query as the public error.

    A 5xx on a variant result type is the backend signalling it does not
    serve that output yet (not a transient outage); surface it clearly.
    """
    if isinstance(exc, TransportServerError) and resolved_type in (
        _VARIANT_RESULT_TYPES
    ):
        raise PicSureQueryError(
            f"{_VARIANT_RESULT_UNSUPPORTED} (The server returned "
            f"HTTP {exc.status_code}.)"
        ) from exc
    raise translate_transport_error(exc, operation=_QUERY_OPERATION) from exc


def _run_dataframe_query(
    client: PicSureClient,
    path: str,
    body: dict[str, object],
    resolved_type: str,
) -> pd.DataFrame:
    """Stream a participant or timestamp result and parse it from disk.

    The buffered path holds the whole CSV in memory and then builds a
    DataFrame from it, so peak usage is the raw bytes plus the frame.
    For a large cohort that is enough to exhaust a notebook kernel,
    which presents as a dead kernel with no error rather than as a
    failure -- and the ten-minute data deadline lets much larger results
    through than the old thirty seconds did.  Streaming to a temporary
    file drops the peak to the frame alone.
    """
    with _download_target() as target:
        try:
            client.post_raw_to_file(path, target, body=body)
        except TransportError as exc:
            _raise_query_error(exc, resolved_type)
        return _parse_dataframe(target)


@contextmanager
def _download_target() -> Iterator[Path]:
    """Yield a path to stream a download into, removed on the way out.

    The enclosing directory is what gets cleaned up, so the ``.part``
    staging file :meth:`PicSureClient.post_raw_to_file` writes goes with
    it whether the download succeeded, failed part-way, or the parse
    afterwards raised.
    """
    with tempfile.TemporaryDirectory(prefix="picsure-query-") as directory:
        yield Path(directory) / "result.csv"


def build_query_body(
    query: Query | Clause | ClauseGroup,
    expected_result_type: str,
) -> dict[str, object]:
    """Assemble the ``/picsure/hpds/{auth,open}/v3/query`` request body.

    Normalizes the query into a phenotypic filter tree and a list of
    ``includeConcepts``; the tree becomes ``phenotypicClause`` and the
    concept paths become the top-level ``select`` array.

    Notes:
        No ``resourceUUID`` is sent: the gateway selects the HPDS backend
        by URL path (``/picsure/hpds/auth`` vs ``/picsure/hpds/open``), not
        by a resource-selection UUID in the body.

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


def _parse_count(raw: bytes, *, context: str = "") -> CountResult:
    """Decode and parse a bytes count response.

    Args:
        raw: The response body.
        context: A description of the query's filters, used to make the
            empty-body message actionable.
    """
    text = raw.decode("utf-8")
    if not text.strip():
        raise PicSureQueryError(_empty_count_message(context))
    return _parse_count_string(text)


def _empty_count_message(context: str) -> str:
    """Explain an empty body where a count was expected.

    The server answers HTTP 200 with no body when it cannot apply a filter,
    so the likeliest cause is a filter the query could not run with — most
    often a filter whose shape does not match its concept's type (a numeric
    ``min``/``max`` on a categorical concept, or ``categories`` on a
    continuous one).
    """
    detail = f" {context}" if context else ""
    return (
        "The server returned an empty response where a count was expected, "
        "which usually means the query was not run — most often because a "
        f"filter could not be applied to the concept it names.{detail} Check "
        "that each filter's shape matches its concept's type: min/max applies "
        "to a continuous concept and categories to a categorical one. "
        "searchDictionary() reports a concept's type."
    )


def _clause_concept_paths(clause: object) -> list[str]:
    """Collect ``conceptPath`` values from a serialized phenotypic clause tree."""
    if not isinstance(clause, dict):
        return []
    path = clause.get("conceptPath")
    if isinstance(path, str):
        return [path]
    children = clause.get("phenotypicClauses")
    if not isinstance(children, list):
        return []
    paths: list[str] = []
    for child in children:
        paths.extend(_clause_concept_paths(child))
    return paths


def _describe_filters(body: dict[str, object]) -> str:
    """Name the filters a request body carries, for use in error messages.

    Returns an empty string if the body is not shaped as expected, so a
    diagnostic message never depends on the body's structure.
    """
    query = body.get("query")
    if not isinstance(query, dict):
        return ""
    concepts = dict.fromkeys(_clause_concept_paths(query.get("phenotypicClause")))
    raw_genomic = query.get("genomicFilters")
    genomic_keys: list[str] = []
    if isinstance(raw_genomic, list):
        genomic_keys = [
            str(g["key"])
            for g in raw_genomic
            if isinstance(g, dict) and isinstance(g.get("key"), str)
        ]
    genomic = dict.fromkeys(genomic_keys)

    parts = []
    if concepts:
        parts.append("phenotypic filters on " + ", ".join(f"'{c}'" for c in concepts))
    if genomic:
        parts.append("genomic filter keys " + ", ".join(f"'{g}'" for g in genomic))
    if not parts:
        return "The query carried no filters."
    return "This query used " + " and ".join(parts) + "."


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


def _parse_dataframe(source: Path) -> pd.DataFrame:
    """Parse a streamed CSV download into a DataFrame.

    Takes a path rather than the response bytes so pandas reads the file
    incrementally and the raw body is never held alongside the frame.
    """
    if _holds_only_whitespace(source):
        return pd.DataFrame()
    try:
        return pd.read_csv(source, encoding="utf-8")
    except (
        UnicodeDecodeError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
    ) as exc:
        raise PicSureQueryError(
            f"Server returned a malformed CSV response: {_download_preview(source)!r}"
        ) from exc


def _holds_only_whitespace(source: Path) -> bool:
    """Whether a download contains no non-whitespace byte.

    An empty or whitespace-only body is a legitimate "no rows" answer
    rather than a parse failure.  Scans in chunks and stops at the first
    real byte, so a full-size result costs a single read.
    """
    with source.open("rb") as handle:
        while chunk := handle.read(_SCAN_BYTES):
            if chunk.strip():
                return False
    return True


def _download_preview(source: Path) -> bytes:
    """Return the leading bytes of a download, to quote in an error."""
    with source.open("rb") as handle:
        return handle.read(_PREVIEW_BYTES)


_QUERY_TYPE_NOT_ALLOWED = "query type not allowed"
_NO_VARIANTS_FOUND = "No Variants Found"
_NO_VARIANT_FILTERS = "No variant filters were supplied"
_VARIANT_RESULT_UNSUPPORTED = (
    "The variant result types (variant_count, variant_list, vcf_excerpt, "
    "aggregate_vcf_excerpt) are not available on this PIC-SURE deployment "
    "yet — genomic filters still work as a constraint on count / "
    "participant queries."
)


def _parse_variant_count(raw: bytes, *, context: str = "") -> CountResult:
    """Parse a VARIANT_COUNT_FOR_QUERY response into a :class:`CountResult`.

    The server answers with a JSON object — ``{"count": 1, "message": "Query
    ran successfully"}`` — whose ``count`` is either a number or a count
    string. A bare count string is still accepted for deployments that send
    one. Either way the count is parsed with the same logic as patient
    counts, so an obfuscated response (``"11309 ±3"`` noisy or ``"< 10"``
    suppressed) is represented faithfully rather than raising.

    ``CountResult.raw`` keeps the whole response body, so the server's
    ``message`` is preserved without a field of its own.

    Args:
        raw: The response body.
        context: A description of the query's filters, used to make the
            empty-body message actionable.

    Raises:
        PicSureQueryError: If the body is empty, reports the result type as
            disallowed, says no variant filters were supplied, or carries no
            usable count.
    """
    text = raw.decode("utf-8").strip()
    if not text:
        raise PicSureQueryError(_VARIANT_RESULT_UNSUPPORTED)
    if _QUERY_TYPE_NOT_ALLOWED in text:
        raise PicSureQueryError(
            f"The server rejected the variant-count query: '{text[:200]}'. "
            "This result type may be disabled on this deployment."
        )
    payload = _variant_count_payload(text)
    if payload is None:
        return _parse_count_string(text)
    return _variant_count_from_payload(payload, text, context)


def _variant_count_payload(text: str) -> dict[str, object] | None:
    """Return the response as a JSON object, or ``None`` if it is not one.

    A bare count such as ``"42"`` is valid JSON but not an object, so it
    falls through to the count-string parser.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _variant_count_from_payload(
    payload: dict[str, object],
    text: str,
    context: str,
) -> CountResult:
    """Read the count out of a variant-count JSON object.

    ``raw`` is set to the whole body rather than just the count, so the
    server's ``message`` survives on the returned :class:`CountResult`.
    """
    message = payload.get("message")
    if isinstance(message, str) and _NO_VARIANT_FILTERS in message:
        detail = f" {context}" if context else ""
        raise PicSureQueryError(
            "A variant count needs at least one genomic filter, and the "
            f"server reports that none were supplied: '{message[:200]}'.{detail} "
            "Add a filter with buildGenomicFilter() and pass it to "
            "buildQuery(genomicFilters=...) — a phenotypic filter alone "
            "cannot select variants."
        )

    count = payload.get("count")
    if isinstance(count, bool) or count is None:
        raise PicSureQueryError(
            "Expected a variant-count response with a 'count' field, but "
            f"got: '{text[:200]}'"
        )
    if isinstance(count, int):
        return CountResult(value=count, margin=None, cap=None, raw=text)
    if isinstance(count, str):
        return replace(_parse_count_string(count), raw=text)
    raise PicSureQueryError(
        "Expected a variant-count 'count' to be a number or a count string, "
        f"but got: '{text[:200]}'"
    )


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
    if not text:
        raise PicSureQueryError(_VARIANT_RESULT_UNSUPPORTED)
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
    if not stripped:
        # A served deployment signals "empty" with the "No Variants Found"
        # sentinel below; a truly empty body means the result type is not
        # available here.
        raise PicSureQueryError(_VARIANT_RESULT_UNSUPPORTED)
    if stripped.startswith(_NO_VARIANTS_FOUND):
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
