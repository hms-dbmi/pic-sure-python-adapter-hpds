# picsure

Python client for the PIC-SURE API. Search the data dictionary, build
cohort queries with nested AND/OR filters, and export participant-level
data — all from a Jupyter notebook.

## Features

- **Connect** to any PIC-SURE instance with a single function call
- **Search** the data dictionary and narrow results with facet filters
- **Build queries** with nested AND/OR clause groups for complex cohort selection
- **Run queries** to get counts, participant-level data, or time series
- **Export** results as CSV, TSV, or PFB

## Quick Example

```python
import picsure
from picsure import ClauseType, GroupOperator

# Connect
session = picsure.connect(platform="BDC Authorized", token=my_token)

# Search the dictionary
results = session.search("blood pressure")

# Build a query
sex = picsure.createClause(
    r"\phs1\sex\", type=ClauseType.FILTER, categories="Male"
)
age = picsure.createClause(
    r"\phs1\age\", type=ClauseType.FILTER, min=40
)
query = picsure.buildClauseGroup([sex, age], root=GroupOperator.AND)

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
