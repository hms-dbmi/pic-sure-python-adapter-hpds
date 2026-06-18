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
from picsure import PhenotypicFilterType, GroupOperator

# Connect to PIC-SURE
session = picsure.connect(platform=picsure.Platform.BDC_AUTHORIZED, token="your-token")

# Search the data dictionary
results = session.searchDictionary("blood pressure")

# Build a query
sex = picsure.buildClause("\\phs1\\sex\\", type=PhenotypicFilterType.FILTER, categories="Male")
age = picsure.buildClause("\\phs1\\age\\", type=PhenotypicFilterType.FILTER, min=40)
query = picsure.buildClauseGroup([sex, age], operator=GroupOperator.AND)

# Run and export
count_result = session.runQuery(query, type="count")
count = count_result.value  # None if suppressed; check count_result.cap
df = session.runQuery(query, type="participant")
session.exportCSV(df, "cohort.csv")
```

## Documentation

- **[Getting Started](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/docs/getting-started.md)** — connect and run your first query
- **[Search & Facets](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/docs/guides/search-and-facets.md)** — search the dictionary with facet filters
- **[Building Queries](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/docs/guides/building-queries.md)** — nested AND/OR clause groups
- **[Running & Exporting](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/docs/guides/running-and-exporting.md)** — counts, DataFrames, CSV/TSV/PFB
- **[API Reference](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/docs/reference/api.md)** — complete function documentation
- **[Migration Guide](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/docs/guides/migrating-from-picsurehpdslib.md)** — upgrading from PicSureHpdsLib
- **[Changelog](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/CHANGELOG.md)** — release history and notable changes

## License

Apache 2.0 — see [LICENSE](https://github.com/hms-dbmi/pic-sure-python-adapter-hpds/blob/main/LICENSE) for details.
