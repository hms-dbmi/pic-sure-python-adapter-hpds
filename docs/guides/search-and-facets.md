# Search & Facets

This guide covers searching the PIC-SURE data dictionary and using
facets to narrow results.

## Basic Search

Search for variables by keyword. Results are returned as a pandas
DataFrame.

```python
results = session.search("blood pressure")
print(f"Found {len(results)} variables")
results.head()
```

### Search with No Term

Pass an empty string (or no argument) to return all variables:

```python
all_vars = session.search()
```

### Exclude Values

For faster searches on large dictionaries, set `include_values=False`
to omit the `values` column:

```python
results = session.search("age", include_values=False)
```

## Facet Filtering

Facets let you narrow search results by category — for example,
filtering to variables from a specific study.

### View Available Facets

```python
# See all facet categories and their options
session.showAllFacets()
```

This returns a DataFrame with columns: `category`, `display`, `value`,
`count`.

### Build a Facet Filter

```python
# Create a FacetSet with available categories
facets = session.facets()

# See current (empty) selections
facets.view()
# {'study_ids': [], 'data_type': [], ...}

# Add a study filter
facets.add("study_ids", "phs000007")

# Add multiple values at once
facets.add("data_type", ["categorical", "continuous"])

# Use in search
filtered = session.search("blood pressure", facets=facets)
```

### Clear Facet Selections

```python
# Clear one category
facets.clear("study_ids")

# Clear all selections
facets.clear()
```

### Invalid Facets

If you pass an invalid category name, you'll get a clear error message
listing the valid options:

```python
facets.add("invalid_category", "value")
# PicSureValidationError: 'invalid_category' is not a valid facet
# category. Valid categories: data_type, study_ids.
```
