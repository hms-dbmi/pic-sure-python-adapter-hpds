# API Reference

Complete reference for all public functions, classes, and types in the
`picsure` package.

## Connection

::: picsure.connect

### Platform

::: picsure.Platform
    options:
      members: true

## Query Construction

::: picsure.buildClause

::: picsure.buildClauseGroup

::: picsure.buildQuery

::: picsure.buildGenomicFilter

::: picsure.removeSubQuery

::: picsure.replaceClause

## Genomic Utilities

::: picsure.genomicConsequences

## Types

### PhenotypicFilterType

::: picsure.PhenotypicFilterType
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

### CountResult

::: picsure.CountResult
    options:
      members:
        - value
        - margin
        - cap
        - raw
        - obfuscated

### GenomicFilter

::: picsure.GenomicFilter

### VariantFrequency

::: picsure.VariantFrequency
    options:
      members: true

## Session

::: picsure.Session
    options:
      members:
        - consents
        - searchDictionary
        - facets
        - showAllFacets
        - searchGenomicValues
        - runQuery
        - runQueryByID
        - loadQueryByID
        - saveQueryByName
        - exportAsPFB
        - exportCSV
        - exportTSV
        - getResourceID
        - setResourceID
        - setResourceIDByName
        - close
        - __enter__
        - __exit__

## Errors

::: picsure.PicSureError

::: picsure.PicSureAuthError

::: picsure.PicSureConnectionError

::: picsure.PicSureQueryError

::: picsure.PicSureValidationError
