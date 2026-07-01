# picsure

Python client for the PIC-SURE API. Search the data dictionary, build
cohort queries with nested AND/OR filters, and export participant-level
data — all from a Jupyter notebook.

## Features

- **Connect** to any PIC-SURE instance with a single function call
- **Search** the data dictionary and narrow results with facet filters
- **Build queries** with nested AND/OR clause groups for complex cohort selection
- **Filter by genomic variant** attributes including gene, consequence, and frequency (authorized platforms)
- **Run queries** to get counts, participant-level data, or time series
- **Export** results as CSV, TSV, or PFB

## Quick Example

```python
import picsure
from picsure import PhenotypicFilterType, GroupOperator

# Connect
session = picsure.connect(platform=picsure.Platform.BDC_AUTHORIZED, token=my_token)

# Search the dictionary
results = session.searchDictionary("blood pressure")

# Build a query
sex = picsure.buildClause(
    "\\phs1\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male"
)
age = picsure.buildClause(
    "\\phs1\\age\\", type=PhenotypicFilterType.FILTER, min=40
)
query = picsure.buildClauseGroup([sex, age], operator=GroupOperator.AND)

# Run and export
count_result = session.runQuery(query, type="count")
count = count_result.value  # None if suppressed; check count_result.cap
df = session.runQuery(query, type="participant")
session.exportCSV(df, "cohort.csv")
```

## Installation

```bash
pip install picsure
```

For PFB export support:

```bash
pip install picsure[pfb]
```

## Next Steps

- [Getting Started](getting-started.md) — connect and run your first query
- [User Guides](guides/search-and-facets.md) — detailed walkthroughs
- [API Reference](reference/api.md) — complete function documentation
- [Migration Guide](guides/migrating-from-picsurehpdslib.md) — upgrading from the old adapter
