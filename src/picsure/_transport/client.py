from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from picsure._dev.events import Event
from picsure._dev.redaction import redact_for_log
from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportServerError,
)

if TYPE_CHECKING:
    from picsure._dev.config import DevConfig

_MAX_RETRIES = 1
_TIMEOUT_SECONDS = 30.0


class PicSureClient:
    """HTTP client for PIC-SURE API calls.

    Wraps httpx.Client with Bearer token auth, retries on 5xx and
    connection errors, and translation to internal transport exceptions.
    """

    def __init__(
        self,
        base_url: str,
        token: str = "",
        dev_config: DevConfig | None = None,
    ) -> None:
        # BDC's API gateway routes auth based on a "request-source" header:
        # "Authorized" when a bearer token is present, "Open" otherwise.
        # Without it, authorized endpoints (e.g. /picsure/v3/query/sync) can
        # reject tokens that are otherwise valid on PSAMA or the data-dictionary.
        headers = {
            "Content-Type": "application/json",
            "request-source": "Authorized" if token else "Open",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
        self._dev_config = dev_config

    def get_json(self, path: str) -> dict:  # type: ignore[type-arg]
        """Send GET request and return parsed JSON."""
        response = self._request("GET", path, body=None)
        return response.json()  # type: ignore[no-any-return]

    def post_json(self, path: str, body: dict | None = None) -> dict:  # type: ignore[type-arg]
        """Send POST request with JSON body and return parsed JSON."""
        response = self._request("POST", path, body=body)
        return response.json()  # type: ignore[no-any-return]

    def post_raw(self, path: str, body: dict | None = None) -> bytes:  # type: ignore[type-arg]
        """Send POST request with JSON body and return raw response bytes.

        Use this for endpoints that return non-JSON data (CSV, PFB, etc.).
        """
        response = self._request("POST", path, body=body)
        return response.content

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None,  # type: ignore[type-arg]
    ) -> httpx.Response:
        last_exc: Exception | None = None
        kwargs: dict[str, object] = {}
        if body is not None:
            kwargs["json"] = body

        for attempt in range(_MAX_RETRIES + 1):
            start = time.monotonic()
            try:
                response = self._http.request(method, path, **kwargs)  # type: ignore[arg-type]
            except httpx.ConnectError as exc:
                last_exc = exc
                self._emit_error(method, path, attempt, start, type(exc).__name__)
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                last_exc = exc
                self._emit_error(method, path, attempt, start, type(exc).__name__)
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(f"Request timed out: {exc}") from exc

            self._emit_http(method, path, body, response, attempt, start)

            if response.status_code in (401, 403):
                raise TransportAuthenticationError(response.status_code, response.text)

            if response.status_code >= 500:
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportServerError(response.status_code, response.text)

            return response

        raise TransportConnectionError("Request failed after retries") from last_exc

    def close(self) -> None:
        self._http.close()

    # --- dev-mode helpers -------------------------------------------------

    def _emit_http(
        self,
        method: str,
        path: str,
        body: dict | None,  # type: ignore[type-arg]
        response: httpx.Response,
        attempt: int,
        start: float,
    ) -> None:
        cfg = self._dev_config
        if cfg is None or not cfg.enabled:
            return

        duration_ms = (time.monotonic() - start) * 1000.0
        bytes_in = (
            len(response.request.content or b"")
            if response.request
            else _estimate_bytes(body)
        )
        bytes_out = len(response.content or b"")
        metadata: dict[str, object] = {}

        if redact_for_log(path, method, body) is None:
            metadata["redacted"] = "participant"

        cfg.emit(
            Event(
                timestamp=datetime.now(timezone.utc),
                kind="http",
                name=path,
                duration_ms=duration_ms,
                bytes_in=bytes_in,
                bytes_out=bytes_out,
                status=response.status_code,
                retry=attempt,
                error=None,
                metadata=metadata,
            )
        )

    def _emit_error(
        self,
        method: str,
        path: str,
        attempt: int,
        start: float,
        error_name: str,
    ) -> None:
        cfg = self._dev_config
        if cfg is None or not cfg.enabled:
            return

        duration_ms = (time.monotonic() - start) * 1000.0
        cfg.emit(
            Event(
                timestamp=datetime.now(timezone.utc),
                kind="error",
                name=path,
                duration_ms=duration_ms,
                bytes_in=None,
                bytes_out=None,
                status=None,
                retry=attempt,
                error=error_name,
                metadata={"method": method},
            )
        )


def _estimate_bytes(body: dict | None) -> int | None:  # type: ignore[type-arg]
    if body is None:
        return 0
    import json as _json

    try:
        return len(_json.dumps(body).encode("utf-8"))
    except Exception:  # pragma: no cover — extremely defensive
        return None
