from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Resource:
    """A PIC-SURE resource descriptor."""

    uuid: str
    name: str
    description: str

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Resource:
        return cls(
            uuid=str(data["uuid"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
        )
