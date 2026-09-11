"""Public exception hierarchy for the PIC-SURE adapter.

Three causes produce three distinguishable families, so a caller can tell
them apart with an ``except`` clause alone:

* :class:`PicSureAuthError` — the server answered and refused you.
  :class:`PicSureAuthenticationError` is a problem with the token itself;
  :class:`PicSureAuthorizationError` (and its
  :class:`PicSureConsentDeniedError` refinement) means the token is fine
  but the account may not see what was asked for.
* :class:`PicSureConnectionError` — the adapter got no usable response.
  :class:`PicSureTLSError` and :class:`PicSureServerError` name the two
  cases worth handling separately.
* :class:`PicSureQueryError` / :class:`PicSureValidationError` — the
  request or the response was wrong, independent of who is asking.
"""


class PicSureError(Exception):
    """Base exception for all PIC-SURE adapter errors.

    Catch this class to handle any error from the picsure library.
    """


class PicSureAuthError(PicSureError):
    """The server answered and refused the request.

    The request reached PIC-SURE and PIC-SURE declined to serve it because
    of who is asking or what they may see.  Catch the two subclasses to
    tell a token problem from a permission problem.
    """


class PicSureAuthenticationError(PicSureAuthError):
    """HTTP 401 — the token is missing, malformed, expired, or rejected.

    Nothing about the account's permissions is implied: the server never
    got far enough to check them.  A fresh token usually resolves it.
    """


class PicSureAuthorizationError(PicSureAuthError):
    """HTTP 403 — the token is valid, but the account is not permitted.

    Re-issuing the token will not help; the account needs the privilege
    (or the study approval) that the request requires.
    """


class PicSureConsentDeniedError(PicSureAuthorizationError):
    """HTTP 403 — approved consents do not cover the requested data.

    The specialization of :class:`PicSureAuthorizationError` the backend
    signals with ``errorType: consent_denied``.  ``status_code``,
    ``body``, ``error_type``, and ``server_message`` carry the server's
    own account of the refusal.
    """

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


class PicSureConnectionError(PicSureError):
    """The adapter could not get a usable response from the server.

    Covers every failure that leaves the request unanswered: DNS failure,
    a refused or reset connection, a certificate the adapter would not
    trust, a timeout, throttling, and server-side faults.  Retrying later
    is the usual response.
    """


class PicSureTLSError(PicSureConnectionError):
    """The server's TLS certificate could not be verified.

    The connection was refused locally, before any request was sent, so
    the server never saw the call.  Either the certificate is genuinely
    untrusted or the deployment uses a private / self-signed CA that this
    machine does not know about.
    """


class PicSureServerError(PicSureConnectionError):
    """The server answered with a 5xx and did not complete the request.

    Distinct from an unreachable server: the request arrived and PIC-SURE
    failed while handling it.  Nothing is wrong with the token or the
    request, so the same call may succeed on a retry.
    """


class PicSureConsentLookupError(PicSureServerError):
    """The server could not resolve the caller's consent permissions.

    The backend raises this as HTTP 502 when its own consent lookup
    against PSAMA fails.  It is neither a rejected token nor a denied
    consent — the server never established what the caller is allowed to
    see.  ``status_code``, ``body``, ``error_type``, and
    ``server_message`` carry the server's own account of the failure.
    """

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
