from __future__ import annotations

import json
from typing import Any

_SENSITIVE_RESULT_TYPES = {
    "DATAFRAME",
    "DATAFRAME_TIMESERIES",
    "DATAFRAME_PFB",
}

# PSAMA's /user/me returns the user's JWT in a `token` field alongside
# `email` and other identity fields.  Treat any of these as secrets when
# they appear in a PSAMA-pathed body.
_PSAMA_SENSITIVE_KEYS = frozenset(
    {
        "email",
        "token",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "apikey",
        "api_key",
    }
)


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with Authorization masked."""
    out = dict(headers)
    for key in list(out.keys()):
        if key.lower() == "authorization":
            out[key] = "Bearer ***"
    return out


def redact_for_log(
    path: str,
    method: str,
    body: dict[str, Any] | list[Any] | None,
) -> str | None:
    """Return a safe string repr of a body, or None if it must not be logged.

    Returning None signals "body is sensitive — log size only."
    """
    if body is None:
        return ""

    if _is_psama_path(path):
        return json.dumps(_redact_psama_secrets(body))

    # Suppress based on body SHAPE, not path: the async PFB export posts the
    # same participant-bearing query body to /picsure/v3/query (and
    # /status, /result), none of which end in /query/sync.
    if _body_is_participant_like(body):
        return None

    # Default: safe to log
    return json.dumps(body, default=str)


def body_is_sensitive(
    path: str,
    method: str,
    body: dict[str, Any] | list[Any] | None,
) -> bool:
    """Cheap predicate: would ``redact_for_log`` refuse to serialize this body?

    Callers that only need the yes/no decision can use this to avoid the
    full ``json.dumps`` round-trip in ``redact_for_log``.
    """
    if body is None:
        return False
    return _body_is_participant_like(body)


def _is_psama_path(path: str) -> bool:
    return path.startswith("/psama/")


def _body_is_participant_like(body: Any) -> bool:
    query = body.get("query") if isinstance(body, dict) else None
    if not isinstance(query, dict):
        return False
    result_type = query.get("expectedResultType")
    return result_type in _SENSITIVE_RESULT_TYPES


def _redact_psama_secrets(body: Any) -> Any:
    if isinstance(body, dict):
        return {
            k: (
                "***"
                if k.lower() in _PSAMA_SENSITIVE_KEYS and isinstance(v, str)
                else _redact_psama_secrets(v)
            )
            for k, v in body.items()
        }
    if isinstance(body, list):
        return [_redact_psama_secrets(item) for item in body]
    return body
