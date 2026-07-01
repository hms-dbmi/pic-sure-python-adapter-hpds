from __future__ import annotations

import json
from importlib import resources

import pandas as pd


def genomicConsequences() -> pd.DataFrame:  # noqa: N802
    """Return the variant-consequence vocabulary as a DataFrame.

    Columns ``severity`` (High/Medium/Low Severity) and ``consequence``,
    one row per consequence, flattened from the severity tree. Static
    reference data bundled with the package — no network or session needed,
    and not restricted to authorized platforms.
    """
    raw = (
        resources.files("picsure._data")
        .joinpath("variant_consequences.json")
        .read_text(encoding="utf-8")
    )
    groups = json.loads(raw)
    rows = [
        {"severity": group["key"], "consequence": child}
        for group in groups
        for child in group["children"]
    ]
    return pd.DataFrame(rows, columns=["severity", "consequence"])
