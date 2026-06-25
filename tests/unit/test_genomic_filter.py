from picsure._models.genomic_filter import GenomicFilter, VariantFrequency, Zygosity


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
    assert Zygosity.HETEROZYGOUS == "0/1"
    assert Zygosity.HETEROZYGOUS_OR_HOMOZYGOUS == "1/1,0/1"
