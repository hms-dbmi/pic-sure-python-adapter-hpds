from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DictionaryEntry:
    """One row from a PIC-SURE data dictionary search result."""

    concept_path: str
    name: str
    display: str = ""
    description: str = ""
    data_type: str = ""
    study_id: str = ""
    values: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DictionaryEntry:
        raw_values = data.get("values", [])
        values: list[str] = (
            [str(v) for v in raw_values] if isinstance(raw_values, list) else []
        )
        data_type_raw = data.get("type", data.get("dataType", ""))
        study_id_raw = data.get("dataset", data.get("studyId", ""))
        return cls(
            concept_path=str(data.get("conceptPath", "")),
            name=str(data.get("name", "")),
            display=str(data.get("display", "")),
            description=str(data.get("description") or ""),
            data_type=str(data_type_raw),
            study_id=str(study_id_raw),
            values=values,
        )
