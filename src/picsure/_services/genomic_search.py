from __future__ import annotations

from urllib.parse import urlencode

import pandas as pd

from picsure._services._errors import rate_limit_message
from picsure._transport.client import PicSureClient
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportValidationError,
)
from picsure.errors import (
    PicSureAuthError,
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

_VALUES_PATH = "/picsure/search/{resource_uuid}/values/"


def search_genomic_values(
    client: PicSureClient,
    resource_uuid: str,
    genomic_concept_path: str,
    *,
    query: str = "",
    page: int = 1,
    size: int = 100,
) -> pd.DataFrame:
    """Fetch one page of valid values for a genomic annotation key.

    Returns a single-column (``value``) DataFrame. Pagination metadata is
    preserved on ``df.attrs``: ``total``, ``page``, ``size``,
    ``genomic_concept_path``.
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
    path = _VALUES_PATH.format(resource_uuid=resource_uuid) + "?" + params

    try:
        data = client.get_json(path)
    except TransportAuthenticationError as exc:
        raise PicSureAuthError(
            f"Authentication failed fetching genomic values "
            f"(HTTP {exc.status_code}): {exc.body[:200]}"
        ) from exc
    except TransportNotFoundError as exc:
        raise PicSureQueryError(
            f"Genomic values endpoint not found (HTTP {exc.status_code}). "
            "This deployment may not support genomic value lookups."
        ) from exc
    except TransportValidationError as exc:
        raise PicSureValidationError(
            f"Server rejected the genomic value request "
            f"(HTTP {exc.status_code}): {exc.body[:200]}"
        ) from exc
    except TransportRateLimitError as exc:
        raise PicSureConnectionError(rate_limit_message(exc)) from exc
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not fetch genomic values. The server may be temporarily unavailable."
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
