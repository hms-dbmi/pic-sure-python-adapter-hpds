from __future__ import annotations

# The PIC-SURE gateway routes HPDS traffic by URL path, not by a resource
# UUID in the request body: ``/hpds/auth/**`` reaches the authorized
# (non-obfuscated) HPDS and ``/hpds/open/**`` the open (aggregate/obfuscated)
# one.  The backend is a path segment; the version is a ``/v3`` sub-prefix.
#
# The adapter keeps today's split: authorized sessions use the v3 query
# routes, open sessions the v1 (non-versioned) routes — matching the
# deployment where open-access traffic is served only on v1 and authorized
# traffic on v3.

# Search routes keep a ``{resourceId}`` path segment for ingress-contract
# parity, but the query-service ignores it for routing (the backend is chosen
# by the ``/hpds/{auth,open}`` prefix).  It must still parse as a UUID, so we
# send a fixed all-zero placeholder rather than a resource-selection UUID.
_PLACEHOLDER_RESOURCE_ID = "00000000-0000-0000-0000-000000000000"


def query_prefix(backend: str, *, v3: bool) -> str:
    """Return the HPDS query-lifecycle path prefix for a backend.

    Args:
        backend: ``"auth"`` or ``"open"`` — selects the HPDS instance by
            path (replaces the legacy resource-UUID selection).
        v3: When ``True``, target the ``/v3`` query routes; otherwise the
            v1 (non-versioned) routes.

    Returns:
        A path prefix such as ``"/hpds/auth/v3"`` or ``"/hpds/open"``, to
        which a ``/query`` suffix is appended by the caller.
    """
    return f"/hpds/{backend}/v3" if v3 else f"/hpds/{backend}"


def search_values_path(backend: str) -> str:
    """Return the HPDS search-values path for a backend.

    The ``{resourceId}`` segment is a UUID-parseable placeholder that the
    query-service ignores (see :data:`_PLACEHOLDER_RESOURCE_ID`).
    """
    return f"/hpds/{backend}/search/{_PLACEHOLDER_RESOURCE_ID}/values/"
