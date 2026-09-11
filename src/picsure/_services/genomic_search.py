from __future__ import annotations

from urllib.parse import urlencode

import pandas as pd

from picsure._services._errors import translate_transport_error
from picsure._services._hpds_paths import search_values_path
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError, TransportNotFoundError
from picsure.errors import PicSureQueryError, PicSureValidationError

_GENOMIC_VALUES_OPERATION = "the genomic value lookup"


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

    Raises:
        PicSureValidationError: If ``genomic_concept_path`` is blank.
        PicSureQueryError: If the endpoint is absent, or the response is not
            a genomic values payload — including the empty body the server
            returns for a concept that is not a genomic annotation.
    """
    if not isinstance(genomic_concept_path, str) or not genomic_concept_path.strip():
        raise PicSureValidationError(
            "genomicConceptPath must be a non-empty string (e.g. 'Gene_with_variant')."
        )

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
    except ValueError as exc:
        # The server answers HTTP 200 with an empty body when the concept is
        # not a genomic annotation, which leaves get_json with nothing to
        # decode.  Without this, a JSONDecodeError escapes the library.
        raise PicSureQueryError(
            f"The server returned no genomic values payload for "
            f"'{genomic_concept_path}'. That concept may not be a genomic "
            "annotation on this deployment — valid keys look like "
            "'Gene_with_variant' or 'Variant_consequence_calculated', not a "
            "phenotypic concept path."
        ) from exc
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
