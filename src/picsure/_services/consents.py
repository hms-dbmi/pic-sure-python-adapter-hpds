from __future__ import annotations

from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import PicSureConnectionError

_CONSENTS_PATH = "/psama/user/me/consents"
_CONSENTS_KEY = "\\_consents\\"


def fetch_consents(client: PicSureClient) -> list[str]:
    """Fetch the user's consent list from PSAMA.

    The consents endpoint returns the user's ``UserConsents`` record,
    whose ``consents`` field maps category keys to identifier lists.
    ``consents["\\\\_consents\\\\"]`` holds the study-consent identifiers
    the user is authorized for, which is what dictionary-api calls
    require on authorized deployments.

    A user with no consent record yields an empty ``consents`` map, so
    an empty list here means "no authorized studies", not a failure.

    Args:
        client: Authenticated HTTP client.

    Returns:
        The list of consent identifiers (e.g. ``["phs000007.c1", ...]``).
        Empty list if the record or the consents key is missing.

    Raises:
        PicSureConnectionError: If the HTTP call fails.
    """
    try:
        response = client.get_json(_CONSENTS_PATH)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not fetch your consent list from PSAMA. "
            "The server may be temporarily unavailable."
        ) from exc

    consents_map = response.get("consents")
    if not isinstance(consents_map, dict):
        return []

    consents = consents_map.get(_CONSENTS_KEY, [])
    if not isinstance(consents, list):
        return []
    return [str(c) for c in consents]
