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

    if _is_query_sync_path(path) and _body_is_participant_like(body):
        return None

    # Default: safe to log
    return json.dumps(body, default=str)


def _is_psama_path(path: str) -> bool:
    return path.startswith("/psama/")


def _is_query_sync_path(path: str) -> bool:
    # Matches both /picsure/query/sync and /picsure/v3/query/sync.
    return path.endswith("/query/sync")


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
