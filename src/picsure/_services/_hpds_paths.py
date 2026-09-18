"""The one place every HPDS route is built.

The PIC-SURE gateway routes HPDS traffic by URL path, not by a resource
UUID in the request body: ``/picsure/hpds/auth/**`` reaches the authorized
(non-obfuscated) HPDS and ``/picsure/hpds/open/**`` the open
(aggregate/obfuscated) one.  The backend is a path segment; the version is a
``/v3`` sub-prefix.  The gateway routes ``/hpds/**`` verbatim (no prefix
strip), so the client must include the ``/picsure`` context prefix.

Both backends use the versioned (/v3) query routes. The path selects the
backend independently of whether the request carries a token.

The query-lifecycle routes carry an identifier the server chose, and the
named-dataset item route carries one the operations service chose, so
every one of them is built here rather than formatted at the call site.
:func:`_segment` is the single place a value is percent-escaped, and it
runs once per path. httpx normalizes ``..`` segments, so an unchecked id
re-points an authenticated request at another route on the same host.

``backend`` is interpolated the same way and is checked against
:data:`BACKENDS` for the same reason. :class:`picsure._models.session.Session`
imports that set rather than keeping a second copy, so the value it
accepts and the values these builders accept cannot drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import quote
from uuid import UUID

from picsure.errors import PicSureQueryError, PicSureValidationError

_QUERY_ID_FIELDS = ("picsureResultId", "resourceResultId", "queryId")

UUID_EXAMPLE = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

BACKENDS = frozenset({"auth", "open"})

NAMED_DATASET_COLLECTION_PATH = "/picsure/operations/dataset/named"


def _check_backend(backend: str) -> None:
    """Refuse a backend that is not one of the two the gateway routes.

    Args:
        backend: The candidate path segment.

    Raises:
        PicSureValidationError: If ``backend`` is not in :data:`BACKENDS`.
    """
    if backend not in BACKENDS:
        raise PicSureValidationError(
            f"backend must be one of {sorted(BACKENDS)}, not {backend!r}. "
            f"It is interpolated straight into the HPDS request path, so "
            f"an unrecognized value would silently produce a 404 on every "
            f"query."
        )


def query_prefix(backend: str, *, v3: bool) -> str:
    """Return the HPDS query-lifecycle path prefix for a backend.

    Args:
        backend: ``"auth"`` or ``"open"``, selecting the HPDS instance by
            path (replaces the legacy resource-UUID selection).
        v3: When ``True``, target the ``/v3`` query routes; otherwise the
            v1 (non-versioned) routes.

    Returns:
        A path prefix such as ``"/picsure/hpds/auth/v3"`` or
        ``"/picsure/hpds/open"``, to which a ``/query`` suffix is appended
        by the caller. The ``/picsure`` context prefix is part of the
        returned path: the gateway routes ``/hpds/**`` verbatim without
        stripping it.

    Raises:
        PicSureValidationError: If ``backend`` is not one of
            :data:`BACKENDS`.
    """
    _check_backend(backend)
    return f"/picsure/hpds/{backend}/v3" if v3 else f"/picsure/hpds/{backend}"


def search_values_path(backend: str) -> str:
    """Return the HPDS search-values path for a backend.

    The registry-era ``{resourceId}`` placeholder segment is gone: the
    well-defined ingress is ``/picsure/hpds/{backend}/search/values``.

    Args:
        backend: ``"auth"`` or ``"open"``.

    Raises:
        PicSureValidationError: If ``backend`` is not one of
            :data:`BACKENDS`.
    """
    _check_backend(backend)
    return f"/picsure/hpds/{backend}/search/values"


def query_submit_path(backend: str) -> str:
    """Return the path a query is submitted to.

    Args:
        backend: ``"auth"`` or ``"open"``.

    Returns:
        The versioned submit path, such as
        ``"/picsure/hpds/auth/v3/query"``.

    Raises:
        PicSureValidationError: If ``backend`` is not one of
            :data:`BACKENDS`.
    """
    return f"{query_prefix(backend, v3=True)}/query"


def query_status_path(backend: str, query_id: str) -> str:
    """Return the poll path for a submitted query.

    Args:
        backend: ``"auth"`` or ``"open"``.
        query_id: The query's canonical identifier, escaped here into a
            single path segment.

    Returns:
        ``"/picsure/hpds/{backend}/v3/query/{id}/status"``.
    """
    return f"{query_submit_path(backend)}/{_segment(query_id)}/status"


def query_result_path(backend: str, query_id: str) -> str:
    """Return the download path for a finished query.

    Args:
        backend: ``"auth"`` or ``"open"``.
        query_id: The query's canonical identifier, escaped here into a
            single path segment.

    Returns:
        ``"/picsure/hpds/{backend}/v3/query/{id}/result"``.
    """
    return f"{query_submit_path(backend)}/{_segment(query_id)}/result"


def query_metadata_path(backend: str, query_id: str) -> str:
    """Return the metadata path for a saved query.

    Query metadata is served under the versioned (/v3) query routes; the
    non-versioned route 404s on the current gateway. The ``backend``
    segment is required for routing, but the read does not depend on
    which backend is named.

    Args:
        backend: ``"auth"`` or ``"open"``.
        query_id: The query's canonical identifier, escaped here into a
            single path segment.

    Returns:
        ``"/picsure/hpds/{backend}/v3/query/{id}/metadata"``.
    """
    return f"{query_submit_path(backend)}/{_segment(query_id)}/metadata"


def named_dataset_item_path(named_dataset_id: str) -> str:
    """Return the item path for one saved NamedDataset record.

    The named-dataset collection lives on the operations service rather
    than on HPDS. The gateway routes ``/operations/**`` there and does
    not strip the prefix, so the client path carries the ``/picsure``
    context prefix like every other one here. There is no gateway
    catch-all; an unrouted path falls through to the SPA and 404s. The
    mapping is slash-less server-side and Spring 6 answers a trailing
    slash with a 404, so the built path must not gain one.

    Args:
        named_dataset_id: The record's canonical identifier, escaped
            here into a single path segment.

    Returns:
        ``"/picsure/operations/dataset/named/{id}"``.
    """
    return f"{NAMED_DATASET_COLLECTION_PATH}/{_segment(named_dataset_id)}"


def query_id_from_submit_response(
    response: Mapping[str, object], *, operation: str
) -> str:
    """Read the query id a submit response carries, in canonical form.

    The gateway populates ``picsureResultId`` and mirrors it into
    ``resourceResultId``; ``queryId`` is read last. ``picsureResultId`` is
    preferred because it is the path parameter the ``/query/{id}/status``
    and ``/query/{id}/result`` routes match on.

    The id is the server's, so an id that is not a UUID is a malformed
    response rather than a caller mistake, and it raises
    :class:`~picsure.errors.PicSureQueryError` rather than a validation
    error.

    Args:
        response: The decoded submit response body.
        operation: Noun phrase naming what was submitted, read as the
            object of the error messages, e.g. ``"the PFB export"``.

    Returns:
        The canonical lower-case hyphenated UUID, unescaped. It is a path
        segment only once a path builder here escapes it, and it is also
        what a request body and a public return value carry.

    Raises:
        PicSureQueryError: If no field carries a non-empty string, or the
            id the server sent is not a UUID.
    """
    for field in _QUERY_ID_FIELDS:
        value = response.get(field)
        if isinstance(value, str) and value:
            return canonical_server_id(
                value, description=f"The query id returned for {operation}"
            )
    raise PicSureQueryError(
        f"Server did not return a query id in the submit response for "
        f"{operation} (expected 'picsureResultId')."
    )


def canonical_server_id(value: object, *, description: str) -> str:
    """Check a server-supplied identifier and return it in canonical form.

    The result is not escaped. Every caller either hands it to a path
    builder here, which escapes it once, or uses it as a request-body
    value or a return value, where an escaped form would be wrong.

    Args:
        value: The identifier exactly as the server sent it.
        description: Capitalized noun phrase naming the identifier, used
            as the subject of the error message, e.g. ``"The query id
            returned for the PFB export"``.

    Returns:
        The canonical lower-case hyphenated UUID.

    Raises:
        PicSureQueryError: If ``value`` is not a string, is blank, or is
            not a UUID. The message quotes what came back.
    """
    if not isinstance(value, str) or not value.strip():
        raise PicSureQueryError(
            f"{description} is missing or is not a string: {value!r}."
        )
    try:
        canonical = str(UUID(value.strip()))
    except ValueError as exc:
        raise PicSureQueryError(
            f"{description} is not a UUID: {value!r}. A PIC-SURE identifier is "
            f"a UUID, for example '{UUID_EXAMPLE}'. The value came back from "
            f"the server, so this is a malformed response rather than a bad "
            f"argument."
        ) from exc
    return canonical


def _segment(value: str) -> str:
    """Percent-escape a value so it stays inside one path segment."""
    return quote(value, safe="")
