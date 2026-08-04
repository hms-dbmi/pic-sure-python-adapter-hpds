"""Single source of truth for the request paths this adapter sends.

Deployments front the API with httpd, which proxies ``/picsure/**`` to the
gateway and STRIPS the ``/picsure/`` prefix on the way in::

    RewriteRule ^/picsure/(.*)$ "http://gateway:8080/$1" [P]
    RewriteRule ^/psama/(.*)$   "http://psama:8090/auth/$1" [P]

So every gateway-bound route the adapter calls -- HPDS, dictionary,
operations -- is written here WITH the ``/picsure`` prefix, exactly as the
web client writes it (see ``PIC-SURE-Frontend/src/lib/paths.ts``, whose
``PREFIX = 'picsure'`` this module mirrors).  PSAMA is the one exception:
httpd proxies ``/psama/**`` straight to the auth service, so it is NOT
gateway-bound and carries no prefix.

The prefix belongs to the deployment ingress, not to the user-facing API:
callers of :func:`picsure.connect` pass the bare origin
(``https://picsure.biodatacatalyst.nhlbi.nih.gov``).  A URL that already
ends in ``/picsure`` is normalized by :func:`normalize_base_url` so the
prefix is never doubled.

HPDS routing notes: the gateway picks the HPDS instance by URL PATH --
``/picsure/hpds/auth/**`` reaches the authorized (non-obfuscated) backend and
``/picsure/hpds/open/**`` the open (aggregate/obfuscated) one -- not by a
resource UUID in the request body.  The non-versioned (v1) aliases
(``/hpds/{backend}/query*``, ``/hpds/{backend}/search[/values]``) have been
DELETED server-side, so every HPDS route below is ``/v3``, for open and
authorized sessions alike.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

# The httpd-stripped ingress prefix shared by every gateway-bound route.
GATEWAY_PREFIX = "/picsure"


def gateway_path(suffix: str) -> str:
    """Return ``suffix`` under the gateway's ``/picsure`` ingress prefix."""
    return f"{GATEWAY_PREFIX}/{suffix.lstrip('/')}"


def normalize_base_url(url: str) -> str:
    """Return the bare origin to hang :data:`GATEWAY_PREFIX` off of.

    Strips trailing slashes and any trailing ``/picsure`` segment(s) a user
    may have copied out of a browser URL bar, so
    ``https://host/picsure`` and ``https://host`` behave identically
    instead of producing ``/picsure/picsure/...``.

    Only the PATH component is trimmed.  A host that happens to be named
    ``picsure`` (``http://picsure``, ``http://picsure:8080``) is left
    untouched -- trimming the raw string would silently destroy it.
    """
    parts = urlsplit(url.strip())
    prefix_segment = GATEWAY_PREFIX.strip("/")

    path = parts.path
    while True:
        head, separator, last = path.rstrip("/").rpartition("/")
        # No separator means the remainder is not a path segment we can
        # safely drop (e.g. a scheme-less "picsure.example.com").
        if not separator or last.lower() != prefix_segment:
            break
        path = head

    return urlunsplit(
        (parts.scheme, parts.netloc, path.rstrip("/"), parts.query, parts.fragment)
    )


# --- HPDS (query-service) --------------------------------------------------


def query_prefix(backend: str) -> str:
    """Return the HPDS query-lifecycle path prefix for a backend.

    Args:
        backend: ``"auth"`` or ``"open"`` — selects the HPDS instance by
            path (replaces the legacy resource-UUID selection).

    Returns:
        A path prefix such as ``"/picsure/hpds/auth/v3"``, to which a
        ``/query`` suffix is appended by the caller.
    """
    return gateway_path(f"hpds/{backend}/v3")


def search_values_path(backend: str) -> str:
    """Return the HPDS search-values path for a backend.

    The registry-era ``{resourceId}`` placeholder segment is gone and the
    non-versioned alias has been deleted: the well-defined ingress is
    ``/picsure/hpds/{backend}/v3/search/values``.
    """
    return f"{query_prefix(backend)}/search/values"


def query_metadata_path(backend: str, query_id: str) -> str:
    """Return the saved-query metadata path for a backend.

    Query metadata is version-agnostic in the query-service (it reads the
    stored query row, not HPDS), but the non-versioned alias has been
    deleted: the route is ``/v3`` like every other HPDS route.  The
    ``{backend}`` segment is required for routing; the read itself does not
    depend on which is named.
    """
    return f"{query_prefix(backend)}/query/{query_id}/metadata"


# --- Dictionary ------------------------------------------------------------

# The gateway routes the dictionary at /dictionary/** (StripPrefix=1) behind
# the /picsure ingress; the legacy /picsure/proxy/dictionary-api relay is gone.
CONCEPTS_PATH = gateway_path("dictionary/concepts")
FACETS_PATH = gateway_path("dictionary/facets")

# --- Operations service ----------------------------------------------------

# The named-dataset collection lives on the operations service, not HPDS.  The
# gateway routes it at its verbatim public path (no prefix strip) and the
# service's own context-path is /operations, so the legacy /picsure/dataset
# catch-all is gone.
NAMED_DATASET_COLLECTION_PATH = gateway_path("operations/dataset/named")
NAMED_DATASET_ITEM_PATH = NAMED_DATASET_COLLECTION_PATH + "/{named_dataset_id}"

# --- PSAMA (NOT gateway-bound) ---------------------------------------------

# httpd proxies /psama/** directly to the auth service (rewriting it to that
# service's own /auth context path), bypassing the gateway entirely -- so this
# route deliberately carries no /picsure prefix.
# The user's study authorizations.  Self-scoped: the subject comes from the
# token, so no user id appears in the path.  This replaced
# /psama/user/me/queryTemplate/, which carried the same map inside a
# JSON-encoded string and has been DELETED server-side.
PSAMA_USER_CONSENTS_PATH = "/psama/user/me/consents"
