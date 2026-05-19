from __future__ import annotations

import re
from typing import TYPE_CHECKING

from picsure._models.query import Query
from picsure._services._errors import translate_stage_error
from picsure._services.query_run import build_query_body
from picsure._transport.errors import TransportError
from picsure.errors import (
    PicSureQueryError,
    PicSureValidationError,
)

if TYPE_CHECKING:
    from picsure._transport.client import PicSureClient

_QUERY_SUBMIT_PATH = "/picsure/v3/query"
_NAMED_DATASET_COLLECTION_PATH = "/picsure/dataset/named"
_NAMED_DATASET_ITEM_PATH = "/picsure/dataset/named/{named_dataset_id}"

# Mirrors the @Pattern on NamedDatasetRequest.name in pic-sure-api-data.
_NAME_PATTERN = re.compile(r"^[\w\d \-\\/?+=\[\]\.():\"']+$")
_NAME_MAX_LEN = 255


def save_query_by_name(
    client: PicSureClient,
    resource_uuid: str,
    query: Query,
    name: str,
    *,
    use_legacy_query_path: bool,
    overwrite: bool = False,
) -> str:
    """Submit a query, then save it to the user's profile under ``name``.

    Returns the PIC-SURE-generated query ID — the same id that
    :func:`load_query` can re-fetch.

    If a NamedDataset already exists for this user with ``name``:
        * ``overwrite=False`` (default) → raise :class:`PicSureValidationError`.
        * ``overwrite=True``            → re-point the existing record at the
          freshly-submitted query via ``PUT /dataset/named/{id}/``.

    Open-access deployments are not supported: the ``/dataset/named/``
    endpoint requires an authenticated principal.
    """
    if use_legacy_query_path:
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

    body = build_query_body(query, resource_uuid, "COUNT")
    query_id = _submit_and_extract_id(client, body)

    if existing is None:
        _create_named_dataset(client, query_id=query_id, name=name)
    else:
        metadata_raw = existing.get("metadata")
        metadata: dict[str, object] = (
            metadata_raw if isinstance(metadata_raw, dict) else {}
        )
        _update_named_dataset(
            client,
            named_dataset_id=str(existing["uuid"]),
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
        raise translate_stage_error(
            exc, service="saveQueryByName", stage="list"
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
        raise translate_stage_error(
            exc, service="saveQueryByName", stage="save"
        ) from exc


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
        raise translate_stage_error(
            exc, service="saveQueryByName", stage="update"
        ) from exc


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise PicSureValidationError("`name` must be a non-empty string.")
    if len(name) > _NAME_MAX_LEN:
        raise PicSureValidationError(
            f"`name` must be at most {_NAME_MAX_LEN} characters."
        )
    if not _NAME_PATTERN.match(name):
        raise PicSureValidationError(
            "`name` contains unsupported characters. Allowed: letters, digits, "
            "spaces, and the symbols - _ \\ / ? + = [ ] . ( ) : \" '"
        )


def _submit_and_extract_id(client: PicSureClient, body: dict[str, object]) -> str:
    try:
        response = client.post_json(_QUERY_SUBMIT_PATH, body=body)
    except TransportError as exc:
        raise translate_stage_error(
            exc, service="saveQueryByName", stage="submit"
        ) from exc
    for field in ("picsureResultId", "resourceResultId", "queryId"):
        v = response.get(field)
        if isinstance(v, str) and v:
            return v
    raise PicSureQueryError(
        "Server did not return a query id in the submit response "
        "(expected 'picsureResultId')."
    )
