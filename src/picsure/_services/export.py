from __future__ import annotations

from pathlib import Path

import pandas as pd

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.count_result import CountResult
from picsure._models.query import Query
from picsure._services.query_run import build_query_body, run_async_query_to_file
from picsure._transport.client import PicSureClient
from picsure.errors import (
    PicSureConnectionError,
    PicSureValidationError,
)

_EXPORT_OPERATION = "the PFB export"


def export_pfb(
    client: PicSureClient,
    query: Query | Clause | ClauseGroup,
    path: str | Path,
    *,
    backend: str,
) -> None:
    """Execute a query and stream the PFB result to disk.

    Runs the server's job flow through
    :func:`picsure._services.query_run.run_async_query_to_file`, the
    same loop a participant or timestamp query uses, on the authorized
    v3 routes: ``POST /picsure/hpds/auth/v3/query`` submits the query,
    ``POST .../query/{id}/status`` is polled straight away and then
    after sleeps of 1s, 2s, 4s, 8s and 10s from there on until the
    server reports ``AVAILABLE``, and ``POST .../query/{id}/result``
    streams the Avro-binary PFB bytes straight to disk. Every route is
    built by :mod:`picsure._services._hpds_paths`, which checks that
    the query id the server chose is a UUID and escapes it into a
    single path segment.

    The submit and the polls together are bounded by the client's
    request timeout, measured from just before the submit and read
    after each poll answers, so one poll that runs to the per-request
    deadline completes before the budget is enforced. The download
    carries the same value as its own per-request deadline.

    The output file is written atomically by
    :meth:`PicSureClient.post_raw_to_file`: bytes land at ``<path>.part``,
    then :func:`os.replace` promotes that to ``path`` on success, and a
    failure at any point removes the partial file before re-raising.

    Args:
        client: Authenticated HTTP client.
        query: A Clause or ClauseGroup.
        path: File path to write the PFB data to.  Accepts ``str`` or
            :class:`pathlib.Path`.
        backend: ``"auth"``. PFB export is only supported on authorized
            sessions (the caller rejects ``"open"`` before reaching here).

    Raises:
        PicSureValidationError: If the server rejects the submit, a poll
            or the download with a 4xx other than 401, 403, 404 and 429.
        PicSureQueryError: If the server returns 404 for the submit,
            status, or result endpoint, answers the submit with no query
            id or with one that is not a UUID, answers a poll with no
            status field, or fails the query (terminal status ``ERROR``).
        PicSureAuthenticationError: If the server returns 401.
        PicSureAuthorizationError: If the server returns 403, including a
            consent denial, which arrives as
            :class:`~picsure.errors.PicSureConsentDeniedError`.
        PicSureConnectionError: If the server is unreachable, rate
            limits the request, leaves the submit and polling past the
            client's request timeout with the result still unavailable,
            or the local disk write fails. A 5xx after retries
            arrives as :class:`~picsure.errors.PicSureServerError` and a
            rejected certificate as
            :class:`~picsure.errors.PicSureTLSError`, both subclasses of
            it.
    """
    target = Path(path)
    body = build_query_body(query, "DATAFRAME_PFB")
    try:
        run_async_query_to_file(
            client, backend, body, target, operation=_EXPORT_OPERATION
        )
    except OSError as exc:
        raise PicSureConnectionError(f"Could not write PFB to {target}: {exc}") from exc


def export_csv(data: pd.DataFrame | pd.Series, path: str | Path) -> None:
    """Write a DataFrame or Series to a CSV file.

    Args:
        data: DataFrame to export (e.g. from runQuery), or a single
            column of one.
        path: File path for the CSV output.

    Raises:
        PicSureValidationError: If ``data`` is neither a DataFrame nor a
            Series.
        PicSureConnectionError: If ``path`` could not be written.
    """
    _write_delimited(data, path, sep=",", fmt="CSV", method="exportCSV")


def export_tsv(data: pd.DataFrame | pd.Series, path: str | Path) -> None:
    """Write a DataFrame or Series to a TSV file.

    Args:
        data: DataFrame to export (e.g. from runQuery), or a single
            column of one.
        path: File path for the TSV output.

    Raises:
        PicSureValidationError: If ``data`` is neither a DataFrame nor a
            Series.
        PicSureConnectionError: If ``path`` could not be written.
    """
    _write_delimited(data, path, sep="\t", fmt="TSV", method="exportTSV")


def _write_delimited(
    data: pd.DataFrame | pd.Series,
    path: str | Path,
    *,
    sep: str,
    fmt: str,
    method: str,
) -> None:
    """Write a DataFrame or Series to a delimited file inside the error hierarchy.

    ``to_csv`` raises a bare ``OSError`` for an unwritable path and, handed
    something that is not a DataFrame or Series, an ``AttributeError``
    naming ``to_csv``. A caller wrapping the call in ``except PicSureError``
    catches neither, and neither names the path that failed. The type is
    checked up front rather than caught, so the message can say what
    arrived instead, and a :class:`CountResult` gets the hint that a
    count query does not produce a table.

    Args:
        data: DataFrame or Series to write.
        path: Destination file path.
        sep: Field delimiter.
        fmt: Format name used in messages, e.g. ``"CSV"``.
        method: Public method name used in messages, e.g. ``"exportCSV"``.

    Raises:
        PicSureValidationError: If ``data`` is neither a DataFrame nor a
            Series.
        PicSureConnectionError: If the file could not be written.
    """
    if not isinstance(data, (pd.DataFrame, pd.Series)):
        raise PicSureValidationError(
            f"{method} writes a pandas DataFrame or Series, but got "
            f"{type(data).__name__}.{_count_result_hint(data)}"
        )
    try:
        data.to_csv(path, sep=sep, index=False)
    except OSError as exc:
        raise PicSureConnectionError(f"Could not write {fmt} to {path}: {exc}") from exc


def _count_result_hint(data: object) -> str:
    """Explain how to get a table when a count result was passed to an export."""
    if not isinstance(data, CountResult):
        return ""
    return (
        " A count query returns a CountResult rather than a table. Run the "
        "query with type='participant' (or read CountResult.value directly) "
        "before exporting."
    )
