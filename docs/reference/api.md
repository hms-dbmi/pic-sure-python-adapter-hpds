# API Reference

Complete reference for all public functions, classes, and types in the
`picsure` package.

## Connection

::: picsure.connect

## Query Construction

::: picsure.createClause

::: picsure.buildClauseGroup

## Types

### ClauseType

::: picsure.ClauseType
    options:
      members: true

### GroupOperator

::: picsure.GroupOperator
    options:
      members: true

### Clause

::: picsure.Clause
    options:
      members:
        - to_query_json

### ClauseGroup

::: picsure.ClauseGroup
    options:
      members:
        - to_query_json

### Query

::: picsure.Query

### FacetSet

::: picsure.FacetSet
    options:
      members:
        - add
        - view
        - clear

## Session

::: picsure.Session
    options:
      members:
        - search
        - facets
        - showAllFacets
        - runQuery
        - exportPFB
        - exportCSV
        - exportTSV
        - getResourceID
        - setResourceID
        - setResourceIDByName

## Errors

::: picsure.PicSureError
