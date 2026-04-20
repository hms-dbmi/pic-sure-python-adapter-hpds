from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountResult:
    """A count returned by PIC-SURE, preserving obfuscation metadata.

    Open-access backends may return a count with one of three shapes:

    - exact:      ``value`` set; ``margin`` and ``cap`` are ``None``
    - noisy:      ``value`` and ``margin`` set (server emitted ``"N ±M"``)
    - suppressed: ``value`` is ``None``; ``cap`` set (server emitted ``"< N"``)

    The ``raw`` field preserves the original server string for debugging
    and for callers that want to re-format the value themselves.
    """

    value: int | None
    margin: int | None
    cap: int | None
    raw: str

    @property
    def obfuscated(self) -> bool:
        """True if the server returned a noisy or suppressed value."""
        return self.margin is not None or self.cap is not None
