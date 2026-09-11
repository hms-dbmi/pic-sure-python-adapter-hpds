from __future__ import annotations

import re
from typing import TYPE_CHECKING

from picsure._models.clause import Clause
from picsure._models.clause_group import ClauseGroup
from picsure._models.query import Query
from picsure._services._errors import translate_transport_error
from picsure._services._hpds_paths import query_prefix
from picsure._services.query_run import build_query_body
from picsure._transport.client import json_object
from picsure._transport.errors import TransportError
from picsure.errors import (
    PicSureQueryError,
    PicSureValidationError,
)

if TYPE_CHECKING:
    from picsure._transport.client import PicSureClient

# The named-dataset collection lives on the operations service, not HPDS. The
# gateway routes ``/operations/**`` there and does not strip the prefix, so the
# client path is ``/picsure/operations/dataset/named``. There is no gateway
# catch-all; an unrouted path falls through to the SPA and 404s. The mapping is
# slash-less server-side, and Spring 6 404s a trailing slash -- so the item
# path must not gain one.
_NAMED_DATASET_COLLECTION_PATH = "/picsure/operations/dataset/named"
_NAMED_DATASET_ITEM_PATH = "/picsure/operations/dataset/named/{named_dataset_id}"

# Mirrors the @Pattern on NamedDatasetRequestDto.name in
# pic-sure-operations-service. That annotation carries no `flags`, so Java's
# \w is ASCII-only -- hence re.ASCII here. Without it Python's Unicode-aware
# \w admits names such as "café", which the server then rejects with a 400.
_NAME_PATTERN = re.compile(r"\A[\w\d \-\\/?+=\[\]\.():\"']+\Z", re.ASCII)
_NAME_ALLOWED_CHAR = re.compile(r"[\w\d \-\\/?+=\[\]\.():\"']", re.ASCII)

# NamedDataset.name is a length-255 column.
_NAME_MAX_LEN = 255


def save_query_by_name(
    client: PicSureClient,
    query: Query | Clause | ClauseGroup,
    name: str,
    *,
    backend: str,
    overwrite: bool = False,
) -> str:
    """Submit a query, then save it to the user's profile under ``name``.

    Returns the PIC-SURE-generated query ID — the same id that
    :func:`load_query` can re-fetch.

    If a NamedDataset already exists for this user with ``name``:
        * ``overwrite=False`` (default) → raise :class:`PicSureValidationError`.
        * ``overwrite=True``            → re-point the existing record at the
          freshly-submitted query via
          ``PUT /picsure/operations/dataset/named/{id}`` — no trailing
          slash, which Spring 6 answers with a 404.

    Open-access deployments are not supported: the
    ``/picsure/operations/dataset/named`` endpoint requires an
    authenticated principal.
    """
    if backend == "open":
        raise PicSureValidationError(
            "saveQueryByName is not supported on open-access platforms. "
            "Connect with an authorized platform (e.g. Platform.BDC_AUTHORIZED) "
            "and a valid token to save named queries."
        )
    _validate_name(name)

    existing = _find_existing_by_name(client, name)
    if existing is not None and not overwrite:
        raise PicSureValidationError(
            f"A named query '{name}' already exists for this user. "
            "Pass overwrite=True to repoint it at the new query."
        )

    body = build_query_body(query, "COUNT")
    submit_path = query_prefix(backend, v3=True) + "/query"
    query_id = _submit_and_extract_id(client, submit_path, body)

    if existing is None:
        _create_named_dataset(client, query_id=query_id, name=name)
    else:
        existing_uuid = existing.get("uuid")
        if not existing_uuid:
            raise PicSureQueryError(
                f"The named query matching '{name}' is missing its identifier; "
                "cannot overwrite it."
            )
        metadata_raw = existing.get("metadata")
        metadata: dict[str, object] = (
            metadata_raw if isinstance(metadata_raw, dict) else {}
        )
        _update_named_dataset(
            client,
            named_dataset_id=str(existing_uuid),
            query_id=query_id,
            name=name,
            archived=bool(existing.get("archived", False)),
            metadata=metadata,
        )
    return query_id


def _find_existing_by_name(
    client: PicSureClient, name: str
) -> dict[str, object] | None:
    """Return the user's NamedDataset record matching ``name``, or ``None``.

    The backend has no unique constraint on (name, user); if duplicates
    somehow exist we return the first match deterministically (sorted by
    uuid) so behavior is stable.
    """
    try:
        response = client.get_json(_NAMED_DATASET_COLLECTION_PATH)
    except TransportError as exc:
        raise translate_transport_error(
            exc, operation="the saved-query name lookup"
        ) from exc
    if isinstance(response, list):
        items: list[object] = response
    elif isinstance(response, dict):
        results = response.get("results")
        items = results if isinstance(results, list) else []
    else:
        items = []
    matches = [r for r in items if isinstance(r, dict) and r.get("name") == name]
    if not matches:
        return None
    return sorted(matches, key=lambda r: str(r.get("uuid") or ""))[0]


def _create_named_dataset(client: PicSureClient, *, query_id: str, name: str) -> None:
    body = {
        "queryId": query_id,
        "name": name,
        "archived": False,
        "metadata": {},
    }
    try:
        client.post_json(_NAMED_DATASET_COLLECTION_PATH, body=body)
    except TransportError as exc:
        raise translate_transport_error(exc, operation="the saved-query save") from exc


def _update_named_dataset(
    client: PicSureClient,
    *,
    named_dataset_id: str,
    query_id: str,
    name: str,
    archived: bool,
    metadata: dict[str, object],
) -> None:
    path = _NAMED_DATASET_ITEM_PATH.format(named_dataset_id=named_dataset_id)
    body = {
        "queryId": query_id,
        "name": name,
        "archived": archived,
        "metadata": metadata,
    }
    try:
        client.put_json(path, body=body)
    except TransportError as exc:
        raise translate_transport_error(
            exc, operation="the saved-query update"
        ) from exc


def _validate_name(name: str) -> None:
    """Reject a name the server's @Pattern would reject, before any query runs.

    Args:
        name: Candidate NamedDataset name.

    Raises:
        PicSureValidationError: If ``name`` is empty, longer than 255
            characters, or contains a character outside the server's
            ASCII-only allow-list. The message names the offending
            characters.
    """
    if not isinstance(name, str) or not name:
        raise PicSureValidationError("`name` must be a non-empty string.")
    if len(name) > _NAME_MAX_LEN:
        raise PicSureValidationError(
            f"`name` must be at most {_NAME_MAX_LEN} characters (got {len(name)})."
        )
    if not _NAME_PATTERN.match(name):
        offenders = sorted({c for c in name if not _NAME_ALLOWED_CHAR.match(c)})
        rendered = ", ".join(repr(c) for c in offenders)
        raise PicSureValidationError(
            f"`name` contains characters the server rejects: {rendered}. "
            "Allowed: ASCII letters, digits, underscore, space, and "
            "- \\ / ? + = [ ] . ( ) : \" ' — accented and non-Latin "
            "characters are not accepted. Rename the query and retry; "
            "no query was submitted."
        )


def _submit_and_extract_id(
    client: PicSureClient, submit_path: str, body: dict[str, object]
) -> str:
    try:
        payload = client.post_json(submit_path, body=body)
    except TransportError as exc:
        raise translate_transport_error(
            exc, operation="the saveQueryByName query submit"
        ) from exc
    response = json_object(payload, path=submit_path)
    for field in ("picsureResultId", "resourceResultId", "queryId"):
        v = response.get(field)
        if isinstance(v, str) and v:
            return v
    raise PicSureQueryError(
        "Server did not return a query id in the submit response "
        "(expected 'picsureResultId')."
    )
