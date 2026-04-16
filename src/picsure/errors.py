class PicSureError(Exception):
    """Base exception for all PIC-SURE adapter errors.

    Catch this class to handle any error from the picsure library.
    """


class PicSureAuthError(PicSureError):
    """Token is invalid, expired, or lacks required permissions."""


class PicSureConnectionError(PicSureError):
    """Cannot reach the PIC-SURE server."""


class PicSureQueryError(PicSureError):
    """The server rejected the query."""


class PicSureValidationError(PicSureError):
    """Invalid input to a picsure function."""
