import picsure
from picsure import buildGenomicFilter, buildQuery


class TestGenomicQueryLive:
    def test_gene_filter_count_returns_count_result(
        self, test_token, test_platform, test_gene
    ):
        from picsure import CountResult

        session = picsure.connect(platform=test_platform, token=test_token)
        gf = buildGenomicFilter("Gene_with_variant", values=[test_gene])
        result = session.runQuery(buildQuery(genomicFilters=gf), type="count")
        assert isinstance(result, CountResult)
        assert (result.value is not None and result.value >= 0) or (
            result.cap is not None and result.cap > 0
        )

    def test_variant_count_returns_int(self, test_token, test_platform, test_gene):
        # Resolves the spec's open question: confirm the server returns a
        # plain integer (not an obfuscated count string) for variant_count.
        session = picsure.connect(platform=test_platform, token=test_token)
        gf = buildGenomicFilter("Gene_with_variant", values=[test_gene])
        result = session.runQuery(buildQuery(genomicFilters=gf), type="variant_count")
        assert isinstance(result, int)
        assert result >= 0

    def test_variant_list_returns_list(self, test_token, test_platform, test_gene):
        session = picsure.connect(platform=test_platform, token=test_token)
        gf = buildGenomicFilter("Gene_with_variant", values=[test_gene])
        result = session.runQuery(buildQuery(genomicFilters=gf), type="variant_list")
        assert isinstance(result, list)
        assert all(isinstance(v, str) for v in result)
        # Each element must be a whole variant spec, not a fragment: the server
        # serializes specs as ``chromosome,offset,ref,alt,gene,consequence``.
        # If the list joiner were mis-split, specs would arrive shredded into
        # single fields. Require the spec shape (>= the 4 core VCF fields).
        for spec in result:
            assert len(spec.split(",")) >= 4, f"variant spec looks fragmented: {spec!r}"
