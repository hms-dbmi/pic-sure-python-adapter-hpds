from picsure._models.genomic_filter import (
    GenomicFilter,
    VariantFrequency,
    is_variant_spec,
)


def test_to_query_json_categorical():
    gf = GenomicFilter(key="Gene_with_variant", values=("BRCA1", "TP53"))
    assert gf.to_query_json() == {
        "key": "Gene_with_variant",
        "values": ["BRCA1", "TP53"],
    }


def test_to_query_json_omits_absent_values():
    gf = GenomicFilter(key="X")
    assert gf.to_query_json() == {"key": "X"}


def test_genomic_filter_has_no_numeric_range():
    # Numeric range (min/max) filtering was removed; the model is categorical
    # only, matching the genomic filters the PIC-SURE frontend actually sends.
    gf = GenomicFilter(key="Gene_with_variant", values=("BRCA1",))
    assert not hasattr(gf, "min")
    assert not hasattr(gf, "max")


def test_value_enums_are_strings():
    assert VariantFrequency.RARE == "Rare"
    assert VariantFrequency.COMMON == "Common"
    assert VariantFrequency.NOVEL == "Novel"


def test_zygosity_enum_removed():
    # Variant-spec (SNP) filtering is not supported yet; the Zygosity genotype
    # enum was removed along with it.
    import picsure

    assert not hasattr(picsure, "Zygosity")


def test_is_variant_spec_matches_specs_not_annotation_keys():
    # rsID and chr,pos,ref,alt[,gene,consequence] are variant specs (SNP keys).
    assert is_variant_spec("rs123")
    assert is_variant_spec("chr5,148481541,T,A")
    assert is_variant_spec("7,100000,A,T,CHD8,missense_variant")
    # Annotation keys (no comma) are never variant specs.
    assert not is_variant_spec("Gene_with_variant")
    assert not is_variant_spec("Variant_consequence_calculated")
    assert not is_variant_spec("Variant_frequency_as_text")


def test_genomic_filter_key_values():
    from picsure._models.genomic_filter import GenomicFilterKey

    assert GenomicFilterKey.GENE_WITH_VARIANT == "Gene_with_variant"
    key = GenomicFilterKey.VARIANT_CONSEQUENCE_CALCULATED
    assert key == "Variant_consequence_calculated"
    assert GenomicFilterKey.VARIANT_FREQUENCY_AS_TEXT == "Variant_frequency_as_text"
    assert GenomicFilterKey.VARIANT_CLASS == "Variant_class"
    assert GenomicFilterKey.VARIANT_SEVERITY == "Variant_severity"


def test_variant_severity_values():
    from picsure._models.genomic_filter import VariantSeverity

    assert VariantSeverity.HIGH == "High Severity"
    assert VariantSeverity.MEDIUM == "Medium Severity"
    assert VariantSeverity.LOW == "Low Severity"


def test_known_severities_order():
    from picsure._models.genomic_filter import known_severities

    assert known_severities() == ("High Severity", "Medium Severity", "Low Severity")


def test_severity_consequences_high_exact():
    from picsure._models.genomic_filter import severity_consequences

    assert severity_consequences("High Severity") == (
        "splice_acceptor_variant",
        "splice_donor_variant",
        "stop_gained",
        "frameshift_variant",
        "stop_lost",
        "start_lost",
    )
    assert "missense_variant" in severity_consequences("Medium Severity")
    assert "synonymous_variant" in severity_consequences("Low Severity")


def test_severity_consequences_unknown_raises_keyerror():
    import pytest

    from picsure._models.genomic_filter import severity_consequences

    with pytest.raises(KeyError):
        severity_consequences("HIGH")


def test_key_and_severity_enums_re_exported():
    import picsure

    assert picsure.GenomicFilterKey.GENE_WITH_VARIANT == "Gene_with_variant"
    assert picsure.VariantSeverity.HIGH == "High Severity"
    assert "GenomicFilterKey" in picsure.__all__
    assert "VariantSeverity" in picsure.__all__


class TestVariantFrequencyBuckets:
    """PL-06: the ``Variant_frequency_as_text`` vocabulary.

    Captured live from a stack with genomic data loaded: ``Low_frequency``,
    ``Ultra_rare``, ``Rare``, ``Common``. The backend's own annotated test
    VCF carries only ``Rare`` and ``Common``, and no source or fixture in
    the PIC-SURE tree mentions ``Novel``, so the enum is a convenience and
    ``searchGenomicValues`` is the authoritative source.
    """

    def test_live_values_are_members(self):
        for value in ("Rare", "Common", "Low_frequency", "Ultra_rare"):
            assert value in {member.value for member in VariantFrequency}

    def test_novel_is_kept_for_back_compat(self):
        # Deprecated, not deleted: still importable so existing code runs.
        assert VariantFrequency.NOVEL == "Novel"

    def test_deprecation_is_documented(self):
        assert "deprecated" in VariantFrequency.__doc__.lower()
        assert "searchGenomicValues" in VariantFrequency.__doc__

    def test_frequency_values_are_accepted_by_the_builder(self):
        # The key does no value validation, so every member must build.
        from picsure import buildGenomicFilter

        for member in VariantFrequency:
            gf = buildGenomicFilter("Variant_frequency_as_text", values=member)
            assert gf.key == "Variant_frequency_as_text"
            assert gf.values == (member.value,)


class TestImpactVocabulary:
    """PL-05: the backend's ``Variant_severity`` impact values."""

    def test_known_impacts_matches_the_live_discovery_output(self):
        from picsure._models.genomic_filter import known_impacts

        assert set(known_impacts()) == {"HIGH", "MODERATE", "LOW", "MODIFIER"}

    def test_known_impacts_is_ordered_by_decreasing_severity(self):
        from picsure._models.genomic_filter import known_impacts

        assert known_impacts() == ("HIGH", "MODERATE", "LOW", "MODIFIER")

    def test_normalize_impact_accepts_canonical_values(self):
        from picsure._models.genomic_filter import known_impacts, normalize_impact

        for impact in known_impacts():
            assert normalize_impact(impact) == impact

    def test_normalize_impact_ignores_case_and_whitespace(self):
        from picsure._models.genomic_filter import normalize_impact

        assert normalize_impact("high") == "HIGH"
        assert normalize_impact("  Modifier  ") == "MODIFIER"

    def test_normalize_impact_rejects_a_severity_bucket(self):
        from picsure._models.genomic_filter import normalize_impact

        assert normalize_impact("High Severity") is None

    def test_normalize_impact_rejects_an_unknown_value(self):
        from picsure._models.genomic_filter import normalize_impact

        assert normalize_impact("Catastrophic") is None
        assert normalize_impact("") is None

    def test_impact_values_and_severity_buckets_are_disjoint(self):
        from picsure._models.genomic_filter import known_impacts, known_severities

        assert set(known_impacts()).isdisjoint(set(known_severities()))
