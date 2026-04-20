# Migrating from PicSureHpdsLib

This guide maps the old `PicSureHpdsLib` API to the new `picsure`
package. The new package is a complete rewrite — old import paths
will not work.

## Installation

**Old:**

```bash
pip install git+https://github.com/hms-dbmi/pic-sure-python-client.git
pip install git+https://github.com/hms-dbmi/pic-sure-python-adapter-hpds.git
```

**New:**

```bash
pip install picsure
```

One package replaces both the client and the adapter.

## Quick Reference

| Old API | New API |
|---|---|
| `PicSureClient.Client(url, token)` | `picsure.connect(platform, token)` |
| `PicSureHpdsLib.Adapter(conn)` | *(not needed — `connect` returns a Session directly)* |
| `adapter.useResource(uuid)` | `session.setResourceID(uuid)` |
| `resource.dictionary().find("sex")` | `session.search("sex")` |
| `resource.query()` | `picsure.createClause(...)` |
| `query.filter().add(path, values)` | `picsure.createClause(path, type=ClauseType.FILTER, categories=values)` |
| `query.require().add(path)` | `picsure.createClause(path, type=ClauseType.REQUIRE)` |
| `query.anyRecordOf().add(path)` | `picsure.createClause(path, type=ClauseType.ANYRECORD)` |
| `query.select().add(path)` | `picsure.createClause(path, type=ClauseType.SELECT)` |
| `query.getCount()` | `session.runQuery(query, type="count")` |
| `query.getResults()` | `session.runQuery(query, type="participant")` |
| `query.getResultsDataFrame()` | `session.runQuery(query, type="participant")` |

### Return-type changes

**Note:** `runQuery(..., type="count")` now returns a `CountResult`, not an
`int`. Use `result.value` for the numeric count (which may be `None` on
open-access deployments that suppress small counts — check `result.cap` in
that case).

## Side-by-Side Examples

### Connecting

**Old:**

```python
import PicSureClient
import PicSureHpdsLib

conn = PicSureClient.Client(url="https://picsure.biodatacatalyst.nhlbi.nih.gov/picsure/", token=my_token)
adapter = PicSureHpdsLib.Adapter(conn)
resource = adapter.useResource(resource_uuid)
```

**New:**

```python
import picsure

session = picsure.connect(platform="BDC Authorized", token=my_token)
```

### Searching the Dictionary

**Old:**

```python
dictionary = resource.dictionary()
results = dictionary.find("blood pressure")
results.DataFrame()
```

**New:**

```python
df = session.search("blood pressure")
```

### Building a Query

**Old:**

```python
query = resource.query()
query.filter().add(r"\phs1\sex\", ["Male"])
query.filter().add(r"\phs1\age\", min=40)
query.require().add(r"\phs1\bmi\")
```

**New:**

```python
from picsure import createClause, buildClauseGroup, ClauseType, GroupOperator

sex = createClause(r"\phs1\sex\", type=ClauseType.FILTER, categories="Male")
age = createClause(r"\phs1\age\", type=ClauseType.FILTER, min=40)
bmi = createClause(r"\phs1\bmi\", type=ClauseType.REQUIRE)

query = buildClauseGroup([sex, age, bmi], root=GroupOperator.AND)
```

### Running a Query

**Old:**

```python
count = query.getCount()
df = query.getResultsDataFrame()
```

**New:**

```python
count_result = session.runQuery(query, type="count")
if count_result.value is not None:
    print(f"{count_result.value} participants match")
else:
    print(f"fewer than {count_result.cap} participants match (suppressed)")
df = session.runQuery(query, type="participant")
```

### Exporting

**Old:**

```python
df.to_csv("output.csv")
```

**New:**

```python
session.exportCSV(df, "output.csv")
# or
session.exportTSV(df, "output.tsv")
# or
session.exportPFB(query, "output.pfb")
```

## What Changed

### Removed

- **Consents handling** — now managed by the backend as part of advanced
  filtering. No adapter-side consent logic needed.
- **BypassAdapter** — direct HPDS connections are no longer supported.
  All connections go through PIC-SURE.
- **Two-package install** — the client and adapter are merged into one
  package.

### Added

- **Facet filtering** — narrow search results by study, data type, etc.
- **Nested AND/OR queries** — build complex cohort logic with clause groups.
- **Named platforms** — connect with `"BDC Authorized"` instead of a URL.
- **PFB export** — export query results in PFB format.
- **Time series queries** — retrieve longitudinal data.
- **Actionable error messages** — every error tells you what went wrong
  and how to fix it.

## Getting Help

If you run into issues migrating, check the
[API Reference](../reference/api.md) for complete function documentation
or open an issue on GitHub.
