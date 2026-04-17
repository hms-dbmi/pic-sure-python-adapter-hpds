from __future__ import annotations

import json

from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import PicSureConnectionError

_QUERY_TEMPLATE_PATH = "/psama/user/me/queryTemplate/"
_CONSENTS_KEY = "\\_consents\\"


def fetch_consents(client: PicSureClient) -> list[str]:
    """Fetch the user's consent list from the PSAMA query template.

    The query template endpoint returns a JSON object whose
    ``queryTemplate`` field is itself a JSON-encoded string.  Inside
    that string, ``categoryFilters["\\\\_consents\\\\"]`` holds the
    list of study-consent identifiers the user is authorized for.
    That list is what dictionary-api calls require on authorized
    deployments.

    Args:
        client: Authenticated HTTP client.

    Returns:
        The list of consent identifiers (e.g. ``["phs000007.c1", ...]``).
        Empty list if the template, filters, or consents key is missing.

    Raises:
        PicSureConnectionError: If the HTTP call fails or the template
            is not valid JSON.
    """
    try:
        response = client.get_json(_QUERY_TEMPLATE_PATH)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not fetch your consent list from PSAMA. "
            "The server may be temporarily unavailable."
        ) from exc

    template_raw = response.get("queryTemplate")
    if not isinstance(template_raw, str):
        return []

    try:
        template = json.loads(template_raw)
    except json.JSONDecodeError as exc:
        raise PicSureConnectionError(
            "Received a malformed query template from PSAMA. "
            "Contact your PIC-SURE administrator if this persists."
        ) from exc

    filters = template.get("categoryFilters", {})
    consents = filters.get(_CONSENTS_KEY, [])
    if not isinstance(consents, list):
        return []
    return [str(c) for c in consents]
