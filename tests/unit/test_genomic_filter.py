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
