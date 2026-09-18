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

### GenomicFilterKey

::: picsure.GenomicFilterKey
    options:
      members: true

### VariantSeverity

::: picsure.VariantSeverity
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
        - close
        - __enter__
        - __exit__

## Errors

Three causes produce three families, so an `except` clause alone is
enough to tell them apart:

| Cause | Catch | Raised as |
|---|---|---|
| The token is missing, malformed, expired, or rejected | `PicSureAuthError` | `PicSureAuthenticationError` (HTTP 401) |
| The token is accepted but the account may not do this | `PicSureAuthError` | `PicSureAuthorizationError` (HTTP 403), or `PicSureConsentDeniedError` when the refusal is a consent decision |
| No usable response came back | `PicSureConnectionError` | `PicSureConnectionError`, `PicSureTLSError` (rejected certificate), or `PicSureServerError` (HTTP 5xx), with `PicSureConsentLookupError` for a failed server-side consent lookup |

```
PicSureError
├── PicSureAuthError
│   ├── PicSureAuthenticationError
│   └── PicSureAuthorizationError
│       └── PicSureConsentDeniedError
├── PicSureConnectionError
│   ├── PicSureTLSError
│   └── PicSureServerError
│       └── PicSureConsentLookupError
├── PicSureQueryError
└── PicSureValidationError
```

`PicSureConsentDeniedError` and `PicSureConsentLookupError` also expose
the server's own account of the failure as `status_code`, `body`,
`error_type`, and `server_message`.

::: picsure.PicSureError

::: picsure.PicSureAuthError

::: picsure.PicSureAuthenticationError

::: picsure.PicSureAuthorizationError

::: picsure.PicSureConsentDeniedError

::: picsure.PicSureConnectionError

::: picsure.PicSureTLSError

::: picsure.PicSureServerError

::: picsure.PicSureConsentLookupError

::: picsure.PicSureQueryError

::: picsure.PicSureValidationError
