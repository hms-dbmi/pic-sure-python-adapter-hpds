# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `Session.facets(term="", *, facets=None)` and `Session.showAllFacets(term="", *, facets=None)` now accept optional search term and facet selections. Counts returned are contextual to the provided search when term/facets are supplied; passing no arguments preserves the previous "global counts" behaviour.
- `DictionaryEntry` exposes `min`, `max`, `allow_filtering`, `meta`, and `study_acronym` fields. The corresponding columns (`min`, `max`, `allowFiltering`, `meta`, `studyAcronym`) are added to the `Session.search` DataFrame result.
- `picsure.connect()` to authenticate and connect to a PIC-SURE instance.
- `Session.getResourceID()` to list available resources as a DataFrame.
- Platform name resolution for BDC Authorized, BDC Open, and Demo.
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
- `CountResult` dataclass exposing `value`, `margin`, `cap`, `raw`, and an `obfuscated` property for count query responses.
- Input validation with actionable error messages for invalid clause configurations.
- `Session.runQuery()` to execute queries and return a `CountResult`, a `dict[str, CountResult]` (cross-count), or a `DataFrame` (participant / timestamp).
- `Session.exportPFB()` to export query results as PFB files.
- `Session.exportCSV()` and `Session.exportTSV()` to save DataFrames to disk.
- `PicSureClient.post_raw()` for non-JSON response handling.
- Query type validation with actionable error messages ("count", "participant", "timestamp").
- Documentation site with MkDocs + Material theme.
- Auto-generated API reference from docstrings via mkdocstrings.
- User guides: search, facets, query building, running, and exporting.
- Migration guide from PicSureHpdsLib with side-by-side examples.
- Docs CI workflow: build on PR, deploy to GitHub Pages on push to main.

### Changed
- Query endpoint changed from `/picsure/query/sync` to `/picsure/v3/query/sync`.
- `Clause.to_query_json()` / `ClauseGroup.to_query_json()` now emit the v3 `PhenotypicClause` / `PhenotypicSubquery` schema (`operator` / `phenotypicClauses` / `not` for groups; `phenotypicFilterType` / `conceptPath` / `values` / `min` / `max` / `not` for leaves). The previous wire format is no longer produced.
- `Clause.to_query_json()` now raises `PicSureValidationError` for `SELECT` clauses. Use `Clause.select_paths()` / `ClauseGroup.select_paths()` to retrieve output paths instead.
- `Session.runQuery(..., type="count")` now returns a `CountResult` dataclass instead of a plain `int`. Access the integer count via `result.value`; check `result.cap` for suppressed small-count responses (`result.value` is `None` in that case) and `result.margin` for noisy responses.
- `Session.runQuery(..., type="cross_count")` now returns a `dict[str, CountResult]` keyed by concept path instead of a DataFrame.
- `PicSureClient` now strips leading/trailing whitespace from the bearer token; a whitespace-only token is treated as anonymous (no `Authorization` header, `request-source: Open`).
- `Session.exportPFB()` / `picsure._services.export.export_pfb` now use the async flow (`POST /picsure/v3/query` → poll `/query/{id}/status` → `POST /query/{id}/result`) rather than `/query/sync`. Response bytes are streamed directly to disk. Polling uses exponential backoff (1s, 2s, 4s, … capped at 60s per poll) and fails with `PicSureConnectionError` after 10 minutes of cumulative waiting. The output file is written atomically (`.part` staging file + rename on success).
- `createClause` now raises `PicSureValidationError` for additional invalid combinations:
  FILTER clauses with both `categories` and `min`/`max`; REQUIRE or SELECT clauses
  with any of `categories`/`min`/`max`; empty keys lists. These were previously
  silently accepted and the extra arguments discarded (or rejected downstream by
  the server with a less actionable error).
- `ClauseGroup.to_query_json()` now raises `PicSureValidationError` if any nested
  child is a SELECT clause (previously it silently stripped them). This is
  symmetric with `Clause.to_query_json()`, which has always raised on SELECT.
  `ClauseGroup.select_paths()` and `build_query_body()` continue to handle SELECT
  extraction at the top level; inline SELECTs inside a group are the error case.
- `createClause` now defensively copies list arguments (`keys`, `categories`), so
  mutating the caller's lists after construction does not affect the resulting
  `Clause`.

### Removed
- Wire-format docstrings on `Clause` and `ClauseGroup` no longer advertise the
  `not` / negation field. The adapter still emits `"not": False` on the wire, but
  negation is not supported by the public API; support will return in a later
  release.

### Fixed
- `Session.search` now raises `PicSureQueryError` when the server's paginated response indicates the result set was truncated (`last != True` or `content` length doesn't match `totalElements`). Previously the adapter silently returned the partial page.
- PFB export against v3 PIC-SURE was silently broken: the previous implementation posted `DATAFRAME_PFB` to `/query/sync`, which v3 HPDS has no handler for. Unit tests passed only because `respx` served a canned 200 body at the wrong URL.
- 4xx responses during PFB submission / status / result are now surfaced as `PicSureValidationError` / `PicSureQueryError` (previously the 4xx body bytes would be written to disk as if they were PFB).
- `OSError` / `PermissionError` during disk writes in `export_pfb` are now wrapped in `PicSureConnectionError` with the target path in the message (previously leaked raw).
