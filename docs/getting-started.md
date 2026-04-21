# Getting Started

This guide walks you through connecting to PIC-SURE, searching the data
dictionary, building a query, and exporting results.

## Prerequisites

- Python 3.10 or later
- A PIC-SURE API token ([generate one here](https://picsure.biodatacatalyst.nhlbi.nih.gov/))
- `pip install picsure`

## Step 1: Connect

```python
import picsure

session = picsure.connect(
    platform="BDC Authorized",
    token="your-api-token",
)
```

You'll see a confirmation message:

```
You're successfully connected to BDC Authorized as user you@email.com!
Your token expires on 2026-06-15T00:00:00Z.
```

The `platform` parameter accepts named platforms (`"BDC Authorized"`,
`"BDC Open"`, `"Demo"`) or a custom URL for other
PIC-SURE instances.

## Step 2: Search the Data Dictionary

```python
# Search for variables containing "blood pressure"
results = session.search("blood pressure")
results.head()
```

The result is a pandas DataFrame with columns like `conceptPath`, `name`,
`display`, `description`, `dataType`, `studyId`, and `values`.

### Narrowing with Facets

```python
# See all available facet categories
session.showAllFacets()

# Create a facet filter
facets = session.facets()
facets.add("study_ids", "phs000007")

# Search with facets
fhs_results = session.search("blood pressure", facets=facets)
```

## Step 3: Build a Query

```python
from picsure import ClauseType, GroupOperator

# Create individual clauses
sex_filter = picsure.createClause(
    r"\phs1\pht1\phv1\sex\",
    type=ClauseType.FILTER,
    categories="Male",
)

age_filter = picsure.createClause(
    r"\phs1\pht1\phv5\age\",
    type=ClauseType.FILTER,
    min=40,
)

# Combine into a group
query = picsure.buildClauseGroup(
    [sex_filter, age_filter],
    root=GroupOperator.AND,
)
```

Queries can be nested arbitrarily deep. See the
[Building Queries](guides/building-queries.md) guide for more examples.

## Step 4: Run the Query

```python
# Get a count of matching participants
count_result = session.runQuery(query, type="count")
if count_result.value is not None:
    print(f"{count_result.value} participants match")
else:
    print(f"fewer than {count_result.cap} participants match (suppressed)")

# Get participant-level data
df = session.runQuery(query, type="participant")
df.head()
```

## Step 5: Export Results

```python
# Save as CSV
session.exportCSV(df, "my_cohort.csv")

# Save as TSV
session.exportTSV(df, "my_cohort.tsv")

# Export as PFB (requires pip install picsure[pfb])
session.exportPFB(query, "my_cohort.pfb")
```

## Next Steps

- [Search & Facets Guide](guides/search-and-facets.md) — advanced search patterns
- [Building Queries Guide](guides/building-queries.md) — nested AND/OR queries
- [API Reference](reference/api.md) — complete function documentation
