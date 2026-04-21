import httpx

from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportNotFoundError,
    TransportRateLimitError,
    TransportServerError,
    TransportValidationError,
)

_MAX_RETRIES = 1
_TIMEOUT_SECONDS = 30.0


class PicSureClient:
    """HTTP client for PIC-SURE API calls.

    Wraps httpx.Client with Bearer token auth, retries on 5xx and
    connection errors, and translation to internal transport exceptions.
    """

    def __init__(self, base_url: str, token: str = "") -> None:
        # BDC's API gateway routes auth based on a "request-source" header:
        # "Authorized" when a bearer token is present, "Open" otherwise.
        # Without it, authorized endpoints (e.g. /picsure/v3/query/sync) can
        # reject tokens that are otherwise valid on PSAMA or the data-dictionary.
        token = token.strip()
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

    def get_json(self, path: str) -> dict:  # type: ignore[type-arg]
        """Send GET request and return parsed JSON."""
        response = self._request("GET", path)
        return response.json()  # type: ignore[no-any-return]

    def post_json(self, path: str, body: dict | None = None) -> dict:  # type: ignore[type-arg]
        """Send POST request with JSON body and return parsed JSON."""
        response = self._request("POST", path, json=body)
        return response.json()  # type: ignore[no-any-return]

    def post_raw(self, path: str, body: dict | None = None) -> bytes:  # type: ignore[type-arg]
        """Send POST request with JSON body and return raw response bytes.

        Use this for endpoints that return non-JSON data (CSV, PFB, etc.).
        """
        response = self._request("POST", path, json=body)
        return response.content

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._http.request(method, path, **kwargs)  # type: ignore[arg-type]
            except httpx.ConnectError as exc:
                last_exc = exc
                # Connection errors are idempotent-safe: the request never
                # reached the server, so retrying can't double-execute.
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                last_exc = exc
                # Timeouts may or may not have reached the server, but
                # the convention in this client is to retry — see the
                # original TransportConnectionError path.
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(f"Request timed out: {exc}") from exc

            status = response.status_code

            if status in (401, 403):
                raise TransportAuthenticationError(status, response.text)

            if status == 404:
                raise TransportNotFoundError(status, response.text)

            if status == 429:
                raise TransportRateLimitError(
                    status, response.text, retry_after=_parse_retry_after(response)
                )

            if 400 <= status < 500:
                # 400, 422, and any other 4xx fall into the validation bucket.
                raise TransportValidationError(status, response.text)

            if status >= 500:
                # POST is non-idempotent: a 5xx after the request reached
                # the server may have partially executed.  Only retry GETs.
                if method == "GET" and attempt < _MAX_RETRIES:
                    continue
                raise TransportServerError(status, response.text)

            return response

        raise TransportConnectionError("Request failed after retries") from last_exc

    def close(self) -> None:
        """Close the underlying HTTP client.  Safe to call more than once."""
        # httpx.Client.close() is itself idempotent, but be explicit so
        # callers can rely on the Session-level contract.
        self._http.close()


def _parse_retry_after(response: httpx.Response) -> int | None:
    """Parse a ``Retry-After`` header as an integer number of seconds.

    Returns ``None`` for missing headers and for HTTP-date values that
    cannot be parsed as a plain integer.  We intentionally don't try to
    parse HTTP-date here: the value we want to surface is "seconds from
    now," and converting a date to that requires a wall-clock reference
    the caller can compute themselves if needed.
    """
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return None
