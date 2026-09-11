"""A wrapper that keeps a credential out of rendered tracebacks.

Python renders the arguments and, under ``--showlocals`` or
``traceback.print_exc`` with a verbose formatter, the locals of *every*
frame on a traceback -- not only the frame that raised.  A bearer token
held as a plain :class:`str` therefore reaches the notebook output of any
exception that passes through a function holding it, whether or not that
function had anything to do with the failure.

:class:`SecretToken` closes that path: it renders as a fixed placeholder
in every string context, and the value comes back only from
:meth:`SecretToken.reveal`.  Wrapping is not on its own sufficient --
a function that takes a plain ``str`` and wraps it still has the raw
string bound to its own parameter, which a traceback printer shows.  The
callers here pair the wrap with ``del`` of the original binding; see
:func:`picsure._services.connect.connect`.
"""

from __future__ import annotations

from typing import NoReturn

_PLACEHOLDER = "<picsure secret token>"


class SecretToken:
    """A PIC-SURE API token that does not render its own value.

    Deliberately **not** a :class:`str` subclass.  A subclass would keep
    working in f-strings, ``%`` formatting and string concatenation,
    which is exactly the silent exposure this type exists to remove; a
    missed call site must fail loudly instead.  For the same reason there
    is no ``__eq__`` against ``str`` -- compare
    ``hmac.compare_digest(a.reveal(), b.reveal())`` where a token
    comparison is genuinely needed.

    The value is stripped once, here, so :meth:`reveal` is always
    wire-ready and callers need no ``.strip()`` of their own.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str | SecretToken = "") -> None:
        """Wrap ``value``, stripping surrounding whitespace.

        Args:
            value: The token.  Accepts a ``SecretToken``, so wrapping is
                idempotent and a call site can normalise without first
                checking what it was handed.
        """
        object.__setattr__(
            self,
            "_value",
            value.reveal() if isinstance(value, SecretToken) else value.strip(),
        )

    def reveal(self) -> str:
        """Return the token itself, stripped and ready for the wire.

        The single accessor, named so that it is obvious in review where
        a credential escapes the wrapper.  Do not bind the result to a
        local that a live frame could still hold when an exception is
        rendered -- build it straight into the value being handed on.
        """
        return self._value

    def __repr__(self) -> str:
        """Return a fixed placeholder, never the value, prefix, or length."""
        return _PLACEHOLDER

    __str__ = __repr__

    def __format__(self, format_spec: str, /) -> str:
        """Return the placeholder, ignoring any format spec.

        Defined so that ``f"{token}"`` and ``f"{token:>40}"`` behave the
        same way: padding a secret to a fixed width would still disclose
        nothing, but honouring the spec invites the assumption that this
        object formats like a string.
        """
        return _PLACEHOLDER

    def __bool__(self) -> bool:
        """Whether a non-empty token was supplied.

        Mirrors the truthiness of the stripped string, so the callers
        that switch on "is there a token at all" -- the ``request-source``
        header, the missing-token check in ``connect()`` -- keep reading
        the way they did when this was a ``str``.
        """
        return bool(self._value)

    def __getattr__(self, name: str) -> NoReturn:
        """Fail actionably for the ``str`` API this type deliberately lacks.

        A call site that was not updated reaches for ``.strip()`` or
        ``.split()``; naming :meth:`reveal` in the error turns that into
        a one-line fix rather than a puzzle.
        """
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise AttributeError(
            f"{type(self).__name__} has no attribute {name!r}. It is not a "
            f"str, so that the token cannot leak into a traceback or an "
            f"f-string. Call reveal() to get the token value."
        )

    def __setattr__(self, name: str, value: object) -> NoReturn:
        """Reject mutation: the wrapper is immutable once constructed."""
        raise AttributeError(
            f"{type(self).__name__} is immutable; construct a new one instead "
            f"of setting {name!r}."
        )

    def __delattr__(self, name: str) -> NoReturn:
        """Reject deletion, for the same reason as :meth:`__setattr__`."""
        raise AttributeError(f"{type(self).__name__} is immutable.")

    def __copy__(self) -> SecretToken:
        """Return self.

        Immutable, so sharing is safe -- and returning the same wrapper
        guarantees a copy can never decay into a plain ``str``.
        """
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> SecretToken:
        """Return self, for the reason given in :meth:`__copy__`."""
        return self

    def __reduce__(self) -> NoReturn:
        """Refuse to pickle.

        Serializing would write the credential to whatever the pickle is
        stored in, so this raises rather than round-tripping.
        """
        raise TypeError(
            "SecretToken cannot be pickled: doing so would write the token "
            "to the pickle stream. Pass the token in from configuration at "
            "the point of use instead."
        )


def as_secret_token(value: str | SecretToken) -> SecretToken:
    """Return ``value`` as a :class:`SecretToken`, wrapping only if needed.

    Idempotent, so a public entry point can normalise whatever it was
    handed -- a ``str`` from a notebook or from the R adapter through
    reticulate, or an already-wrapped token from an internal caller --
    as its first statement.
    """
    return value if isinstance(value, SecretToken) else SecretToken(value)
