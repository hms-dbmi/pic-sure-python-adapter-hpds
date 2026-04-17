# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `picsure.connect()` to authenticate and connect to a PIC-SURE instance.
- `Session.getResourceID()` to list available resources as a DataFrame.
- Platform name resolution for BDC Authorized, BDC Open, Demo, and AIM-AHEAD.
- Actionable error messages via `PicSureError`.
- Unit test suite with mocked HTTP via respx.
- Integration test scaffold gated by `PICSURE_INTEGRATION` env var.
- GitHub Actions CI with Python 3.10/3.11/3.12 matrix.
- `Session.search()` to search the data dictionary with optional facet filtering.
- `Session.facets()` to retrieve available facet categories as a `FacetSet`.
- `Session.showAllFacets()` to display all facet categories and values as a DataFrame.
- `FacetSet` for building facet selections with validation.
- Search result deduplication by concept path.
- Zero-result searches return empty DataFrames with a stderr note.
- `picsure.createClause()` to build individual filter clauses (FILTER, ANYRECORD, SELECT, REQUIRE).
- `picsure.buildClauseGroup()` to combine clauses with AND/OR logic, supporting arbitrary nesting.
- `ClauseType` and `GroupOperator` enums for type-safe clause and group construction.
- `Clause`, `ClauseGroup`, and `Query` types with `to_query_json()` serialization.
- Input validation with actionable error messages for invalid clause configurations.
- `Session.runQuery()` to execute queries and return count (int) or data (DataFrame).
- `Session.exportPFB()` to export query results as PFB files.
- `Session.exportCSV()` and `Session.exportTSV()` to save DataFrames to disk.
- `PicSureClient.post_raw()` for non-JSON response handling.
- Query type validation with actionable error messages ("count", "participant", "timestamp").
- Documentation site with MkDocs + Material theme.
- Auto-generated API reference from docstrings via mkdocstrings.
- User guides: search, facets, query building, running, and exporting.
- Migration guide from PicSureHpdsLib with side-by-side examples.
- Docs CI workflow: build on PR, deploy to GitHub Pages on push to main.
