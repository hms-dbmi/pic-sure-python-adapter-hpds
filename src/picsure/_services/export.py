from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

import pandas as pd

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.query import Query
from picsure._services._errors import translate_transport_error
from picsure._services._hpds_paths import query_prefix
from picsure._services.query_run import build_query_body
from picsure._transport.client import PicSureClient, json_object
from picsure._transport.errors import TransportError
from picsure.errors import (
    PicSureConnectionError,
    PicSureQueryError,
    PicSureValidationError,
)

# Terminal status values returned by PIC-SURE's ``PicSureStatus`` enum.
# Only AVAILABLE (success) and ERROR (failure) are terminal; every other
# status (QUEUED, PENDING, RUNNING, STARTED, PROCESSING, or any future HPDS
# value surfaced via ``resourceStatus``) is treated as in-progress and we
# keep polling, bounded by ``_TOTAL_TIMEOUT_SECONDS`` (10 minutes).
_STATUS_AVAILABLE = "AVAILABLE"
_STATUS_ERROR = "ERROR"

# Polling parameters.  The sequence is 1s, 2s, 4s, 8s, 16s, 32s, 60s, 60s, ...
# (doubling, capped at 60s per poll).  Cumulative elapsed time is bounded
# by ``_TOTAL_TIMEOUT_SECONDS``.
_INITIAL_POLL_INTERVAL_SECONDS = 1.0
_MAX_POLL_INTERVAL_SECONDS = 60.0
_TOTAL_TIMEOUT_SECONDS = 600.0


def export_pfb(
    client: PicSureClient,
    query: Query | Clause | ClauseGroup,
    path: str | Path,
    *,
    backend: str,
) -> None:
    """Execute a query and stream the PFB result to disk.

    Uses PIC-SURE's async flow on the authorized v3 routes, built from
    ``backend`` by :func:`~picsure._services._hpds_paths.query_prefix`:

    1. ``POST /picsure/hpds/auth/v3/query`` — submit the query, receive a
       query id.
    2. ``POST /picsure/hpds/auth/v3/query/{id}/status`` — poll with
       exponential backoff (1s, 2s, 4s, ..., capped at 60s per poll) until
       the server reports ``AVAILABLE``.  Total elapsed time is bounded at
       10 minutes.
    3. ``POST /picsure/hpds/auth/v3/query/{id}/result`` — stream the
       Avro-binary PFB bytes straight to disk.

    The output file is written atomically: bytes land at
    ``<path>.part``, then :func:`os.replace` promotes that to ``path``
    on success.  Any exception after the ``.part`` file has been
    created removes the partial file before re-raising.

    Args:
        client: Authenticated HTTP client.
        query: A Clause or ClauseGroup.
        path: File path to write the PFB data to.  Accepts ``str`` or
            :class:`pathlib.Path`.
        backend: ``"auth"`` — PFB export is only supported on authorized
            sessions (the caller rejects ``"open"`` before reaching here).

    Raises:
        PicSureValidationError: If the server rejects the request
            (HTTP 400 / 422 / other 4xx) at any stage.
        PicSureQueryError: If the server returns 404 for the submit,
            status, or result endpoint.
        PicSureAuthenticationError: If the server returns 401.
        PicSureAuthorizationError: If the server returns 403.
        PicSureConnectionError: If the server is unreachable, rate
            limits the request, returns 5xx after retries, fails the
            query (terminal status ``ERROR``), does not produce a result
            within 10 minutes, or the local disk write fails.
    """
    target = Path(path)
    part_path = target.with_suffix(target.suffix + ".part")

    base = query_prefix(backend, v3=True)
    body = build_query_body(query, "DATAFRAME_PFB")

    # 1. Submit the query.
    submit_response = _submit_query(client, base, body)
    query_id = _extract_query_id(submit_response)

    # 2. Poll until AVAILABLE (or timeout / error).
    _poll_until_available(client, base, query_id, body)

    # 3. Stream the result to disk atomically.
    _download_result(client, base, query_id, body, target, part_path)


def _submit_query(
    client: PicSureClient,
    base: str,
    body: dict[str, object],
) -> dict[str, object]:
    submit_path = f"{base}/query"
    try:
        payload = client.post_json(submit_path, body=body)
    except TransportError as exc:
        raise translate_transport_error(exc, operation="the PFB export submit") from exc
    return json_object(payload, path=submit_path)


def _extract_query_id(response: dict[str, object]) -> str:
    """Pull the query id out of the submit response.

    The gateway populates ``picsureResultId`` (and mirrors it into
    ``resourceResultId``).  Either field is acceptable; prefer
    ``picsureResultId`` because that's the path parameter the
    ``/query/{id}/status`` and ``/query/{id}/result`` routes match on.
    """
    for field in ("picsureResultId", "resourceResultId", "queryId"):
        value = response.get(field)
        if isinstance(value, str) and value:
            return value
    raise PicSureQueryError(
        "Server did not return a query id in the PFB submit response "
        "(expected 'picsureResultId')."
    )


def _poll_until_available(
    client: PicSureClient,
    base: str,
    query_id: str,
    body: dict[str, object],
) -> None:
    status_path = f"{base}/query/{query_id}/status"

    interval = _INITIAL_POLL_INTERVAL_SECONDS
    start = time.monotonic()

    while True:
        try:
            status_payload = client.post_json(status_path, body=body)
        except TransportError as exc:
            raise translate_transport_error(
                exc, operation="the PFB export status check"
            ) from exc

        status = _extract_status(json_object(status_payload, path=status_path))

        if status == _STATUS_AVAILABLE:
            return
        if status == _STATUS_ERROR:
            raise PicSureQueryError(
                f"PFB export failed on the server (query {query_id} status=ERROR)."
            )
        # Any other status is treated as in-progress; keep polling. The
        # 10-minute total timeout below protects against an infinite loop.

        elapsed = time.monotonic() - start
        if elapsed >= _TOTAL_TIMEOUT_SECONDS:
            raise PicSureConnectionError(
                "PFB export did not complete within 10 minutes."
            )

        time.sleep(interval)
        interval = min(interval * 2, _MAX_POLL_INTERVAL_SECONDS)


def _extract_status(response: dict[str, object]) -> str:
    """Pull the status string out of a ``QueryStatus`` response.

    PIC-SURE's ``QueryStatus`` has both a top-level ``status`` (the
    canonical ``PicSureStatus`` enum) and ``resourceStatus`` (the raw
    string from HPDS).  They should agree in v3; prefer ``status``.
    """
    for field in ("status", "resourceStatus"):
        value = response.get(field)
        if isinstance(value, str) and value:
            return value.upper()
    raise PicSureQueryError(
        "Server did not return a status field in the PFB poll response."
    )


def _download_result(
    client: PicSureClient,
    base: str,
    query_id: str,
    body: dict[str, object],
    target: Path,
    part_path: Path,
) -> None:
    result_path = f"{base}/query/{query_id}/result"

    try:
        with client.post_raw_stream(result_path, body=body) as response:
            _stream_to_file(response, part_path)
    except TransportError as exc:
        _cleanup_partial(part_path)
        raise translate_transport_error(
            exc, operation="the PFB export download"
        ) from exc
    except OSError as exc:
        _cleanup_partial(part_path)
        raise PicSureConnectionError(f"Could not write PFB to {target}: {exc}") from exc
    except BaseException:
        _cleanup_partial(part_path)
        raise

    # Promote .part -> final path atomically.
    try:
        os.replace(part_path, target)
    except OSError as exc:
        _cleanup_partial(part_path)
        raise PicSureConnectionError(
            f"Could not finalise PFB at {target}: {exc}"
        ) from exc


def _stream_to_file(response: object, part_path: Path) -> None:
    """Iterate ``response.iter_bytes()`` into ``part_path``.

    Separated out so the streaming body is easy to mock in tests.
    Typed ``response: object`` intentionally — the concrete type is
    :class:`httpx.Response`, but declaring it here would force a
    transport-layer import into this helper.
    """
    with open(part_path, "wb") as out:
        for chunk in response.iter_bytes(chunk_size=64 * 1024):  # type: ignore[attr-defined]
            if chunk:
                out.write(chunk)


def _cleanup_partial(part_path: Path) -> None:
    """Best-effort removal of the ``.part`` staging file.

    If we can't even delete the partial, there's nothing useful to do —
    the original exception will still propagate.
    """
    with contextlib.suppress(OSError):
        part_path.unlink(missing_ok=True)


def export_csv(data: pd.DataFrame, path: str | Path) -> None:
    """Write a DataFrame to a CSV file.

    Args:
        data: DataFrame to export (e.g. from runQuery).
        path: File path for the CSV output.

    Raises:
        PicSureValidationError: If ``data`` is not a DataFrame.
        PicSureConnectionError: If ``path`` could not be written.
    """
    _write_delimited(data, path, sep=",", fmt="CSV", method="exportCSV")


def export_tsv(data: pd.DataFrame, path: str | Path) -> None:
    """Write a DataFrame to a TSV file.

    Args:
        data: DataFrame to export (e.g. from runQuery).
        path: File path for the TSV output.

    Raises:
        PicSureValidationError: If ``data`` is not a DataFrame.
        PicSureConnectionError: If ``path`` could not be written.
    """
    _write_delimited(data, path, sep="\t", fmt="TSV", method="exportTSV")


def _write_delimited(
    data: pd.DataFrame,
    path: str | Path,
    *,
    sep: str,
    fmt: str,
    method: str,
) -> None:
    """Write a DataFrame to a delimited file inside the public error hierarchy.

    ``DataFrame.to_csv`` raises a bare ``OSError`` for an unwritable path
    and, handed something that is not a DataFrame, an ``AttributeError``
    naming ``to_csv`` -- neither of which a caller wrapping the call in
    ``except PicSureError`` catches, and neither of which names the path
    that failed. The type is checked up front rather than caught, so the
    message can say what arrived instead.

    Args:
        data: DataFrame to write.
        path: Destination file path.
        sep: Field delimiter.
        fmt: Format name used in messages, e.g. ``"CSV"``.
        method: Public method name used in messages, e.g. ``"exportCSV"``.

    Raises:
        PicSureValidationError: If ``data`` is not a DataFrame.
        PicSureConnectionError: If the file could not be written.
    """
    if not isinstance(data, pd.DataFrame):
        raise PicSureValidationError(
            f"{method} writes a pandas DataFrame, but got "
            f"{type(data).__name__}. A count query returns a CountResult "
            f"rather than a table -- run the query with "
            f"type='participant' (or read CountResult.value directly) "
            f"before exporting."
        )
    try:
        data.to_csv(path, sep=sep, index=False)
    except OSError as exc:
        raise PicSureConnectionError(f"Could not write {fmt} to {path}: {exc}") from exc
