from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast


def coerce_float(value: object) -> float | None:
    """Coerce a JSON-parsed number to ``float``, rejecting bool.

    ``bool`` is an ``int`` subclass in Python, so a bare
    ``isinstance(x, (int, float))`` accepts ``True``/``False`` as
    valid numerics. This guard prevents that surprise when ingesting
    server payloads.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


@dataclass(frozen=True)
class DictionaryEntry:
    """One row from a PIC-SURE data dictionary search result.

    Fields map to the backend ``Concept`` (``CategoricalConcept`` or
    ``ContinuousConcept``) payload:

    - ``concept_path``/``name``/``display``/``description`` — identity and
      labels, always present.
    - ``data_type`` — ``"Categorical"`` or ``"Continuous"`` (from ``type``).
    - ``study_id`` — dbGaP study accession (from ``dataset``).
    - ``values`` — categorical value list; empty for Continuous concepts.
    - ``min``/``max`` — continuous-range bounds; ``None`` for Categorical
      and when the server omits them.
    - ``allow_filtering`` — whether the concept may be used as a filter
      predicate. ``None`` when the server omits the field.
    - ``meta`` — pass-through metadata dictionary from the server; ``None``
      when absent.
    - ``study_acronym`` — short study label (e.g. ``"FHS"``).

    A field the server sends as an explicit JSON ``null`` is read the
    same way as one it omits, so ``type: null`` still falls back to the
    legacy ``dataType`` and no absent value renders as the four-character
    string ``"None"``.
    """

    concept_path: str
    name: str
    display: str = ""
    description: str = ""
    data_type: str = ""
    study_id: str = ""
    values: list[str] = field(default_factory=list)
    min: float | None = None
    max: float | None = None
    allow_filtering: bool | None = None
    meta: dict[str, Any] | None = None
    study_acronym: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DictionaryEntry:
        raw_values = data.get("values", [])
        values: list[str] = (
            [str(v) for v in raw_values] if isinstance(raw_values, list) else []
        )
        data_type_raw = _first_non_null(data, "type", "dataType")
        study_id_raw = _first_non_null(data, "dataset", "studyId")
        study_acronym_raw = _first_non_null(data, "studyAcronym")

        min_val = coerce_float(data.get("min"))
        max_val = coerce_float(data.get("max"))

        raw_allow = data.get("allowFiltering")
        allow_filtering: bool | None = (
            bool(raw_allow) if isinstance(raw_allow, bool) else None
        )

        raw_meta = data.get("meta")
        meta: dict[str, Any] | None = (
            cast(dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else None
        )

        return cls(
            concept_path=str(data.get("conceptPath", "")),
            name=str(data.get("name", "")),
            display=str(data.get("display", "")),
            description=str(data.get("description") or ""),
            data_type="" if data_type_raw is None else str(data_type_raw),
            study_id="" if study_id_raw is None else str(study_id_raw),
            values=values,
            min=min_val,
            max=max_val,
            allow_filtering=allow_filtering,
            meta=meta,
            study_acronym=(
                None if study_acronym_raw is None else str(study_acronym_raw)
            ),
        )


def _first_non_null(data: dict[str, object], *keys: str) -> object | None:
    """Return the first of ``keys`` the payload carries a non-null value for.

    An explicit JSON ``null`` counts as an absent field, so a legacy
    fallback key is still consulted when the modern one is null and no
    caller is handed ``str(None)``.

    Args:
        data: The decoded server payload.
        keys: Field names in preference order.

    Returns:
        The first non-null value, or ``None`` when every key is absent or
        explicitly null.
    """
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None
