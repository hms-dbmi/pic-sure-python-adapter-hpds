class TransportError(Exception):
    """Base class for internal transport-layer errors."""


class TransportAuthenticationError(TransportError):
    """HTTP 401 or 403 from the server."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:200]}")


class TransportServerError(TransportError):
    """HTTP 5xx from the server after retries."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:200]}")


class TransportConnectionError(TransportError):
    """Network-level failure: DNS, timeout, connection refused."""
