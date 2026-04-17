# Building Queries

This guide covers creating filter clauses and combining them into
nested AND/OR query groups.

## Clause Types

PIC-SURE supports four types of clauses:

| Type | Purpose | Example |
|---|---|---|
| `FILTER` | Filter by value or range | Males only, age > 40 |
| `ANYRECORD` | Match any record with a value | Has any BMI measurement |
| `SELECT` | Include in output, no filtering | Add height to results |
| `REQUIRE` | Require non-null value | Must have blood pressure |

## Creating Clauses

```python
from picsure import createClause, ClauseType

# Categorical filter
sex = createClause(
    r"\phs1\pht1\phv1\sex\",
    type=ClauseType.FILTER,
    categories="Male",
)

# Multiple categorical values
asthma = createClause(
    r"\phs1\pht2\phv3\asthma\",
    type=ClauseType.FILTER,
    categories=["Yes, recent", "Yes, since childhood"],
)

# Numeric range filter
age = createClause(
    r"\phs1\pht1\phv5\age\",
    type=ClauseType.FILTER,
    min=40,
    max=80,
)

# Min only (no upper bound)
age_over_40 = createClause(
    r"\phs1\pht1\phv5\age\",
    type=ClauseType.FILTER,
    min=40,
)

# Any record of a variable
has_sleep_data = createClause(
    r"\phs1\pht3\phv8\trouble_sleeping\",
    type=ClauseType.ANYRECORD,
)

# Select for output without filtering
include_height = createClause(
    r"\phs1\pht1\phv10\height\",
    type=ClauseType.SELECT,
)
```

## Combining Clauses with AND/OR

Use `buildClauseGroup` to combine clauses:

```python
from picsure import buildClauseGroup, GroupOperator

# AND: all conditions must be true
males_over_40 = buildClauseGroup(
    [sex, age_over_40],
    root=GroupOperator.AND,
)

# OR: at least one condition must be true
copd_or_asthma = buildClauseGroup(
    [copd, asthma],
    root=GroupOperator.OR,
)
```

## Nesting Groups

Groups can contain other groups for complex logic:

```python
# Find males over 40 with COPD or asthma
full_query = buildClauseGroup(
    [males_over_40, copd_or_asthma],
    root=GroupOperator.AND,
)
```

This produces the logical expression:

```
(sex = Male AND age >= 40) AND (COPD = Yes OR asthma in [Yes, recent; Yes, since childhood])
```

### Full Example from the Product Spec

Select participants who are male, over 40, and have either
COPD/asthma or sleep problems:

```python
import picsure
from picsure import createClause, buildClauseGroup, ClauseType, GroupOperator

sex_filter = createClause(r"\phs1\sex\", type=ClauseType.FILTER, categories="Male")
age_filter = createClause(r"\phs1\age\", type=ClauseType.FILTER, min=40)
copd_filter = createClause(r"\phs1\copd\", type=ClauseType.FILTER, categories="Yes")
asthma_filter = createClause(r"\phs1\asthma\", type=ClauseType.FILTER, categories="Yes")
sleep_filter = createClause(r"\phs1\trouble_sleeping\", type=ClauseType.ANYRECORD)
insomnia_filter = createClause(r"\phs1\insomnia\", type=ClauseType.ANYRECORD)

copd_or_asthma = buildClauseGroup([copd_filter, asthma_filter], root=GroupOperator.OR)
sleep_or_insomnia = buildClauseGroup([sleep_filter, insomnia_filter], root=GroupOperator.OR)

full_query = buildClauseGroup(
    [sex_filter, age_filter, copd_or_asthma, sleep_or_insomnia],
    root=GroupOperator.AND,
)
```

## Validation

The library validates clause configurations and provides actionable
error messages:

```python
# ANYRECORD with categories raises an error
createClause(r"\path\", type=ClauseType.ANYRECORD, categories="Male")
# PicSureValidationError: ANYRECORD clauses cannot have categories.
# ANYRECORD matches the presence of any value for the variable.
# Remove the categories argument.

# FILTER without any criteria raises an error
createClause(r"\path\", type=ClauseType.FILTER)
# PicSureValidationError: FILTER clauses require at least one of:
# categories, min, or max.
```

## Inspecting Query JSON

Every clause and group can serialize to the v3 query JSON format:

```python
import json
print(json.dumps(full_query.to_query_json(), indent=2))
```
