class PicSureError(Exception):
    """Base exception for all PIC-SURE adapter errors.

    Catch this class to handle any error from the picsure library.
    """


class PicSureAuthError(PicSureError):
    """Token is invalid, expired, or lacks required permissions."""


class PicSureConnectionError(PicSureError):
    """Cannot reach the PIC-SURE server."""


class PicSureConsentDeniedError(PicSureError):
    """The caller no longer has consent to access the requested data."""

    def __init__(
        self,
        status_code: int,
        body: str,
        error_type: str,
        server_message: str,
        message: str,
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.error_type = error_type
        self.server_message = server_message
        super().__init__(message)


class PicSureConsentLookupError(PicSureConnectionError):
    """The server could not resolve the caller's consent permissions."""

    def __init__(
        self,
        status_code: int,
        body: str,
        error_type: str,
        server_message: str,
        message: str,
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.error_type = error_type
        self.server_message = server_message
        super().__init__(message)


class PicSureQueryError(PicSureError):
    """The server rejected the query."""


class PicSureValidationError(PicSureError):
    """Invalid input to a picsure function."""
