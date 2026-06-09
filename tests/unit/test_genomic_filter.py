from picsure._models.genomic_filter import GenomicFilter, VariantFrequency, Zygosity


def test_to_query_json_categorical():
    gf = GenomicFilter(key="Gene_with_variant", values=("BRCA1", "TP53"))
    assert gf.to_query_json() == {
        "key": "Gene_with_variant",
        "values": ["BRCA1", "TP53"],
    }


def test_to_query_json_range():
    gf = GenomicFilter(key="Variant_frequency_in_gnomAD", min=0.0, max=0.01)
    assert gf.to_query_json() == {
        "key": "Variant_frequency_in_gnomAD",
        "min": 0.0,
        "max": 0.01,
    }


def test_to_query_json_omits_absent_fields():
    gf = GenomicFilter(key="X", min=0.5)
    assert gf.to_query_json() == {"key": "X", "min": 0.5}


def test_value_enums_are_strings():
    assert VariantFrequency.RARE == "Rare"
    assert Zygosity.HETEROZYGOUS == "0/1"
    assert Zygosity.HETEROZYGOUS_OR_HOMOZYGOUS == "1/1,0/1"
