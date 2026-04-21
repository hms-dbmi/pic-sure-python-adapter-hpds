# Running Queries & Exporting Data

This guide covers executing queries and saving results.

## Running Queries

Use `session.runQuery()` with your query and a result type:

### Count

Get the number of matching participants:

```python
count_result = session.runQuery(my_query, type="count")
if count_result.value is not None:
    print(f"{count_result.value} participants match")
else:
    print(f"fewer than {count_result.cap} participants match (suppressed)")
```

Returns a `CountResult`. Access the numeric count via `.value` (which may be
`None` on open-access deployments that suppress small counts — check `.cap`
in that case).

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
sex = picsure.createClause("\\phs1\\sex\\", type=ClauseType.FILTER, categories="Male")

# This works — no buildClauseGroup needed for simple queries
count_result = session.runQuery(sex, type="count")
count = count_result.value  # None if suppressed; check count_result.cap
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
