from __future__ import annotations

# The PIC-SURE gateway routes HPDS traffic by URL path, not by a resource
# UUID in the request body: ``/hpds/auth/**`` reaches the authorized
# (non-obfuscated) HPDS and ``/hpds/open/**`` the open (aggregate/obfuscated)
# one.  The backend is a path segment; the version is a ``/v3`` sub-prefix.
#
# The non-versioned (v1) aliases -- ``/hpds/{backend}/query*``,
# ``/hpds/{backend}/search`` and ``/hpds/{backend}/search/values`` -- have been
# DELETED server-side.  Every route below is ``/v3``, for open and authorized
# sessions alike: open-access async now lives at ``/hpds/open/v3/query``.


def query_prefix(backend: str) -> str:
    """Return the HPDS query-lifecycle path prefix for a backend.

    Args:
        backend: ``"auth"`` or ``"open"`` — selects the HPDS instance by
            path (replaces the legacy resource-UUID selection).

    Returns:
        A path prefix such as ``"/hpds/auth/v3"``, to which a ``/query``
        suffix is appended by the caller.
    """
    return f"/hpds/{backend}/v3"


def search_values_path(backend: str) -> str:
    """Return the HPDS search-values path for a backend.

    The registry-era ``{resourceId}`` placeholder segment is gone and the
    non-versioned alias has been deleted: the well-defined ingress is
    ``/hpds/{backend}/v3/search/values``.
    """
    return f"/hpds/{backend}/v3/search/values"
