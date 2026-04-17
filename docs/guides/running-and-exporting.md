# Running Queries & Exporting Data

This guide covers executing queries and saving results.

## Running Queries

Use `session.runQuery()` with your query and a result type:

### Count

Get the number of matching participants:

```python
count = session.runQuery(my_query, type="count")
print(f"Found {count} matching participants")
```

Returns an integer.

### Participant Data

Get participant-level data as a DataFrame:

```python
df = session.runQuery(my_query, type="participant")
df.head()
```

Returns a pandas DataFrame with one row per participant.

### Time Series Data

Get time-series data as a DataFrame:

```python
df = session.runQuery(my_query, type="timestamp")
df.head()
```

Returns a pandas DataFrame with repeated measurements over time.

## Exporting Data

### CSV

```python
df = session.runQuery(my_query, type="participant")
session.exportCSV(df, "my_cohort.csv")
```

### TSV

```python
session.exportTSV(df, "my_cohort.tsv")
```

### PFB

PFB export runs the query server-side and writes the result directly
to a file:

```python
session.exportPFB(my_query, "my_cohort.pfb")
```

!!! note
    PFB export requires the optional `pypfb` dependency:
    ```bash
    pip install picsure[pfb]
    ```

## Simple Queries

You can pass a single clause directly to `runQuery` — you don't have
to wrap it in a group first:

```python
sex = picsure.createClause(r"\phs1\sex\", type=ClauseType.FILTER, categories="Male")

# This works — no buildClauseGroup needed for simple queries
count = session.runQuery(sex, type="count")
```

## Error Handling

If something goes wrong, you'll get a clear error message:

```python
# Invalid query type
session.runQuery(my_query, type="invalid")
# PicSureValidationError: 'invalid' is not a valid query type.
# Valid types: count, participant, timestamp.
```

Researchers don't need to write try/except blocks. The error messages
tell you what happened and what to do about it.
