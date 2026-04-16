from __future__ import annotations

from pathlib import Path

import pandas as pd

from picsure._models.query import Query
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import PicSureConnectionError

_PICSURE_QUERY_SYNC_PATH = "/picsure/query/sync"


def export_pfb(
    client: PicSureClient,
    resource_uuid: str,
    query: Query,
    path: str | Path,
) -> None:
    """Execute a query and write the result as a PFB file.

    Args:
        client: Authenticated HTTP client.
        resource_uuid: The resource to query.
        query: A Clause or ClauseGroup.
        path: File path to write the PFB data to.

    Raises:
        PicSureConnectionError: If the server is unreachable.
    """
    body: dict[str, object] = {
        "resourceUUID": resource_uuid,
        "query": query.to_query_json(),
        "expectedResultType": "PFB",
    }

    try:
        raw = client.post_raw(_PICSURE_QUERY_SYNC_PATH, body=body)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not export PFB. The server may be temporarily unavailable."
        ) from exc

    Path(path).write_bytes(raw)


def export_csv(data: pd.DataFrame, path: str | Path) -> None:
    """Write a DataFrame to a CSV file.

    Args:
        data: DataFrame to export (e.g. from runQuery).
        path: File path for the CSV output.
    """
    data.to_csv(path, index=False)


def export_tsv(data: pd.DataFrame, path: str | Path) -> None:
    """Write a DataFrame to a TSV file.

    Args:
        data: DataFrame to export (e.g. from runQuery).
        path: File path for the TSV output.
    """
    data.to_csv(path, sep="\t", index=False)
