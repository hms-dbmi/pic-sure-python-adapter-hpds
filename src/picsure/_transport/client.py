import httpx

from picsure._transport.errors import (
    TransportAuthenticationError,
    TransportConnectionError,
    TransportServerError,
)

_MAX_RETRIES = 1
_TIMEOUT_SECONDS = 30.0


class PicSureClient:
    """HTTP client for PIC-SURE API calls.

    Wraps httpx.Client with Bearer token auth, retries on 5xx and
    connection errors, and translation to internal transport exceptions.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
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

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._http.request(method, path, **kwargs)  # type: ignore[arg-type]
            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    continue
                raise TransportConnectionError(f"Request timed out: {exc}") from exc

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
