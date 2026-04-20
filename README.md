# picsure

Python client for the PIC-SURE API. Search the data dictionary, build
cohort queries with nested AND/OR filters, and export participant-level
data — all from a Jupyter notebook.

## Installation

```bash
pip install picsure
```

For PFB export support:

```bash
pip install picsure[pfb]
```

## Quickstart

```python
import picsure
from picsure import ClauseType, GroupOperator

# Connect to PIC-SURE
session = picsure.connect(platform="BDC Authorized", token="your-token")

# Search the data dictionary
results = session.search("blood pressure")

# Build a query
sex = picsure.createClause(r"\phs1\sex\", type=ClauseType.FILTER, categories="Male")
age = picsure.createClause(r"\phs1\age\", type=ClauseType.FILTER, min=40)
query = picsure.buildClauseGroup([sex, age], root=GroupOperator.AND)

# Run and export
count_result = session.runQuery(query, type="count")
count = count_result.value  # None if suppressed; check count_result.cap
df = session.runQuery(query, type="participant")
session.exportCSV(df, "cohort.csv")
```

## Documentation

- **[Getting Started](docs/getting-started.md)** — connect and run your first query
- **[Search & Facets](docs/guides/search-and-facets.md)** — search the dictionary with facet filters
- **[Building Queries](docs/guides/building-queries.md)** — nested AND/OR clause groups
- **[Running & Exporting](docs/guides/running-and-exporting.md)** — counts, DataFrames, CSV/TSV/PFB
- **[API Reference](docs/reference/api.md)** — complete function documentation
- **[Migration Guide](docs/guides/migrating-from-picsurehpdslib.md)** — upgrading from PicSureHpdsLib

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
