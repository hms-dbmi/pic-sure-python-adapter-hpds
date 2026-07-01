# Building Queries

This guide covers creating filter clauses, combining them into nested
AND/OR query groups, and assembling a complete query with the output
concepts to include.

## The build\* pipeline

Queries are built in three tiers, each builder named after what it returns:

| Builder | Returns | Purpose |
|---|---|---|
| `buildClause` | `Clause` | A single filter leaf |
| `buildClauseGroup` | `ClauseGroup` | Combine clauses/groups under AND/OR (nestable) |
| `buildQuery` | `Query` | Assemble a filter tree + output concepts to return |

A bare `Clause` or `ClauseGroup` can be run directly (filter only, no extra
output columns); use `buildQuery` when you also want to choose which concept
paths appear in the result.

## Clause Types

PIC-SURE supports three filter clause types:

| Type | Purpose | Example |
|---|---|---|
| `FILTER` | Filter by value or range | Males only, age > 40 |
| `ANYRECORD` | Match any record with a value | Has any BMI measurement |
| `REQUIRE` | Require non-null value | Must have blood pressure |

To **include a concept path in the output without filtering** (what the old
`SELECT` clause did), pass it to `buildQuery(includeConcepts=...)` instead —
output columns are no longer a clause type.

## Creating Clauses

```python
from picsure import buildClause, PhenotypicFilterType

# Categorical filter
sex = buildClause(
    "\\phs1\\pht1\\phv1\\sex\\",
    type=PhenotypicFilterType.FILTER,
    categories="Male",
)

# Multiple categorical values
asthma = buildClause(
    "\\phs1\\pht2\\phv3\\asthma\\",
    type=PhenotypicFilterType.FILTER,
    categories=["Yes, recent", "Yes, since childhood"],
)

# Numeric range filter
age = buildClause(
    "\\phs1\\pht1\\phv5\\age\\",
    type=PhenotypicFilterType.FILTER,
    min=40,
    max=80,
)

# Min only (no upper bound)
age_over_40 = buildClause(
    "\\phs1\\pht1\\phv5\\age\\",
    type=PhenotypicFilterType.FILTER,
    min=40,
)

# Any record of a variable
has_sleep_data = buildClause(
    "\\phs1\\pht3\\phv8\\trouble_sleeping\\",
    type=PhenotypicFilterType.ANYRECORD,
)
```

## Combining Clauses with AND/OR

Use `buildClauseGroup` to combine clauses:

```python
from picsure import buildClauseGroup, GroupOperator

# AND: all conditions must be true
males_over_40 = buildClauseGroup(
    [sex, age_over_40],
    operator=GroupOperator.AND,
)

# OR: at least one condition must be true
copd_or_asthma = buildClauseGroup(
    [copd, asthma],
    operator=GroupOperator.OR,
)
```

## Nesting Groups

Groups can contain other groups for complex logic:

```python
# Find males over 40 with COPD or asthma
filters = buildClauseGroup(
    [males_over_40, copd_or_asthma],
    operator=GroupOperator.AND,
)
```

This produces the logical expression:

```
(sex = Male AND age >= 40) AND (COPD = Yes OR asthma in [Yes, recent; Yes, since childhood])
```

## Assembling a Query and Choosing Output Concepts

`buildQuery` bundles a filter tree with the concept paths to return as
output columns:

```python
from picsure import buildQuery

# Filter + the columns you want back
query = buildQuery(
    phenotypicFilter=filters,
    includeConcepts=["\\phs1\\pht1\\phv10\\height\\", "\\phs1\\pht1\\phv11\\bmi\\"],
)
df = session.runQuery(query, type="participant")

# Include-only — return these concepts for every matching record, no filter
heights = buildQuery(includeConcepts=["\\phs1\\pht1\\phv10\\height\\"])

# Filter only — bare ClauseGroup/Clause works without buildQuery
count = session.runQuery(filters, type="count")
```

`includeConcepts` preserves order and drops duplicates.

Variables you filter on are returned automatically — you don't need to repeat
them in `includeConcepts`. Use `includeConcepts` only for *additional* output
columns that aren't already part of the filter. A bare `Clause`/`ClauseGroup`
run as `participant` therefore returns its filtered variables as columns, not
just the participant ID.

### Full Example from the Product Spec

Select participants who are male, over 40, and have either
COPD/asthma or sleep problems, returning their height in the output:

```python
import picsure
from picsure import buildClause, buildClauseGroup, buildQuery, PhenotypicFilterType, GroupOperator

sex_filter = buildClause("\\phs1\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male")
age_filter = buildClause("\\phs1\\age\\", type=PhenotypicFilterType.FILTER, min=40)
copd_filter = buildClause("\\phs1\\copd\\", type=PhenotypicFilterType.FILTER, categories="Yes")
asthma_filter = buildClause("\\phs1\\asthma\\", type=PhenotypicFilterType.FILTER, categories="Yes")
sleep_filter = buildClause("\\phs1\\trouble_sleeping\\", type=PhenotypicFilterType.ANYRECORD)
insomnia_filter = buildClause("\\phs1\\insomnia\\", type=PhenotypicFilterType.ANYRECORD)

copd_or_asthma = buildClauseGroup([copd_filter, asthma_filter], operator=GroupOperator.OR)
sleep_or_insomnia = buildClauseGroup([sleep_filter, insomnia_filter], operator=GroupOperator.OR)

filters = buildClauseGroup(
    [sex_filter, age_filter, copd_or_asthma, sleep_or_insomnia],
    operator=GroupOperator.AND,
)

full_query = buildQuery(
    phenotypicFilter=filters,
    includeConcepts=["\\phs1\\height\\"],
)
```

## Genomic Filters

On genomic-capable platforms (BDC_AUTHORIZED, BDC_DEV_AUTHORIZED, BDC_PREDEV_AUTHORIZED,
NHANES_AUTHORIZED), you can add genomic filters to a query using `buildGenomicFilter`.
Each call produces one categorical `GenomicFilter`; the filters are AND-combined with
the phenotypic filter when the query runs.

### Building a genomic filter

```python
from picsure import buildGenomicFilter, VariantFrequency

# Filter to a specific gene
gene_filter = buildGenomicFilter("Gene_with_variant", values="BRCA2")

# Multiple genes at once
multi_gene = buildGenomicFilter("Gene_with_variant", values=["BRCA1", "BRCA2"])

# Filter by variant consequence
csq_filter = buildGenomicFilter("Variant_consequence_calculated", values="missense_variant")

# Filter by frequency using the VariantFrequency enum
freq_filter = buildGenomicFilter("Variant_frequency_as_text", values=VariantFrequency.RARE)
```

`values` is required. Variant-spec and SNP keys are rejected with an actionable error.
`VariantFrequency` has three members: `RARE`, `COMMON`, and `NOVEL`.

### Genomic-only query

Pass a list of `GenomicFilter` objects to `buildQuery(genomicFilters=...)`. A
`phenotypicFilter` is not required:

```python
from picsure import buildQuery

genomic_query = buildQuery(genomicFilters=[gene_filter, freq_filter])
count_result = session.runQuery(genomic_query, type="count")
```

### Combined phenotypic and genomic query

Phenotypic and genomic filters are AND-combined:

```python
from picsure import buildClause, buildClauseGroup, buildQuery, PhenotypicFilterType, GroupOperator

sex_filter = buildClause("\\phs1\\sex\\", type=PhenotypicFilterType.FILTER, categories="Female")
age_filter = buildClause("\\phs1\\age\\", type=PhenotypicFilterType.FILTER, min=18, max=45)
pheno = buildClauseGroup([sex_filter, age_filter], operator=GroupOperator.AND)

gene_filter = buildGenomicFilter("Gene_with_variant", values="BRCA2")
freq_filter = buildGenomicFilter("Variant_frequency_as_text", values=VariantFrequency.RARE)

query = buildQuery(phenotypicFilter=pheno, genomicFilters=[gene_filter, freq_filter])
count_result = session.runQuery(query, type="count")
```

## Editing an Existing Query

`removeSubQuery` and `replaceClause` let you edit a query tree without
rebuilding it from scratch. Both return a **new** query — the input is
not mutated. Matching is structural (frozen-dataclass equality): a node
matches when every field is equal, including nested children.

They accept a bare `Clause`/`ClauseGroup` or a `Query`; for a `Query` the
edit applies to its `phenotypicFilter` tree and the `includeConcepts` are
preserved.

```python
from picsure import removeSubQuery, replaceClause

# Drop the sleep/insomnia OR group entirely (preserving includeConcepts)
without_sleep = removeSubQuery(full_query, sleep_or_insomnia)

# Swap "Male" for "Female"
female_filter = buildClause(
    "\\phs1\\sex\\", type=PhenotypicFilterType.FILTER, categories="Female"
)
female_query = replaceClause(full_query, sex_filter, female_filter)
```

`removeSubQuery` drops any `ClauseGroup` left empty by a removal, so
you don't end up with orphan operators. It raises
`PicSureValidationError` if the removal would empty the whole tree —
build a fresh query instead in that case.

## Validation

The library validates clause configurations and provides actionable
error messages:

```python
# ANYRECORD with categories raises an error
buildClause("\\path\\", type=PhenotypicFilterType.ANYRECORD, categories="Male")
# PicSureValidationError: ANYRECORD clauses cannot have categories.
# ANYRECORD matches the presence of any value for the variable.
# Remove the categories argument.

# FILTER without any criteria raises an error
buildClause("\\path\\", type=PhenotypicFilterType.FILTER)
# PicSureValidationError: FILTER clauses require at least one of:
# categories, min, or max.
```

## Inspecting Query JSON

Every clause and group can serialize to the v3 query JSON format:

```python
import json
print(json.dumps(filters.to_query_json(), indent=2))
```
