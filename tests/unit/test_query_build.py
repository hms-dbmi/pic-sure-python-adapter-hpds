import pytest

from picsure._models.clause import Clause, PhenotypicFilterType
from picsure._models.clause_group import ClauseGroup, GroupOperator
from picsure._models.query import Query
from picsure._services.query_build import buildClause, buildClauseGroup, buildQuery
from picsure.errors import PicSureValidationError


class TestBuildClause:
    def test_categorical_filter(self):
        clause = buildClause(
            "\\phs1\\sex\\",
            type=PhenotypicFilterType.FILTER,
            categories="Male",
        )
        assert isinstance(clause, Clause)
        assert clause.keys == ("\\phs1\\sex\\",)
        assert clause.categories == ("Male",)

    def test_keys_list_preserved(self):
        clause = buildClause(
            ["\\p1\\", "\\p2\\"],
            type=PhenotypicFilterType.ANYRECORD,
        )
        assert clause.keys == ("\\p1\\", "\\p2\\")

    def test_categories_list_preserved(self):
        clause = buildClause(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            categories=["Male", "Female"],
        )
        assert clause.categories == ("Male", "Female")

    def test_continuous_filter_min_only(self):
        clause = buildClause(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            min=40.0,
        )
        assert clause.min == 40.0
        assert clause.max is None

    def test_continuous_filter_min_and_max(self):
        clause = buildClause(
            "\\path\\",
            type=PhenotypicFilterType.FILTER,
            min=18.0,
            max=65.0,
        )
        assert clause.min == 18.0
        assert clause.max == 65.0

    def test_anyrecord(self):
        clause = buildClause("\\path\\", type=PhenotypicFilterType.ANYRECORD)
        assert clause.type == PhenotypicFilterType.ANYRECORD
        assert clause.categories is None
        assert clause.min is None

    def test_require(self):
        clause = buildClause("\\path\\", type=PhenotypicFilterType.REQUIRE)
        assert clause.type == PhenotypicFilterType.REQUIRE


class TestBuildClauseValidation:
    def test_anyrecord_with_categories_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                categories="Male",
            )

    def test_anyrecord_with_categories_message_is_actionable(self):
        with pytest.raises(PicSureValidationError, match="Remove the categories"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                categories=["x"],
            )

    def test_anyrecord_with_min_raises(self):
        with pytest.raises(PicSureValidationError, match="ANYRECORD"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.ANYRECORD,
                min=10.0,
            )

    def test_filter_without_criteria_raises(self):
        with pytest.raises(PicSureValidationError, match="FILTER"):
            buildClause("\\path\\", type=PhenotypicFilterType.FILTER)

    def test_filter_without_criteria_message_is_actionable(self):
        with pytest.raises(PicSureValidationError, match="categories.*min.*max"):
            buildClause("\\path\\", type=PhenotypicFilterType.FILTER)

    def test_filter_with_categories_and_min_raises(self):
        with pytest.raises(PicSureValidationError, match="FILTER"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.FILTER,
                categories="Male",
                min=40.0,
            )

    def test_filter_with_categories_and_min_message_mentions_both(self):
        with pytest.raises(PicSureValidationError, match="categories and min/max"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.FILTER,
                categories="Male",
                min=40.0,
            )

    def test_require_with_categories_raises(self):
        with pytest.raises(PicSureValidationError, match="REQUIRE"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.REQUIRE,
                categories="Male",
            )

    def test_require_with_min_raises(self):
        with pytest.raises(PicSureValidationError, match="REQUIRE"):
            buildClause(
                "\\path\\",
                type=PhenotypicFilterType.REQUIRE,
                min=10.0,
            )

    def test_empty_keys_list_raises(self):
        with pytest.raises(PicSureValidationError, match="at least one concept path"):
            buildClause([], type=PhenotypicFilterType.FILTER, categories="x")


class TestSelectRemoved:
    def test_select_member_is_gone(self):
        assert not hasattr(PhenotypicFilterType, "SELECT")


class TestBuildClauseGroup:
    def test_and_group(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = buildClause("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        group = buildClauseGroup([c1, c2], operator=GroupOperator.AND)
        assert isinstance(group, ClauseGroup)
        assert group.operator == GroupOperator.AND
        assert len(group.clauses) == 2

    def test_or_group(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = buildClause("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        group = buildClauseGroup([c1, c2], operator=GroupOperator.OR)
        assert group.operator == GroupOperator.OR

    def test_default_operator_is_and(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        group = buildClauseGroup([c1])
        assert group.operator == GroupOperator.AND

    def test_nested_groups(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = buildClause("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        inner = buildClauseGroup([c1, c2], operator=GroupOperator.OR)
        c3 = buildClause("\\p3\\", type=PhenotypicFilterType.FILTER, min=40.0)
        outer = buildClauseGroup([c3, inner], operator=GroupOperator.AND)
        assert len(outer.clauses) == 2
        assert isinstance(outer.clauses[1], ClauseGroup)

    def test_empty_list_raises(self):
        with pytest.raises(PicSureValidationError, match="at least one"):
            buildClauseGroup([])

    def test_copies_caller_list(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        c2 = buildClause("\\p2\\", type=PhenotypicFilterType.FILTER, categories="B")
        clauses = [c1, c2]
        group = buildClauseGroup(clauses, operator=GroupOperator.AND)
        clauses.append(
            buildClause("\\p3\\", type=PhenotypicFilterType.FILTER, categories="C")
        )
        assert len(group.clauses) == 2

    def test_serializes_end_to_end(self):
        sex = buildClause(
            "\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male"
        )
        age = buildClause("\\age\\", type=PhenotypicFilterType.FILTER, min=40.0)
        copd = buildClause(
            "\\copd\\", type=PhenotypicFilterType.FILTER, categories="Yes"
        )
        asthma = buildClause("\\asthma\\", type=PhenotypicFilterType.ANYRECORD)

        copd_or_asthma = buildClauseGroup([copd, asthma], operator=GroupOperator.OR)
        full = buildClauseGroup([sex, age, copd_or_asthma], operator=GroupOperator.AND)

        result = full.to_query_json()
        assert result["operator"] == "AND"
        children = result["phenotypicClauses"]
        assert len(children) == 3  # type: ignore[arg-type]
        assert children[0]["phenotypicFilterType"] == "FILTER"  # type: ignore[index]
        assert children[0]["conceptPath"] == "\\sex\\"  # type: ignore[index]
        assert children[2]["operator"] == "OR"  # type: ignore[index]


class TestBuildQuery:
    def test_filter_and_include_concepts(self):
        males = buildClause(
            "\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male"
        )
        q = buildQuery(phenotypicFilter=males, includeConcepts=["\\bmi\\", "\\hdl\\"])
        assert isinstance(q, Query)
        assert q.phenotypicFilter is males
        assert q.includeConcepts == ("\\bmi\\", "\\hdl\\")

    def test_filter_only(self):
        males = buildClause(
            "\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male"
        )
        q = buildQuery(phenotypicFilter=males)
        assert q.phenotypicFilter is males
        assert q.includeConcepts == ()

    def test_include_only(self):
        q = buildQuery(includeConcepts=["\\bmi\\"])
        assert q.phenotypicFilter is None
        assert q.includeConcepts == ("\\bmi\\",)

    def test_include_concepts_string_normalized(self):
        q = buildQuery(includeConcepts="\\bmi\\")
        assert q.includeConcepts == ("\\bmi\\",)

    def test_include_concepts_dedup_preserves_order(self):
        q = buildQuery(includeConcepts=["\\b\\", "\\a\\", "\\b\\", "\\c\\", "\\a\\"])
        assert q.includeConcepts == ("\\b\\", "\\a\\", "\\c\\")

    def test_accepts_clause_group_filter(self):
        c1 = buildClause("\\p1\\", type=PhenotypicFilterType.FILTER, categories="A")
        group = buildClauseGroup([c1])
        q = buildQuery(phenotypicFilter=group, includeConcepts="\\bmi\\")
        assert q.phenotypicFilter is group

    def test_empty_raises(self):
        with pytest.raises(PicSureValidationError, match="requires a phenotypicFilter"):
            buildQuery()

    def test_bad_filter_type_raises(self):
        with pytest.raises(
            PicSureValidationError, match="must be a Clause or ClauseGroup"
        ):
            buildQuery(phenotypicFilter=["not", "a", "clause"], includeConcepts="\\b\\")

    def test_query_is_frozen(self):
        q = buildQuery(includeConcepts="\\bmi\\")
        with pytest.raises((AttributeError, TypeError)):
            q.includeConcepts = ("\\x\\",)  # type: ignore[misc]


class TestBuildGenomicFilter:
    def test_categorical(self):
        from picsure._models.genomic_filter import GenomicFilter
        from picsure._services.query_build import buildGenomicFilter

        gf = buildGenomicFilter("Gene_with_variant", values=["BRCA1"])
        assert gf == GenomicFilter(key="Gene_with_variant", values=("BRCA1",))

    def test_single_string_value_normalized(self):
        from picsure._services.query_build import buildGenomicFilter

        gf = buildGenomicFilter("Gene_with_variant", values="BRCA1")
        assert gf.values == ("BRCA1",)

    def test_enum_value_coerced(self):
        from picsure._models.genomic_filter import VariantFrequency
        from picsure._services.query_build import buildGenomicFilter

        gf = buildGenomicFilter(
            "Variant_frequency_as_text", values=VariantFrequency.RARE
        )
        assert gf.values == ("Rare",)

    def test_no_min_max_kwargs(self):
        # Numeric range filtering was removed; min/max are no longer accepted,
        # matching the categorical-only genomic filters the frontend sends.
        from picsure._services.query_build import buildGenomicFilter

        with pytest.raises(TypeError):
            buildGenomicFilter("X", min=0.0, max=0.01)  # type: ignore[call-arg]

    def test_values_required(self):
        from picsure._services.query_build import buildGenomicFilter

        with pytest.raises(TypeError):
            buildGenomicFilter("X")  # type: ignore[call-arg]

    def test_rejects_empty_key(self):
        from picsure._services.query_build import buildGenomicFilter

        with pytest.raises(PicSureValidationError):
            buildGenomicFilter("", values=["a"])

    def test_rejects_empty_scalar_value(self):
        from picsure._services.query_build import buildGenomicFilter

        with pytest.raises(PicSureValidationError):
            buildGenomicFilter("Gene_with_variant", values="")

    def test_rejects_empty_value_in_sequence(self):
        from picsure._services.query_build import buildGenomicFilter

        with pytest.raises(PicSureValidationError):
            buildGenomicFilter("Gene_with_variant", values=["BRCA1", ""])

    def test_rejects_variant_spec_key(self):
        # Variant-spec (SNP) filtering is not supported yet.
        from picsure._services.query_build import buildGenomicFilter

        with pytest.raises(PicSureValidationError, match="SNP"):
            buildGenomicFilter("chr5,148481541,T,A", values=["0/1"])

    def test_rejects_rsid_key(self):
        from picsure._services.query_build import buildGenomicFilter

        with pytest.raises(PicSureValidationError, match="SNP"):
            buildGenomicFilter("rs123", values=["0/1"])

    def test_allows_annotation_keys(self):
        # Gene / consequence / frequency keys (no comma) are not variant specs.
        from picsure._services.query_build import buildGenomicFilter

        for key, vals in (
            ("Gene_with_variant", ["BRCA1"]),
            ("Variant_consequence_calculated", ["missense_variant"]),
            ("Variant_frequency_as_text", ["Rare"]),
        ):
            assert buildGenomicFilter(key, values=vals).key == key


class TestBuildQueryGenomic:
    def test_single_genomic_filter(self):
        from picsure._services.query_build import buildGenomicFilter

        gf = buildGenomicFilter("Gene_with_variant", values=["BRCA1"])
        q = buildQuery(genomicFilters=gf)
        assert isinstance(q, Query)
        assert q.genomicFilters == (gf,)
        assert q.phenotypicFilter is None

    def test_genomic_filter_list(self):
        from picsure._services.query_build import buildGenomicFilter

        gf1 = buildGenomicFilter("Gene_with_variant", values=["BRCA1"])
        gf2 = buildGenomicFilter("Variant_frequency_as_text", values=["Common"])
        q = buildQuery(genomicFilters=[gf1, gf2])
        assert q.genomicFilters == (gf1, gf2)

    def test_genomic_filter_rejects_wrong_type(self):
        with pytest.raises(PicSureValidationError):
            buildQuery(genomicFilters=["not a filter"])

    def test_empty_still_rejected(self):
        with pytest.raises(PicSureValidationError):
            buildQuery()


class TestGenomicFilterKeyEnum:
    def test_accepts_enum_key(self):
        from picsure import GenomicFilterKey, buildGenomicFilter

        gf = buildGenomicFilter(GenomicFilterKey.GENE_WITH_VARIANT, values=["BRCA1"])
        assert gf.key == "Gene_with_variant"
        assert gf.values == ("BRCA1",)

    def test_accepts_valid_string_key(self):
        from picsure import buildGenomicFilter

        gf = buildGenomicFilter("Variant_class", values=["SNV"])
        assert gf.key == "Variant_class"

    def test_unknown_string_key_is_rejected(self):
        from picsure import PicSureValidationError, buildGenomicFilter

        with pytest.raises(
            PicSureValidationError, match="not a recognized genomic filter key"
        ):
            buildGenomicFilter("Variant_severty", values=["x"])

    def test_unknown_key_error_lists_valid_keys(self):
        from picsure import PicSureValidationError, buildGenomicFilter

        with pytest.raises(PicSureValidationError, match="Gene_with_variant"):
            buildGenomicFilter("nope", values=["x"])

    def test_snp_key_still_reports_snp(self):
        from picsure import PicSureValidationError, buildGenomicFilter

        with pytest.raises(PicSureValidationError, match="SNP"):
            buildGenomicFilter("rs123", values=["x"])

    def test_severity_enum_expands_to_consequences(self):
        from picsure import GenomicFilterKey, VariantSeverity, buildGenomicFilter

        gf = buildGenomicFilter(
            GenomicFilterKey.VARIANT_SEVERITY, values=VariantSeverity.HIGH
        )
        assert gf.key == "Variant_consequence_calculated"
        assert gf.values == (
            "splice_acceptor_variant",
            "splice_donor_variant",
            "stop_gained",
            "frameshift_variant",
            "stop_lost",
            "start_lost",
        )

    def test_severity_string_label_expands(self):
        from picsure import buildGenomicFilter

        gf = buildGenomicFilter("Variant_severity", values="High Severity")
        assert gf.key == "Variant_consequence_calculated"
        assert "stop_gained" in gf.values

    def test_multiple_severities_union_dedup_ordered(self):
        from picsure import GenomicFilterKey, VariantSeverity, buildGenomicFilter

        gf = buildGenomicFilter(
            GenomicFilterKey.VARIANT_SEVERITY,
            values=[VariantSeverity.HIGH, VariantSeverity.MEDIUM],
        )
        assert gf.key == "Variant_consequence_calculated"
        assert gf.values[0] == "splice_acceptor_variant"
        assert "missense_variant" in gf.values
        assert len(gf.values) == len(set(gf.values))

    def test_unknown_severity_value_is_rejected(self):
        from picsure import GenomicFilterKey, PicSureValidationError, buildGenomicFilter

        with pytest.raises(
            PicSureValidationError, match="not a valid variant severity"
        ):
            buildGenomicFilter(GenomicFilterKey.VARIANT_SEVERITY, values="Catastrophic")

    def test_unknown_severity_message_names_both_vocabularies(self):
        # PL-05: the flat rejection did not say that two vocabularies exist,
        # so a user who fed searchGenomicValues output back in had nothing to
        # go on.
        from picsure import GenomicFilterKey, PicSureValidationError, buildGenomicFilter

        with pytest.raises(PicSureValidationError) as exc_info:
            buildGenomicFilter(GenomicFilterKey.VARIANT_SEVERITY, values="Catastrophic")

        message = str(exc_info.value)
        assert "HIGH" in message
        assert "MODIFIER" in message
        assert "High Severity" in message
        assert "searchGenomicValues" in message
        assert "Variant_consequence_calculated" in message


class TestVariantSeverityImpactValues:
    """The backend's own ``Variant_severity`` vocabulary (PL-05).

    ``searchGenomicValues("Variant_severity")`` returns HIGH / MODERATE /
    LOW / MODIFIER and the backend applies the key verbatim, so these are
    sent through unchanged rather than expanded. Verified live: each of the
    four returns a distinct non-zero count, and a bogus key or value returns
    0, so the filter is genuinely applied.
    """

    @pytest.mark.parametrize("impact", ["HIGH", "MODERATE", "LOW", "MODIFIER"])
    def test_impact_value_passes_through_on_severity_key(self, impact):
        from picsure import GenomicFilterKey, buildGenomicFilter

        gf = buildGenomicFilter(GenomicFilterKey.VARIANT_SEVERITY, values=impact)
        assert gf.key == "Variant_severity"
        assert gf.values == (impact,)

    def test_impact_values_accepted_as_a_sequence(self):
        from picsure import GenomicFilterKey, buildGenomicFilter

        gf = buildGenomicFilter(
            GenomicFilterKey.VARIANT_SEVERITY, values=["HIGH", "MODERATE"]
        )
        assert gf.key == "Variant_severity"
        assert gf.values == ("HIGH", "MODERATE")

    def test_impact_matching_ignores_case_and_whitespace(self):
        from picsure import buildGenomicFilter

        gf = buildGenomicFilter("Variant_severity", values=["  high ", "Moderate"])
        assert gf.key == "Variant_severity"
        assert gf.values == ("HIGH", "MODERATE")

    def test_duplicate_impacts_are_collapsed(self):
        from picsure import buildGenomicFilter

        gf = buildGenomicFilter("Variant_severity", values=["HIGH", "high", "HIGH"])
        assert gf.values == ("HIGH",)

    def test_modifier_is_unreachable_through_severity_buckets(self):
        # MODIFIER is a populated bucket on the live stack (32 patients via
        # intron_variant) that no VariantSeverity bucket covers, so the impact
        # vocabulary is the only way to express it.
        from picsure._models.genomic_filter import (
            known_severities,
            severity_consequences,
        )

        covered = {
            consequence
            for bucket in known_severities()
            for consequence in severity_consequences(bucket)
        }
        assert "intron_variant" not in covered

    def test_mixing_vocabularies_in_one_filter_is_rejected(self):
        from picsure import GenomicFilterKey, PicSureValidationError, buildGenomicFilter

        with pytest.raises(PicSureValidationError, match="cannot mix"):
            buildGenomicFilter(
                GenomicFilterKey.VARIANT_SEVERITY,
                values=["HIGH", "Low Severity"],
            )

    def test_mixing_message_explains_the_two_keys(self):
        from picsure import PicSureValidationError, buildGenomicFilter

        with pytest.raises(PicSureValidationError) as exc_info:
            buildGenomicFilter("Variant_severity", values=["HIGH", "Low Severity"])

        message = str(exc_info.value)
        assert "'Variant_severity'" in message
        assert "'Variant_consequence_calculated'" in message

    def test_buckets_still_expand_unchanged(self):
        # Back-compat: the bucket vocabulary keeps its existing behaviour.
        from picsure import VariantSeverity, buildGenomicFilter

        gf = buildGenomicFilter("Variant_severity", values=VariantSeverity.HIGH)
        assert gf.key == "Variant_consequence_calculated"
        assert "stop_gained" in gf.values

    def test_empty_values_sequence_is_rejected(self):
        from picsure import PicSureValidationError, buildGenomicFilter

        with pytest.raises(PicSureValidationError, match="non-empty"):
            buildGenomicFilter("Gene_with_variant", values=[])
