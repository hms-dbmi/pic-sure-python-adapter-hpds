from __future__ import annotations

from urllib.parse import urlencode

import pandas as pd

from picsure._services._errors import (
    bodiless_response_succeeded,
    translate_transport_error,
)
from picsure._services._hpds_paths import search_values_path
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError, TransportNotFoundError
from picsure.errors import EmptyBodyError, PicSureQueryError, PicSureValidationError

_GENOMIC_VALUES_OPERATION = "the genomic value lookup"


def _validate_paging(page: int, size: int) -> None:
    """Reject paging arguments before they are urlencoded onto the wire.

    The sibling dictionary search validates its own paging arguments, so
    an unusable value never becomes an HTTP round trip there either. The
    floor is 1 for both because this route's paging is one-based.

    Args:
        page: One-based page number.
        size: Rows per page.

    Raises:
        PicSureValidationError: If either argument is not an integer, is
            a ``bool``, or is below 1.
    """
    if not isinstance(page, int) or isinstance(page, bool):
        raise PicSureValidationError("`page` must be an integer.")
    if page < 1:
        raise PicSureValidationError(
            f"`page` must be 1 or greater (got {page}); genomic value paging is "
            "one-based, unlike searchDictionary's zero-based `page`."
        )
    if not isinstance(size, int) or isinstance(size, bool):
        raise PicSureValidationError("`size` must be an integer.")
    if size < 1:
        raise PicSureValidationError(f"`size` must be 1 or greater (got {size}).")


def search_genomic_values(
    client: PicSureClient,
    genomic_concept_path: str,
    *,
    backend: str,
    query: str = "",
    page: int = 1,
    size: int = 50,
) -> pd.DataFrame:
    """Fetch one page of valid values for a genomic annotation key.

    Hits ``/hpds/{backend}/search/values`` — the backend is chosen by URL
    path (see :func:`picsure._services._hpds_paths.search_values_path`).

    Returns a single-column (``value``) DataFrame. Pagination metadata is
    preserved on ``df.attrs``: ``total``, ``page``, ``size``,
    ``genomic_concept_path``.

    Args:
        client: Authenticated HTTP client.
        genomic_concept_path: The annotation key to list values for, e.g.
            ``"Gene_with_variant"``.
        backend: ``"auth"`` or ``"open"``, selecting the HPDS route.
        query: Optional substring the returned values must match.
        page: **One-based** page number, so the first page is ``page=1``.
            This differs from :func:`picsure._services.search.searchDictionary`,
            whose ``page`` is zero-based.
        size: Rows per page. Named ``size`` here and ``page_size`` in the
            dictionary search.

    Raises:
        PicSureValidationError: If ``genomic_concept_path`` is blank, or
            if ``page`` or ``size`` is not an integer of 1 or greater.
            Both are checked before any request is sent.
        PicSureQueryError: If the endpoint is absent, if the server answers
            with the empty body it sends for a concept that is not a genomic
            annotation, if the body is not JSON, or if the payload is not a
            genomic values object. Only a 2xx with an empty body is read as
            "not a genomic annotation"; a bodiless redirect names its status
            instead, since an expired gateway session looks the same on the
            wire and the annotation key is not what failed. The other cases
            keep the decoder's message.
    """
    if not isinstance(genomic_concept_path, str) or not genomic_concept_path.strip():
        raise PicSureValidationError(
            "genomicConceptPath must be a non-empty string (e.g. 'Gene_with_variant')."
        )
    _validate_paging(page, size)

    params = urlencode(
        {
            "genomicConceptPath": genomic_concept_path,
            "query": query,
            "page": page,
            "size": size,
        }
    )
    path = search_values_path(backend) + "?" + params

    try:
        data = client.get_json(path)
    except EmptyBodyError as exc:
        raise _empty_body_error(exc, genomic_concept_path) from exc
    except TransportNotFoundError as exc:
        raise PicSureQueryError(
            f"Genomic values endpoint not found (HTTP {exc.status_code}). "
            "This deployment may not support genomic value lookups."
        ) from exc
    except TransportError as exc:
        raise translate_transport_error(
            exc, operation=_GENOMIC_VALUES_OPERATION
        ) from exc

    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise PicSureQueryError(
            "Expected a genomic values response with a 'results' list, but "
            f"got: {str(data)[:200]}"
        )

    df = pd.DataFrame({"value": [str(v) for v in data["results"]]})
    df.attrs.update(
        {
            "total": data.get("total"),
            "page": data.get("page"),
            "size": size,
            "genomic_concept_path": genomic_concept_path,
        }
    )
    return df


def _empty_body_error(
    exc: EmptyBodyError, genomic_concept_path: str
) -> PicSureQueryError:
    """Explain a bodiless response, blaming the concept only on a success status.

    A 200 with no body is how this route reports a key that is not a
    genomic annotation, so the concept path is the thing to change. Any
    other status below 400 reaches here too, and a ``302`` to an SSO
    login on an expired gateway session is the common one: nothing about
    the concept path is wrong there, and a caller who reads the concept
    message edits the one argument that was already correct.

    Args:
        exc: The empty-body failure the transport raised.
        genomic_concept_path: The annotation key the caller asked for,
            named only when it is what failed.

    Returns:
        The public error to raise.
    """
    if bodiless_response_succeeded(exc):
        return PicSureQueryError(
            f"The server returned no genomic values payload for "
            f"'{genomic_concept_path}'. That concept may not be a genomic "
            "annotation on this deployment. Valid keys look like "
            "'Gene_with_variant' or 'Variant_consequence_calculated', not a "
            "phenotypic concept path."
        )
    return PicSureQueryError(
        f"The server answered HTTP {exc.status_code} with an empty body on the "
        f"genomic value lookup, so no values came back. Only a 2xx with no "
        f"body reports a key that is not a genomic annotation; a redirect "
        f"usually means the gateway session expired. Reconnect and retry, and "
        f"leave the annotation key as it is."
    )
