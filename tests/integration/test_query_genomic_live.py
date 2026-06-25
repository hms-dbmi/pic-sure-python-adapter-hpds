import pytest

import picsure
from picsure import PicSureQueryError, buildGenomicFilter, buildQuery

# As of 2026-06, BDC's deployed PIC-SURE does not serve the variant-centric
# result types: the v3 sync endpoint returns HTTP 200 with an empty body
# (the adapter surfaces this as a "not available on this PIC-SURE deployment"
# PicSureQueryError). Genomic filters as a *constraint* (count/participant)
# work — see test_gene_filter_count_returns_count_result, which is not gated.
# The variant-result-type tests below probe-and-skip on that signal, so they
# auto-resume as real assertions once the backend serves these types.
_UNSUPPORTED = "not available on this PIC-SURE deployment"


def _skip_if_variant_types_unsupported(exc: PicSureQueryError) -> None:
    if _UNSUPPORTED in str(exc):
        pytest.skip(
            "Variant result types are not served by this PIC-SURE deployment "
            "yet (empty response). Genomic filtering as a constraint still works."
        )
    raise exc


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

    def test_variant_count_returns_count_result(
        self, test_token, test_platform, test_gene
    ):
        # variant_count is parsed like a patient count, so it handles both an
        # exact value and an obfuscated response without raising.
        from picsure import CountResult

        session = picsure.connect(platform=test_platform, token=test_token)
        gf = buildGenomicFilter("Gene_with_variant", values=[test_gene])
        try:
            result = session.runQuery(
                buildQuery(genomicFilters=gf), type="variant_count"
            )
        except PicSureQueryError as exc:
            _skip_if_variant_types_unsupported(exc)
        assert isinstance(result, CountResult)
        assert (result.value is not None and result.value >= 0) or (
            result.cap is not None and result.cap > 0
        )

    def test_variant_list_returns_list(self, test_token, test_platform, test_gene):
        session = picsure.connect(platform=test_platform, token=test_token)
        gf = buildGenomicFilter("Gene_with_variant", values=[test_gene])
        try:
            result = session.runQuery(
                buildQuery(genomicFilters=gf), type="variant_list"
            )
        except PicSureQueryError as exc:
            _skip_if_variant_types_unsupported(exc)
        assert isinstance(result, list)
        assert all(isinstance(v, str) for v in result)
        # Each element must be a whole variant spec, not a fragment: the server
        # serializes specs as ``chromosome,offset,ref,alt,gene,consequence``.
        # If the list joiner were mis-split, specs would arrive shredded into
        # single fields. Require the spec shape (>= the 4 core VCF fields).
        for spec in result:
            assert len(spec.split(",")) >= 4, f"variant spec looks fragmented: {spec!r}"

    def test_search_genomic_values_returns_genes(
        self, test_token, test_platform, test_gene
    ):
        session = picsure.connect(platform=test_platform, token=test_token)
        df = session.searchGenomicValues("Gene_with_variant", query=test_gene, size=20)
        assert "value" in df.columns
        assert df.attrs.get("total") is not None
        if len(df):
            assert all(isinstance(v, str) for v in df["value"])
