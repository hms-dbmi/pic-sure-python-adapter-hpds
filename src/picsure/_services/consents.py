from __future__ import annotations

from picsure._paths import PSAMA_USER_CONSENTS_PATH
from picsure._transport.client import PicSureClient
from picsure._transport.errors import TransportError
from picsure.errors import PicSureConnectionError

# The CONCEPT PATHS PSAMA's BdcConsentsBuilder files consents under.  These are
# map KEYS, not study accessions, and the escaping is part of the key: a drift
# of a single backslash reads as "no consents" and silently drops every
# authorization filter rather than failing loudly.
CONSENTS_KEY = "\\_consents\\"
HARMONIZED_CONSENTS_KEY = "\\_harmonized_consent\\"
TOPMED_CONSENTS_KEY = "\\_topmed_consents\\"


def consent_values(consents: object, concept_path: str) -> list[str]:
    """Return the consent identifiers stored under ``concept_path``.

    The values ride verbatim -- they are matched against dictionary values
    and put into a v3 query as-is, never parsed or reformatted.

    Args:
        consents: The ``consents`` map from a ``UserConsentsResponse``.
        concept_path: One of the ``*_CONSENTS_KEY`` constants, or any other
            key the server may add.

    Returns:
        The identifiers, or an empty list when the path is absent, null, or
        malformed.  The server documents the keys it writes as KNOWN rather
        than exhaustive, so an unrecognised path means "nothing authorized
        here", never an error.
    """
    if not isinstance(consents, dict):
        return []
    values = consents.get(concept_path)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def fetch_consents(client: PicSureClient) -> list[str]:
    """Fetch the user's consent list from PSAMA.

    ``GET /psama/user/me/consents`` answers PSAMA's ``UserConsentsResponse``
    contract: ``{"userId": ..., "consents": {<concept path>: [<id>, ...]}}``.
    The map is keyed by CONCEPT PATH -- not by study accession -- and
    ``\\\\_consents\\\\`` holds every consent identifier the user is authorized
    for plus every public study.  That list is what dictionary-api calls
    require on authorized deployments.

    This replaced a read of ``/psama/user/me/queryTemplate/``, which carried
    the same map inside a JSON-encoded string and has been DELETED
    server-side.  The endpoint is self-scoped: the subject comes from the
    token, so no user id appears in the path.

    Args:
        client: Authenticated HTTP client.

    Returns:
        The list of consent identifiers (e.g. ``["phs000007.c1", ...]``).
        Empty list if the user has no stored consents -- which the server
        answers as ``{"userId": ..., "consents": {}}`` rather than an error.

    Raises:
        PicSureConnectionError: If the HTTP call fails.
    """
    try:
        response = client.get_json(PSAMA_USER_CONSENTS_PATH)
    except TransportError as exc:
        raise PicSureConnectionError(
            "Could not fetch your consent list from PSAMA. "
            "The server may be temporarily unavailable."
        ) from exc

    return consent_values(response.get("consents"), CONSENTS_KEY)
