from __future__ import annotations

from picsure._services._errors import translate_transport_error
from picsure._transport.client import PicSureClient, json_object
from picsure._transport.errors import TransportError
from picsure.errors import PicSureConnectionError, PicSureQueryError

_CONSENTS_PATH = "/psama/user/me/consents"
_CONSENTS_KEY = "\\_consents\\"

_CONSENTS_OPERATION = "the PSAMA consent lookup"


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
        PicSureAuthenticationError: If the token is rejected (HTTP 401).
        PicSureAuthorizationError: If the account may not read its own
            consents (HTTP 403).
        PicSureConnectionError: If PSAMA could not be reached or failed,
            and if the response body could not be read as the
            ``UserConsents`` object, which on this route points at the
            base URL rather than at the response. That covers a body that
            is not JSON and a body that is JSON but not an object; both
            are decode failures of the same route and carry the same
            class, so moving the narrowing step does not change what a
            caller catches.
    """
    try:
        response = json_object(client.get_json(_CONSENTS_PATH), path=_CONSENTS_PATH)
    except TransportError as exc:
        raise translate_transport_error(exc, operation=_CONSENTS_OPERATION) from exc
    except PicSureQueryError as exc:
        raise PicSureConnectionError(
            f"{_CONSENTS_PATH} answered with a body the consent list could not "
            f"be read from: either it is not JSON at all, or it is JSON that "
            f"is not the UserConsents object this route returns. This usually "
            f"means the URL is not a PIC-SURE deployment root. The decoder "
            f"said: {exc}"
        ) from exc

    consents_map = response.get("consents")
    if not isinstance(consents_map, dict):
        return []

    consents = consents_map.get(_CONSENTS_KEY, [])
    if not isinstance(consents, list):
        return []
    return [str(c) for c in consents]
