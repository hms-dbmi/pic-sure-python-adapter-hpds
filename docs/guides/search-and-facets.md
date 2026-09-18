# Search & Facets

This guide covers searching the PIC-SURE data dictionary and using
facets to narrow results.

## Basic Search

Search for variables by keyword. Results are returned as a pandas
DataFrame.

```python
results = session.searchDictionary("blood pressure")
print(f"Found {len(results)} variables")
results.head()
```

### Search with No Term

Pass an empty string (or no argument) to return all variables:

```python
all_vars = session.searchDictionary()
```

The server sends the dictionary a page at a time, so this walks the
pages and returns the whole result set as one DataFrame. It is not a
single request: the walk issues one HTTP call per 500 rows by default.

A production dictionary is large enough that the call above can fail.
An unpaged search refuses to collect more than 100,000 rows and raises
`PicSureValidationError` when the match count is above it, naming the
count and telling you to page. Narrowing with a term or a facet is the
other way out.

### Paging

Pass `page` to fetch exactly one page and stop. Pages are **zero-based**:
`page=0` is the first one. `page_size` sets the rows per HTTP request
and defaults to 500.

```python
first = session.searchDictionary("blood pressure", page=0, page_size=100)
second = session.searchDictionary("blood pressure", page=1, page_size=100)
```

Every returned DataFrame carries the paging state in
[`df.attrs`](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.attrs.html):

| Key | Meaning |
|---|---|
| `total_elements` | The server's total match count, or `None` when the response omitted it. |
| `has_more` | Whether pages remain beyond what was returned. |
| `page` | The page you asked for, or `None` when every page was collected. |
| `page_size` | Rows requested per HTTP call. |
| `pages_fetched` | How many HTTP calls the result took. |

`has_more` is what to loop on, since the last page is usually a short
one rather than an empty one:

```python
page = 0
while True:
    chunk = session.searchDictionary("blood pressure", page=page, page_size=1000)
    process(chunk)
    if not chunk.attrs["has_more"]:
        break
    page += 1
```

On an unpaged call `page` comes back `None` and `has_more` is `True`
only in one case: the server reported no match count and the final page
carried the walk past the 100,000-row ceiling, so the surplus rows were
dropped.

### Exclude Values

For faster searches on large dictionaries, set `include_values=False`
to omit the `values` column:

```python
results = session.searchDictionary("age", include_values=False)
```

## Facet Filtering

Facets let you narrow search results by category — for example,
filtering to variables from a specific study.

### View Available Facets

```python
# See all facet categories and their options
session.showAllFacets()
```

This returns a DataFrame with six columns:

| Column | Meaning |
|---|---|
| `category` | Category identifier (e.g. `dataset_id`) — pass this to `FacetSet.add`. |
| `Category Display` | Human-readable category label (e.g. `Dataset`). |
| `display` | Facet option's display label. |
| `description` | Facet option's description, if any. |
| `value` | Option identifier — pass this to `FacetSet.add`. |
| `count` | Number of concepts matching this option. |

### Build a Facet Filter

```python
# Create a FacetSet with available categories
facets = session.facets()

# See current (empty) selections
facets.view()
# {'dataset_id': [], 'data_type': [], ...}

# Add a study filter
facets.add("dataset_id", "phs000007")

# Add multiple values at once
facets.add("data_type", ["categorical", "continuous"])

# Use in search
filtered = session.searchDictionary("blood pressure", facets=facets)
```

### Clear Facet Selections

```python
# Clear one category
facets.clear("dataset_id")

# Clear all selections
facets.clear()
```

### Invalid Facets

If you pass an invalid category name, you'll get a clear error message
listing the valid options:

```python
facets.add("invalid_category", "value")
# PicSureValidationError: 'invalid_category' is not a valid facet
# category. Valid categories: data_type, dataset_id.
```

## Genomic Value Discovery

On genomic-capable platforms (BDC_AUTHORIZED, NHANES_AUTHORIZED), you can look
up valid values for any genomic key before building a filter.

### Search genomic values

`session.searchGenomicValues` queries the server and returns a DataFrame of
matching values. Results are paginated; metadata (total, page, size) is on
`df.attrs`.

```python
# Find genes matching "BRCA"
df = session.searchGenomicValues("Gene_with_variant", query="BRCA")
print(df)

# List all values for a key (no query term)
all_consequences = session.searchGenomicValues("Variant_consequence_calculated")

# Page through large result sets
page2 = session.searchGenomicValues("Gene_with_variant", query="", page=2, size=100)
print(df.attrs)  # {'total': ..., 'page': 2, 'size': 100}
```

### Variant consequences (offline)

`picsure.genomicConsequences()` returns the full list of consequence terms with
severity rankings without a network call. It works on any platform, including
open-access ones.

```python
import picsure

consequences = picsure.genomicConsequences()
# DataFrame with columns: severity, consequence
print(consequences.head())
```
