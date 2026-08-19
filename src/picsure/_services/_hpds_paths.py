from __future__ import annotations

# The PIC-SURE gateway routes HPDS traffic by URL path, not by a resource
# UUID in the request body: ``/picsure/hpds/auth/**`` reaches the authorized
# (non-obfuscated) HPDS and ``/picsure/hpds/open/**`` the open
# (aggregate/obfuscated) one.  The backend is a path segment; the version is a
# ``/v3`` sub-prefix.  The gateway routes ``/hpds/**`` verbatim (no prefix
# strip), so the client must include the ``/picsure`` context prefix.
#
# Both backends use the versioned (/v3) query routes: the open backend's v1
# ingress is retired (returns 502), while v3 preserves count obfuscation via
# AggregateV3Controller.


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
    return f"/picsure/hpds/{backend}/v3" if v3 else f"/picsure/hpds/{backend}"


def search_values_path(backend: str) -> str:
    """Return the HPDS search-values path for a backend.

    The registry-era ``{resourceId}`` placeholder segment is gone: the
    well-defined ingress is ``/hpds/{backend}/search/values``.
    """
    return f"/picsure/hpds/{backend}/search/values"
