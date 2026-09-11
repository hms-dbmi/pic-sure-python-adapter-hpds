from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.genomic_filter import (
    GenomicFilter,
    GenomicFilterKey,
    is_variant_spec,
    known_impacts,
    known_severities,
    normalize_impact,
    severity_consequences,
)
from picsure._models.query import Query
from picsure.errors import PicSureValidationError


def buildClause(  # noqa: N802
    keys: str | list[str],
    type: PhenotypicFilterType,  # noqa: A002
    categories: str | list[str] | None = None,
    min: float | None = None,  # noqa: A002
    max: float | None = None,  # noqa: A002
) -> Clause:
    """Create a single filter clause for use in a query.

    Args:
        keys: Concept path(s) this clause applies to.
        type: The kind of filter. Use ``PhenotypicFilterType.FILTER`` for
            categorical or range filters, ``PhenotypicFilterType.ANYRECORD``
            to match the presence of any value, or
            ``PhenotypicFilterType.REQUIRE`` to require a non-null value.
        categories: For FILTER clauses on categorical variables.
        min: For FILTER clauses on numeric variables, minimum value.
        max: For FILTER clauses on numeric variables, maximum value.

    Returns:
        A Clause that can be combined with ``buildClauseGroup()``, assembled
        into a query with ``buildQuery()``, or passed directly to
        ``Session.runQuery()``.

    Raises:
        PicSureValidationError: If the clause configuration is invalid.

    Note:
        Variables you filter on are returned as output columns automatically.
        To include *additional* concept paths in the output without filtering,
        use ``buildQuery(includeConcepts=...)`` — output columns are not a
        clause type.

    Example:
        >>> from picsure import buildClause, PhenotypicFilterType
        >>> sex = buildClause(
        ...     r"\\phs1\\pht1\\phv1\\sex\\",
        ...     type=PhenotypicFilterType.FILTER,
        ...     categories="Male",
        ... )
        >>> age = buildClause(
        ...     r"\\phs1\\pht1\\phv5\\age\\",
        ...     type=PhenotypicFilterType.FILTER,
        ...     min=40.0,
        ... )
    """
    key_paths = (keys,) if isinstance(keys, str) else tuple(keys)
    category_values = (
        None
        if categories is None
        else ((categories,) if isinstance(categories, str) else tuple(categories))
    )

    if not key_paths:
        raise PicSureValidationError("Clause must have at least one concept path.")

    if type == PhenotypicFilterType.ANYRECORD:
        if category_values is not None:
            raise PicSureValidationError(
                "ANYRECORD clauses cannot have categories. ANYRECORD matches "
                "the presence of any value for the variable. Remove the "
                "categories argument."
            )
        if min is not None or max is not None:
            raise PicSureValidationError(
                "ANYRECORD clauses cannot have min or max values. ANYRECORD "
                "matches the presence of any value for the variable. Remove "
                "the min/max arguments."
            )

    if type == PhenotypicFilterType.FILTER:
        if category_values is None and min is None and max is None:
            raise PicSureValidationError(
                "FILTER clauses require at least one of: categories, min, or max. "
                "Use categories for categorical variables or min/max for "
                "continuous variables."
            )
        if category_values is not None and (min is not None or max is not None):
            raise PicSureValidationError(
                "FILTER clauses cannot have both categories and min/max."
            )

    if type == PhenotypicFilterType.REQUIRE and (
        category_values is not None or min is not None or max is not None
    ):
        raise PicSureValidationError(
            "REQUIRE clauses cannot have categories, min, or max."
        )

    return Clause(
        keys=key_paths,
        type=type,
        categories=category_values,
        min=min,
        max=max,
    )


def buildClauseGroup(  # noqa: N802
    clauses: list[Clause | ClauseGroup],
    operator: GroupOperator = GroupOperator.AND,
) -> ClauseGroup:
    """Combine clauses (and nested groups) under an AND or OR operator.

    Args:
        clauses: List of Clause or ClauseGroup objects to combine.
        operator: Logical operator — ``GroupOperator.AND`` (default) or
            ``GroupOperator.OR``.

    Returns:
        A ClauseGroup that can be nested in another ``buildClauseGroup()``,
        assembled into a query with ``buildQuery()``, or passed directly to
        ``Session.runQuery()``.

    Raises:
        PicSureValidationError: If the clause list is empty.

    Example:
        >>> from picsure import buildClauseGroup, GroupOperator
        >>> group = buildClauseGroup(
        ...     [sex_filter, age_filter],
        ...     operator=GroupOperator.AND,
        ... )
    """
    if not clauses:
        raise PicSureValidationError("A clause group must contain at least one clause.")

    return ClauseGroup(clauses=tuple(clauses), operator=operator)


def buildQuery(  # noqa: N802
    phenotypicFilter: Clause | ClauseGroup | None = None,  # noqa: N803
    includeConcepts: str | list[str] | tuple[str, ...] = (),  # noqa: N803
    genomicFilters: GenomicFilter | Sequence[GenomicFilter] | None = None,  # noqa: N803
) -> Query:
    """Assemble a complete query from a filter tree and/or output concepts.

    Args:
        phenotypicFilter: A Clause or ClauseGroup (from ``buildClause()`` /
            ``buildClauseGroup()``) to filter on, or ``None`` for an
            include-only or genomic-only query.
        includeConcepts: *Additional* concept path(s) to include as output
            columns, beyond the variables already named in
            ``phenotypicFilter`` — those are returned automatically. Order is
            preserved and duplicates are dropped.
        genomicFilters: A :class:`GenomicFilter` (from
            ``buildGenomicFilter()``), a sequence of them, or ``None``.
            Applied as a flat conjunctive list alongside the phenotypic
            filter.

    Returns:
        A Query suitable for ``Session.runQuery()``, ``Session.exportAsPFB()``,
        or ``Session.saveQueryByName()``.

    Raises:
        PicSureValidationError: If ``phenotypicFilter`` is not a Clause /
            ClauseGroup / None, if ``genomicFilters`` contains a non-filter,
            or if all arguments are empty.

    Example:
        >>> from picsure import buildClause, buildQuery, PhenotypicFilterType
        >>> males = buildClause(
        ...     sex_path, type=PhenotypicFilterType.FILTER, categories="Male"
        ... )
        >>> q = buildQuery(phenotypicFilter=males, includeConcepts=[bmi, hdl])
        >>> df = session.runQuery(q, type="participant")
    """
    cols = (
        [includeConcepts] if isinstance(includeConcepts, str) else list(includeConcepts)
    )

    if phenotypicFilter is not None and not isinstance(
        phenotypicFilter, (Clause, ClauseGroup)
    ):
        raise PicSureValidationError(
            "phenotypicFilter must be a Clause or ClauseGroup (from "
            "buildClause()/buildClauseGroup()), or None."
        )

    if genomicFilters is None:
        genomic: tuple[GenomicFilter, ...] = ()
    elif isinstance(genomicFilters, GenomicFilter):
        genomic = (genomicFilters,)
    else:
        genomic = tuple(genomicFilters)
    if any(not isinstance(g, GenomicFilter) for g in genomic):
        raise PicSureValidationError(
            "genomicFilters must be GenomicFilter objects (from "
            "buildGenomicFilter()), a single one, or None."
        )

    if phenotypicFilter is None and not cols and not genomic:
        raise PicSureValidationError(
            "buildQuery requires a phenotypicFilter, includeConcepts, or "
            "genomicFilters."
        )

    # de-dup includeConcepts while preserving order
    return Query(
        phenotypicFilter=phenotypicFilter,
        includeConcepts=tuple(dict.fromkeys(cols)),
        genomicFilters=genomic,
    )


def buildGenomicFilter(  # noqa: N802
    key: str | GenomicFilterKey,
    *,
    values: str | Sequence[str],
) -> GenomicFilter:
    """Create a single categorical genomic (variant-annotation) filter.

    Args:
        key: The genomic annotation to filter on. Pass a
            :class:`GenomicFilterKey` member (preferred) or the equivalent
            string — an unrecognized string raises an error listing the valid
            keys. Variant-spec (SNP) keys — an rsID or a ``chr,pos,ref,alt``
            spec — are not supported and are rejected.
        values: One value or a sequence of values that must match.
            :class:`VariantFrequency` / :class:`VariantSeverity` members are
            accepted and coerced to their string value.

    Returns:
        A :class:`GenomicFilter` to pass to ``buildQuery(genomicFilters=...)``.

    Note:
        ``GenomicFilterKey.VARIANT_SEVERITY`` accepts two vocabularies, and a
        single filter must not mix them:

        - the backend's own impact values — ``HIGH``, ``MODERATE``, ``LOW``,
          ``MODIFIER`` (:func:`known_impacts`), exactly what
          ``searchGenomicValues("Variant_severity")`` returns — are sent on
          the ``Variant_severity`` key unchanged;
        - this adapter's :class:`VariantSeverity` buckets (e.g.
          ``"High Severity"``) are expanded into the matching
          ``Variant_consequence_calculated`` values, so the returned filter's
          ``key`` is ``"Variant_consequence_calculated"``.

        On observed data the two routes select the same patients, but only the
        impact values can express ``MODIFIER``, which no bucket covers.

    Raises:
        PicSureValidationError: If ``key`` is empty, unrecognized, or a
            variant-spec (SNP) key; if ``values`` is empty or contains blank
            strings; or if a ``VARIANT_SEVERITY`` value is neither an impact
            value nor a severity bucket, or mixes the two.

    Example:
        >>> from picsure import buildGenomicFilter, GenomicFilterKey, VariantSeverity
        >>> gene = buildGenomicFilter(
        ...     GenomicFilterKey.GENE_WITH_VARIANT, values=["BRCA1"]
        ... )
        >>> severe = buildGenomicFilter(
        ...     GenomicFilterKey.VARIANT_SEVERITY, values=VariantSeverity.HIGH
        ... )
        >>> high_impact = buildGenomicFilter(
        ...     GenomicFilterKey.VARIANT_SEVERITY, values="HIGH"
        ... )
    """
    if isinstance(key, GenomicFilterKey):
        resolved = key
    elif isinstance(key, str) and key.strip():
        try:
            resolved = GenomicFilterKey(key)
        except ValueError:
            if is_variant_spec(key):
                raise PicSureValidationError(
                    "Variant-spec (SNP) genomic filtering is not supported yet; "
                    f"the key {key!r} looks like a specific variant. Filter by a "
                    "gene or annotation key (e.g. 'Gene_with_variant') instead."
                ) from None
            valid_keys = ", ".join(k.value for k in GenomicFilterKey)
            raise PicSureValidationError(
                f"{key!r} is not a recognized genomic filter key. Valid keys: "
                f"{valid_keys}. Pass a GenomicFilterKey member or one of these "
                "strings."
            ) from None
    else:
        raise PicSureValidationError(
            "buildGenomicFilter requires a non-empty 'key' string or a "
            "GenomicFilterKey member."
        )

    items = [values] if isinstance(values, str) else list(values)
    if not items:
        raise PicSureValidationError(
            "buildGenomicFilter 'values' must be a non-empty string or sequence."
        )
    normalized = tuple(str(v.value) if isinstance(v, Enum) else str(v) for v in items)
    if any(not v.strip() for v in normalized):
        raise PicSureValidationError(
            "buildGenomicFilter 'values' must not contain empty or blank strings."
        )

    if resolved is GenomicFilterKey.VARIANT_SEVERITY:
        return _build_severity_filter(normalized)

    return GenomicFilter(key=resolved.value, values=normalized)


def _build_severity_filter(values: tuple[str, ...]) -> GenomicFilter:
    """Build the effective filter for a ``Variant_severity`` request.

    Impact values pass through on the ``Variant_severity`` key; severity
    buckets expand into ``Variant_consequence_calculated`` values. The two
    vocabularies describe the same thing through different keys, so one
    filter cannot carry both.

    Args:
        values: The already-normalized requested severity values.

    Returns:
        The :class:`GenomicFilter` to send.

    Raises:
        PicSureValidationError: If a value belongs to neither vocabulary, or
            the request mixes the two.
    """
    impacts: list[str] = []
    buckets: list[str] = []
    for value in values:
        impact = normalize_impact(value)
        if impact is not None:
            impacts.append(impact)
        elif value in known_severities():
            buckets.append(value)
        else:
            raise PicSureValidationError(_severity_value_message(value))

    if impacts and buckets:
        raise PicSureValidationError(
            "buildGenomicFilter cannot mix Variant_severity vocabularies in "
            f"one filter: {', '.join(repr(i) for i in impacts)} are backend "
            "impact values sent on the 'Variant_severity' key, while "
            f"{', '.join(repr(b) for b in buckets)} are severity buckets "
            "expanded into 'Variant_consequence_calculated' values. Build one "
            "filter per vocabulary and pass both to buildQuery."
        )

    if impacts:
        return GenomicFilter(
            key=GenomicFilterKey.VARIANT_SEVERITY.value,
            values=tuple(dict.fromkeys(impacts)),
        )

    expanded: list[str] = []
    for bucket in buckets:
        expanded.extend(severity_consequences(bucket))
    return GenomicFilter(
        key=GenomicFilterKey.VARIANT_CONSEQUENCE_CALCULATED.value,
        values=tuple(dict.fromkeys(expanded)),
    )


def _severity_value_message(value: str) -> str:
    """Explain both accepted ``Variant_severity`` vocabularies for a bad value."""
    return (
        f"{value!r} is not a valid variant severity. Pass either a backend "
        f"impact value ({', '.join(known_impacts())}) — what "
        "searchGenomicValues('Variant_severity') returns, sent on the "
        "'Variant_severity' key as-is — or a severity bucket "
        f"({', '.join(known_severities())}), which is expanded into the "
        "matching 'Variant_consequence_calculated' values. A single filter "
        "cannot mix the two."
    )
