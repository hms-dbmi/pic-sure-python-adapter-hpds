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
